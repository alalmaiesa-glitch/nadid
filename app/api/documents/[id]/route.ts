import { loadAnalyzedDocument } from "@/lib/server/document-persistence";
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
