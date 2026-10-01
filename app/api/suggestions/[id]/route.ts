import { getSupabaseAdmin } from "@/lib/supabase-admin";
import { authorizeDocument } from "@/lib/server/authz";
import { enforceSameOriginMutation } from "@/lib/server/request-integrity";

export async function PATCH(
  request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const integrity = enforceSameOriginMutation(request);
  if (integrity) return integrity;
  const { id } = await context.params;

  const body = (await request.json()) as {
    status?: "accepted" | "rejected";
    documentId?: string;
    versionNo?: number;
  };

  if (body.status !== "accepted" && body.status !== "rejected") {
    return Response.json(
      { error: "حالة الملاحظة غير صالحة." },
      { status: 400 }
    );
  }

  if (
    !body.documentId ||
    !Number.isInteger(body.versionNo) ||
    Number(body.versionNo) < 1
  ) {
    return Response.json(
      {
        error: "نطاق الملاحظة غير مكتمل.",
        code: "SUGGESTION_SCOPE_REQUIRED"
      },
      { status: 400 }
    );
  }

  const auth = await authorizeDocument(body.documentId);
  if (!auth.ok) return auth.response;

  const supabase = getSupabaseAdmin();

  if (!supabase) {
    return Response.json({
      persisted: false,
      reason: "supabase_not_configured"
    });
  }

  if (!auth.userId) {
    return Response.json(
      { error: "Authentication required." },
      { status: 401 }
    );
  }

  const { data, error } = await supabase.rpc(
    "record_suggestion_decision",
    {
      p_document_id: body.documentId,
      p_version_no: Number(body.versionNo),
      p_client_suggestion_id: id,
      p_owner_id: auth.userId,
      p_decision: body.status
    }
  );

  if (error) {
    const message = error.message ?? "";

    if (message.includes("suggestion_version_changed")) {
      return Response.json(
        {
          error:
            "ظهرت نسخة أحدث من المستند. أعد تحميل الصفحة قبل حفظ القرار.",
          code: "VERSION_CHANGED"
        },
        { status: 409 }
      );
    }

    if (message.includes("suggestion_scope_not_found")) {
      return Response.json(
        {
          error: "الملاحظة غير موجودة في هذه النسخة.",
          code: "SUGGESTION_NOT_FOUND"
        },
        { status: 404 }
      );
    }

    if (
      message.includes("invalid_suggestion_decision") ||
      message.includes("invalid_suggestion_version")
    ) {
      return Response.json(
        {
          error: "بيانات قرار الملاحظة غير صالحة.",
          code: "INVALID_SUGGESTION_DECISION"
        },
        { status: 400 }
      );
    }

    return Response.json(
      { error: "تعذر حفظ قرار المراجعة." },
      { status: 500 }
    );
  }

  const decision = data?.[0];

  return Response.json({
    persisted: true,
    decisionId: decision?.decision_id ?? null,
    suggestionId: decision?.suggestion_id ?? null,
    versionId: decision?.version_id ?? null,
    status: decision?.status ?? body.status
  });
}
