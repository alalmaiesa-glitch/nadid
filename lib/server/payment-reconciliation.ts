import { timingSafeEqual } from "node:crypto";
import {
  callbackEventType,
  fetchMoyasarPayment
} from "@/lib/server/moyasar-client";
import { applyMoyasarPaymentWebhook } from "@/lib/server/moyasar-webhook";

export const RECONCILABLE_PAYMENT_STATUSES = [
  "pending",
  "paid",
  "partially_refunded"
] as const;

export function reconciliationSecretValid(
  authorization: string | null,
  expected: string | undefined
) {
  if (!expected) return false;

  const [scheme, supplied = ""] = (authorization ?? "").split(" ", 2);
  if (scheme?.toLowerCase() !== "bearer" || !supplied) return false;

  const left = Buffer.from(supplied);
  const right = Buffer.from(expected);
  if (left.length !== right.length) return false;
  return timingSafeEqual(left, right);
}

function canonicalRemoteState(
  payment: {
    id: string;
    status: string;
    amount: number;
    currency: string;
    captured: number;
    refunded: number;
    created_at?: string;
    updated_at?: string;
  },
  live: boolean
) {
  return JSON.stringify({
    id: payment.id,
    status: payment.status.toLowerCase(),
    amount: payment.amount,
    currency: payment.currency.toUpperCase(),
    captured: payment.captured,
    refunded: payment.refunded,
    live,
    occurredAt: payment.updated_at ?? payment.created_at ?? null
  });
}

export async function reconcileMoyasarPayment(paymentId: string) {
  const remote = await fetchMoyasarPayment(paymentId);
  if (!remote.ok) {
    return {
      ok: false as const,
      code: remote.code,
      status: remote.status
    };
  }

  const payment = remote.payment;
  const eventType = callbackEventType(payment.status);

  if (!eventType) {
    return {
      ok: true as const,
      outcome: "ignored_status",
      paymentId: payment.id,
      remoteStatus: payment.status
    };
  }

  const occurredAt =
    payment.updated_at ?? payment.created_at ?? null;

  // Deterministic identity and digest source are derived only from the
  // verified provider state. Re-running reconciliation for the same state is
  // idempotent even if irrelevant provider JSON formatting changes.
  const eventId = [
    "reconcile",
    payment.id,
    payment.status.toLowerCase(),
    String(payment.captured),
    String(payment.refunded),
    occurredAt ?? "unknown"
  ].join(":");

  const applied = await applyMoyasarPaymentWebhook(
    {
      eventId,
      eventType,
      paymentId: payment.id,
      amount: payment.amount,
      currency: payment.currency,
      capturedMinor: payment.captured,
      refundedMinor: payment.refunded,
      live: remote.live,
      occurredAt
    },
    canonicalRemoteState(payment, remote.live)
  );

  if (!applied.ok) {
    return {
      ok: false as const,
      code: applied.code,
      status:
        applied.code === "WEBHOOK_REPLAY_MISMATCH" ? 409 : 503
    };
  }

  return {
    ok: true as const,
    outcome: applied.result.outcome,
    paymentId: payment.id,
    remoteStatus: payment.status
  };
}
