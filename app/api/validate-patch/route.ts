import type { ProtectedFact } from "@/lib/nadid-types";
import {
  isAeeBackendConfigured,
  validatePatchWithAee
} from "@/lib/server/aee-client";
import { authorizeUser } from "@/lib/server/authz";
import { readBoundedJson } from "@/lib/server/request-bounds";
import { enforceSameOriginMutation } from "@/lib/server/request-integrity";

type PatchRequest = {
  blockText: string;
  original: string;
  replacement: string;
  protectedFacts: ProtectedFact[];
};

export async function POST(request: Request) {
  const integrity = enforceSameOriginMutation(request);
  if (integrity) return integrity;

  const auth = await authorizeUser();
  if (!auth.ok) return auth.response;

  const parsed = await readBoundedJson<PatchRequest>(
    request,
    256 * 1024
  );
  if (!parsed.ok) return parsed.response;

  const body = parsed.value;

  if (
    !body.blockText ||
    !body.original ||
    typeof body.replacement !== "string" ||
    body.blockText.length > 100_000 ||
    body.original.length > 20_000 ||
    body.replacement.length > 20_000 ||
    !Array.isArray(body.protectedFacts) ||
    body.protectedFacts.length > 500
  ) {
    return Response.json(
      { error: "بيانات التعديل غير مكتملة." },
      { status: 400 }
    );
  }

  if (isAeeBackendConfigured()) {
    try {
      const result = await validatePatchWithAee(body);
      return Response.json(result);
    } catch {
      // Keep the local validator available as a resilience fallback.
    }
  }

  if (!body.blockText.includes(body.original)) {
    return Response.json({
      status: "BLOCK",
      reason: "SOURCE_CHANGED",
      candidate: body.blockText,
      checks: []
    });
  }

  const candidate = body.blockText.replace(body.original, body.replacement);
  const checks = body.protectedFacts.map((fact) => {
    const existedBefore = body.blockText.includes(fact.value);
    const existsAfter = candidate.includes(fact.value);
    const passed = !existedBefore || existsAfter;

    return {
      factId: fact.id,
      type: fact.type,
      value: fact.value,
      status: passed ? "PASS" : "BLOCK"
    };
  });

  const blocked = checks.some((check) => check.status === "BLOCK");

  return Response.json({
    status: blocked ? "BLOCK" : "PASS",
    reason: blocked ? "PROTECTED_FACT_CHANGED" : null,
    candidate: blocked ? body.blockText : candidate,
    checks
  });
}
