import { authorizeUser } from "@/lib/server/authz";
import { listUserDocuments } from "@/lib/server/document-persistence";

export async function GET() {
  const auth = await authorizeUser();
  if (!auth.ok) return auth.response;

  if (!auth.userId) {
    return Response.json({ documents: [], mode: "local" });
  }

  try {
    const documents = await listUserDocuments(auth.userId);
    return Response.json({ documents, mode: "persistent" });
  } catch {
    return Response.json(
      { error: "Could not load documents." },
      { status: 500 }
    );
  }
}
