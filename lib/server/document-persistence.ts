import { createHash, randomUUID } from "node:crypto";
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
  sourceBuffer: Buffer,
  ownerId?: string | null
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
        owner_id: ownerId ?? null,
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
    .select("id, version_no")
    .eq("document_id", documentId)
    .eq("status", "ready")
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
          "id, client_suggestion_id, node_id, category, title, explanation, original_text, replacement_text, confidence, status"
        )
        .eq("version_id", version.id)
        .eq("status", "pending"),
      supabase
        .from("protected_spans")
        .select("id, client_fact_id, node_id, span_type, surface_text")
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
      id: item.client_suggestion_id ?? item.id,
      blockId: item.node_id
        ? nodeIdToLogical.get(item.node_id) ?? ""
        : "",
      category: item.category,
      title: item.title,
      explanation: item.explanation,
      original: item.original_text,
      replacement: item.replacement_text ?? undefined,
      confidence: Number(item.confidence)
    })
  );

  const protectedFacts: ProtectedFact[] = (facts ?? []).map((fact) => ({
    id: fact.client_fact_id ?? fact.id,
    blockId: fact.node_id
      ? nodeIdToLogical.get(fact.node_id) ?? ""
      : "",
    type: fact.span_type,
    value: fact.surface_text
  }));

  const response: AnalyzeResponse = {
    document: {
      id: document.id,
      filename: document.filename,
      wordCount: document.word_count,
      paragraphCount: document.paragraph_count,
      versionNo: Number(version.version_no),
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
    .eq("status", "ready")
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
        client_suggestion_id:
          `deep-conflict-${versionId}-${conflict.id}`,
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
    .eq("status", "ready")
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
    .eq("status", "ready")
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
    .eq("status", "ready")
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

  const { data: latestAny, error: latestAnyError } = await supabase
    .from("document_versions")
    .select("version_no")
    .eq("document_id", documentId)
    .order("version_no", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (latestAnyError) throw latestAnyError;

  const nextVersionNo = Math.max(
    parentVersionNo,
    Number(latestAny?.version_no ?? parentVersionNo)
  ) + 1;

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

  query = query.eq("status", "ready");

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


export async function listDocumentVersions(documentId: string) {
  const supabase = getSupabaseAdmin();
  if (!supabase) return [];

  const { data, error } = await supabase
    .from("document_versions")
    .select(
      "id, version_no, is_source, status, change_summary, created_at"
    )
    .eq("document_id", documentId)
    .order("version_no", { ascending: false });

  if (error) throw error;

  return (data ?? []).map((version) => ({
    id: version.id as string,
    versionNo: Number(version.version_no),
    isSource: Boolean(version.is_source),
    status: version.status as string,
    changeSummary:
      (version.change_summary as Record<string, unknown> | null) ?? {},
    createdAt: version.created_at as string
  }));
}


export async function assertDocumentOwner(
  documentId: string,
  ownerId: string
) {
  const supabase = getSupabaseAdmin();
  if (!supabase) return false;

  const { data, error } = await supabase
    .from("documents")
    .select("id")
    .eq("id", documentId)
    .eq("owner_id", ownerId)
    .maybeSingle();

  if (error) throw error;
  return Boolean(data?.id);
}

export async function assertSuggestionOwner(
  suggestionId: string,
  ownerId: string
) {
  const supabase = getSupabaseAdmin();
  if (!supabase) return false;

  const { data: suggestion, error: suggestionError } = await supabase
    .from("suggestions")
    .select("version_id")
    .eq("client_suggestion_id", suggestionId)
    .maybeSingle();

  if (suggestionError || !suggestion?.version_id) return false;

  const { data: version, error: versionError } = await supabase
    .from("document_versions")
    .select("document_id")
    .eq("id", suggestion.version_id)
    .maybeSingle();

  if (versionError || !version?.document_id) return false;

  return assertDocumentOwner(version.document_id, ownerId);
}

export async function listUserDocuments(ownerId: string) {
  const supabase = getSupabaseAdmin();
  if (!supabase) return [];

  const { data: documents, error } = await supabase
    .from("documents")
    .select(
      "id, title, filename, status, word_count, paragraph_count, created_at, updated_at"
    )
    .eq("owner_id", ownerId)
    .order("updated_at", { ascending: false });

  if (error) throw error;

  if (!documents?.length) return [];

  const ids = documents.map((document) => document.id);

  const { data: versions, error: versionsError } = await supabase
    .from("document_versions")
    .select("document_id, version_no, status")
    .in("document_id", ids)
    .eq("status", "ready")
    .order("version_no", { ascending: false });

  if (versionsError) throw versionsError;

  const latestVersion = new Map<string, number>();

  for (const version of versions ?? []) {
    if (!latestVersion.has(version.document_id)) {
      latestVersion.set(
        version.document_id,
        Number(version.version_no)
      );
    }
  }

  return documents.map((document) => ({
    id: document.id as string,
    title: document.title as string,
    filename: document.filename as string,
    status: document.status as string,
    wordCount: Number(document.word_count),
    paragraphCount: Number(document.paragraph_count),
    versionNo: latestVersion.get(document.id) ?? 1,
    createdAt: document.created_at as string,
    updatedAt: document.updated_at as string
  }));
}


export async function getDocumentProcessingStatus(documentId: string) {
  const supabase = getSupabaseAdmin();
  if (!supabase) return null;

  const { data: document, error: documentError } = await supabase
    .from("documents")
    .select("status, updated_at")
    .eq("id", documentId)
    .maybeSingle();

  if (documentError || !document) return null;

  const { data: job } = await supabase
    .from("processing_jobs")
    .select("status, attempts, max_attempts, last_error, updated_at")
    .eq("document_id", documentId)
    .eq("job_type", "initial_review")
    .maybeSingle();

  const { data: version, error: versionError } = await supabase
    .from("document_versions")
    .select("id, version_no")
    .eq("document_id", documentId)
    .eq("status", "ready")
    .order("version_no", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (versionError || !version) {
    return {
      documentStatus: document.status,
      versionNo: null,
      memoryState: "missing",
      fastState: "missing",
      deepState: "missing",
      pendingSuggestions: 0,
      queueState: job?.status ?? "missing",
      queueAttempts: Number(job?.attempts ?? 0),
      queueMaxAttempts: Number(job?.max_attempts ?? 0),
      queueError: job?.last_error ?? null,
      updatedAt: document.updated_at
    };
  }

  const [
    { data: memory },
    { data: runs },
    { count: pendingSuggestions }
  ] = await Promise.all([
    supabase
      .from("document_memory")
      .select("state")
      .eq("version_id", version.id)
      .maybeSingle(),
    supabase
      .from("analysis_runs")
      .select("run_type, state, started_at, completed_at")
      .eq("version_id", version.id)
      .order("started_at", { ascending: false }),
    supabase
      .from("suggestions")
      .select("id", { count: "exact", head: true })
      .eq("version_id", version.id)
      .eq("status", "pending")
  ]);

  const latestByType = new Map<string, string>();
  for (const run of runs ?? []) {
    if (!latestByType.has(run.run_type)) {
      latestByType.set(run.run_type, run.state);
    }
  }

  return {
    documentStatus: document.status as string,
    versionNo: Number(version.version_no),
    memoryState: memory?.state ?? "missing",
    fastState: latestByType.get("fast") ?? "missing",
    deepState: latestByType.get("deep") ?? "missing",
    pendingSuggestions: pendingSuggestions ?? 0,
    queueState: job?.status ?? "complete",
    queueAttempts: Number(job?.attempts ?? 0),
    queueMaxAttempts: Number(job?.max_attempts ?? 0),
    queueError: job?.last_error ?? null,
    updatedAt: document.updated_at as string
  };
}


export async function createPendingDocumentUpload(
  ownerId: string,
  filename: string
) {
  const supabase = getSupabaseAdmin();
  if (!supabase) throw new Error("supabase_not_configured");

  const maxDailyUploads = Math.max(
    1,
    Number(process.env.NADID_MAX_UPLOADS_PER_DAY ?? 20)
  );
  const maxActiveUploads = Math.max(
    1,
    Number(process.env.NADID_MAX_ACTIVE_UPLOADS ?? 3)
  );

  const dayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  const activeWindow = new Date(
    Date.now() - 30 * 60 * 1000
  ).toISOString();

  const [
    { count: dailyUploads, error: dailyError },
    { count: activeUploads, error: activeError }
  ] = await Promise.all([
    supabase
      .from("documents")
      .select("id", { count: "exact", head: true })
      .eq("owner_id", ownerId)
      .gte("created_at", dayAgo),
    supabase
      .from("documents")
      .select("id", { count: "exact", head: true })
      .eq("owner_id", ownerId)
      .in("status", ["uploading", "queued", "processing"])
      .gte("created_at", activeWindow)
  ]);

  if (dailyError || activeError) {
    throw dailyError ?? activeError ?? new Error("quota_check_failed");
  }

  if ((dailyUploads ?? 0) >= maxDailyUploads) {
    throw new Error("upload_daily_limit");
  }

  if ((activeUploads ?? 0) >= maxActiveUploads) {
    throw new Error("upload_active_limit");
  }

  const documentId = randomUUID();
  const storagePath =
    `${ownerId}/${documentId}/v1/source.docx`;

  const { error: documentError } = await supabase
    .from("documents")
    .insert({
      id: documentId,
      owner_id: ownerId,
      title: filename.replace(/\.docx$/i, ""),
      filename,
      source_type: "docx",
      storage_path: storagePath,
      status: "uploading",
      word_count: 0,
      paragraph_count: 0
    });

  if (documentError) throw documentError;

  const { data, error: signedError } = await supabase.storage
    .from(STORAGE_BUCKET)
    .createSignedUploadUrl(storagePath);

  if (signedError || !data?.token) {
    await supabase
      .from("documents")
      .delete()
      .eq("id", documentId)
      .eq("owner_id", ownerId);

    throw signedError ?? new Error("signed_upload_not_created");
  }

  return {
    documentId,
    storagePath,
    token: data.token
  };
}

export async function enqueueDocumentProcessing(
  documentId: string,
  ownerId: string
) {
  const supabase = getSupabaseAdmin();
  if (!supabase) throw new Error("supabase_not_configured");

  const { data: document, error: documentError } = await supabase
    .from("documents")
    .select("id, owner_id, storage_path, status")
    .eq("id", documentId)
    .eq("owner_id", ownerId)
    .maybeSingle();

  if (documentError || !document?.storage_path) {
    throw new Error("document_not_found");
  }

  const { data: readyVersion, error: versionError } = await supabase
    .from("document_versions")
    .select("id")
    .eq("document_id", documentId)
    .eq("version_no", 1)
    .eq("status", "ready")
    .maybeSingle();

  if (versionError) throw versionError;

  if (readyVersion?.id) {
    return {
      documentId,
      status: "ready" as const
    };
  }

  const storagePath = document.storage_path as string;
  const segments = storagePath.split("/");
  const filename = segments.pop();

  if (!filename) throw new Error("uploaded_file_missing");

  const folder = segments.join("/");
  const { data: objects, error: listError } = await supabase.storage
    .from(STORAGE_BUCKET)
    .list(folder, {
      limit: 10,
      search: filename
    });

  if (
    listError ||
    !(objects ?? []).some((item) => item.name === filename)
  ) {
    throw new Error("uploaded_file_missing");
  }

  const { data: existingJob, error: existingJobError } = await supabase
    .from("processing_jobs")
    .select("id, status, attempts, max_attempts")
    .eq("document_id", documentId)
    .eq("job_type", "initial_review")
    .maybeSingle();

  if (existingJobError) throw existingJobError;

  let job = existingJob;

  if (!job) {
    const { data: created, error: createError } = await supabase
      .from("processing_jobs")
      .insert({
        document_id: documentId,
        owner_id: ownerId,
        job_type: "initial_review",
        status: "queued"
      })
      .select("id, status, attempts, max_attempts")
      .single();

    if (createError || !created) {
      throw createError ?? new Error("processing_job_not_created");
    }

    job = created;
  } else if (job.status === "failed") {
    const { data: reset, error: resetError } = await supabase
      .from("processing_jobs")
      .update({
        status: "queued",
        attempts: 0,
        available_at: new Date().toISOString(),
        locked_at: null,
        locked_by: null,
        last_error: null,
        completed_at: null,
        updated_at: new Date().toISOString()
      })
      .eq("id", job.id)
      .select("id, status, attempts, max_attempts")
      .single();

    if (resetError || !reset) {
      throw resetError ?? new Error("processing_job_not_reset");
    }

    job = reset;
  }

  const { error: statusError } = await supabase
    .from("documents")
    .update({
      status: job.status === "processing" ? "processing" : "queued",
      updated_at: new Date().toISOString()
    })
    .eq("id", documentId)
    .eq("owner_id", ownerId);

  if (statusError) throw statusError;

  return {
    documentId,
    jobId: job.id as string,
    status: job.status as "queued" | "processing",
    attempts: Number(job.attempts ?? 0),
    maxAttempts: Number(job.max_attempts ?? 3)
  };
}


export async function loadPendingDocumentUpload(
  documentId: string,
  ownerId: string
) {
  const supabase = getSupabaseAdmin();
  if (!supabase) return null;

  const { data: document, error: documentError } = await supabase
    .from("documents")
    .select("id, filename, storage_path, status")
    .eq("id", documentId)
    .eq("owner_id", ownerId)
    .maybeSingle();

  if (
    documentError ||
    !document?.storage_path ||
    !document?.filename
  ) {
    return null;
  }

  const { data: existingVersion } = await supabase
    .from("document_versions")
    .select("id, version_no")
    .eq("document_id", documentId)
    .eq("version_no", 1)
    .eq("status", "ready")
    .maybeSingle();

  if (existingVersion) {
    return {
      documentId,
      filename: document.filename as string,
      storagePath: document.storage_path as string,
      status: "finalized" as const,
      existingVersionId: existingVersion.id as string
    };
  }

  const { data: source, error: storageError } = await supabase.storage
    .from(STORAGE_BUCKET)
    .download(document.storage_path);

  if (storageError || !source) return null;

  return {
    documentId,
    filename: document.filename as string,
    storagePath: document.storage_path as string,
    status: "pending" as const,
    buffer: Buffer.from(await source.arrayBuffer())
  };
}

export async function finalizePendingDocument(
  documentId: string,
  ownerId: string,
  storagePath: string,
  buffer: Buffer,
  analysis: AnalyzeResponse
) {
  const supabase = getSupabaseAdmin();
  if (!supabase) throw new Error("supabase_not_configured");

  const owned = await assertDocumentOwner(documentId, ownerId);
  if (!owned) throw new Error("document_not_owned");

  const { data: existing } = await supabase
    .from("document_versions")
    .select("id")
    .eq("document_id", documentId)
    .eq("version_no", 1)
    .eq("status", "ready")
    .maybeSingle();

  if (existing?.id) {
    return {
      versionId: existing.id as string,
      reused: true
    };
  }

  const { data: version, error: versionError } = await supabase
    .from("document_versions")
    .insert({
      document_id: documentId,
      version_no: 1,
      is_source: true,
      storage_path: storagePath,
      status: "ready",
      source_sha256: sha256(buffer),
      engine_manifest: {
        parser: "aee_docx_v0.1",
        fast_review: "fast_rules_v0.1",
        protected_spans: "atomic_guard_v0.1"
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

    const { error: updateError } = await supabase
      .from("documents")
      .update({
        status: "partial_ready",
        word_count: analysis.document.wordCount,
        paragraph_count: analysis.document.paragraphCount,
        updated_at: new Date().toISOString()
      })
      .eq("id", documentId)
      .eq("owner_id", ownerId);

    if (updateError) throw updateError;
  } catch (error) {
    await supabase
      .from("document_versions")
      .update({ status: "failed" })
      .eq("id", version.id);

    await supabase
      .from("documents")
      .update({
        status: "failed",
        updated_at: new Date().toISOString()
      })
      .eq("id", documentId)
      .eq("owner_id", ownerId);

    throw error;
  }

  return {
    versionId: version.id as string,
    reused: false
  };
}


export async function enqueueDeepReview(
  documentId: string,
  ownerId: string
) {
  const supabase = getSupabaseAdmin();
  if (!supabase) throw new Error("supabase_not_configured");

  const owned = await assertDocumentOwner(documentId, ownerId);
  if (!owned) throw new Error("document_not_owned");

  const { data: version, error: versionError } = await supabase
    .from("document_versions")
    .select("id")
    .eq("document_id", documentId)
    .eq("status", "ready")
    .order("version_no", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (versionError) throw versionError;
  if (!version?.id) throw new Error("ready_version_missing");

  const { data: memory, error: memoryError } = await supabase
    .from("document_memory")
    .select("state")
    .eq("version_id", version.id)
    .maybeSingle();

  if (memoryError) throw memoryError;

  if (memory?.state === "ready") {
    return {
      documentId,
      status: "ready" as const
    };
  }

  const { data: existing, error: existingError } = await supabase
    .from("processing_jobs")
    .select("id, status, attempts, max_attempts")
    .eq("document_id", documentId)
    .eq("job_type", "deep_review")
    .maybeSingle();

  if (existingError) throw existingError;

  let job = existing;

  if (!job) {
    const { data: created, error: createError } = await supabase
      .from("processing_jobs")
      .insert({
        document_id: documentId,
        owner_id: ownerId,
        job_type: "deep_review",
        status: "queued"
      })
      .select("id, status, attempts, max_attempts")
      .single();

    if (createError || !created) {
      throw createError ?? new Error("deep_job_not_created");
    }

    job = created;
  } else if (job.status === "failed") {
    const { data: reset, error: resetError } = await supabase
      .from("processing_jobs")
      .update({
        status: "queued",
        attempts: 0,
        available_at: new Date().toISOString(),
        locked_at: null,
        locked_by: null,
        last_error: null,
        completed_at: null,
        updated_at: new Date().toISOString()
      })
      .eq("id", job.id)
      .select("id, status, attempts, max_attempts")
      .single();

    if (resetError || !reset) {
      throw resetError ?? new Error("deep_job_not_reset");
    }

    job = reset;
  }

  return {
    documentId,
    jobId: job.id as string,
    status: job.status as "queued" | "processing" | "complete",
    attempts: Number(job.attempts ?? 0),
    maxAttempts: Number(job.max_attempts ?? 3)
  };
}


export async function deleteDocumentFully(
  documentId: string,
  ownerId: string
) {
  const supabase = getSupabaseAdmin();
  if (!supabase) throw new Error("supabase_not_configured");

  const { data: document, error: documentError } = await supabase
    .from("documents")
    .select("id, storage_path")
    .eq("id", documentId)
    .eq("owner_id", ownerId)
    .maybeSingle();

  if (documentError) throw documentError;
  if (!document) return { deleted: false as const, reason: "not_found" };

  const { data: versions, error: versionsError } = await supabase
    .from("document_versions")
    .select("storage_path")
    .eq("document_id", documentId);

  if (versionsError) throw versionsError;

  const paths = new Set<string>();

  if (document.storage_path) {
    paths.add(document.storage_path as string);
  }

  for (const version of versions ?? []) {
    if (version.storage_path) {
      paths.add(version.storage_path as string);
    }
  }

  const { error: markError } = await supabase
    .from("documents")
    .update({
      status: "deleting",
      updated_at: new Date().toISOString()
    })
    .eq("id", documentId)
    .eq("owner_id", ownerId);

  if (markError) throw markError;

  if (paths.size > 0) {
    const { error: storageError } = await supabase.storage
      .from(STORAGE_BUCKET)
      .remove([...paths]);

    if (storageError) {
      await supabase
        .from("documents")
        .update({
          status: "delete_failed",
          updated_at: new Date().toISOString()
        })
        .eq("id", documentId)
        .eq("owner_id", ownerId);

      throw storageError;
    }
  }

  const { error: deleteError } = await supabase
    .from("documents")
    .delete()
    .eq("id", documentId)
    .eq("owner_id", ownerId);

  if (deleteError) throw deleteError;

  return {
    deleted: true as const,
    removedObjects: paths.size
  };
}
