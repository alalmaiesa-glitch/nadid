import { createHash } from "node:crypto";
import type {
  AnalyzeResponse,
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
        .eq("version_id", versionId)
        .order("sequence_no", { ascending: true }),
      supabase
        .from("suggestions")
        .select(
          "client_suggestion_id, node_id, category, title, explanation, original_text, replacement_text, confidence, status"
        )
        .eq("version_id", versionId)
        .eq("status", "pending"),
      supabase
        .from("protected_spans")
        .select("client_fact_id, node_id, span_type, surface_text")
        .eq("version_id", versionId)
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
