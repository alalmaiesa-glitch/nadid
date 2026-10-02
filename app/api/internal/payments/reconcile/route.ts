import { getSupabaseAdmin } from "@/lib/supabase-admin";
import {
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

async function finishRun(
  supabase: any,
  runId: string,
  status: "succeeded" | "partial_failure" | "lookup_failure",
  summary: {
    scanned: number;
    reconciled: number;
    ignored: number;
    failed: number;
  },
  errorCode: string | null
) {
  const { data, error } = await supabase.rpc(
    "finish_payment_reconciliation_run",
    {
      p_run_id: runId,
      p_status: status,
      p_scanned: summary.scanned,
      p_reconciled: summary.reconciled,
      p_ignored: summary.ignored,
      p_failed: summary.failed,
      p_error_code: errorCode
    }
  );

  return !error && data === true;
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

  const started = await supabase.rpc("start_payment_reconciliation_run");
  const runId =
    !started.error && typeof started.data === "string"
      ? started.data
      : "";

  if (!runId) {
    return Response.json(
      {
        error: "Could not start reconciliation audit run.",
        code: "PAYMENT_RECONCILIATION_AUDIT_START_FAILED"
      },
      { status: 503 }
    );
  }

  const { data, error } = await supabase.rpc(
    "claim_payment_reconciliation_batch",
    { p_limit: batchSize() }
  );

  if (error) {
    const summary = {
      scanned: 0,
      reconciled: 0,
      ignored: 0,
      failed: 0
    };
    const audited = await finishRun(
      supabase,
      runId,
      "lookup_failure",
      summary,
      "PAYMENT_RECONCILIATION_LOOKUP_FAILED"
    );

    return Response.json(
      {
        error: audited
          ? "Could not load reconciliation candidates."
          : "Reconciliation lookup and audit finalization failed.",
        code: audited
          ? "PAYMENT_RECONCILIATION_LOOKUP_FAILED"
          : "PAYMENT_RECONCILIATION_AUDIT_FAILED"
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
    const audited = await finishRun(
      supabase,
      runId,
      "partial_failure",
      summary,
      "PAYMENT_RECONCILIATION_PARTIAL_FAILURE"
    );

    if (!audited) {
      return Response.json(
        {
          ok: false,
          code: "PAYMENT_RECONCILIATION_AUDIT_FAILED",
          ...summary,
          failures
        },
        { status: 503 }
      );
    }

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

  const audited = await finishRun(
    supabase,
    runId,
    "succeeded",
    summary,
    null
  );

  if (!audited) {
    return Response.json(
      {
        ok: false,
        code: "PAYMENT_RECONCILIATION_AUDIT_FAILED",
        ...summary
      },
      { status: 503 }
    );
  }

  return Response.json({
    ok: true,
    runId,
    ...summary
  });
}
