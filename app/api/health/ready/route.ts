import { getSupabaseAdmin } from "@/lib/supabase-admin";

function configured(name: string) {
  return Boolean(process.env[name]);
}

export async function GET() {
  const configuration = {
    supabaseUrl: configured("NEXT_PUBLIC_SUPABASE_URL"),
    supabasePublishableKey: configured("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"),
    supabaseServiceRole: configured("SUPABASE_SERVICE_ROLE_KEY"),
    aeeUrl: configured("AEE_BACKEND_URL"),
    aeeInternalToken: configured("AEE_INTERNAL_TOKEN")
  };

  const configurationReady = Object.values(configuration).every(Boolean);

  let database = false;
  let aee = false;
  let worker = false;

  const queue = {
    queued: 0,
    processing: 0,
    failed: 0
  };

  const supabase = getSupabaseAdmin();

  if (supabase) {
    const cutoff = new Date(Date.now() - 120_000).toISOString();

    const [
      { error: databaseError },
      { data: heartbeat, error: heartbeatError },
      { count: queuedCount },
      { count: processingCount },
      { count: failedCount }
    ] = await Promise.all([
      supabase
        .from("documents")
        .select("id", { head: true, count: "exact" })
        .limit(1),
      supabase
        .from("worker_heartbeats")
        .select("worker_id, last_seen")
        .gte("last_seen", cutoff)
        .order("last_seen", { ascending: false })
        .limit(1)
        .maybeSingle(),
      supabase
        .from("processing_jobs")
        .select("id", { head: true, count: "exact" })
        .eq("status", "queued"),
      supabase
        .from("processing_jobs")
        .select("id", { head: true, count: "exact" })
        .eq("status", "processing"),
      supabase
        .from("processing_jobs")
        .select("id", { head: true, count: "exact" })
        .eq("status", "failed")
    ]);

    database = !databaseError;
    worker = !heartbeatError && Boolean(heartbeat?.last_seen);
    queue.queued = queuedCount ?? 0;
    queue.processing = processingCount ?? 0;
    queue.failed = failedCount ?? 0;
  }

  const aeeBase = process.env.AEE_BACKEND_URL?.replace(/\/$/, "");

  if (aeeBase) {
    try {
      const response = await fetch(aeeBase + "/health", {
        cache: "no-store",
        signal: AbortSignal.timeout(5_000)
      });

      aee = response.ok;
    } catch {
      aee = false;
    }
  }

  const ready =
    configurationReady &&
    database &&
    aee &&
    worker;

  return Response.json(
    {
      status: ready ? "ready" : "not_ready",
      components: {
        configuration: configurationReady,
        database,
        aee,
        worker
      },
      queue
    },
    {
      status: ready ? 200 : 503,
      headers: {
        "Cache-Control": "no-store"
      }
    }
  );
}
