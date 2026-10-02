import { createHash } from "node:crypto";
import { resolveMoyasarEnvironment } from "@/lib/server/moyasar-environment";

export type MoyasarFetchedPayment = {
  id: string;
  status: string;
  amount: number;
  currency: string;
  captured: number;
  refunded: number;
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, unknown>;
};

const RETRYABLE_MOYASAR_STATUSES = new Set([
  408,
  425,
  429,
  500,
  502,
  503,
  504
]);

function boundedInteger(
  raw: string | undefined,
  fallback: number,
  minimum: number,
  maximum: number
) {
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed)) return fallback;
  return Math.min(Math.max(parsed, minimum), maximum);
}

export function moyasarFetchTimeoutMs() {
  return boundedInteger(
    process.env.NADID_MOYASAR_FETCH_TIMEOUT_MS,
    8000,
    1000,
    30000
  );
}

export function moyasarFetchMaxAttempts() {
  return boundedInteger(
    process.env.NADID_MOYASAR_FETCH_MAX_ATTEMPTS,
    3,
    1,
    5
  );
}

function retryDelayMs(attempt: number, response?: Response) {
  const retryAfter = response?.headers.get("retry-after");
  if (retryAfter && /^\d+$/.test(retryAfter)) {
    return Math.min(Number(retryAfter) * 1000, 2000);
  }

  return Math.min(150 * 2 ** Math.max(attempt - 1, 0), 1000);
}

async function sleep(ms: number) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

function providerFailureCode(status: number | null, timedOut: boolean) {
  if (timedOut) return "MOYASAR_FETCH_TIMEOUT";
  if (status === 429) return "MOYASAR_RATE_LIMITED";
  if (status === 404) return "MOYASAR_PAYMENT_NOT_FOUND";
  return "MOYASAR_FETCH_FAILED";
}

export async function fetchMoyasarPayment(
  paymentId: string
): Promise<
  | { ok: true; payment: MoyasarFetchedPayment; rawBody: string; live: boolean }
  | { ok: false; code: string; status: number }
> {
  const environment = resolveMoyasarEnvironment();
  if (!environment.ok) {
    return {
      ok: false,
      code: environment.code,
      status: 503
    };
  }

  const auth = Buffer.from(`${environment.secretKey}:`).toString("base64");
  const maxAttempts = moyasarFetchMaxAttempts();
  const timeoutMs = moyasarFetchTimeoutMs();
  let response: Response | null = null;
  let timedOut = false;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
      response = await fetch(
        `https://api.moyasar.com/v1/payments/${encodeURIComponent(paymentId)}`,
        {
          method: "GET",
          headers: {
            Authorization: `Basic ${auth}`,
            Accept: "application/json"
          },
          cache: "no-store",
          signal: controller.signal
        }
      );
      timedOut = false;
    } catch (error) {
      timedOut =
        error instanceof Error &&
        (error.name === "AbortError" || controller.signal.aborted);
      response = null;
    } finally {
      clearTimeout(timeout);
    }

    const retryable =
      response === null ||
      RETRYABLE_MOYASAR_STATUSES.has(response.status);

    if (retryable && attempt < maxAttempts) {
      await sleep(retryDelayMs(attempt, response ?? undefined));
      continue;
    }

    break;
  }

  if (!response) {
    return {
      ok: false,
      code: providerFailureCode(null, timedOut),
      status: 503
    };
  }

  if (!response.ok) {
    return {
      ok: false,
      code: providerFailureCode(response.status, false),
      status: response.status === 404 ? 404 : 503
    };
  }

  const rawBody = await response.text();

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
  const captured = Number(item.captured);
  const refunded = Number(item.refunded);
  const currency =
    typeof item.currency === "string"
      ? item.currency.toUpperCase()
      : "";

  if (
    id !== paymentId ||
    !status ||
    !Number.isSafeInteger(amount) ||
    amount < 0 ||
    !Number.isSafeInteger(captured) ||
    captured < 0 ||
    captured > amount ||
    !Number.isSafeInteger(refunded) ||
    refunded < 0 ||
    refunded > amount ||
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
      captured,
      refunded,
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
    live: environment.mode === "live"
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
