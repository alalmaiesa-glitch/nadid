export const PROTECTED_ROUTE_PREFIXES = [
  "/documents",
  "/upload",
  "/editor"
] as const;

export function isProtectedRoute(pathname: string) {
  return PROTECTED_ROUTE_PREFIXES.some(
    (prefix) =>
      pathname === prefix ||
      pathname.startsWith(prefix + "/")
  );
}

const ENCODED_SEPARATOR_OR_CONTROL =
  /%(?:0[0-9a-f]|1[0-9a-f]|2f|5c|7f)/i;

export function safeInternalNext(
  value: string | null | undefined,
  fallback = "/documents"
) {
  if (!value) return fallback;

  if (
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.startsWith("/\\") ||
    value.includes("\\") ||
    /[\u0000-\u001F\u007F]/.test(value) ||
    ENCODED_SEPARATOR_OR_CONTROL.test(value)
  ) {
    return fallback;
  }

  return value;
}
