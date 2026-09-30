from __future__ import annotations

from dataclasses import dataclass, field

from app.contracts import (
    DocumentNode,
    PatchOperation,
    ProtectedSpan,
    Suggestion,
)
from app.pipeline.evidence import build_evidence_traces
from app.pipeline.patch_validator import validate_patch


@dataclass(frozen=True)
class AutoApplySkip:
    suggestion_id: str
    node_id: str
    reason: str


@dataclass(frozen=True)
class AutoApplyPlan:
    patches: list[PatchOperation] = field(default_factory=list)
    skipped: list[AutoApplySkip] = field(default_factory=list)


def build_safe_auto_apply_plan(
    nodes: list[DocumentNode],
    suggestions: list[Suggestion],
    protected_spans: list[ProtectedSpan],
) -> AutoApplyPlan:
    """
    Select only policy-approved auto-fixes, then revalidate them sequentially.

    The second validation is intentional: earlier edits may make a later
    suggestion stale or may change the Meaning Lock context.
    """
    traces = build_evidence_traces(
        nodes,
        suggestions=suggestions,
        protected_spans=protected_spans,
    )
    trace_by_id = {trace.finding_id: trace for trace in traces}

    protected_by_node: dict[str, list[ProtectedSpan]] = {}
    for span in protected_spans:
        protected_by_node.setdefault(span.node_id, []).append(span)

    working_text = {node.id: node.text for node in nodes}
    node_sequence = {node.id: node.sequence_no for node in nodes}
    patches: list[PatchOperation] = []
    skipped: list[AutoApplySkip] = []

    # Process exact spans right-to-left within each node. Replacements at
    # higher offsets cannot invalidate lower offsets, which avoids ambiguity
    # when identical source fragments occur more than once.
    ordered_suggestions = sorted(
        suggestions,
        key=lambda suggestion: (
            node_sequence.get(suggestion.node_id, 10**9),
            -(
                suggestion.start_offset
                if suggestion.start_offset is not None
                else -1
            ),
            suggestion.id,
        ),
    )

    for suggestion in ordered_suggestions:
        trace = trace_by_id.get(suggestion.id)
        if trace is None:
            skipped.append(
                AutoApplySkip(
                    suggestion_id=suggestion.id,
                    node_id=suggestion.node_id,
                    reason="TRACE_NOT_FOUND",
                )
            )
            continue

        if not trace.auto_apply_allowed:
            skipped.append(
                AutoApplySkip(
                    suggestion_id=suggestion.id,
                    node_id=suggestion.node_id,
                    reason=f"ACTION_{trace.recommended_action.upper()}",
                )
            )
            continue

        if suggestion.replacement is None:
            skipped.append(
                AutoApplySkip(
                    suggestion_id=suggestion.id,
                    node_id=suggestion.node_id,
                    reason="REPLACEMENT_MISSING",
                )
            )
            continue

        if suggestion.start_offset is None:
            skipped.append(
                AutoApplySkip(
                    suggestion_id=suggestion.id,
                    node_id=suggestion.node_id,
                    reason="PRECISE_LOCATION_MISSING",
                )
            )
            continue

        source = working_text.get(suggestion.node_id)
        if source is None:
            skipped.append(
                AutoApplySkip(
                    suggestion_id=suggestion.id,
                    node_id=suggestion.node_id,
                    reason="NODE_NOT_FOUND",
                )
            )
            continue

        validation = validate_patch(
            block_text=source,
            original=suggestion.original,
            replacement=suggestion.replacement,
            protected_spans=protected_by_node.get(suggestion.node_id, []),
            start_offset=suggestion.start_offset,
        )

        if validation.status != "PASS":
            skipped.append(
                AutoApplySkip(
                    suggestion_id=suggestion.id,
                    node_id=suggestion.node_id,
                    reason=validation.reason or "MEANING_LOCK_BLOCK",
                )
            )
            continue

        working_text[suggestion.node_id] = validation.candidate
        patches.append(
            PatchOperation(
                node_id=suggestion.node_id,
                original=suggestion.original,
                replacement=suggestion.replacement,
                start_offset=suggestion.start_offset,
            )
        )

    return AutoApplyPlan(patches=patches, skipped=skipped)
