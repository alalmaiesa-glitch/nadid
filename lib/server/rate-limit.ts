import { getSupabaseAdmin } from "@/lib/supabase-admin";

export type ApiRateLimitPolicy = {
  action: string;
  limit: number;
  windowSeconds: number;
};

export const API_RATE_LIMITS = {
  analyze: {
    action: "analyze",
    limit: 12,
    windowSeconds: 60
  },
  validatePatch: {
    action: "validate_patch",
    limit: 120,
    windowSeconds: 60
  },
  contextSearch: {
    action: "context_search",
    limit: 120,
    windowSeconds: 60
  },
  deepReview: {
    action: "deep_review",
    limit: 6,
    windowSeconds: 3600
  },
  uploadCreate: {
    action: "upload_create",
    limit: 30,
    windowSeconds: 60
  },
  finalizeUpload: {
    action: "finalize_upload",
    limit: 30,
    windowSeconds: 60
  },
  suggestionDecision: {
    action: "suggestion_decision",
    limit: 120,
    windowSeconds: 60
  },
  createVersion: {
    action: "create_version",
    limit: 12,
    windowSeconds: 60
  }
} as const satisfies Record<string, ApiRateLimitPolicy>;

export async function enforceUserRateLimit(
  userId: string | null,
  policy: ApiRateLimitPolicy
): Promise<Response | null> {
  if (!userId) {
    if (process.env.NODE_ENV === "production") {
      return Response.json(
        {
          error: "Rate limit identity is unavailable.",
          code: "RATE_LIMIT_IDENTITY_UNAVAILABLE"
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
          error: "Rate limit service is unavailable.",
          code: "RATE_LIMIT_SERVICE_UNAVAILABLE"
        },
        { status: 503 }
      );
    }

    return null;
  }

  const { data, error } = await supabase.rpc(
    "consume_api_rate_limit",
    {
      p_user_id: userId,
      p_action: policy.action,
      p_window_seconds: policy.windowSeconds,
      p_limit: policy.limit
    }
  );

  if (error || !data?.[0]) {
    return Response.json(
      {
        error: "Rate limit service failed.",
        code: "RATE_LIMIT_CHECK_FAILED"
      },
      { status: 503 }
    );
  }

  const result = data[0];

  if (!result.allowed) {
    return Response.json(
      {
        error: "Too many requests. Try again shortly.",
        code: "RATE_LIMITED",
        action: policy.action,
        retryAfterSeconds: result.retry_after_seconds
      },
      {
        status: 429,
        headers: {
          "Retry-After": String(
            Math.max(1, result.retry_after_seconds)
          )
        }
      }
    );
  }

  return null;
}
