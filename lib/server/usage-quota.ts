import { getSupabaseAdmin } from "@/lib/supabase-admin";

type ConsumeQuotaResult = {
  allowed: boolean;
  already_charged: boolean;
  included_used: number;
  topup_used: number;
  remaining_included: number;
  remaining_topup: number;
};

export async function consumeCharacterQuota(
  userId: string | null,
  operationId: string,
  characters: number
): Promise<Response | null> {
  if (!userId) {
    if (process.env.NODE_ENV === "production") {
      return Response.json(
        {
          error: "Usage quota identity is unavailable.",
          code: "USAGE_QUOTA_IDENTITY_UNAVAILABLE"
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
          error: "Usage quota service is unavailable.",
          code: "USAGE_QUOTA_SERVICE_UNAVAILABLE"
        },
        { status: 503 }
      );
    }
    return null;
  }

  const safeCharacters = Math.max(0, Math.trunc(characters));
  if (safeCharacters < 1) return null;

  const { data, error } = await supabase.rpc(
    "consume_character_quota",
    {
      p_user_id: userId,
      p_operation_id: operationId,
      p_action: "analyze",
      p_characters: safeCharacters
    }
  );

  if (error || !data?.[0]) {
    return Response.json(
      {
        error: "Usage quota check failed.",
        code: "USAGE_QUOTA_CHECK_FAILED"
      },
      { status: 503 }
    );
  }

  const result = data[0] as ConsumeQuotaResult;

  if (!result.allowed) {
    return Response.json(
      {
        error: "Monthly character quota exhausted.",
        code: "CHARACTER_QUOTA_EXCEEDED",
        remainingCharacters:
          Number(result.remaining_included) +
          Number(result.remaining_topup)
      },
      { status: 402 }
    );
  }

  return null;
}
