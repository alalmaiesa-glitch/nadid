import { createHash } from "node:crypto";
import type {
  AnalyzeResponse,
  DeepAnalysisResult,
  DeepMemorySnapshot,
  DocumentBlock,
  ProtectedFact,
  QuickSuggestion
} from "@/lib/nadid-types";
import { getSupabaseAdmin } from "@/lib/supabase-admin";

const STORAGE_BUCKET = "nadid-documents";

function sha256(buffer: Buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function validatorForFact(type: ProtectedFact["type"]) {
  switch (type) {
    case "currency":
    case "number":
    case "percentage":
      return "numeric_equivalence";
    case "date":
      return "date_equivalence";
    case "standard":
      return "exact_or_normalized_identifier";
    case "negation":
      return "negation_preservation";
    default:
      return "exact_text";
  }
}

export async function persistAnalyzedDocument(
  analysis: AnalyzeResponse,
  sourceBuffer: Buffer
) {
  const supabase = getSupabaseAdmin();
  if (!supabase) {
    return { persisted: false as const, reason: "supabase_not_configured" };
  }

  const sourcePath = `${analysis.document.id}/v1/source.docx`;

  const { error: storageError } = await supabase.storage
    .from(STORAGE_BUCKET)
    .upload(sourcePath, sourceBuffer, {
      contentType:
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      upsert: true
    });

  if (storageError) throw storageError;

  const { error: documentError } = await supabase
    .from("documents")
    .upsert(
      {
        id: analysis.document.id,
        title: analysis.document.filename.replace(/\.docx$/i, ""),
        filename: analysis.document.filename,
        source_type: "docx",
        storage_path: sourcePath,
        status: "partial_ready",
        word_count: analysis.document.wordCount,
        paragraph_count: analysis.document.paragraphCount
      },
      { onConflict: "id" }
    );

  if (documentError) throw documentError;

  const { data: createdVersion, error: versionError } = await supabase
    .from("document_versions")
    .insert({
      document_id: analysis.document.id,
      version_no: 1,
      is_source: true,
      storage_path: sourcePath,
      status: "ready",
      source_sha256: sha256(sourceBuffer),
      engine_manifest: {
        parser: "mammoth",
        fast_review: "fast_rules_v0.1",
        protected_spans: "atomic_guard_v0.1"
      }
    })
    .select("id")
    .single();

  let versionId = createdVersion?.id as string | undefined;

  if (versionError || !versionId) {
    const { data: existing, error: existingError } = await supabase
      .from("document_versions")
      .select("id")
      .eq("document_id", analysis.document.id)
      .eq("version_no", 1)
      .single();

    if (existingError || !existing?.id) {
      throw versionError ?? existingError ?? new Error("version_not_created");
    }

    versionId = existing.id;
  }

  const nodeRows = analysis.document.blocks.map((block, index) => ({
    version_id: versionId,
    logical_node_key: block.id,
    node_type: block.type,
    sequence_no: index,
    text: block.text,
    normalized_text: block.text.normalize("NFC"),
    content_hash: createHash("sha256").update(block.text).digest("hex")
  }));

  const { data: insertedNodes, error: nodeError } = await supabase
    .from("document_nodes")
    .insert(nodeRows)
    .select("id, logical_node_key");

  if (nodeError) throw nodeError;

  const nodeMap = new Map(
    (insertedNodes ?? []).map((row) => [row.logical_node_key, row.id])
  );

  if (analysis.suggestions.length > 0) {
    const suggestionRows = analysis.suggestions.map((item) => ({
      version_id: versionId,
      node_id: nodeMap.get(item.blockId) ?? null,
      client_suggestion_id: item.id,
      category: item.category,
      title: item.title,
      explanation: item.explanation,
      original_text: item.original,
      replacement_text: item.replacement ?? null,
      confidence: item.confidence,
      status: "pending",
      source_engine: "fast_rules_v0.1"
    }));

    const { error } = await supabase
      .from("suggestions")
      .insert(suggestionRows);

    if (error) throw error;
  }

  if (analysis.protectedFacts.length > 0) {
    const factRows = analysis.protectedFacts.map((fact) => ({
      version_id: versionId,
      node_id: nodeMap.get(fact.blockId) ?? null,
      client_fact_id: fact.id,
      span_type: fact.type,
      surface_text: fact.value,
      canonical_value: { surface: fact.value },
      validator_key: validatorForFact(fact.type),
      lock_policy:
        fact.type === "negation" ? "semantic_exact" : "normalize_only",
      lock_mode: "block",
      confidence: 1
    }));

    const { error } = await supabase
      .from("protected_spans")
      .insert(factRows);

    if (error) throw error;
  }

  const { error: runError } = await supabase.from("analysis_runs").insert({
    version_id: versionId,
    run_type: "fast",
    state: "complete",
    engine_manifest: {
      parser: "mammoth",
      reviewer: "fast_rules_v0.1"
    },
    metrics: {
      suggestions: analysis.suggestions.length,
      protected_facts: analysis.protectedFacts.length
    },
    completed_at: new Date().toISOString()
  });

  if (runError) throw runError;

  return {
    persisted: true as const,
    versionId: versionId,
    sourcePath
  };
}

export async function loadAnalyzedDocument(documentId: string) {
  const supabase = getSupabaseAdmin();
  if (!supabase) return null;

  const { data: document, error: documentError } = await supabase
    .from("documents")
    .select("id, filename, word_count, paragraph_count")
    .eq("id", documentId)
    .single();

  if (documentError || !document) return null;

  const { data: version, error: versionError } = await supabase
    .from("document_versions")
    .select("id")
    .eq("document_id", documentId)
    .order("version_no", { ascending: false })
    .limit(1)
    .single();

  if (versionError || !version) return null;

  const [{ data: nodes }, { data: suggestions }, { data: facts }] =
    await Promise.all([
      supabase
        .from("document_nodes")
        .select("id, logical_node_key, node_type, sequence_no, text")
        .eq("version_id", version.id)
        .order("sequence_no", { ascending: true }),
      supabase
        .from("suggestions")
        .select(
          "client_suggestion_id, node_id, category, title, explanation, original_text, replacement_text, confidence, status"
        )
        .eq("version_id", version.id)
        .eq("status", "pending"),
      supabase
        .from("protected_spans")
        .select("client_fact_id, node_id, span_type, surface_text")
        .eq("version_id", version.id)
    ]);

  const nodeIdToLogical = new Map(
    (nodes ?? []).map((node) => [node.id, node.logical_node_key])
  );

  const blocks: DocumentBlock[] = (nodes ?? []).map((node) => ({
    id: node.logical_node_key,
    type: node.node_type === "heading" ? "heading" : "paragraph",
    text: node.text
  }));

  const mappedSuggestions: QuickSuggestion[] = (suggestions ?? []).map(
    (item) => ({
      id: item.client_suggestion_id,
      blockId: nodeIdToLogical.get(item.node_id) ?? "",
      category: item.category,
      title: item.title,
      explanation: item.explanation,
      original: item.original_text,
      replacement: item.replacement_text ?? undefined,
      confidence: Number(item.confidence)
    })
  );

  const protectedFacts: ProtectedFact[] = (facts ?? []).map((fact) => ({
    id: fact.client_fact_id,
    blockId: nodeIdToLogical.get(fact.node_id) ?? "",
    type: fact.span_type,
    value: fact.surface_text
  }));

  const response: AnalyzeResponse = {
    document: {
      id: document.id,
      filename: document.filename,
      wordCount: document.word_count,
      paragraphCount: document.paragraph_count,
      blocks
    },
    suggestions: mappedSuggestions,
    protectedFacts,
    warnings: []
  };

  return response;
}


export async function loadDocumentSource(documentId: string) {
  const supabase = getSupabaseAdmin();
  if (!supabase) return null;

  const { data: document, error: documentError } = await supabase
    .from("documents")
    .select("id, filename, storage_path")
    .eq("id", documentId)
    .single();

  if (documentError || !document) return null;

  const { data: version, error: versionError } = await supabase
    .from("document_versions")
    .select("id, version_no, storage_path")
    .eq("document_id", documentId)
    .order("version_no", { ascending: false })
    .limit(1)
    .single();

  if (versionError || !version) return null;

  const storagePath =
    (version.storage_path as string | null) ??
    (document.storage_path as string | null);

  if (!storagePath) return null;

  const { data: source, error: storageError } = await supabase.storage
    .from(STORAGE_BUCKET)
    .download(storagePath);

  if (storageError || !source) return null;

  return {
    documentId,
    versionId: version.id as string,
    versionNo: Number(version.version_no),
    storagePath,
    filename: document.filename as string,
    buffer: Buffer.from(await source.arrayBuffer())
  };
}

export async function persistDeepAnalysis(
  documentId: string,
  versionId: string,
  deep: DeepAnalysisResult
) {
  const supabase = getSupabaseAdmin();
  if (!supabase) {
    return { persisted: false as const, reason: "supabase_not_configured" };
  }

  const { error: memoryStartError } = await supabase
    .from("document_memory")
    .upsert(
      {
        version_id: versionId,
        state: "building",
        headings: deep.memory.headings,
        protected_count: deep.memory.protectedCount,
        chunk_count: deep.memory.chunkCount,
        engine_manifest: {
          memory: "deterministic_v0.1",
          facts: "deterministic_v0.1",
          retrieval: "lexical_v0.1"
        },
        updated_at: new Date().toISOString()
      },
      { onConflict: "version_id" }
    );

  if (memoryStartError) throw memoryStartError;

  const cleanupTables = [
    "fact_conflicts",
    "fact_assertions",
    "memory_terms",
    "document_chunks"
  ] as const;

  for (const table of cleanupTables) {
    const { error } = await supabase
      .from(table)
      .delete()
      .eq("version_id", versionId);

    if (error) throw error;
  }

  if (deep.chunks.length > 0) {
    const { error } = await supabase.from("document_chunks").insert(
      deep.chunks.map((chunk, index) => ({
        version_id: versionId,
        chunk_key: chunk.id,
        sequence_no: index,
        node_keys: chunk.nodeIds,
        chunk_text: chunk.text,
        token_estimate: chunk.tokenEstimate
      }))
    );

    if (error) throw error;
  }

  if (deep.memory.terms.length > 0) {
    const { error } = await supabase.from("memory_terms").insert(
      deep.memory.terms.map((term) => ({
        version_id: versionId,
        term: term.term,
        occurrence_count: term.count,
        node_keys: term.nodeIds
      }))
    );

    if (error) throw error;
  }

  if (deep.memory.facts.length > 0) {
    const { error } = await supabase.from("fact_assertions").insert(
      deep.memory.facts.map((fact) => ({
        version_id: versionId,
        client_fact_id: fact.id,
        node_key: fact.nodeId,
        fact_type: fact.factType,
        claim_key: fact.claimKey,
        surface_value: fact.value,
        canonical_value: fact.canonicalValue,
        context_text: fact.context,
        confidence: fact.confidence,
        authority: "extracted"
      }))
    );

    if (error) throw error;
  }

  if (deep.memory.conflicts.length > 0) {
    const { error } = await supabase.from("fact_conflicts").insert(
      deep.memory.conflicts.map((conflict) => ({
        version_id: versionId,
        client_conflict_id: conflict.id,
        claim_key: conflict.claimKey,
        fact_ids: conflict.factIds,
        values_found: conflict.values,
        confidence: conflict.confidence,
        status: "open"
      }))
    );

    if (error) throw error;
  }

  const { error: oldDeepSuggestionError } = await supabase
    .from("suggestions")
    .delete()
    .eq("version_id", versionId)
    .eq("source_engine", "deep_consistency_v0.1");

  if (oldDeepSuggestionError) throw oldDeepSuggestionError;

  if (deep.memory.conflicts.length > 0) {
    const { data: nodes, error: nodeLookupError } = await supabase
      .from("document_nodes")
      .select("id, logical_node_key")
      .eq("version_id", versionId);

    if (nodeLookupError) throw nodeLookupError;

    const nodeMap = new Map(
      (nodes ?? []).map((node) => [node.logical_node_key, node.id])
    );
    const factMap = new Map(
      deep.memory.facts.map((fact) => [fact.id, fact])
    );

    const rows = deep.memory.conflicts.map((conflict) => {
      const firstFact = conflict.factIds
        .map((factId) => factMap.get(factId))
        .find(Boolean);

      return {
        version_id: versionId,
        node_id: firstFact ? nodeMap.get(firstFact.nodeId) ?? null : null,
        client_suggestion_id: `deep-conflict-${conflict.id}`,
        category: "consistency",
        title: "تعارض محتمل في حقيقة",
        explanation:
          "وجد نَضِيد قيمًا مختلفة لادعاء يبدو متطابقًا عبر المستند: " +
          conflict.values.join(" / "),
        original_text: firstFact?.value ?? conflict.values.join(" / "),
        replacement_text: null,
        confidence: conflict.confidence,
        status: "pending",
        source_engine: "deep_consistency_v0.1",
        evidence: [
          {
            type: "fact_conflict",
            conflict_id: conflict.id,
            fact_ids: conflict.factIds,
            values: conflict.values
          }
        ]
      };
    });

    const { error: deepSuggestionError } = await supabase
      .from("suggestions")
      .insert(rows);

    if (deepSuggestionError) throw deepSuggestionError;
  }

  const { error: memoryReadyError } = await supabase
    .from("document_memory")
    .update({
      state: "ready",
      built_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
    .eq("version_id", versionId);

  if (memoryReadyError) throw memoryReadyError;

  const { error: documentStatusError } = await supabase
    .from("documents")
    .update({
      status: "ready",
      updated_at: new Date().toISOString()
    })
    .eq("id", documentId);

  if (documentStatusError) throw documentStatusError;

  const { error: runError } = await supabase.from("analysis_runs").insert({
    version_id: versionId,
    run_type: "deep",
    state: "complete",
    engine_manifest: {
      memory: "deterministic_v0.1",
      facts: "deterministic_v0.1",
      retrieval: "lexical_v0.1"
    },
    metrics: {
      chunks: deep.chunks.length,
      terms: deep.memory.terms.length,
      facts: deep.memory.facts.length,
      conflicts: deep.memory.conflicts.length
    },
    completed_at: new Date().toISOString()
  });

  if (runError) throw runError;

  return { persisted: true as const };
}

export async function loadDeepMemory(
  documentId: string
): Promise<DeepMemorySnapshot | null> {
  const supabase = getSupabaseAdmin();
  if (!supabase) return null;

  const { data: version, error: versionError } = await supabase
    .from("document_versions")
    .select("id")
    .eq("document_id", documentId)
    .order("version_no", { ascending: false })
    .limit(1)
    .single();

  if (versionError || !version) return null;

  const { data: memory, error: memoryError } = await supabase
    .from("document_memory")
    .select("state, headings, protected_count, chunk_count")
    .eq("version_id", version.id)
    .single();

  if (memoryError || !memory || memory.state !== "ready") return null;

  const [
    { data: terms, error: termsError },
    { data: facts, error: factsError },
    { data: conflicts, error: conflictsError }
  ] = await Promise.all([
    supabase
      .from("memory_terms")
      .select("term, occurrence_count, node_keys")
      .eq("version_id", version.id)
      .order("occurrence_count", { ascending: false }),
    supabase
      .from("fact_assertions")
      .select(
        "client_fact_id, node_key, fact_type, claim_key, surface_value, canonical_value, context_text, confidence"
      )
      .eq("version_id", version.id),
    supabase
      .from("fact_conflicts")
      .select(
        "client_conflict_id, claim_key, fact_ids, values_found, confidence"
      )
      .eq("version_id", version.id)
      .eq("status", "open")
  ]);

  if (termsError || factsError || conflictsError) {
    throw termsError ?? factsError ?? conflictsError;
  }

  return {
    headings: Array.isArray(memory.headings) ? memory.headings : [],
    terms: (terms ?? []).map((term) => ({
      term: term.term,
      count: term.occurrence_count,
      nodeIds: term.node_keys ?? []
    })),
    facts: (facts ?? []).map((fact) => ({
      id: fact.client_fact_id,
      nodeId: fact.node_key,
      factType: fact.fact_type,
      claimKey: fact.claim_key,
      value: fact.surface_value,
      canonicalValue: fact.canonical_value,
      context: fact.context_text,
      confidence: Number(fact.confidence)
    })),
    conflicts: (conflicts ?? []).map((conflict) => ({
      id: conflict.client_conflict_id,
      claimKey: conflict.claim_key,
      factIds: conflict.fact_ids ?? [],
      values: conflict.values_found ?? [],
      confidence: Number(conflict.confidence)
    })),
    protectedCount: memory.protected_count,
    chunkCount: memory.chunk_count
  };
}


export async function searchStoredContext(
  documentId: string,
  query: string,
  limit = 5
) {
  const supabase = getSupabaseAdmin();
  if (!supabase || !query.trim()) return [];

  const { data: version, error: versionError } = await supabase
    .from("document_versions")
    .select("id")
    .eq("document_id", documentId)
    .order("version_no", { ascending: false })
    .limit(1)
    .single();

  if (versionError || !version) return [];

  const { data, error } = await supabase.rpc("search_document_chunks", {
    p_version_id: version.id,
    p_query: query,
    p_limit: Math.max(1, Math.min(limit, 12))
  });

  if (error) throw error;

  return (data ?? []).map((row: any) => ({
    chunkId: row.chunk_key,
    sequenceNo: row.sequence_no,
    nodeIds: row.node_keys ?? [],
    text: row.chunk_text,
    tokenEstimate: row.token_estimate,
    score: Number(row.rank ?? 0)
  }));
}


async function persistFastAnalysisRows(
  versionId: string,
  analysis: AnalyzeResponse
) {
  const supabase = getSupabaseAdmin();
  if (!supabase) throw new Error("supabase_not_configured");

  const nodeRows = analysis.document.blocks.map((block, index) => ({
    version_id: versionId,
    logical_node_key: block.id,
    node_type: block.type,
    sequence_no: index,
    text: block.text,
    normalized_text: block.text.normalize("NFC"),
    content_hash: createHash("sha256").update(block.text).digest("hex")
  }));

  const { data: insertedNodes, error: nodeError } = await supabase
    .from("document_nodes")
    .insert(nodeRows)
    .select("id, logical_node_key");

  if (nodeError) throw nodeError;

  const nodeMap = new Map(
    (insertedNodes ?? []).map((row) => [row.logical_node_key, row.id])
  );

  if (analysis.suggestions.length > 0) {
    const { error } = await supabase.from("suggestions").insert(
      analysis.suggestions.map((item) => ({
        version_id: versionId,
        node_id: nodeMap.get(item.blockId) ?? null,
        client_suggestion_id: item.id,
        category: item.category,
        title: item.title,
        explanation: item.explanation,
        original_text: item.original,
        replacement_text: item.replacement ?? null,
        confidence: item.confidence,
        status: "pending",
        source_engine: "fast_rules_v0.1"
      }))
    );

    if (error) throw error;
  }

  if (analysis.protectedFacts.length > 0) {
    const { error } = await supabase.from("protected_spans").insert(
      analysis.protectedFacts.map((fact) => ({
        version_id: versionId,
        node_id: nodeMap.get(fact.blockId) ?? null,
        client_fact_id: fact.id,
        span_type: fact.type,
        surface_text: fact.value,
        canonical_value: { surface: fact.value },
        validator_key: validatorForFact(fact.type),
        lock_policy:
          fact.type === "negation" ? "semantic_exact" : "normalize_only",
        lock_mode: "block",
        confidence: 1
      }))
    );

    if (error) throw error;
  }

  const { error: runError } = await supabase.from("analysis_runs").insert({
    version_id: versionId,
    run_type: "fast",
    state: "complete",
    engine_manifest: {
      parser: "aee_docx_v0.1",
      reviewer: "fast_rules_v0.1"
    },
    metrics: {
      suggestions: analysis.suggestions.length,
      protected_facts: analysis.protectedFacts.length
    },
    completed_at: new Date().toISOString()
  });

  if (runError) throw runError;
}

export async function loadAcceptedPatches(documentId: string) {
  const supabase = getSupabaseAdmin();
  if (!supabase) return null;

  const { data: version, error: versionError } = await supabase
    .from("document_versions")
    .select("id, version_no")
    .eq("document_id", documentId)
    .order("version_no", { ascending: false })
    .limit(1)
    .single();

  if (versionError || !version) return null;

  const [
    { data: nodes, error: nodesError },
    { data: suggestions, error: suggestionsError }
  ] = await Promise.all([
    supabase
      .from("document_nodes")
      .select("id, logical_node_key")
      .eq("version_id", version.id),
    supabase
      .from("suggestions")
      .select(
        "node_id, client_suggestion_id, original_text, replacement_text"
      )
      .eq("version_id", version.id)
      .eq("status", "accepted")
      .not("replacement_text", "is", null)
      .order("created_at", { ascending: true })
  ]);

  if (nodesError || suggestionsError) {
    throw nodesError ?? suggestionsError;
  }

  const nodeMap = new Map(
    (nodes ?? []).map((node) => [node.id, node.logical_node_key])
  );

  return {
    versionId: version.id as string,
    versionNo: Number(version.version_no),
    patches: (suggestions ?? [])
      .map((item) => ({
        suggestionId: item.client_suggestion_id as string,
        nodeId: nodeMap.get(item.node_id) ?? "",
        original: item.original_text as string,
        replacement: item.replacement_text as string
      }))
      .filter((item) => item.nodeId && item.replacement !== null)
  };
}

export async function createDocumentVersion(
  documentId: string,
  parentVersionId: string,
  parentVersionNo: number,
  buffer: Buffer,
  analysis: AnalyzeResponse,
  appliedSuggestionIds: string[]
) {
  const supabase = getSupabaseAdmin();
  if (!supabase) {
    return { persisted: false as const, reason: "supabase_not_configured" };
  }

  const nextVersionNo = parentVersionNo + 1;
  const storagePath =
    `${documentId}/v${nextVersionNo}/source.docx`;

  const { error: storageError } = await supabase.storage
    .from(STORAGE_BUCKET)
    .upload(storagePath, buffer, {
      contentType:
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      upsert: false
    });

  if (storageError) throw storageError;

  const { data: version, error: versionError } = await supabase
    .from("document_versions")
    .insert({
      document_id: documentId,
      version_no: nextVersionNo,
      parent_version_id: parentVersionId,
      is_source: false,
      storage_path: storagePath,
      status: "ready",
      source_sha256: sha256(buffer),
      engine_manifest: {
        exporter: "aee_docx_patch_v0.1",
        parser: "aee_docx_v0.1"
      },
      change_summary: {
        applied_suggestions: appliedSuggestionIds,
        applied_count: appliedSuggestionIds.length
      }
    })
    .select("id")
    .single();

  if (versionError || !version?.id) throw versionError;

  try {
    await persistFastAnalysisRows(version.id, {
      ...analysis,
      document: {
        ...analysis.document,
        id: documentId
      }
    });

    const { error: documentError } = await supabase
      .from("documents")
      .update({
        status: "partial_ready",
        word_count: analysis.document.wordCount,
        paragraph_count: analysis.document.paragraphCount,
        updated_at: new Date().toISOString()
      })
      .eq("id", documentId);

    if (documentError) throw documentError;
  } catch (error) {
    await supabase
      .from("document_versions")
      .update({ status: "failed" })
      .eq("id", version.id);

    throw error;
  }

  return {
    persisted: true as const,
    versionId: version.id as string,
    versionNo: nextVersionNo,
    storagePath
  };
}

export async function downloadDocumentVersion(
  documentId: string,
  versionNo?: number
) {
  const supabase = getSupabaseAdmin();
  if (!supabase) return null;

  let query = supabase
    .from("document_versions")
    .select("id, version_no, storage_path")
    .eq("document_id", documentId);

  if (versionNo != null) {
    query = query.eq("version_no", versionNo);
  } else {
    query = query.order("version_no", { ascending: false }).limit(1);
  }

  const { data: version, error: versionError } = await query.single();
  if (versionError || !version?.storage_path) return null;

  const { data: document, error: documentError } = await supabase
    .from("documents")
    .select("filename")
    .eq("id", documentId)
    .single();

  if (documentError || !document) return null;

  const { data: blob, error: storageError } = await supabase.storage
    .from(STORAGE_BUCKET)
    .download(version.storage_path);

  if (storageError || !blob) return null;

  return {
    versionNo: Number(version.version_no),
    filename: document.filename as string,
    buffer: Buffer.from(await blob.arrayBuffer())
  };
}
