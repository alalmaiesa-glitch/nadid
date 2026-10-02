export type MoyasarMode = "test" | "live";

function keyMode(
  value: string | undefined,
  kind: "pk" | "sk"
): MoyasarMode | null {
  if (!value) return null;
  if (value.startsWith(`${kind}_test_`)) return "test";
  if (value.startsWith(`${kind}_live_`)) return "live";
  return null;
}

export function resolveMoyasarEnvironment():
  | {
      ok: true;
      mode: MoyasarMode;
      publishableKey: string;
      secretKey: string;
    }
  | { ok: false; code: string } {
  const publishableKey =
    process.env.NEXT_PUBLIC_MOYASAR_PUBLISHABLE_KEY;
  const secretKey = process.env.MOYASAR_SECRET_KEY;

  if (!publishableKey || !secretKey) {
    return {
      ok: false,
      code: "PAYMENT_PROVIDER_NOT_CONFIGURED"
    };
  }

  const publicMode = keyMode(publishableKey, "pk");
  const secretMode = keyMode(secretKey, "sk");

  if (!publicMode || !secretMode) {
    return {
      ok: false,
      code: "PAYMENT_PROVIDER_KEY_FORMAT_INVALID"
    };
  }

  if (publicMode !== secretMode) {
    return {
      ok: false,
      code: "PAYMENT_PROVIDER_MODE_MISMATCH"
    };
  }

  return {
    ok: true,
    mode: publicMode,
    publishableKey,
    secretKey
  };
}
