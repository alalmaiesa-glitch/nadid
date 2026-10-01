const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function normalizedOrigin(value: string | null | undefined) {
  if (!value) return null;

  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
}

function expectedApplicationOrigin(request: Request) {
  const configured = normalizedOrigin(
    process.env.NEXT_PUBLIC_APP_URL
  );

  if (configured) return configured;

  if (process.env.NODE_ENV === "production") {
    return null;
  }

  return normalizedOrigin(request.url);
}

export function enforceSameOriginMutation(
  request: Request
): Response | null {
  if (SAFE_METHODS.has(request.method.toUpperCase())) {
    return null;
  }

  const fetchSite = (
    request.headers.get("sec-fetch-site") ?? ""
  ).toLowerCase();

  if (fetchSite === "cross-site") {
    return Response.json(
      {
        error: "Cross-site mutation requests are not allowed.",
        code: "CROSS_SITE_REQUEST_BLOCKED"
      },
      { status: 403 }
    );
  }

  const expectedOrigin = expectedApplicationOrigin(request);

  if (!expectedOrigin) {
    return Response.json(
      {
        error: "Application origin is not configured.",
        code: "APP_ORIGIN_NOT_CONFIGURED"
      },
      { status: 503 }
    );
  }

  const suppliedOrigin = normalizedOrigin(
    request.headers.get("origin")
  );

  if (!suppliedOrigin) {
    if (process.env.NODE_ENV === "production") {
      return Response.json(
        {
          error: "Mutation request origin is required.",
          code: "REQUEST_ORIGIN_REQUIRED"
        },
        { status: 403 }
      );
    }

    return null;
  }

  if (suppliedOrigin !== expectedOrigin) {
    return Response.json(
      {
        error: "Mutation request origin does not match the application.",
        code: "REQUEST_ORIGIN_MISMATCH"
      },
      { status: 403 }
    );
  }

  return null;
}
