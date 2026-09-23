import os from "node:os";
import { createHash } from "node:crypto";
import { setTimeout as sleep } from "node:timers/promises";
import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL =
  process.env.SUPABASE_URL ??
  process.env.NEXT_PUBLIC_SUPABASE_URL;
const SERVICE_ROLE = process.env.SUPABASE_SERVICE_ROLE_KEY;
const AEE_BACKEND_URL = process.env.AEE_BACKEND_URL?.replace(/\/$/, "");
const AEE_INTERNAL_TOKEN = process.env.AEE_INTERNAL_TOKEN;
const WORKER_ID =
  process.env.WORKER_ID ?? `${os.hostname()}:${process.pid}`;
const POLL_INTERVAL_MS = Math.max(
  500,
  Number(process.env.WORKER_POLL_INTERVAL_MS ?? 2000)
);

if (!SUPABASE_URL) throw new Error("SUPABASE_URL is required");
if (!SERVICE_ROLE) throw new Error("SUPABASE_SERVICE_ROLE_KEY is required");
if (!AEE_BACKEND_URL) throw new Error("AEE_BACKEND_URL is required");
if (!AEE_INTERNAL_TOKEN) throw new Error("AEE_INTERNAL_TOKEN is required");

const supabase = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: {
    persistSession: false,
    autoRefreshToken: false
  }
});

let stopping = false;

async function writeHeartbeat() {
  const now = new Date().toISOString();

  const { error } = await supabase
    .from("worker_heartbeats")
    .upsert(
      {
        worker_id: WORKER_ID,
        last_seen: now,
        metadata: {
          service: "initial_review",
          poll_interval_ms: POLL_INTERVAL_MS
        }
      },
      { onConflict: "worker_id" }
    );

  if (error) throw error;
}

async function heartbeatLoop() {
  while (!stopping) {
    try {
      await writeHeartbeat();
    } catch (error) {
      log("heartbeat_failed", {
        error:
          error instanceof Error
            ? error.message.slice(0, 300)
            : String(error).slice(0, 300)
      });
    }

    await sleep(30_000);
  }
}

process.on("SIGTERM", () => {
  stopping = true;
});

process.on("SIGINT", () => {
  stopping = true;
});

function log(event, details = {}) {
  console.log(
    JSON.stringify({
      ts: new Date().toISOString(),
      service: "nadid-worker",
      event,
      workerId: WORKER_ID,
      ...details
    })
  );
}

function validatorForFact(type) {
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

async function claimJob() {
  const { data, error } = await supabase.rpc("claim_processing_job", {
    p_worker_id: WORKER_ID
  });

  if (error) throw error;
  return data?.[0] ?? null;
}

async function callAee(filename, buffer) {
  const bytes = new Uint8Array(buffer.length);
  bytes.set(buffer);

  const body = new FormData();
  body.append(
    "file",
    new Blob([bytes.buffer], {
      type:
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }),
    filename
  );

  const response = await fetch(`${AEE_BACKEND_URL}/v1/analyze/docx`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${AEE_INTERNAL_TOKEN}`
    },
    body,
    signal: AbortSignal.timeout(180_000)
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(
      `aee_analyze_failed_${response.status}:${detail.slice(0, 300)}`
    );
  }

  return response.json();
}

async function callAeeDeep(filename, buffer) {
  const bytes = new Uint8Array(buffer.length);
  bytes.set(buffer);

  const body = new FormData();
  body.append(
    "file",
    new Blob([bytes.buffer], {
      type:
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }),
    filename
  );

  const response = await fetch(
    `${AEE_BACKEND_URL}/v1/analyze/docx/deep`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${AEE_INTERNAL_TOKEN}`
      },
      body,
      signal: AbortSignal.timeout(240_000)
    }
  );

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(
      `aee_deep_failed_${response.status}:${detail.slice(0, 300)}`
    );
  }

  return response.json();
}

async function markComplete(
  jobId,
  documentId,
  documentStatus = "partial_ready"
) {
  const now = new Date().toISOString();

  const { error: jobError } = await supabase
    .from("processing_jobs")
    .update({
      status: "complete",
      locked_at: null,
      locked_by: null,
      last_error: null,
      completed_at: now,
      updated_at: now
    })
    .eq("id", jobId);

  if (jobError) throw jobError;

  const { error: documentError } = await supabase
    .from("documents")
    .update({
      status: documentStatus,
      updated_at: now
    })
    .eq("id", documentId);

  if (documentError) throw documentError;
}

async function markFailure(job, error) {
  const attempts = Number(job.attempts ?? 1);
  const maxAttempts = Number(job.max_attempts ?? 3);
  const exhausted = attempts >= maxAttempts;
  const delaySeconds = Math.min(
    300,
    5 * Math.pow(2, Math.max(0, attempts - 1))
  );
  const now = new Date();
  const availableAt = new Date(
    now.getTime() + delaySeconds * 1000
  ).toISOString();
  const message =
    error instanceof Error ? error.message : String(error);

  await supabase
    .from("processing_jobs")
    .update({
      status: exhausted ? "failed" : "queued",
      available_at: availableAt,
      locked_at: null,
      locked_by: null,
      last_error: message.slice(0, 1000),
      updated_at: now.toISOString()
    })
    .eq("id", job.id);

  const documentStatus =
    job.job_type === "deep_review"
      ? "partial_ready"
      : exhausted
        ? "failed"
        : "queued";

  await supabase
    .from("documents")
    .update({
      status: documentStatus,
      updated_at: now.toISOString()
    })
    .eq("id", job.document_id);

  log("job_failed", {
    jobId: job.id,
    documentId: job.document_id,
    attempts,
    exhausted,
    error: message.slice(0, 300)
  });
}

async function processInitialReview(job) {
  const { data: document, error: documentError } = await supabase
    .from("documents")
    .select("id, owner_id, filename, storage_path, status")
    .eq("id", job.document_id)
    .single();

  if (documentError || !document?.storage_path) {
    throw documentError ?? new Error("document_or_storage_path_missing");
  }

  const { data: existingVersion, error: existingVersionError } =
    await supabase
      .from("document_versions")
      .select("id, status")
      .eq("document_id", document.id)
      .eq("version_no", 1)
      .maybeSingle();

  if (existingVersionError) throw existingVersionError;

  if (existingVersion?.status === "ready") {
    await markComplete(job.id, document.id);
    log("job_reused_ready_version", {
      jobId: job.id,
      documentId: document.id
    });
    return;
  }

  if (existingVersion?.id) {
    const { error: cleanupError } = await supabase
      .from("document_versions")
      .delete()
      .eq("id", existingVersion.id);

    if (cleanupError) throw cleanupError;
  }

  const { error: processingStatusError } = await supabase
    .from("documents")
    .update({
      status: "processing",
      updated_at: new Date().toISOString()
    })
    .eq("id", document.id);

  if (processingStatusError) throw processingStatusError;

  const { data: source, error: storageError } = await supabase.storage
    .from("nadid-documents")
    .download(document.storage_path);

  if (storageError || !source) {
    throw storageError ?? new Error("source_download_failed");
  }

  const buffer = Buffer.from(await source.arrayBuffer());
  const analysis = await callAee(document.filename, buffer);

  const { data: version, error: versionError } = await supabase
    .from("document_versions")
    .insert({
      document_id: document.id,
      version_no: 1,
      is_source: true,
      storage_path: document.storage_path,
      status: "processing",
      source_sha256: createHash("sha256")
        .update(buffer)
        .digest("hex"),
      engine_manifest: {
        parser: "aee_docx_v0.1",
        fast_review: "fast_rules_v0.1",
        protected_spans: "atomic_guard_v0.1"
      }
    })
    .select("id")
    .single();

  if (versionError || !version?.id) {
    throw versionError ?? new Error("version_not_created");
  }

  try {
    const nodeRows = (analysis.nodes ?? []).map((node, index) => ({
      version_id: version.id,
      logical_node_key: node.id,
      node_type: node.type,
      sequence_no: index,
      text: node.text,
      normalized_text: node.text.normalize("NFC"),
      content_hash: createHash("sha256")
        .update(node.text)
        .digest("hex")
    }));

    const { data: insertedNodes, error: nodeError } = await supabase
      .from("document_nodes")
      .insert(nodeRows)
      .select("id, logical_node_key");

    if (nodeError) throw nodeError;

    const nodeMap = new Map(
      (insertedNodes ?? []).map((row) => [
        row.logical_node_key,
        row.id
      ])
    );

    if ((analysis.suggestions ?? []).length > 0) {
      const { error } = await supabase.from("suggestions").insert(
        analysis.suggestions.map((item) => ({
          version_id: version.id,
          node_id: nodeMap.get(item.node_id) ?? null,
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

    if ((analysis.protected_spans ?? []).length > 0) {
      const { error } = await supabase.from("protected_spans").insert(
        analysis.protected_spans.map((fact) => ({
          version_id: version.id,
          node_id: nodeMap.get(fact.node_id) ?? null,
          client_fact_id: fact.id,
          span_type: fact.type,
          surface_text: fact.value,
          canonical_value: { surface: fact.value },
          validator_key: validatorForFact(fact.type),
          lock_policy:
            fact.type === "negation"
              ? "semantic_exact"
              : "normalize_only",
          lock_mode: "block",
          confidence: 1
        }))
      );

      if (error) throw error;
    }

    const { error: runError } = await supabase
      .from("analysis_runs")
      .insert({
        version_id: version.id,
        run_type: "fast",
        state: "complete",
        engine_manifest: {
          parser: "aee_docx_v0.1",
          reviewer: "fast_rules_v0.1"
        },
        metrics: {
          suggestions: (analysis.suggestions ?? []).length,
          protected_facts:
            (analysis.protected_spans ?? []).length
        },
        completed_at: new Date().toISOString()
      });

    if (runError) throw runError;

    const { error: versionReadyError } = await supabase
      .from("document_versions")
      .update({ status: "ready" })
      .eq("id", version.id);

    if (versionReadyError) throw versionReadyError;

    const { error: documentReadyError } = await supabase
      .from("documents")
      .update({
        status: "partial_ready",
        word_count: Number(analysis.document.word_count ?? 0),
        paragraph_count: Number(
          analysis.document.paragraph_count ?? 0
        ),
        updated_at: new Date().toISOString()
      })
      .eq("id", document.id);

    if (documentReadyError) throw documentReadyError;

    await markComplete(job.id, document.id);

    log("job_completed", {
      jobId: job.id,
      documentId: document.id,
      attempts: job.attempts
    });
  } catch (error) {
    await supabase
      .from("document_versions")
      .update({ status: "failed" })
      .eq("id", version.id);

    throw error;
  }
}

async function processDeepReview(job) {
  const { data: document, error: documentError } = await supabase
    .from("documents")
    .select("id, filename, storage_path")
    .eq("id", job.document_id)
    .single();

  if (documentError || !document) {
    throw documentError ?? new Error("document_missing");
  }

  const { data: version, error: versionError } = await supabase
    .from("document_versions")
    .select("id, storage_path")
    .eq("document_id", document.id)
    .eq("status", "ready")
    .order("version_no", { ascending: false })
    .limit(1)
    .single();

  if (versionError || !version) {
    throw versionError ?? new Error("ready_version_missing");
  }

  const { data: existingMemory, error: memoryLookupError } =
    await supabase
      .from("document_memory")
      .select("state")
      .eq("version_id", version.id)
      .maybeSingle();

  if (memoryLookupError) throw memoryLookupError;

  if (existingMemory?.state === "ready") {
    await markComplete(job.id, document.id, "ready");
    log("deep_job_reused_ready_memory", {
      jobId: job.id,
      documentId: document.id
    });
    return;
  }

  const storagePath = version.storage_path ?? document.storage_path;

  if (!storagePath) {
    throw new Error("source_storage_path_missing");
  }

  const { data: source, error: storageError } = await supabase.storage
    .from("nadid-documents")
    .download(storagePath);

  if (storageError || !source) {
    throw storageError ?? new Error("source_download_failed");
  }

  const buffer = Buffer.from(await source.arrayBuffer());
  const deep = await callAeeDeep(document.filename, buffer);
  const memory = deep.memory ?? {};
  const chunks = deep.base?.chunks ?? [];

  const { error: memoryStartError } = await supabase
    .from("document_memory")
    .upsert(
      {
        version_id: version.id,
        state: "building",
        headings: memory.headings ?? [],
        protected_count: Number(memory.protected_count ?? 0),
        chunk_count: Number(memory.chunk_count ?? chunks.length),
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

  for (const table of [
    "fact_conflicts",
    "fact_assertions",
    "memory_terms",
    "document_chunks"
  ]) {
    const { error } = await supabase
      .from(table)
      .delete()
      .eq("version_id", version.id);

    if (error) throw error;
  }

  const { error: oldDeepSuggestionError } = await supabase
    .from("suggestions")
    .delete()
    .eq("version_id", version.id)
    .eq("source_engine", "deep_consistency_v0.1");

  if (oldDeepSuggestionError) throw oldDeepSuggestionError;

  if (chunks.length > 0) {
    const { error } = await supabase.from("document_chunks").insert(
      chunks.map((chunk, index) => ({
        version_id: version.id,
        chunk_key: chunk.id,
        sequence_no: index,
        node_keys: chunk.node_ids ?? [],
        chunk_text: chunk.text,
        token_estimate: Number(chunk.token_estimate ?? 0)
      }))
    );

    if (error) throw error;
  }

  const terms = memory.terms ?? [];
  if (terms.length > 0) {
    const { error } = await supabase.from("memory_terms").insert(
      terms.map((term) => ({
        version_id: version.id,
        term: term.term,
        occurrence_count: Number(term.count ?? 0),
        node_keys: term.node_ids ?? []
      }))
    );

    if (error) throw error;
  }

  const facts = memory.facts ?? [];
  if (facts.length > 0) {
    const { error } = await supabase.from("fact_assertions").insert(
      facts.map((fact) => ({
        version_id: version.id,
        client_fact_id: fact.id,
        node_key: fact.node_id,
        fact_type: fact.fact_type,
        claim_key: fact.claim_key,
        surface_value: fact.value,
        canonical_value: fact.canonical_value,
        context_text: fact.context ?? "",
        confidence: Number(fact.confidence ?? 0),
        authority: "extracted"
      }))
    );

    if (error) throw error;
  }

  const conflicts = memory.conflicts ?? [];
  if (conflicts.length > 0) {
    const { error } = await supabase.from("fact_conflicts").insert(
      conflicts.map((conflict) => ({
        version_id: version.id,
        client_conflict_id: conflict.id,
        claim_key: conflict.claim_key,
        fact_ids: conflict.fact_ids ?? [],
        values_found: conflict.values ?? [],
        confidence: Number(conflict.confidence ?? 0),
        status: "open"
      }))
    );

    if (error) throw error;

    const { data: nodes, error: nodesError } = await supabase
      .from("document_nodes")
      .select("id, logical_node_key")
      .eq("version_id", version.id);

    if (nodesError) throw nodesError;

    const nodeMap = new Map(
      (nodes ?? []).map((node) => [
        node.logical_node_key,
        node.id
      ])
    );
    const factMap = new Map(
      facts.map((fact) => [fact.id, fact])
    );

    const { error: suggestionError } = await supabase
      .from("suggestions")
      .insert(
        conflicts.map((conflict) => {
          const firstFact = (conflict.fact_ids ?? [])
            .map((factId) => factMap.get(factId))
            .find(Boolean);

          return {
            version_id: version.id,
            node_id: firstFact
              ? nodeMap.get(firstFact.node_id) ?? null
              : null,
            client_suggestion_id:
              `deep-conflict-${version.id}-${conflict.id}`,
            category: "consistency",
            title: "تعارض محتمل في حقيقة",
            explanation:
              "وجد نَضِيد قيمًا مختلفة لادعاء يبدو متطابقًا عبر المستند: " +
              (conflict.values ?? []).join(" / "),
            original_text:
              firstFact?.value ??
              (conflict.values ?? []).join(" / "),
            replacement_text: null,
            confidence: Number(conflict.confidence ?? 0),
            status: "pending",
            source_engine: "deep_consistency_v0.1",
            evidence: [
              {
                type: "fact_conflict",
                conflict_id: conflict.id,
                fact_ids: conflict.fact_ids ?? [],
                values: conflict.values ?? []
              }
            ]
          };
        })
      );

    if (suggestionError) throw suggestionError;
  }

  await supabase
    .from("analysis_runs")
    .delete()
    .eq("version_id", version.id)
    .eq("run_type", "deep");

  const { error: runError } = await supabase
    .from("analysis_runs")
    .insert({
      version_id: version.id,
      run_type: "deep",
      state: "complete",
      engine_manifest: {
        memory: "deterministic_v0.1",
        facts: "deterministic_v0.1",
        retrieval: "lexical_v0.1"
      },
      metrics: {
        chunks: chunks.length,
        terms: terms.length,
        facts: facts.length,
        conflicts: conflicts.length
      },
      completed_at: new Date().toISOString()
    });

  if (runError) throw runError;

  const { error: memoryReadyError } = await supabase
    .from("document_memory")
    .update({
      state: "ready",
      built_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
    .eq("version_id", version.id);

  if (memoryReadyError) throw memoryReadyError;

  await markComplete(job.id, document.id, "ready");

  log("deep_job_completed", {
    jobId: job.id,
    documentId: document.id,
    conflicts: conflicts.length
  });
}

async function processJob(job) {
  if (job.job_type === "deep_review") {
    return processDeepReview(job);
  }

  return processInitialReview(job);
}

async function main() {
  log("worker_started");
  await writeHeartbeat();
  const heartbeatTask = heartbeatLoop();

  while (!stopping) {
    try {
      const job = await claimJob();

      if (!job) {
        await sleep(POLL_INTERVAL_MS);
        continue;
      }

      log("job_claimed", {
        jobId: job.id,
        documentId: job.document_id,
        attempts: job.attempts
      });

      try {
        await processJob(job);
      } catch (error) {
        await markFailure(job, error);
      }
    } catch (error) {
      log("worker_loop_error", {
        error:
          error instanceof Error
            ? error.message.slice(0, 300)
            : String(error).slice(0, 300)
      });
      await sleep(Math.max(POLL_INTERVAL_MS, 3000));
    }
  }

  await heartbeatTask;
  log("worker_stopped");
}

main().catch((error) => {
  log("worker_fatal", {
    error:
      error instanceof Error
        ? error.message.slice(0, 300)
        : String(error).slice(0, 300)
  });
  process.exitCode = 1;
});
