import { getSupabaseAdmin } from "@/lib/supabase-admin";

export type BillingEntitlement =
  | "basic_review"
  | "docx_upload"
  | "original_preserved"
  | "context_review"
  | "consistency_review"
  | "rewrite"
  | "export"
  | "deep_review"
  | "fact_lock"
  | "version_history";

type EffectivePlan = {
  plan_id: string;
  tier: string;
  entitlements: Record<string, unknown>;
};

export async function enforcePlanEntitlement(
  userId: string | null,
  entitlement: BillingEntitlement
): Promise<Response | null> {
  if (!userId) {
    if (process.env.NODE_ENV === "production") {
      return Response.json(
        {
          error: "Billing identity is unavailable.",
          code: "BILLING_IDENTITY_UNAVAILABLE"
        },
        { status: 503 }
      );
    }
    return null;
  }

  const supabase = getSupabaseAdmin();

  if (!supabase) {
    if (process.env.NODE_ENV === "production") {
      return Response.json(
        {
          error: "Billing entitlement service is unavailable.",
          code: "BILLING_ENTITLEMENT_SERVICE_UNAVAILABLE"
        },
        { status: 503 }
      );
    }
    return null;
  }

  const { data, error } = await supabase.rpc(
    "get_effective_billing_plan",
    { p_user_id: userId }
  );

  if (error || !data?.[0]) {
    return Response.json(
      {
        error: "Could not resolve billing entitlements.",
        code: "BILLING_ENTITLEMENT_CHECK_FAILED"
      },
      { status: 503 }
    );
  }

  const plan = data[0] as EffectivePlan;
  const allowed = plan.entitlements?.[entitlement] === true;

  if (!allowed) {
    return Response.json(
      {
        error: "This feature is not included in the current plan.",
        code: "PLAN_ENTITLEMENT_REQUIRED",
        entitlement,
        planId: plan.plan_id,
        tier: plan.tier
      },
      { status: 403 }
    );
  }

  return null;
}
