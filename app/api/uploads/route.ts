import { isSupabaseAdminConfigured } from "@/lib/supabase-admin";
import { authorizeUser } from "@/lib/server/authz";
import { createPendingDocumentUpload } from "@/lib/server/document-persistence";

export async function POST(request: Request) {
  if (
    process.env.NODE_ENV === "production" &&
    !isSupabaseAdminConfigured()
  ) {
    return Response.json(
      { error: "Document storage is not configured." },
      { status: 503 }
    );
  }

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

  const configuredMaxMb = Number(
    process.env.NADID_MAX_FILE_MB ?? 100
  );
  const maxFileMb = Math.min(
    100,
    Math.max(1, Number.isFinite(configuredMaxMb) ? configuredMaxMb : 100)
  );

  if (size > maxFileMb * 1024 * 1024) {
    return Response.json(
      {
        error:
          `File exceeds the ${maxFileMb} MB operational limit.`
      },
      { status: 413 }
    );
  }

  try {
    const upload = await createPendingDocumentUpload(
      auth.userId,
      filename
    );

    return Response.json(upload, { status: 201 });
  } catch (error) {
    const code =
      error instanceof Error ? error.message : "upload_create_failed";

    if (code === "upload_daily_limit") {
      return Response.json(
        { error: "Daily upload limit reached." },
        { status: 429 }
      );
    }

    if (code === "upload_active_limit") {
      return Response.json(
        {
          error:
            "Too many active uploads. Wait for current uploads to finish."
        },
        { status: 429 }
      );
    }

    return Response.json(
      { error: "Could not create upload." },
      { status: 500 }
    );
  }
}
