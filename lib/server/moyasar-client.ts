import { createHash } from "node:crypto";

export type MoyasarFetchedPayment = {
  id: string;
  status: string;
  amount: number;
  currency: string;
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, unknown>;
};

export async function fetchMoyasarPayment(
  paymentId: string
): Promise<
  | { ok: true; payment: MoyasarFetchedPayment; rawBody: string; live: boolean }
  | { ok: false; code: string; status: number }
> {
  const secret = process.env.MOYASAR_SECRET_KEY;
  if (!secret) {
    return {
      ok: false,
      code: "MOYASAR_SECRET_NOT_CONFIGURED",
      status: 503
    };
  }

  const auth = Buffer.from(`${secret}:`).toString("base64");

  let response: Response;
  try {
    response = await fetch(
      `https://api.moyasar.com/v1/payments/${encodeURIComponent(paymentId)}`,
      {
        method: "GET",
        headers: {
          Authorization: `Basic ${auth}`,
          Accept: "application/json"
        },
        cache: "no-store"
      }
    );
  } catch {
    return {
      ok: false,
      code: "MOYASAR_FETCH_FAILED",
      status: 503
    };
  }

  const rawBody = await response.text();

  if (!response.ok) {
    return {
      ok: false,
      code:
        response.status === 404
          ? "MOYASAR_PAYMENT_NOT_FOUND"
          : "MOYASAR_FETCH_FAILED",
      status: response.status === 404 ? 404 : 503
    };
  }

  let value: unknown;
  try {
    value = JSON.parse(rawBody);
  } catch {
    return {
      ok: false,
      code: "MOYASAR_INVALID_RESPONSE",
      status: 502
    };
  }

  if (!value || typeof value !== "object") {
    return {
      ok: false,
      code: "MOYASAR_INVALID_RESPONSE",
      status: 502
    };
  }

  const item = value as Record<string, unknown>;
  const id = typeof item.id === "string" ? item.id : "";
  const status = typeof item.status === "string" ? item.status : "";
  const amount = Number(item.amount);
  const currency =
    typeof item.currency === "string"
      ? item.currency.toUpperCase()
      : "";

  if (
    id !== paymentId ||
    !status ||
    !Number.isSafeInteger(amount) ||
    amount < 0 ||
    !currency
  ) {
    return {
      ok: false,
      code: "MOYASAR_INVALID_RESPONSE",
      status: 502
    };
  }

  return {
    ok: true,
    payment: {
      id,
      status,
      amount,
      currency,
      created_at:
        typeof item.created_at === "string"
          ? item.created_at
          : undefined,
      updated_at:
        typeof item.updated_at === "string"
          ? item.updated_at
          : undefined,
      metadata:
        item.metadata && typeof item.metadata === "object"
          ? (item.metadata as Record<string, unknown>)
          : undefined
    },
    rawBody,
    live: secret.startsWith("sk_live_")
  };
}

export function callbackEventType(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "paid") return "payment_paid";
  if (normalized === "captured") return "payment_captured";
  if (normalized === "refunded") return "payment_refunded";
  if (normalized === "voided") return "payment_voided";
  if (normalized === "authorized") return "payment_authorized";
  if (normalized === "verified") return "payment_verified";
  if (
    normalized === "failed" ||
    normalized === "expired"
  ) {
    return "payment_failed";
  }
  return null;
}

export function callbackDigest(rawBody: string) {
  return createHash("sha256").update(rawBody).digest("hex");
}
