export type BoundedJsonResult<T> =
  | { ok: true; value: T }
  | { ok: false; response: Response };

function payloadTooLarge(maxBytes: number) {
  return Response.json(
    {
      error: "Request payload is too large.",
      code: "REQUEST_BODY_TOO_LARGE",
      maxBytes
    },
    { status: 413 }
  );
}

export function enforceDeclaredContentLength(
  request: Request,
  maxBytes: number
): Response | null {
  const raw = request.headers.get("content-length");
  if (!raw) return null;

  const length = Number(raw);

  if (!Number.isFinite(length) || length < 0) {
    return Response.json(
      {
        error: "Invalid Content-Length header.",
        code: "INVALID_CONTENT_LENGTH"
      },
      { status: 400 }
    );
  }

  if (length > maxBytes) {
    return payloadTooLarge(maxBytes);
  }

  return null;
}

export async function readBoundedJson<T>(
  request: Request,
  maxBytes: number
): Promise<BoundedJsonResult<T>> {
  const declared = enforceDeclaredContentLength(
    request,
    maxBytes
  );
  if (declared) {
    return { ok: false, response: declared };
  }

  const contentType = (
    request.headers.get("content-type") ?? ""
  ).toLowerCase();

  if (
    !contentType.startsWith("application/json") &&
    !contentType.includes("+json")
  ) {
    return {
      ok: false,
      response: Response.json(
        {
          error: "JSON request body required.",
          code: "JSON_CONTENT_TYPE_REQUIRED"
        },
        { status: 415 }
      )
    };
  }

  if (!request.body) {
    return {
      ok: false,
      response: Response.json(
        {
          error: "JSON request body required.",
          code: "JSON_BODY_REQUIRED"
        },
        { status: 400 }
      )
    };
  }

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;

      total += value.byteLength;

      if (total > maxBytes) {
        await reader.cancel();
        return {
          ok: false,
          response: payloadTooLarge(maxBytes)
        };
      }

      chunks.push(value);
    }
  } catch {
    return {
      ok: false,
      response: Response.json(
        {
          error: "Could not read request body.",
          code: "REQUEST_BODY_READ_FAILED"
        },
        { status: 400 }
      )
    };
  }

  const payload = new Uint8Array(total);
  let offset = 0;

  for (const chunk of chunks) {
    payload.set(chunk, offset);
    offset += chunk.byteLength;
  }

  try {
    const text = new TextDecoder().decode(payload);
    return {
      ok: true,
      value: JSON.parse(text) as T
    };
  } catch {
    return {
      ok: false,
      response: Response.json(
        {
          error: "Invalid JSON request body.",
          code: "INVALID_JSON"
        },
        { status: 400 }
      )
    };
  }
}
