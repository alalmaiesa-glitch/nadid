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
    blocks: DocumentBlock[];
  };
  suggestions: QuickSuggestion[];
  protectedFacts: ProtectedFact[];
  warnings: string[];
};
