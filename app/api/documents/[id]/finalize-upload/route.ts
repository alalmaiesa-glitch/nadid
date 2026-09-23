import { authorizeDocument } from "@/lib/server/authz";
import {
  finalizePendingDocument,
  loadAnalyzedDocument,
  loadPendingDocumentUpload
} from "@/lib/server/document-persistence";
import {
  analyzeDocxWithAee,
  isAeeBackendConfigured
} from "@/lib/server/aee-client";

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

  const pending = await loadPendingDocumentUpload(
    id,
    auth.userId
  );

  if (!pending) {
    return Response.json(
      { error: "Uploaded file was not found." },
      { status: 404 }
    );
  }

  if (pending.status === "finalized") {
    const existing = await loadAnalyzedDocument(id);

    if (!existing) {
      return Response.json(
        { error: "Finalized document could not be loaded." },
        { status: 500 }
      );
    }

    return Response.json(existing);
  }

  if (!isAeeBackendConfigured()) {
    return Response.json(
      {
        error: "AEE backend is not configured.",
        code: "AEE_UNAVAILABLE"
      },
      { status: 409 }
    );
  }

  try {
    const analysis = await analyzeDocxWithAee(
      pending.filename,
      pending.buffer
    );

    const normalized = {
      ...analysis,
      document: {
        ...analysis.document,
        id
      }
    };

    await finalizePendingDocument(
      id,
      auth.userId,
      pending.storagePath,
      pending.buffer,
      normalized
    );

    return Response.json(normalized);
  } catch (error) {
    return Response.json(
      {
        error: "Could not finalize uploaded document.",
        detail:
          error instanceof Error
            ? error.message
            : "finalize_failed"
      },
      { status: 502 }
    );
  }
}
