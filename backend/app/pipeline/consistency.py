from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.contracts import DocumentMemory, DocumentNode, FactConflict, SemanticIssue
from app.pipeline.chunker import build_chunks
from app.pipeline.memory import build_document_memory
from app.pipeline.protection import extract_protected_spans
from app.pipeline.semantic_review import semantic_review


@dataclass(frozen=True)
class ConsistencyReport:
    document_ids: list[str]
    node_count: int
    nodes: list[DocumentNode]
    memory: DocumentMemory
    semantic_issues: list[SemanticIssue]
    fact_conflicts: list[FactConflict]
    node_document: dict[str, str]

    def evidence_documents(self, node_ids: list[str]) -> list[str]:
        return sorted({
            self.node_document[node_id]
            for node_id in node_ids
            if node_id in self.node_document
        })


def _namespace_nodes(
    document_id: str,
    nodes: list[DocumentNode],
    sequence_offset: int,
) -> tuple[list[DocumentNode], dict[str, str]]:
    output: list[DocumentNode] = []
    mapping: dict[str, str] = {}

    for index, node in enumerate(nodes):
        namespaced_id = f"{document_id}::{node.id}"
        mapping[namespaced_id] = document_id
        source_anchor = {
            **node.source_anchor,
            "document_id": document_id,
            "original_node_id": node.id,
        }
        output.append(
            node.model_copy(
                update={
                    "id": namespaced_id,
                    "sequence_no": sequence_offset + index,
                    "source_anchor": source_anchor,
                }
            )
        )

    return output, mapping


def review_document_set(
    documents: Mapping[str, list[DocumentNode]],
) -> ConsistencyReport:
    """
    Review one logical document set as a shared consistency scope.

    A set can contain one long document or multiple related documents.
    Node IDs are namespaced before building memory, so evidence can be
    traced back to its source document without collisions.
    """
    combined: list[DocumentNode] = []
    node_document: dict[str, str] = {}
    offset = 0

    for document_id, nodes in documents.items():
        namespaced, mapping = _namespace_nodes(document_id, nodes, offset)
        combined.extend(namespaced)
        node_document.update(mapping)
        offset += len(namespaced)

    chunks = build_chunks(combined)
    protected = extract_protected_spans(combined)
    memory = build_document_memory(combined, chunks, protected)
    issues = semantic_review(combined, memory)

    return ConsistencyReport(
        document_ids=list(documents.keys()),
        node_count=len(combined),
        nodes=combined,
        memory=memory,
        semantic_issues=issues,
        fact_conflicts=memory.conflicts,
        node_document=node_document,
    )
