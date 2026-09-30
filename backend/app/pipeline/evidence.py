from __future__ import annotations

from app.contracts import (
    DocumentMemory,
    DocumentNode,
    EvidenceLocation,
    EvidenceTrace,
    SemanticIssue,
    Suggestion,
)
from app.pipeline.confidence import calibrate_evidence_traces


def _excerpt(text: str, needle: str | None = None, radius: int = 140) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= radius * 2:
        return clean

    if needle:
        normalized_needle = " ".join(needle.split())
        index = clean.find(normalized_needle)
        if index >= 0:
            start = max(0, index - radius)
            end = min(len(clean), index + len(normalized_needle) + radius)
            prefix = "…" if start else ""
            suffix = "…" if end < len(clean) else ""
            return prefix + clean[start:end] + suffix

    return clean[: radius * 2] + "…"


def _location_label(node: DocumentNode) -> str:
    anchor = node.source_anchor or {}
    kind = anchor.get("kind", node.type)
    block_index = anchor.get("block_index")

    if kind == "table_cell":
        row = anchor.get("row")
        cell = anchor.get("cell")
        parts = ["table_cell"]
        if block_index is not None:
            parts.append(f"block:{int(block_index) + 1}")
        if row is not None:
            parts.append(f"row:{int(row) + 1}")
        if cell is not None:
            parts.append(f"cell:{int(cell) + 1}")
        return "/".join(parts)

    parts = [str(kind)]
    if block_index is not None:
        parts.append(f"block:{int(block_index) + 1}")
    else:
        parts.append(f"node:{node.sequence_no + 1}")
    return "/".join(parts)


def _location(
    node: DocumentNode,
    default_document_id: str | None = None,
    needle: str | None = None,
) -> EvidenceLocation:
    anchor = node.source_anchor or {}
    return EvidenceLocation(
        document_id=anchor.get("document_id") or default_document_id,
        node_id=node.id,
        original_node_id=anchor.get("original_node_id"),
        sequence_no=node.sequence_no,
        node_type=node.type,
        location_label=_location_label(node),
        source_anchor=anchor,
        excerpt=_excerpt(node.text, needle),
    )


def _suggestion_trace(
    suggestion: Suggestion,
    nodes: dict[str, DocumentNode],
    default_document_id: str | None,
) -> EvidenceTrace:
    node = nodes.get(suggestion.node_id)
    locations = (
        [_location(node, default_document_id, suggestion.original)]
        if node
        else []
    )
    source_present = bool(
        node and suggestion.original and suggestion.original in node.text
    )

    return EvidenceTrace(
        finding_id=suggestion.id,
        finding_kind="suggestion",
        category=suggestion.category,
        title=suggestion.title,
        explanation=suggestion.explanation,
        confidence=suggestion.confidence,
        reason_code="review_rule_match",
        evidence_locations=locations,
        evidence_values=[
            value
            for value in [suggestion.original, suggestion.replacement or ""]
            if value
        ],
        trace_status=(
            "complete"
            if len(locations) == 1 and source_present
            else "partial"
        ),
    )


def _semantic_trace(
    issue: SemanticIssue,
    nodes: dict[str, DocumentNode],
    default_document_id: str | None,
) -> EvidenceTrace:
    locations = [
        _location(nodes[node_id], default_document_id)
        for node_id in issue.evidence_node_ids
        if node_id in nodes
    ]
    expected = len(set(issue.evidence_node_ids))
    complete = expected >= 2 and len(locations) == expected

    return EvidenceTrace(
        finding_id=issue.id,
        finding_kind="semantic_issue",
        category="consistency",
        title=issue.title,
        explanation=issue.explanation,
        confidence=issue.confidence,
        reason_code=f"semantic:{issue.issue_type}",
        evidence_locations=locations,
        evidence_values=issue.evidence_values,
        trace_status="complete" if complete else "partial",
    )


def _fact_conflict_traces(
    memory: DocumentMemory,
    nodes: dict[str, DocumentNode],
    default_document_id: str | None,
) -> list[EvidenceTrace]:
    facts = {fact.id: fact for fact in memory.facts}
    traces: list[EvidenceTrace] = []

    for conflict in memory.conflicts:
        conflict_facts = [
            facts[fact_id]
            for fact_id in conflict.fact_ids
            if fact_id in facts
        ]
        locations = [
            _location(
                nodes[fact.node_id],
                default_document_id,
                fact.value,
            )
            for fact in conflict_facts
            if fact.node_id in nodes
        ]
        expected = len(set(conflict.fact_ids))
        complete = (
            expected >= 2
            and len(conflict_facts) == expected
            and len(locations) == expected
        )

        traces.append(
            EvidenceTrace(
                finding_id=conflict.id,
                finding_kind="fact_conflict",
                category="consistency",
                title="تعارض في قيمة موثقة",
                explanation=(
                    "وجد نَضِيد قيمًا مختلفة لادعاء واحد ضمن "
                    "نطاق الاتساق نفسه."
                ),
                confidence=conflict.confidence,
                reason_code="fact:value_conflict",
                evidence_locations=locations,
                evidence_values=conflict.values,
                trace_status="complete" if complete else "partial",
            )
        )

    return traces


def build_evidence_traces(
    nodes: list[DocumentNode],
    suggestions: list[Suggestion] | None = None,
    semantic_issues: list[SemanticIssue] | None = None,
    memory: DocumentMemory | None = None,
    default_document_id: str | None = None,
) -> list[EvidenceTrace]:
    node_map = {node.id: node for node in nodes}
    traces: list[EvidenceTrace] = []

    for suggestion in suggestions or []:
        traces.append(
            _suggestion_trace(
                suggestion,
                node_map,
                default_document_id,
            )
        )

    for issue in semantic_issues or []:
        traces.append(
            _semantic_trace(
                issue,
                node_map,
                default_document_id,
            )
        )

    if memory is not None:
        traces.extend(
            _fact_conflict_traces(
                memory,
                node_map,
                default_document_id,
            )
        )

    return calibrate_evidence_traces(traces)
