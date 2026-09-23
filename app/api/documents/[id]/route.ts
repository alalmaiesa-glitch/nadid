import { loadAnalyzedDocument } from "@/lib/server/document-persistence";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const document = await loadAnalyzedDocument(id);

  if (!document) {
    return Response.json(
      { error: "المستند غير موجود في التخزين الدائم." },
      { status: 404 }
    );
  }

  return Response.json(document);
}
