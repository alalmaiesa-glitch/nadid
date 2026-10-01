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

const ENCODED_PATH_SEPARATOR = /%(?:2f|5c)/i;
const ENCODED_CONTROL = /%(?:0[0-9a-f]|1[0-9a-f]|7f)/i;

export function safeInternalNext(
  value: string | null | undefined,
  fallback = "/documents"
) {
  if (!value) return fallback;

  const pathEnd = value.search(/[?#]/);
  const pathPart = pathEnd < 0 ? value : value.slice(0, pathEnd);

  if (
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.startsWith("/\\") ||
    value.includes("\\") ||
    /[\u0000-\u001F\u007F]/.test(value) ||
    ENCODED_PATH_SEPARATOR.test(pathPart) ||
    ENCODED_CONTROL.test(value)
  ) {
    return fallback;
  }

  return value;
}
