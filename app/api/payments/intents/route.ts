import { authorizeUser } from "@/lib/server/authz";
import {
  API_RATE_LIMITS,
  enforceUserRateLimit
} from "@/lib/server/rate-limit";
import { enforceSameOriginMutation } from "@/lib/server/request-integrity";
import { getSupabaseAdmin } from "@/lib/supabase-admin";
import { resolveMoyasarEnvironment } from "@/lib/server/moyasar-environment";

export const runtime = "nodejs";

const MAX_INTENT_BODY_BYTES = 8 * 1024;
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type IntentBody = {
  productKind?: unknown;
  productId?: unknown;
};

export async function POST(request: Request) {
  const integrity = enforceSameOriginMutation(request);
  if (integrity) return integrity;

  const auth = await authorizeUser();
  if (!auth.ok) return auth.response;
  if (!auth.userId) {
    return Response.json(
      {
        error: "Billing identity is unavailable.",
        code: "BILLING_IDENTITY_UNAVAILABLE"
      },
      { status: 503 }
    );
  }

  const rateLimit = await enforceUserRateLimit(
    auth.userId,
    API_RATE_LIMITS.paymentIntent
  );
  if (rateLimit) return rateLimit;

  const declared = Number(request.headers.get("content-length") || "0");
  if (declared > MAX_INTENT_BODY_BYTES) {
    return Response.json(
      { error: "Payment intent request is too large.", code: "REQUEST_TOO_LARGE" },
      { status: 413 }
    );
  }

  const idempotencyKey = (
    request.headers.get("idempotency-key") ?? ""
  ).trim();

  if (!UUID_RE.test(idempotencyKey)) {
    return Response.json(
      {
        error: "A UUID Idempotency-Key is required.",
        code: "IDEMPOTENCY_KEY_REQUIRED"
      },
      { status: 400 }
    );
  }

  let body: IntentBody;
  try {
    const raw = await request.text();
    if (Buffer.byteLength(raw, "utf8") > MAX_INTENT_BODY_BYTES) {
      return Response.json(
        { error: "Payment intent request is too large.", code: "REQUEST_TOO_LARGE" },
        { status: 413 }
      );
    }
    body = JSON.parse(raw) as IntentBody;
  } catch {
    return Response.json(
      { error: "Invalid payment intent JSON.", code: "INVALID_REQUEST" },
      { status: 400 }
    );
  }

  const productKind =
    typeof body.productKind === "string" ? body.productKind.trim() : "";
  const productId =
    typeof body.productId === "string" ? body.productId.trim() : "";

  if (
    !["subscription", "credit_topup"].includes(productKind) ||
    !/^[a-z0-9_-]{2,80}$/i.test(productId)
  ) {
    return Response.json(
      { error: "Invalid payment product.", code: "INVALID_PAYMENT_PRODUCT" },
      { status: 400 }
    );
  }

  const providerEnvironment = resolveMoyasarEnvironment();
  if (!providerEnvironment.ok) {
    return Response.json(
      {
        error: "Payment provider configuration is unsafe.",
        code: providerEnvironment.code
      },
      { status: 503 }
    );
  }

  const supabase = getSupabaseAdmin() as any;
  if (!supabase) {
    return Response.json(
      { error: "Payment service is unavailable.", code: "PAYMENT_SERVICE_UNAVAILABLE" },
      { status: 503 }
    );
  }

  const { data, error } = await supabase.rpc(
    "create_payment_intent",
    {
      p_user_id: auth.userId,
      p_product_kind: productKind,
      p_product_id: productId,
      p_request_id: idempotencyKey,
      p_provider_mode: providerEnvironment.mode
    }
  );

  if (error || !data?.[0]) {
    const message = error?.message ?? "";
    const code =
      message.includes("payment_intent_idempotency_mismatch")
        ? "IDEMPOTENCY_MISMATCH"
        : message.includes("paid_plan_not_found") ||
            message.includes("credit_pack_not_found")
          ? "PAYMENT_PRODUCT_NOT_FOUND"
          : "PAYMENT_INTENT_FAILED";

    return Response.json(
      { error: "Could not create payment intent.", code },
      { status: code === "PAYMENT_PRODUCT_NOT_FOUND" ? 404 : code === "IDEMPOTENCY_MISMATCH" ? 409 : 503 }
    );
  }

  const intent = data[0];
  const appUrl = process.env.NEXT_PUBLIC_APP_URL;

  if (!appUrl) {
    return Response.json(
      {
        error: "Payment provider is not configured.",
        code: "PAYMENT_PROVIDER_NOT_CONFIGURED"
      },
      { status: 503 }
    );
  }

  const callbackUrl = new URL(
    "/api/payments/moyasar/callback",
    appUrl
  ).toString();

  return Response.json({
    paymentId: intent.payment_id,
    reused: intent.reused,
    provider: "moyasar",
    givenId: intent.payment_id,
    amount: Number(intent.amount_minor),
    currency: intent.currency,
    purpose: intent.purpose,
    metadata: intent.payment_metadata,
    callbackUrl,
    publishableKey: providerEnvironment.publishableKey,
    providerMode: providerEnvironment.mode
  });
}
