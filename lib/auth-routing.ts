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
    /[\u0000-\u001F\u007F]/.test(value)
  ) {
    return fallback;
  }

  return value;
}
