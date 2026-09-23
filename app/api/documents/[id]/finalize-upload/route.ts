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

    return Response.json(
      {
        error: "Could not queue uploaded document.",
        code
      },
      { status: 500 }
    );
  }
}
