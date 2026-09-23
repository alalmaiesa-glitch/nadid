import { authorizeUser } from "@/lib/server/authz";
import { createPendingDocumentUpload } from "@/lib/server/document-persistence";

export async function POST(request: Request) {
  const auth = await authorizeUser();
  if (!auth.ok) return auth.response;

  if (!auth.userId) {
    return Response.json(
      { error: "Persistent upload is not configured." },
      { status: 409 }
    );
  }

  const body = (await request.json()) as {
    filename?: string;
    size?: number;
  };

  const filename = body.filename?.trim() ?? "";
  const size = Number(body.size ?? 0);

  if (!filename.toLowerCase().endsWith(".docx")) {
    return Response.json(
      { error: "DOCX files only." },
      { status: 415 }
    );
  }

  if (!Number.isFinite(size) || size <= 0) {
    return Response.json(
      { error: "Invalid file size." },
      { status: 400 }
    );
  }

  if (size > 100 * 1024 * 1024) {
    return Response.json(
      { error: "File exceeds the 100 MB operational limit." },
      { status: 413 }
    );
  }

  try {
    const upload = await createPendingDocumentUpload(
      auth.userId,
      filename
    );

    return Response.json(upload, { status: 201 });
  } catch {
    return Response.json(
      { error: "Could not create upload." },
      { status: 500 }
    );
  }
}
