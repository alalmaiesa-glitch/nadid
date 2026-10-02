import { getSupabaseAdmin } from "@/lib/supabase-admin";
import {
  RECONCILABLE_PAYMENT_STATUSES,
  reconciliationSecretValid,
  reconcileMoyasarPayment
} from "@/lib/server/payment-reconciliation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function batchSize() {
  const parsed = Number(process.env.NADID_PAYMENT_RECONCILE_BATCH ?? "25");
  if (!Number.isSafeInteger(parsed) || parsed <= 0) return 25;
  return Math.min(parsed, 100);
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

  const { data, error } = await supabase
    .from("payments")
    .select("id,provider_payment_id,status,updated_at")
    .eq("provider", "moyasar")
    .in("status", [...RECONCILABLE_PAYMENT_STATUSES])
    .not("provider_payment_id", "is", null)
    .order("updated_at", { ascending: true })
    .limit(batchSize());

  if (error) {
    return Response.json(
      {
        error: "Could not load reconciliation candidates.",
        code: "PAYMENT_RECONCILIATION_LOOKUP_FAILED"
      },
      { status: 503 }
    );
  }

  const rows = Array.isArray(data) ? data : [];
  const summary = {
    scanned: rows.length,
    reconciled: 0,
    ignored: 0,
    failed: 0
  };
  const failures: Array<{ paymentId: string; code: string }> = [];

  for (const row of rows) {
    const paymentId =
      typeof row.provider_payment_id === "string"
        ? row.provider_payment_id
        : "";

    if (!paymentId) {
      summary.failed += 1;
      failures.push({
        paymentId: String(row.id ?? ""),
        code: "MISSING_PROVIDER_PAYMENT_ID"
      });
      continue;
    }

    const result = await reconcileMoyasarPayment(paymentId);

    if (!result.ok) {
      summary.failed += 1;
      failures.push({
        paymentId,
        code: result.code
      });
      continue;
    }

    if (
      result.outcome === "applied" ||
      result.outcome === "rejected_mismatch"
    ) {
      summary.reconciled += 1;
    } else {
      summary.ignored += 1;
    }
  }

  if (summary.failed > 0) {
    return Response.json(
      {
        ok: false,
        code: "PAYMENT_RECONCILIATION_PARTIAL_FAILURE",
        ...summary,
        failures
      },
      { status: 503 }
    );
  }

  return Response.json({
    ok: true,
    ...summary
  });
}
