import {
  enqueueDeepReview,
  loadDeepMemory
} from "@/lib/server/document-persistence";
import { authorizeDocument } from "@/lib/server/authz";
import { getSupabaseAdmin } from "@/lib/supabase-admin";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const auth = await authorizeDocument(id);
  if (!auth.ok) return auth.response;

  const memory = await loadDeepMemory(id);

  if (memory) {
    return Response.json({
      state: "ready",
      memory
    });
  }

  const supabase = getSupabaseAdmin();

  if (!supabase) {
    return Response.json(
      { state: "unavailable" },
      { status: 409 }
    );
  }

  const { data: job } = await supabase
    .from("processing_jobs")
    .select("status, attempts, max_attempts, last_error")
    .eq("document_id", id)
    .eq("job_type", "deep_review")
    .maybeSingle();

  if (!job) {
    return Response.json(
      { state: "missing" },
      { status: 404 }
    );
  }

  return Response.json({
    state: job.status,
    attempts: Number(job.attempts ?? 0),
    maxAttempts: Number(job.max_attempts ?? 3),
    error: job.status === "failed" ? job.last_error : null
  });
}

export async function POST(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const auth = await authorizeDocument(id);
  if (!auth.ok) return auth.response;

  if (!auth.userId) {
    return Response.json(
      { state: "unavailable" },
      { status: 409 }
    );
  }

  const existing = await loadDeepMemory(id);

  if (existing) {
    return Response.json({
      state: "ready",
      memory: existing,
      reused: true
    });
  }

  try {
    const job = await enqueueDeepReview(id, auth.userId);

    return Response.json(
      {
        state: job.status,
        ...job
      },
      {
        status: job.status === "ready" ? 200 : 202
      }
    );
  } catch (error) {
    return Response.json(
      {
        state: "failed",
        error:
          error instanceof Error
            ? error.message
            : "deep_review_enqueue_failed"
      },
      { status: 500 }
    );
  }
}
