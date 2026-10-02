import { getSupabaseAdmin } from "@/lib/supabase-admin";
import {
  reconciliationSecretValid,
  reconcileMoyasarPayment
} from "@/lib/server/payment-reconciliation";
import {
  moyasarFetchMaxAttempts,
  moyasarFetchTimeoutMs
} from "@/lib/server/moyasar-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function batchSize() {
  const parsed = Number(process.env.NADID_PAYMENT_RECONCILE_BATCH ?? "25");
  if (!Number.isSafeInteger(parsed) || parsed <= 0) return 25;
  return Math.min(parsed, 100);
}

function claimLeaseSeconds() {
  const parsed = Number(
    process.env.NADID_PAYMENT_RECONCILE_CLAIM_LEASE_SECONDS ?? "900"
  );
  if (!Number.isSafeInteger(parsed)) return 900;
  return Math.min(Math.max(parsed, 60), 3600);
}

function runBudgetMs() {
  const parsed = Number(
    process.env.NADID_PAYMENT_RECONCILE_RUN_BUDGET_MS ?? "240000"
  );
  if (!Number.isSafeInteger(parsed)) return 240000;
  return Math.min(Math.max(parsed, 60000), 900000);
}

function nextItemReserveMs() {
  const attempts = moyasarFetchMaxAttempts();
  const providerWait =
    moyasarFetchTimeoutMs() * attempts +
    Math.max(attempts - 1, 0) * 2000;

  // Keep a small margin for webhook/RPC persistence and JSON handling after
  // the provider call has completed.
  return providerWait + 5000;
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

  const limit = batchSize();
  const deadline = Date.now() + runBudgetMs();
  const summary = {
    scanned: 0,
    reconciled: 0,
    ignored: 0,
    failed: 0
  };
  const failures: Array<{ paymentId: string; code: string }> = [];
  let budgetExhausted = false;
  let lookupFailed = false;

  while (summary.scanned < limit) {
    if (Date.now() + nextItemReserveMs() >= deadline) {
      budgetExhausted = true;
      break;
    }

    const { data, error } = await supabase.rpc(
      "claim_payment_reconciliation_batch",
      {
        p_limit: 1,
        p_lease_seconds: claimLeaseSeconds()
      }
    );

    if (error) {
      lookupFailed = true;
      break;
    }

    const rows = Array.isArray(data) ? data : [];
    if (rows.length === 0) {
      break;
    }

    const row = rows[0];
    summary.scanned += 1;

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

  if (lookupFailed) {
    const status =
      summary.scanned === 0 ? "lookup_failure" : "partial_failure";
    const errorCode =
      summary.scanned === 0
        ? "PAYMENT_RECONCILIATION_LOOKUP_FAILED"
        : "PAYMENT_RECONCILIATION_PARTIAL_FAILURE";

    const audited = await finishRun(
      supabase,
      runId,
      status,
      summary,
      errorCode
    );

    return Response.json(
      {
        ok: false,
        code: audited
          ? errorCode
          : "PAYMENT_RECONCILIATION_AUDIT_FAILED",
        ...summary,
        failures
      },
      { status: 503 }
    );
  }

  if (budgetExhausted) {
    const audited = await finishRun(
      supabase,
      runId,
      "partial_failure",
      summary,
      "PAYMENT_RECONCILIATION_TIME_BUDGET_EXHAUSTED"
    );

    return Response.json(
      {
        ok: false,
        code: audited
          ? "PAYMENT_RECONCILIATION_TIME_BUDGET_EXHAUSTED"
          : "PAYMENT_RECONCILIATION_AUDIT_FAILED",
        ...summary,
        failures
      },
      { status: 503 }
    );
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
