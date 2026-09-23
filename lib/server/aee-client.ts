import { randomUUID } from "node:crypto";
import type {
  AnalyzeResponse,
  ProtectedFact
} from "@/lib/nadid-types";

type AeeNode = {
  id: string;
  type: "heading" | "paragraph" | "table_cell";
  text: string;
};

type AeeSuggestion = {
  id: string;
  node_id: string;
  category: "language" | "style" | "consistency" | "protection";
  title: string;
  explanation: string;
  original: string;
  replacement?: string | null;
  confidence: number;
};

type AeeProtected = {
  id: string;
  node_id: string;
  type: ProtectedFact["type"];
  value: string;
};

type AeeAnalyzeResponse = {
  document: {
    filename: string;
    word_count: number;
    paragraph_count: number;
    heading_count: number;
  };
  nodes: AeeNode[];
  suggestions: AeeSuggestion[];
  protected_spans: AeeProtected[];
};

export function isAeeBackendConfigured() {
  return Boolean(process.env.AEE_BACKEND_URL);
}

function aeeUrl(path: string) {
  const base = process.env.AEE_BACKEND_URL?.replace(/\/$/, "");
  if (!base) throw new Error("aee_backend_not_configured");
  return base + path;
}

export async function analyzeDocxWithAee(
  filename: string,
  buffer: Buffer
): Promise<AnalyzeResponse> {
  const body = new FormData();
  body.append(
    "file",
    new Blob([buffer], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }),
    filename
  );

  const response = await fetch(aeeUrl("/v1/analyze/docx"), {
    method: "POST",
    body,
    signal: AbortSignal.timeout(120_000)
  });

  if (!response.ok) {
    throw new Error(`aee_analyze_failed_${response.status}`);
  }

  const payload = (await response.json()) as AeeAnalyzeResponse;

  return {
    document: {
      id: randomUUID(),
      filename: payload.document.filename,
      wordCount: payload.document.word_count,
      paragraphCount: payload.document.paragraph_count,
      blocks: payload.nodes.map((node) => ({
        id: node.id,
        type: node.type === "heading" ? "heading" : "paragraph",
        text: node.text
      }))
    },
    suggestions: payload.suggestions.map((item) => ({
      id: item.id,
      blockId: item.node_id,
      category: item.category,
      title: item.title,
      explanation: item.explanation,
      original: item.original,
      replacement: item.replacement ?? undefined,
      confidence: item.confidence
    })),
    protectedFacts: payload.protected_spans.map((item) => ({
      id: item.id,
      blockId: item.node_id,
      type: item.type,
      value: item.value
    })),
    warnings: []
  };
}

function validatorKey(type: ProtectedFact["type"]) {
  if (["number", "currency", "percentage"].includes(type)) {
    return "numeric_equivalence";
  }
  if (type === "date") return "date_equivalence";
  if (type === "standard") return "exact_or_normalized_identifier";
  if (type === "negation") return "negation_preservation";
  return "exact_text";
}

export async function validatePatchWithAee(input: {
  blockText: string;
  original: string;
  replacement: string;
  protectedFacts: ProtectedFact[];
}) {
  const response = await fetch(aeeUrl("/v1/validate-patch"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      block_text: input.blockText,
      original: input.original,
      replacement: input.replacement,
      protected_spans: input.protectedFacts.map((fact) => ({
        id: fact.id,
        node_id: fact.blockId || "unknown",
        type: fact.type,
        value: fact.value,
        validator_key: validatorKey(fact.type),
        lock_policy:
          fact.type === "negation" ? "semantic_exact" : "normalize_only",
        lock_mode: "block"
      }))
    }),
    signal: AbortSignal.timeout(30_000)
  });

  if (!response.ok) {
    throw new Error(`aee_patch_validation_failed_${response.status}`);
  }

  return response.json();
}
