from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


NodeType = Literal["heading", "paragraph", "table_cell"]
ReviewCategory = Literal["language", "style", "consistency", "protection"]
ProtectedType = Literal[
    "number",
    "currency",
    "percentage",
    "date",
    "standard",
    "negation",
    "entity",
    "legal_reference",
    "role",
    "obligation",
    "condition",
    "qualifier",
    "quotation",
    "quantity",
]


class DocumentNode(BaseModel):
    id: str
    type: NodeType
    text: str
    sequence_no: int
    parent_id: str | None = None
    source_anchor: dict = Field(default_factory=dict)


class Chunk(BaseModel):
    id: str
    node_ids: list[str]
    text: str
    token_estimate: int
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None


class Suggestion(BaseModel):
    id: str
    node_id: str
    category: ReviewCategory
    title: str
    explanation: str
    original: str
    replacement: str | None = None
    confidence: float = Field(ge=0, le=1)


class ProtectedSpan(BaseModel):
    id: str
    node_id: str
    type: ProtectedType
    value: str
    validator_key: str
    lock_policy: str = "normalize_only"
    lock_mode: str = "block"


class DocumentSummary(BaseModel):
    filename: str
    word_count: int
    paragraph_count: int
    heading_count: int


class AnalyzeResponse(BaseModel):
    document: DocumentSummary
    nodes: list[DocumentNode]
    chunks: list[Chunk]
    suggestions: list[Suggestion]
    protected_spans: list[ProtectedSpan]


class FactAssertion(BaseModel):
    id: str
    node_id: str
    fact_type: str
    claim_key: str
    value: str
    canonical_value: str
    context: str
    confidence: float = Field(default=0.9, ge=0, le=1)


class FactConflict(BaseModel):
    id: str
    claim_key: str
    fact_ids: list[str]
    values: list[str]
    confidence: float = Field(default=0.8, ge=0, le=1)


class MemoryTerm(BaseModel):
    term: str
    count: int
    node_ids: list[str]


MemoryItemKind = Literal[
    "entity",
    "definition",
    "abbreviation",
    "decision",
    "reference",
    "concept",
    "obligation",
    "condition",
    "relation",
]


class MemoryItem(BaseModel):
    id: str
    kind: MemoryItemKind
    key: str
    value: str
    node_ids: list[str]
    aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.9, ge=0, le=1)
    metadata: dict = Field(default_factory=dict)


class DocumentMemory(BaseModel):
    headings: list[str]
    terms: list[MemoryTerm]
    facts: list[FactAssertion]
    conflicts: list[FactConflict]
    knowledge_items: list[MemoryItem] = Field(default_factory=list)
    protected_count: int
    chunk_count: int


class ContextRequest(BaseModel):
    target_node_id: str
    query: str | None = None
    max_chunks: int = Field(default=5, ge=1, le=12)


class ContextHit(BaseModel):
    chunk_id: str
    score: float
    text: str
    node_ids: list[str]


class ContextPackage(BaseModel):
    target_node_id: str
    local_nodes: list[DocumentNode]
    hits: list[ContextHit]
    related_facts: list[FactAssertion]


SemanticIssueType = Literal[
    "definition_conflict",
    "abbreviation_conflict",
    "polarity_conflict",
    "decision_conflict",
]


class SemanticIssue(BaseModel):
    id: str
    node_id: str
    issue_type: SemanticIssueType
    title: str
    explanation: str
    original: str
    evidence_node_ids: list[str]
    evidence_values: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.9, ge=0, le=1)


EvidenceFindingKind = Literal[
    "suggestion",
    "semantic_issue",
    "fact_conflict",
]
EvidenceTraceStatus = Literal["complete", "partial"]
SeverityLevel = Literal["critical", "high", "medium", "low"]
ConfidenceLevel = Literal["high", "medium", "low"]
ReviewAction = Literal[
    "auto_fix",
    "suggest",
    "require_review",
    "block",
]
MeaningLockStatus = Literal[
    "PASS",
    "BLOCK",
    "UNKNOWN",
    "NOT_APPLICABLE",
]


class EvidenceLocation(BaseModel):
    document_id: str | None = None
    node_id: str
    original_node_id: str | None = None
    sequence_no: int
    node_type: NodeType
    location_label: str
    source_anchor: dict = Field(default_factory=dict)
    excerpt: str


class EvidenceTrace(BaseModel):
    finding_id: str
    finding_kind: EvidenceFindingKind
    category: ReviewCategory
    title: str
    explanation: str
    # Operational confidence after policy calibration. This is not an
    # empirically calibrated probability until Human Gold is available.
    confidence: float = Field(ge=0, le=1)
    source_confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_level: ConfidenceLevel = "low"
    severity: SeverityLevel = "low"
    strong_assertion: bool = False
    calibration_method: str = "policy_v1_unvalidated"
    calibration_reasons: list[str] = Field(default_factory=list)
    recommended_action: ReviewAction = "require_review"
    auto_apply_allowed: bool = False
    meaning_lock_status: MeaningLockStatus = "NOT_APPLICABLE"
    action_reasons: list[str] = Field(default_factory=list)
    reason_code: str
    evidence_locations: list[EvidenceLocation] = Field(default_factory=list)
    evidence_values: list[str] = Field(default_factory=list)
    trace_status: EvidenceTraceStatus = "complete"


class DeepAnalyzeResponse(BaseModel):
    base: AnalyzeResponse
    memory: DocumentMemory
    semantic_issues: list[SemanticIssue] = Field(default_factory=list)
    evidence_traces: list[EvidenceTrace] = Field(default_factory=list)


class PatchOperation(BaseModel):
    node_id: str
    original: str
    replacement: str
