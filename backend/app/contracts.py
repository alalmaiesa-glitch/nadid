from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


NodeType = Literal["heading", "paragraph", "table_cell"]
ReviewCategory = Literal["language", "style", "consistency", "protection"]
ProtectedType = Literal[
    "number", "currency", "percentage", "date", "standard", "negation"
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


class DocumentMemory(BaseModel):
    headings: list[str]
    terms: list[MemoryTerm]
    facts: list[FactAssertion]
    conflicts: list[FactConflict]
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


class DeepAnalyzeResponse(BaseModel):
    base: AnalyzeResponse
    memory: DocumentMemory
