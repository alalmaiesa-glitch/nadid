import type { ProtectedFact } from "@/lib/nadid-types";

type PatchRequest = {
  blockText: string;
  original: string;
  replacement: string;
  protectedFacts: ProtectedFact[];
};

export async function POST(request: Request) {
  const body = (await request.json()) as PatchRequest;

  if (
    !body.blockText ||
    !body.original ||
    typeof body.replacement !== "string"
  ) {
    return Response.json(
      { error: "بيانات التعديل غير مكتملة." },
      { status: 400 }
    );
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
