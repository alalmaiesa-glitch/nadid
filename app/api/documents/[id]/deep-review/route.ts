import {
  loadDeepMemory,
  loadDocumentSource,
  persistDeepAnalysis
} from "@/lib/server/document-persistence";
import {
  analyzeDocxDeepWithAee,
  isAeeBackendConfigured
} from "@/lib/server/aee-client";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const memory = await loadDeepMemory(id);

  if (!memory) {
    return Response.json(
      { state: "missing" },
      { status: 404 }
    );
  }

  return Response.json({
    state: "ready",
    memory
  });
}

export async function POST(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;

  const existing = await loadDeepMemory(id);
  if (existing) {
    return Response.json({
      state: "ready",
      memory: existing,
      reused: true
    });
  }

  if (!isAeeBackendConfigured()) {
    return Response.json(
      {
        state: "unavailable",
        error: "AEE_BACKEND_URL is not configured."
      },
      { status: 409 }
    );
  }

  const source = await loadDocumentSource(id);
  if (!source) {
    return Response.json(
      {
        state: "unavailable",
        error: "Persistent source file is not available."
      },
      { status: 404 }
    );
  }

  try {
    const deep = await analyzeDocxDeepWithAee(
      source.filename,
      source.buffer
    );

    await persistDeepAnalysis(
      id,
      source.versionId,
      deep
    );

    return Response.json({
      state: "ready",
      memory: deep.memory,
      reused: false
    });
  } catch (error) {
    return Response.json(
      {
        state: "failed",
        error:
          error instanceof Error
            ? error.message
            : "deep_review_failed"
      },
      { status: 502 }
    );
  }
}
