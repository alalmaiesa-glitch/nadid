import {
  assertDocumentOwner,
  assertSuggestionOwner
} from "@/lib/server/document-persistence";
import {
  getCurrentUser,
  isSupabaseConfigured
} from "@/lib/supabase-server";

type Authorized = {
  ok: true;
  userId: string | null;
};

type Unauthorized = {
  ok: false;
  response: Response;
};

export async function authorizeUser(): Promise<
  Authorized | Unauthorized
> {
  if (!isSupabaseConfigured()) {
    return { ok: true, userId: null };
  }

  const user = await getCurrentUser();

  if (!user) {
    return {
      ok: false,
      response: Response.json(
        { error: "Authentication required." },
        { status: 401 }
      )
    };
  }

  return { ok: true, userId: user.id };
}

export async function authorizeDocument(
  documentId: string
): Promise<Authorized | Unauthorized> {
  const auth = await authorizeUser();
  if (!auth.ok) return auth;

  if (!auth.userId) return auth;

  const allowed = await assertDocumentOwner(
    documentId,
    auth.userId
  );

  if (!allowed) {
    return {
      ok: false,
      response: Response.json(
        { error: "Document not found." },
        { status: 404 }
      )
    };
  }

  return auth;
}

export async function authorizeSuggestion(
  suggestionId: string
): Promise<Authorized | Unauthorized> {
  const auth = await authorizeUser();
  if (!auth.ok) return auth;

  if (!auth.userId) return auth;

  const allowed = await assertSuggestionOwner(
    suggestionId,
    auth.userId
  );

  if (!allowed) {
    return {
      ok: false,
      response: Response.json(
        { error: "Suggestion not found." },
        { status: 404 }
      )
    };
  }

  return auth;
}
