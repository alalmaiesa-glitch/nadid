import { authorizeUser } from "@/lib/server/authz";
import {
  deleteDocumentFully,
  listUserDocuments
} from "@/lib/server/document-persistence";
import { getSupabaseAdmin } from "@/lib/supabase-admin";

export async function DELETE() {
  const auth = await authorizeUser();
  if (!auth.ok) return auth.response;

  if (!auth.userId) {
    return Response.json(
      { error: "Persistent account storage is not configured." },
      { status: 409 }
    );
  }

  const supabase = getSupabaseAdmin();

  if (!supabase) {
    return Response.json(
      { error: "Account service is not configured." },
      { status: 503 }
    );
  }

  try {
    const documents = await listUserDocuments(auth.userId);

    for (const document of documents) {
      const result = await deleteDocumentFully(
        document.id,
        auth.userId
      );

      if (!result.deleted) {
        throw new Error("document_delete_incomplete");
      }
    }

    const { error: userError } =
      await supabase.auth.admin.deleteUser(auth.userId);

    if (userError) throw userError;

    return Response.json({
      deleted: true,
      removedDocuments: documents.length
    });
  } catch {
    return Response.json(
      {
        error:
          "Could not delete the account and all associated data."
      },
      { status: 500 }
    );
  }
}
