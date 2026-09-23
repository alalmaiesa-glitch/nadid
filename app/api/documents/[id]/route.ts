import {
  deleteDocumentFully,
  loadAnalyzedDocument
} from "@/lib/server/document-persistence";
import { authorizeDocument } from "@/lib/server/authz";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const auth = await authorizeDocument(id);
  if (!auth.ok) return auth.response;

  const document = await loadAnalyzedDocument(id);

  if (!document) {
    return Response.json(
      { error: "المستند غير موجود في التخزين الدائم." },
      { status: 404 }
    );
  }

  return Response.json(document);
}


export async function DELETE(
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
    const result = await deleteDocumentFully(id, auth.userId);

    if (!result.deleted) {
      return Response.json(
        { error: "Document not found." },
        { status: 404 }
      );
    }

    return Response.json(result);
  } catch {
    return Response.json(
      { error: "Could not delete document completely." },
      { status: 500 }
    );
  }
}
