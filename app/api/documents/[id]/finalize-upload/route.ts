import { authorizeDocument } from "@/lib/server/authz";
import { enqueueDocumentProcessing } from "@/lib/server/document-persistence";

export async function POST(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const auth = await authorizeDocument(id);
  if (!auth.ok) return auth.response;

  if (!auth.userId) {
    return Response.json(
      { error: "Persistent storage is not configured." },
      { status: 409 }
    );
  }

  try {
    const job = await enqueueDocumentProcessing(id, auth.userId);

    return Response.json(
      job,
      { status: job.status === "ready" ? 200 : 202 }
    );
  } catch (error) {
    const code =
      error instanceof Error ? error.message : "enqueue_failed";

    if (code === "uploaded_file_missing") {
      return Response.json(
        { error: "Uploaded file was not found." },
        { status: 404 }
      );
    }

    if (code === "upload_integrity_mismatch") {
      return Response.json(
        {
          error:
            "The uploaded source changed after finalization. Upload a new document.",
          code: "UPLOAD_INTEGRITY_MISMATCH"
        },
        { status: 409 }
      );
    }

    if (code === "document_not_finalizable") {
      return Response.json(
        {
          error: "Document cannot be finalized in its current state.",
          code: "DOCUMENT_NOT_FINALIZABLE"
        },
        { status: 409 }
      );
    }

    return Response.json(
      {
        error: "Could not queue uploaded document.",
        code
      },
      { status: 500 }
    );
  }
}
