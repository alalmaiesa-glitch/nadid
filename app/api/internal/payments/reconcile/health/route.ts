import { getSupabaseAdmin } from "@/lib/supabase-admin";
import { reconciliationSecretValid } from "@/lib/server/payment-reconciliation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function maxAgeMinutes() {
  const parsed = Number(
    process.env.NADID_PAYMENT_RECONCILE_MAX_AGE_MINUTES ?? "2160"
  );
  if (!Number.isSafeInteger(parsed)) return 2160;
  return Math.min(Math.max(parsed, 60), 10080);
}

export async function GET(request: Request) {
  if (
    !reconciliationSecretValid(
      request.headers.get("authorization"),
      process.env.CRON_SECRET
    )
  ) {
    return Response.json(
      { error: "Unauthorized.", code: "UNAUTHORIZED" },
      { status: 401 }
    );
  }

  const supabase = getSupabaseAdmin() as any;
  if (!supabase) {
    return Response.json(
      {
        error: "Payment service is unavailable.",
        code: "PAYMENT_SERVICE_UNAVAILABLE"
      },
      { status: 503 }
    );
  }

  const { data, error } = await supabase.rpc(
    "get_payment_reconciliation_health",
    { p_max_age_minutes: maxAgeMinutes() }
  );

  const health = Array.isArray(data) ? data[0] : null;

  if (error || !health) {
    return Response.json(
      {
        error: "Could not resolve reconciliation scheduler health.",
        code: "PAYMENT_RECONCILIATION_HEALTH_FAILED"
      },
      { status: 503 }
    );
  }

  const stale = health.stale === true;
  const staleRunning = health.stale_running === true;

  if (stale || staleRunning) {
    return Response.json(
      {
        ok: false,
        code: "PAYMENT_RECONCILIATION_SCHEDULER_STALE",
        stale,
        staleRunning,
        lastStartedAt: health.last_started_at ?? null,
        lastCompletedAt: health.last_completed_at ?? null,
        lastSuccessAt: health.last_success_at ?? null,
        oldestRunningAt: health.oldest_running_at ?? null
      },
      { status: 503 }
    );
  }

  return Response.json({
    ok: true,
    stale: false,
    staleRunning: false,
    lastStartedAt: health.last_started_at ?? null,
    lastCompletedAt: health.last_completed_at ?? null,
    lastSuccessAt: health.last_success_at ?? null,
    oldestRunningAt: health.oldest_running_at ?? null
  });
}
