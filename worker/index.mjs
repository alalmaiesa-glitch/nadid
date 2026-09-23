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

async function markComplete(jobId, documentId) {
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
      status: "partial_ready",
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

  await supabase
    .from("documents")
    .update({
      status: exhausted ? "failed" : "queued",
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

async function processJob(job) {
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
