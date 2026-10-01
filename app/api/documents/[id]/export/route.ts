import { downloadDocumentVersion } from "@/lib/server/document-persistence";
import { authorizeDocument } from "@/lib/server/authz";

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const auth = await authorizeDocument(id);
  if (!auth.ok) return auth.response;

  const url = new URL(request.url);
  const requested = url.searchParams.get("version");
  const versionNo = requested ? Number(requested) : undefined;

  if (
    requested &&
    (!Number.isInteger(versionNo) || Number(versionNo) < 1)
  ) {
    return Response.json(
      { error: "Invalid document version." },
      { status: 400 }
    );
  }

  let result;

  try {
    result = await downloadDocumentVersion(id, versionNo);
  } catch (error) {
    if (
      error instanceof Error &&
      error.message === "source_integrity_mismatch"
    ) {
      return Response.json(
        {
          error:
            "Stored source integrity check failed. Export was blocked.",
          code: "SOURCE_INTEGRITY_MISMATCH"
        },
        { status: 409 }
      );
    }

    throw error;
  }

  if (!result) {
    return Response.json(
      { error: "Requested version was not found." },
      { status: 404 }
    );
  }

  const baseName = result.filename.replace(/\.docx$/i, "");
  const outputName =
    `${baseName}-nadid-v${result.versionNo}.docx`;

  return new Response(new Uint8Array(result.buffer), {
    headers: {
      "Content-Type":
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "Content-Disposition":
        `attachment; filename*=UTF-8''${encodeURIComponent(outputName)}`,
      "Content-Length": String(result.buffer.length)
    }
  });
}
