import { downloadDocumentVersion } from "@/lib/server/document-persistence";

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const url = new URL(request.url);
  const requested = url.searchParams.get("version");
  const versionNo = requested ? Number(requested) : undefined;

  if (requested && !Number.isInteger(versionNo)) {
    return Response.json(
      { error: "Invalid document version." },
      { status: 400 }
    );
  }

  const result = await downloadDocumentVersion(id, versionNo);

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
