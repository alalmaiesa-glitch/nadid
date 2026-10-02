import { authorizeUser } from "@/lib/server/authz";
import {
  API_RATE_LIMITS,
  enforceUserRateLimit
} from "@/lib/server/rate-limit";
import { fetchMoyasarPayment, callbackEventType } from "@/lib/server/moyasar-client";
import { applyMoyasarPaymentWebhook } from "@/lib/server/moyasar-webhook";
import { getSupabaseAdmin } from "@/lib/supabase-admin";

export const runtime = "nodejs";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function GET(request: Request) {
  const auth = await authorizeUser();
  if (!auth.ok) return auth.response;
  if (!auth.userId) {
    return Response.json(
      { error: "Billing identity is unavailable.", code: "BILLING_IDENTITY_UNAVAILABLE" },
      { status: 503 }
    );
  }

  const rateLimit = await enforceUserRateLimit(
    auth.userId,
    API_RATE_LIMITS.paymentVerify
  );
  if (rateLimit) return rateLimit;

  const url = new URL(request.url);
  const paymentId = (url.searchParams.get("id") ?? "").trim();

  if (!UUID_RE.test(paymentId)) {
    return Response.json(
      { error: "Invalid payment ID.", code: "INVALID_PAYMENT_ID" },
      { status: 400 }
    );
  }

  const supabase = getSupabaseAdmin() as any;
  if (!supabase) {
    return Response.json(
      { error: "Payment service is unavailable.", code: "PAYMENT_SERVICE_UNAVAILABLE" },
      { status: 503 }
    );
  }

  const { data: localPayment, error: localError } = await supabase
    .from("payments")
    .select("id,user_id,provider_payment_id,provider_mode,amount_minor,currency,status")
    .eq("provider", "moyasar")
    .eq("provider_payment_id", paymentId)
    .eq("user_id", auth.userId)
    .maybeSingle();

  if (localError) {
    return Response.json(
      { error: "Payment lookup failed.", code: "PAYMENT_LOOKUP_FAILED" },
      { status: 503 }
    );
  }

  if (!localPayment) {
    return Response.json(
      { error: "Payment not found.", code: "PAYMENT_NOT_FOUND" },
      { status: 404 }
    );
  }

  const remote = await fetchMoyasarPayment(paymentId);
  if (!remote.ok) {
    return Response.json(
      { error: "Could not verify payment.", code: remote.code },
      { status: remote.status }
    );
  }

  const payment = remote.payment;

  const remoteMode = remote.live ? "live" : "test";

  if (
    String(localPayment.provider_mode) !== remoteMode ||
    Number(localPayment.amount_minor) !== payment.amount ||
    String(localPayment.currency).toUpperCase() !== payment.currency
  ) {
    return Response.json(
      {
        error: "Payment verification mismatch.",
        code: "PAYMENT_VERIFICATION_MISMATCH"
      },
      { status: 409 }
    );
  }

  const eventType = callbackEventType(payment.status);

  if (eventType) {
    const eventId =
      `callback:${payment.id}:${payment.updated_at ?? payment.created_at ?? payment.status}:${payment.status}`;

    const applied = await applyMoyasarPaymentWebhook(
      {
        eventId,
        eventType,
        paymentId: payment.id,
        amount: payment.amount,
        currency: payment.currency,
        live: remote.live,
        occurredAt: payment.updated_at ?? payment.created_at ?? null
      },
      remote.rawBody
    );

    if (!applied.ok) {
      return Response.json(
        {
          error: "Verified payment could not be reconciled.",
          code: applied.code
        },
        { status: applied.code === "WEBHOOK_REPLAY_MISMATCH" ? 409 : 503 }
      );
    }
  }

  return Response.json({
    verified: true,
    paymentId: payment.id,
    status: payment.status,
    paid: ["paid", "captured"].includes(payment.status),
    localStatus: localPayment.status
  });
}
