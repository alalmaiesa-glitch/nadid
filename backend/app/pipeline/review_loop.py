from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

from app.arabic_numbers import normalize_numeric_text
from app.contracts import DocumentNode, EvidenceTrace, Suggestion
from app.pipeline.auto_apply import AutoApplySkip, build_safe_auto_apply_plan
from app.pipeline.chunker import build_chunks
from app.pipeline.docx_patch import apply_patches_to_docx
from app.pipeline.evidence import build_evidence_traces
from app.pipeline.memory import build_document_memory
from app.pipeline.parser import parse_docx
from app.pipeline.protection import extract_protected_spans
from app.pipeline.reviewer import fast_review
from app.pipeline.semantic_review import semantic_review


NON_IDENTITY_RE = re.compile(r"[^0-9A-Za-z\u0600-\u06FF]+")


@dataclass(frozen=True)
class ReviewLoopRound:
    index: int
    input_sha256: str
    output_sha256: str
    suggestion_count: int
    auto_fix_count: int
    applied_count: int
    skipped: list[AutoApplySkip] = field(default_factory=list)
    meaning_preserved: bool = True
    structure_preserved: bool = True


@dataclass(frozen=True)
class ReviewLoopResult:
    output: bytes
    stable: bool
    safety_pass: bool
    rounds: list[ReviewLoopRound]
    initial_suggestion_count: int
    final_suggestion_count: int
    initial_auto_fix_count: int
    final_auto_fix_count: int
    new_suggestion_keys: list[str]
    new_high_impact_keys: list[str]
    meaning_preserved: bool
    structure_preserved: bool


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_identity(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalize_numeric_text(normalized)
    normalized = normalized.replace("ـ", "")
    normalized = normalized.translate(
        str.maketrans(
            {
                "أ": "ا",
                "إ": "ا",
                "آ": "ا",
                "ٱ": "ا",
                "ى": "ي",
            }
        )
    )
    return NON_IDENTITY_RE.sub("", normalized.casefold())


def _meaning_signature(nodes: list[DocumentNode]) -> tuple[tuple[str, str, str], ...]:
    """
    Multiset-like protected-meaning signature.

    Punctuation and harmless formatting are normalized away, while protected
    values, identities, clauses, numbers, dates, roles, markers and units
    remain observable. Every auto-applied round must preserve this signature.
    """
    spans = extract_protected_spans(nodes)
    return tuple(
        sorted(
            (
                span.type,
                span.validator_key,
                _normalize_identity(span.value),
            )
            for span in spans
        )
    )


def _structure_signature(nodes: list[DocumentNode]) -> tuple[tuple, ...]:
    signature: list[tuple] = []
    for node in nodes:
        anchor = node.source_anchor or {}
        signature.append(
            (
                node.id,
                node.type,
                node.sequence_no,
                anchor.get("kind"),
                anchor.get("block_index"),
                anchor.get("row"),
                anchor.get("cell"),
                anchor.get("heading_level"),
            )
        )
    return tuple(signature)


def _suggestion_key(suggestion: Suggestion) -> str:
    return "|".join(
        [
            suggestion.node_id,
            suggestion.category,
            suggestion.title,
            suggestion.original,
            suggestion.replacement or "",
        ]
    )


def _trace_key(trace: EvidenceTrace) -> str:
    evidence = "|".join(sorted(trace.evidence_values))
    documents = "|".join(
        sorted(
            {
                location.document_id or ""
                for location in trace.evidence_locations
            }
        )
    )
    return "|".join(
        [
            trace.finding_kind,
            trace.category,
            trace.reason_code,
            evidence,
            documents,
        ]
    )


def _analyze(nodes: list[DocumentNode]):
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    suggestions = fast_review(nodes)
    memory = build_document_memory(nodes, chunks, protected)
    semantic_issues = semantic_review(nodes, memory)
    traces = build_evidence_traces(
        nodes,
        suggestions=suggestions,
        semantic_issues=semantic_issues,
        memory=memory,
        protected_spans=protected,
    )
    return protected, suggestions, traces


def _auto_fix_ids(traces: list[EvidenceTrace]) -> set[str]:
    return {
        trace.finding_id
        for trace in traces
        if trace.auto_apply_allowed
        and trace.recommended_action == "auto_fix"
    }


def run_docx_review_loop(
    data: bytes,
    *,
    max_rounds: int = 4,
) -> ReviewLoopResult:
    """
    Run safe review/apply/review cycles until no policy-approved auto-fix remains.

    Fail-closed invariants:
    - every round must preserve protected meaning;
    - document node identity/structure must remain stable;
    - patch application must not skip a policy-approved patch;
    - high/critical findings must not be newly created by the loop.

    The loop is considered stable only when a fresh review produces zero
    auto-fixes. Remaining Suggest/Require Review/Block findings are allowed.
    """
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")

    original_nodes = parse_docx(data)
    original_meaning = _meaning_signature(original_nodes)
    original_structure = _structure_signature(original_nodes)
    original_protected, original_suggestions, original_traces = _analyze(
        original_nodes
    )
    del original_protected

    original_auto_ids = _auto_fix_ids(original_traces)
    initial_non_auto_keys = {
        _suggestion_key(suggestion)
        for suggestion in original_suggestions
        if suggestion.id not in original_auto_ids
    }
    initial_high_impact = {
        _trace_key(trace)
        for trace in original_traces
        if trace.severity in {"critical", "high"}
    }

    current = data
    rounds: list[ReviewLoopRound] = []
    stable = False
    safety_pass = True
    meaning_preserved = True
    structure_preserved = True

    for index in range(1, max_rounds + 1):
        nodes = parse_docx(current)
        protected, suggestions, traces = _analyze(nodes)
        plan = build_safe_auto_apply_plan(
            nodes,
            suggestions,
            protected,
        )

        input_hash = _sha256(current)

        if not plan.patches:
            rounds.append(
                ReviewLoopRound(
                    index=index,
                    input_sha256=input_hash,
                    output_sha256=input_hash,
                    suggestion_count=len(suggestions),
                    auto_fix_count=0,
                    applied_count=0,
                    skipped=plan.skipped,
                )
            )
            stable = True
            break

        output, apply_report = apply_patches_to_docx(
            current,
            plan.patches,
        )
        after_nodes = parse_docx(output)

        round_meaning_preserved = (
            _meaning_signature(nodes)
            == _meaning_signature(after_nodes)
        )
        round_structure_preserved = (
            _structure_signature(nodes)
            == _structure_signature(after_nodes)
        )
        applied_complete = (
            len(apply_report.applied) == len(plan.patches)
            and not apply_report.skipped
            and apply_report.fidelity_ok
        )

        rounds.append(
            ReviewLoopRound(
                index=index,
                input_sha256=input_hash,
                output_sha256=_sha256(output),
                suggestion_count=len(suggestions),
                auto_fix_count=len(plan.patches),
                applied_count=len(apply_report.applied),
                skipped=plan.skipped,
                meaning_preserved=round_meaning_preserved,
                structure_preserved=round_structure_preserved,
            )
        )

        meaning_preserved = (
            meaning_preserved and round_meaning_preserved
        )
        structure_preserved = (
            structure_preserved and round_structure_preserved
        )

        if (
            not round_meaning_preserved
            or not round_structure_preserved
            or not applied_complete
        ):
            safety_pass = False
            current = output
            break

        current = output

    final_nodes = parse_docx(current)
    final_protected, final_suggestions, final_traces = _analyze(final_nodes)
    del final_protected

    final_auto_ids = _auto_fix_ids(final_traces)
    final_keys = {
        _suggestion_key(suggestion)
        for suggestion in final_suggestions
    }
    new_suggestion_keys = sorted(
        final_keys - initial_non_auto_keys
    )

    final_high_impact = {
        _trace_key(trace)
        for trace in final_traces
        if trace.severity in {"critical", "high"}
    }
    new_high_impact_keys = sorted(
        final_high_impact - initial_high_impact
    )

    global_meaning_preserved = (
        _meaning_signature(final_nodes) == original_meaning
    )
    global_structure_preserved = (
        _structure_signature(final_nodes) == original_structure
    )

    meaning_preserved = meaning_preserved and global_meaning_preserved
    structure_preserved = (
        structure_preserved and global_structure_preserved
    )

    if new_suggestion_keys:
        safety_pass = False
    if new_high_impact_keys:
        safety_pass = False
    if not meaning_preserved or not structure_preserved:
        safety_pass = False

    # The final analysis is itself a fresh review. If no auto-fix remains,
    # convergence is proven even when the last allowed round applied patches.
    stable = bool(not final_auto_ids and safety_pass)

    return ReviewLoopResult(
        output=current,
        stable=stable,
        safety_pass=safety_pass,
        rounds=rounds,
        initial_suggestion_count=len(original_suggestions),
        final_suggestion_count=len(final_suggestions),
        initial_auto_fix_count=len(original_auto_ids),
        final_auto_fix_count=len(final_auto_ids),
        new_suggestion_keys=new_suggestion_keys,
        new_high_impact_keys=new_high_impact_keys,
        meaning_preserved=meaning_preserved,
        structure_preserved=structure_preserved,
    )
