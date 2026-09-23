import {
  createDocumentVersion,
  listDocumentVersions,
  loadAcceptedPatches,
  loadDocumentSource
} from "@/lib/server/document-persistence";
import {
  analyzeDocxWithAee,
  applyDocxPatchesWithAee,
  isAeeBackendConfigured
} from "@/lib/server/aee-client";

export async function POST(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;

  if (!isAeeBackendConfigured()) {
    return Response.json(
      { error: "AEE export backend is not configured." },
      { status: 409 }
    );
  }

  const [source, accepted] = await Promise.all([
    loadDocumentSource(id),
    loadAcceptedPatches(id)
  ]);

  if (!source || !accepted) {
    return Response.json(
      { error: "Current document version was not found." },
      { status: 404 }
    );
  }

  if (source.versionId !== accepted.versionId) {
    return Response.json(
      {
        error: "The current version changed during export preparation.",
        code: "VERSION_CHANGED"
      },
      { status: 409 }
    );
  }

  if (accepted.patches.length === 0) {
    return Response.json(
      {
        error: "No accepted patches are available.",
        code: "NO_ACCEPTED_PATCHES"
      },
      { status: 409 }
    );
  }

  try {
    const patched = await applyDocxPatchesWithAee(
      source.filename,
      source.buffer,
      accepted.patches.map((patch) => ({
        nodeId: patch.nodeId,
        original: patch.original,
        replacement: patch.replacement
      }))
    );

    const analysis = await analyzeDocxWithAee(
      source.filename,
      patched
    );

    const created = await createDocumentVersion(
      id,
      source.versionId,
      source.versionNo,
      patched,
      {
        ...analysis,
        document: {
          ...analysis.document,
          id
        }
      },
      accepted.patches.map((patch) => patch.suggestionId)
    );

    if (!created.persisted) {
      return Response.json(
        { error: "Persistent storage is not configured." },
        { status: 409 }
      );
    }

    return Response.json({
      versionId: created.versionId,
      versionNo: created.versionNo,
      appliedCount: accepted.patches.length,
      downloadUrl:
        `/api/documents/${id}/export?version=${created.versionNo}`
    });
  } catch (error) {
    return Response.json(
      {
        error: "Could not create a new version.",
        detail:
          error instanceof Error
            ? error.message
            : "version_creation_failed"
      },
      { status: 502 }
    );
  }
}


export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;

  try {
    const versions = await listDocumentVersions(id);

    return Response.json({
      versions: versions.map((version) => ({
        ...version,
        downloadUrl:
          version.status === "ready"
            ? `/api/documents/${id}/export?version=${version.versionNo}`
            : null
      }))
    });
  } catch {
    return Response.json(
      { error: "Could not load document versions." },
      { status: 500 }
    );
  }
}
