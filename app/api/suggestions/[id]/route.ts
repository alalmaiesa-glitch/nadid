import { getSupabaseAdmin } from "@/lib/supabase-admin";

export async function PATCH(
  request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const body = (await request.json()) as {
    status?: "accepted" | "rejected";
  };

  if (body.status !== "accepted" && body.status !== "rejected") {
    return Response.json(
      { error: "حالة الملاحظة غير صالحة." },
      { status: 400 }
    );
  }

  const supabase = getSupabaseAdmin();

  if (!supabase) {
    return Response.json({
      persisted: false,
      reason: "supabase_not_configured"
    });
  }

  const { error } = await supabase
    .from("suggestions")
    .update({ status: body.status })
    .eq("client_suggestion_id", id);

  if (error) {
    return Response.json(
      { error: "تعذر حفظ قرار المراجعة." },
      { status: 500 }
    );
  }

  return Response.json({ persisted: true });
}
