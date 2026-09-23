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
  type: "number" | "currency" | "percentage" | "date" | "standard" | "negation";
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
  protectedCount: number;
  chunkCount: number;
};

export type DeepAnalysisResult = {
  chunks: MemoryChunk[];
  memory: DeepMemorySnapshot;
};
