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
