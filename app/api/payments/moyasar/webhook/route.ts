import {
  applyMoyasarPaymentWebhook,
  parseMoyasarPaymentWebhook,
  validateMoyasarWebhookSecret,
  type MoyasarWebhookPayload
} from "@/lib/server/moyasar-webhook";

export const runtime = "nodejs";

const MAX_WEBHOOK_BYTES = 256 * 1024;

export async function POST(request: Request) {
  const declared = Number(request.headers.get("content-length") || "0");
  if (declared > MAX_WEBHOOK_BYTES) {
    return Response.json(
      { error: "Webhook payload too large.", code: "WEBHOOK_TOO_LARGE" },
      { status: 413 }
    );
  }

  const rawBody = await request.text();
  if (Buffer.byteLength(rawBody, "utf8") > MAX_WEBHOOK_BYTES) {
    return Response.json(
      { error: "Webhook payload too large.", code: "WEBHOOK_TOO_LARGE" },
      { status: 413 }
    );
  }

  let payload: MoyasarWebhookPayload;
  try {
    payload = JSON.parse(rawBody) as MoyasarWebhookPayload;
  } catch {
    return Response.json(
      { error: "Invalid webhook JSON.", code: "INVALID_WEBHOOK_JSON" },
      { status: 400 }
    );
  }

  if (
    !validateMoyasarWebhookSecret(
      payload.secret_token,
      process.env.MOYASAR_WEBHOOK_SECRET
    )
  ) {
    return Response.json(
      { error: "Unauthorized webhook.", code: "INVALID_WEBHOOK_SECRET" },
      { status: 401 }
    );
  }

  const parsed = parseMoyasarPaymentWebhook(payload);
  if (!parsed) {
    return Response.json(
      { error: "Invalid webhook payload.", code: "INVALID_WEBHOOK_PAYLOAD" },
      { status: 400 }
    );
  }

  const applied = await applyMoyasarPaymentWebhook(parsed, rawBody);
  if (!applied.ok) {
    const status =
      applied.code === "WEBHOOK_REPLAY_MISMATCH"
        ? 409
        : applied.code === "PAYMENT_SERVICE_UNAVAILABLE"
          ? 503
          : 500;
    return Response.json(
      { error: "Webhook processing failed.", code: applied.code },
      { status }
    );
  }

  // Moyasar retries non-2xx deliveries. Returning 200 for unmatched or ignored
  // events prevents retry storms while the event remains auditable internally.
  return Response.json({
    received: true,
    reused: applied.result.reused,
    outcome: applied.result.outcome
  });
}
