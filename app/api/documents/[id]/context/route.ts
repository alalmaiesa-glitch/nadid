import { searchStoredContext } from "@/lib/server/document-persistence";
import { authorizeDocument } from "@/lib/server/authz";

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const auth = await authorizeDocument(id);
  if (!auth.ok) return auth.response;

  const url = new URL(request.url);
  const query = url.searchParams.get("q")?.trim() ?? "";
  const limit = Number(url.searchParams.get("limit") ?? "5");

  if (!query) {
    return Response.json(
      { error: "Missing context query." },
      { status: 400 }
    );
  }

  try {
    const hits = await searchStoredContext(
      id,
      query,
      Number.isFinite(limit) ? limit : 5
    );

    return Response.json({ hits });
  } catch {
    return Response.json(
      { error: "Could not search stored context." },
      { status: 500 }
    );
  }
}
