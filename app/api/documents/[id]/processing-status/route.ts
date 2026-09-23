import { authorizeDocument } from "@/lib/server/authz";
import { getDocumentProcessingStatus } from "@/lib/server/document-persistence";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const auth = await authorizeDocument(id);
  if (!auth.ok) return auth.response;

  const status = await getDocumentProcessingStatus(id);

  if (!status) {
    return Response.json(
      { error: "Document status was not found." },
      { status: 404 }
    );
  }

  return Response.json(status);
}
