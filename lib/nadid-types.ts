import type { Json } from "@/lib/database.types";

export type ReviewCategory = "language" | "style" | "consistency" | "protection";

export type DocumentBlock = {
  id: string;
  type: "heading" | "paragraph";
  text: string;
};

export type QuickSuggestion = {
  id: string;
  blockId: string;
  category: ReviewCategory;
  title: string;
  explanation: string;
  original: string;
  replacement?: string;
  confidence: number;
};

export type ProtectedFact = {
  id: string;
  blockId: string;
  type:
    | "number"
    | "currency"
    | "percentage"
    | "date"
    | "standard"
    | "negation"
    | "entity"
    | "legal_reference"
    | "role"
    | "obligation"
    | "condition"
    | "qualifier"
    | "quotation"
    | "quantity";
  value: string;
};

export type AnalyzeResponse = {
  document: {
    id: string;
    filename: string;
    wordCount: number;
    paragraphCount: number;
    versionNo?: number;
    blocks: DocumentBlock[];
  };
  suggestions: QuickSuggestion[];
  protectedFacts: ProtectedFact[];
  warnings: string[];
};


export type MemoryTerm = {
  term: string;
  count: number;
  nodeIds: string[];
};

export type MemoryItemKind =
  | "entity"
  | "definition"
  | "abbreviation"
  | "decision"
  | "reference"
  | "concept"
  | "obligation"
  | "condition"
  | "relation";

export type MemoryItem = {
  id: string;
  kind: MemoryItemKind;
  key: string;
  value: string;
  nodeIds: string[];
  aliases: string[];
  confidence: number;
  metadata: Json;
};

export type FactAssertion = {
  id: string;
  nodeId: string;
  factType: string;
  claimKey: string;
  value: string;
  canonicalValue: string;
  context: string;
  confidence: number;
};

export type FactConflict = {
  id: string;
  claimKey: string;
  factIds: string[];
  values: string[];
  confidence: number;
};

export type MemoryChunk = {
  id: string;
  nodeIds: string[];
  text: string;
  tokenEstimate: number;
};

export type DeepMemorySnapshot = {
  headings: string[];
  terms: MemoryTerm[];
  facts: FactAssertion[];
  conflicts: FactConflict[];
  knowledgeItems: MemoryItem[];
  protectedCount: number;
  chunkCount: number;
};

export type SemanticIssue = {
  id: string;
  nodeId: string;
  issueType:
    | "definition_conflict"
    | "abbreviation_conflict"
    | "polarity_conflict"
    | "decision_conflict";
  title: string;
  explanation: string;
  original: string;
  evidenceNodeIds: string[];
  evidenceValues: string[];
  confidence: number;
};

export type DeepAnalysisResult = {
  chunks: MemoryChunk[];
  memory: DeepMemorySnapshot;
  semanticIssues: SemanticIssue[];
};
