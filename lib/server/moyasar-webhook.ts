import { createHash, timingSafeEqual } from "node:crypto";
import { getSupabaseAdmin } from "@/lib/supabase-admin";

export const MOYASAR_PAYMENT_EVENTS = new Set([
  "payment_paid",
  "payment_captured",
  "payment_failed",
  "payment_faild",
  "payment_refunded",
  "payment_voided",
  "payment_authorized",
  "payment_verified"
]);

type MoyasarPaymentData = {
  id?: unknown;
  status?: unknown;
  amount?: unknown;
  currency?: unknown;
  captured?: unknown;
  refunded?: unknown;
  metadata?: unknown;
};

export type MoyasarWebhookPayload = {
  id?: unknown;
  type?: unknown;
  created_at?: unknown;
  secret_token?: unknown;
  live?: unknown;
  data?: MoyasarPaymentData;
};

function safeEqual(left: string, right: string) {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

export function validateMoyasarWebhookSecret(
  supplied: unknown,
  expected: string | undefined
) {
  if (!expected || typeof supplied !== "string") return false;
  return safeEqual(supplied, expected);
}

export function parseMoyasarPaymentWebhook(
  payload: MoyasarWebhookPayload
) {
  const eventId =
    typeof payload.id === "string" ? payload.id.trim() : "";
  const eventType =
    typeof payload.type === "string" ? payload.type.trim() : "";
  const paymentId =
    typeof payload.data?.id === "string" ? payload.data.id.trim() : "";
  const currency =
    typeof payload.data?.currency === "string"
      ? payload.data.currency.trim().toUpperCase()
      : "";
  const amount = Number(payload.data?.amount);
  const capturedValue = payload.data?.captured;
  const refundedValue = payload.data?.refunded;
  const capturedMinor =
    capturedValue === undefined || capturedValue === null
      ? null
      : Number(capturedValue);
  const refundedMinor =
    refundedValue === undefined || refundedValue === null
      ? null
      : Number(refundedValue);
  const occurredAt =
    typeof payload.created_at === "string" ? payload.created_at : null;

  if (
    !eventId ||
    !MOYASAR_PAYMENT_EVENTS.has(eventType) ||
    !paymentId ||
    !Number.isSafeInteger(amount) ||
    amount < 0 ||
    !currency ||
    (capturedMinor !== null &&
      (!Number.isSafeInteger(capturedMinor) || capturedMinor < 0)) ||
    (refundedMinor !== null &&
      (!Number.isSafeInteger(refundedMinor) || refundedMinor < 0))
  ) {
    return null;
  }

  return {
    eventId,
    eventType,
    paymentId,
    amount,
    currency,
    capturedMinor,
    refundedMinor,
    live: payload.live === true,
    occurredAt
  };
}

export function webhookPayloadDigest(rawBody: string) {
  return createHash("sha256").update(rawBody).digest("hex");
}

type ApplyResult = {
  local_payment_id: string | null;
  reused: boolean;
  outcome: string;
  purpose: string | null;
  payment_metadata: Record<string, unknown> | null;
};

export async function applyMoyasarPaymentWebhook(
  parsed: ReturnType<typeof parseMoyasarPaymentWebhook>,
  rawBody: string
) {
  if (!parsed) {
    return { ok: false as const, code: "INVALID_WEBHOOK_PAYLOAD" };
  }

  const supabase = getSupabaseAdmin() as any;
  if (!supabase) {
    return { ok: false as const, code: "PAYMENT_SERVICE_UNAVAILABLE" };
  }

  const { data, error } = await supabase.rpc(
    "apply_payment_webhook_event",
    {
      p_provider: "moyasar",
      p_event_id: parsed.eventId,
      p_event_type: parsed.eventType,
      p_provider_payment_id: parsed.paymentId,
      p_amount_minor: parsed.amount,
      p_currency: parsed.currency,
      p_captured_minor: parsed.capturedMinor,
      p_refunded_minor: parsed.refundedMinor,
      p_live: parsed.live,
      p_occurred_at: parsed.occurredAt,
      p_payload_digest: webhookPayloadDigest(rawBody)
    }
  );

  if (error || !data?.[0]) {
    return {
      ok: false as const,
      code:
        error?.message?.includes("webhook_event_replay_mismatch")
          ? "WEBHOOK_REPLAY_MISMATCH"
          : "PAYMENT_WEBHOOK_APPLY_FAILED"
    };
  }

  const result = data[0] as ApplyResult;

  if (
    result.outcome === "applied" &&
    ["payment_paid", "payment_captured"].includes(parsed.eventType) &&
    result.local_payment_id
  ) {
    const metadata = result.payment_metadata ?? {};

    if (
      result.purpose === "subscription" &&
      typeof metadata.plan_id === "string"
    ) {
      const activation = await supabase.rpc(
        "activate_subscription_from_payment",
        {
          p_payment_id: result.local_payment_id,
          p_plan_id: metadata.plan_id
        }
      );
      if (activation.error) {
        return {
          ok: false as const,
          code: "SUBSCRIPTION_ACTIVATION_FAILED"
        };
      }
    }

    if (
      result.purpose === "credit_topup" &&
      typeof metadata.pack_id === "string"
    ) {
      const activation = await supabase.rpc(
        "activate_topup_from_payment",
        {
          p_payment_id: result.local_payment_id,
          p_pack_id: metadata.pack_id
        }
      );
      if (activation.error) {
        return {
          ok: false as const,
          code: "TOPUP_ACTIVATION_FAILED"
        };
      }
    }
  }

  return { ok: true as const, result };
}
