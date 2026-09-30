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
const MAINTENANCE_INTERVAL_MS = Math.max(
  60_000,
  Number(process.env.WORKER_MAINTENANCE_INTERVAL_MS ?? 3_600_000)
);
const STALE_UPLOAD_HOURS = Math.max(
  1,
  Number(process.env.NADID_STALE_UPLOAD_HOURS ?? 24)
);
const JOB_LEASE_RENEW_INTERVAL_MS = Math.max(
  5_000,
  Number(process.env.WORKER_JOB_LEASE_RENEW_INTERVAL_MS ?? 60_000)
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
let lastMaintenanceAt = 0;

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
    case "number":
      return "numeric_equivalence";
    case "currency":
    case "percentage":
      return "numeric_unit_equivalence";
    case "date":
      return "date_equivalence";
    case "standard":
    case "entity":
    case "legal_reference":
    case "role":
    case "quotation":
    case "quantity":
      return "exact_or_normalized_identifier";
    case "negation":
    case "obligation":
    case "condition":
      return "normalized_clause_preservation";
    case "qualifier":
      return "meaning_marker_preservation";
    default:
      return "exact_text";
  }
}

async function runMaintenanceIfDue() {
  if (Date.now() - lastMaintenanceAt < MAINTENANCE_INTERVAL_MS) {
    return;
  }

  lastMaintenanceAt = Date.now();
  const staleBefore = new Date(
    Date.now() - STALE_UPLOAD_HOURS * 60 * 60 * 1000
  ).toISOString();

  const { data: staleDocuments, error: staleError } = await supabase
    .from("documents")
    .select("id, storage_path")
    .eq("status", "uploading")
    .lt("created_at", staleBefore)
    .limit(100);

  if (staleError) {
    log("maintenance_stale_query_failed", {
      error: staleError.message.slice(0, 300)
    });
    return;
  }

  let removed = 0;

  for (const document of staleDocuments ?? []) {
    try {
      if (document.storage_path) {
        const { error: storageError } = await supabase.storage
          .from("nadid-documents")
          .remove([document.storage_path]);

        if (storageError) {
          throw storageError;
        }
      }

      const { error: deleteError } = await supabase
        .from("documents")
        .delete()
        .eq("id", document.id)
        .eq("status", "uploading");

      if (deleteError) throw deleteError;
      removed += 1;
    } catch (error) {
      log("maintenance_stale_delete_failed", {
        documentId: document.id,
        error:
          error instanceof Error
            ? error.message.slice(0, 300)
            : String(error).slice(0, 300)
      });
    }
  }

  const oldHeartbeatCutoff = new Date(
    Date.now() - 24 * 60 * 60 * 1000
  ).toISOString();

  await supabase
    .from("worker_heartbeats")
    .delete()
    .lt("last_seen", oldHeartbeatCutoff)
    .neq("worker_id", WORKER_ID);

  if (removed > 0) {
    log("maintenance_stale_uploads_removed", { removed });
  }
}

async function claimJob() {
  const { data, error } = await supabase.rpc("claim_processing_job", {
    p_worker_id: WORKER_ID
  });

  if (error) throw error;
  return data?.[0] ?? null;
}

async function renewJobLease(jobId) {
  const { data, error } = await supabase.rpc(
    "renew_processing_job_lease",
    {
      p_job_id: jobId,
      p_worker_id: WORKER_ID
    }
  );

  if (error) throw error;
  return data === true;
}

function startJobLeaseRenewal(jobId) {
  let stopped = false;
  let renewing = false;
  let leaseLost = false;

  const timer = setInterval(async () => {
    if (stopped || renewing) return;
    renewing = true;

    try {
      const renewed = await renewJobLease(jobId);
      if (!renewed) {
        leaseLost = true;
        log("job_lease_lost", { jobId });
      }
    } catch (error) {
      log("job_lease_renew_failed", {
        jobId,
        error:
          error instanceof Error
            ? error.message.slice(0, 300)
            : String(error).slice(0, 300)
      });
    } finally {
      renewing = false;
    }
  }, JOB_LEASE_RENEW_INTERVAL_MS);

  timer.unref?.();

  return {
    stop() {
      stopped = true;
      clearInterval(timer);
    },
    leaseLost() {
      return leaseLost;
    }
  };
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

  const { data: completedJob, error: jobError } = await supabase
    .from("processing_jobs")
    .update({
      status: "complete",
      locked_at: null,
      locked_by: null,
      last_error: null,
      completed_at: now,
      updated_at: now
    })
    .eq("id", jobId)
    .eq("status", "processing")
    .eq("locked_by", WORKER_ID)
    .select("id")
    .maybeSingle();

  if (jobError) throw jobError;
  if (!completedJob?.id) {
    throw new Error("job_lease_lost_before_complete");
  }

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

  const { data: failedJob, error: failureUpdateError } =
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
      .eq("id", job.id)
      .eq("status", "processing")
      .eq("locked_by", WORKER_ID)
      .select("id")
      .maybeSingle();

  if (failureUpdateError) throw failureUpdateError;

  if (!failedJob?.id) {
    log("job_failure_ignored_after_lease_loss", {
      jobId: job.id,
      documentId: job.document_id
    });
    return;
  }

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
        protected_spans: "meaning_lock_v0.1"
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
            ["negation", "obligation", "condition"].includes(fact.type)
              ? "semantic_strict"
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
  const terms = memory.terms ?? [];
  const facts = memory.facts ?? [];
  const conflicts = memory.conflicts ?? [];
  const knowledgeItems = memory.knowledge_items ?? [];

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
          memory: "knowledge_memory_v0.1",
          facts: "deterministic_v0.1",
          retrieval: "semantic_hybrid_v0.1",
          semantic_review: "semantic_review_v0.1"
        },
        updated_at: new Date().toISOString()
      },
      { onConflict: "version_id" }
    );

  if (memoryStartError) throw memoryStartError;

  for (const table of [
    "fact_conflicts",
    "fact_assertions",
    "document_memory_items",
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
    .in("source_engine", [
      "deep_consistency_v0.1",
      "semantic_review_v0.1"
    ]);

  if (oldDeepSuggestionError) throw oldDeepSuggestionError;

  if (chunks.length > 0) {
    const { error: chunkInsertError } = await supabase
      .from("document_chunks")
      .insert(
        chunks.map((chunk, index) => ({
          version_id: version.id,
          chunk_key: chunk.id,
          sequence_no: index,
          node_keys: chunk.node_ids ?? [],
          chunk_text: chunk.text ?? "",
          token_estimate: Number(chunk.token_estimate ?? 0)
        }))
      );

    if (chunkInsertError) throw chunkInsertError;
  }

  if (terms.length > 0) {
    const { error: termInsertError } = await supabase
      .from("memory_terms")
      .insert(
        terms.map((term) => ({
          version_id: version.id,
          term: term.term,
          occurrence_count: Number(term.count ?? 0),
          node_keys: term.node_ids ?? []
        }))
      );

    if (termInsertError) throw termInsertError;
  }

  if (facts.length > 0) {
    const { error: factInsertError } = await supabase
      .from("fact_assertions")
      .insert(
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

    if (factInsertError) throw factInsertError;
  }

  if (conflicts.length > 0) {
    const { error: conflictInsertError } = await supabase
      .from("fact_conflicts")
      .insert(
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

    if (conflictInsertError) throw conflictInsertError;
  }

  if (knowledgeItems.length > 0) {
    const { error: memoryItemInsertError } = await supabase
      .from("document_memory_items")
      .insert(
        knowledgeItems.map((item) => ({
          version_id: version.id,
          client_item_id: item.id,
          kind: item.kind,
          item_key: item.key,
          item_value: item.value,
          node_keys: item.node_ids ?? [],
          aliases: item.aliases ?? [],
          confidence: Number(item.confidence ?? 0),
          metadata: item.metadata ?? {}
        }))
      );

    if (memoryItemInsertError) throw memoryItemInsertError;
  }

  const semanticIssues = deep.semantic_issues ?? [];
  const needsDeepSuggestions =
    conflicts.length > 0 || semanticIssues.length > 0;

  if (needsDeepSuggestions) {
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

    if (conflicts.length > 0) {
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

    if (semanticIssues.length > 0) {
      const { error: semanticSuggestionError } = await supabase
        .from("suggestions")
        .insert(
          semanticIssues.map((issue) => ({
            version_id: version.id,
            node_id: nodeMap.get(issue.node_id) ?? null,
            client_suggestion_id:
              `semantic-${version.id}-${issue.id}`,
            category: "consistency",
            title: issue.title,
            explanation: issue.explanation,
            original_text: issue.original,
            replacement_text: null,
            confidence: Number(issue.confidence ?? 0),
            status: "pending",
            source_engine: "semantic_review_v0.1",
            evidence: [
              {
                type: "semantic_issue",
                issue_type: issue.issue_type,
                evidence_node_ids:
                  issue.evidence_node_ids ?? [],
                evidence_values:
                  issue.evidence_values ?? []
              }
            ]
          }))
        );

      if (semanticSuggestionError) {
        throw semanticSuggestionError;
      }
    }
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
        retrieval: "semantic_hybrid_v0.1",
        semantic_review: "semantic_review_v0.1"
      },
      metrics: {
        chunks: chunks.length,
        terms: terms.length,
        facts: facts.length,
        conflicts: conflicts.length,
        knowledge_items: knowledgeItems.length,
        semantic_issues: semanticIssues.length
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
      await runMaintenanceIfDue();
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

      const lease = startJobLeaseRenewal(job.id);

      try {
        await processJob(job);

        if (lease.leaseLost()) {
          throw new Error("job_lease_lost_during_processing");
        }
      } catch (error) {
        await markFailure(job, error);
      } finally {
        lease.stop();
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
