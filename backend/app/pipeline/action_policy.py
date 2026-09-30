from __future__ import annotations

from app.contracts import EvidenceTrace


def apply_review_action(trace: EvidenceTrace) -> EvidenceTrace:
    """
    Convert evidence + calibrated confidence into one user-facing action.

    Auto-fix is deliberately narrower than "strong assertion":
    it is available only for complete, high-confidence language suggestions
    that independently pass Meaning Lock and include a concrete replacement.
    """
    reasons: list[str] = []

    if trace.meaning_lock_status == "BLOCK":
        action = "block"
        reasons.append("meaning_lock_block")
    elif trace.category == "protection":
        action = "block"
        reasons.append("meaning_safety_requires_block")
    elif trace.trace_status != "complete":
        action = "require_review"
        reasons.append("partial_evidence_requires_review")
    elif trace.finding_kind in {"semantic_issue", "fact_conflict"}:
        action = "require_review"
        reasons.append("cross_evidence_conflict_requires_review")
    elif trace.category == "consistency":
        action = "require_review"
        reasons.append("consistency_finding_requires_review")
    elif trace.severity in {"critical", "high"}:
        action = "require_review"
        reasons.append("high_impact_never_auto_applied")
    elif trace.category == "style":
        action = "suggest"
        reasons.append("style_is_advisory")
    elif trace.finding_kind == "suggestion" and trace.category == "language":
        has_replacement = len(trace.evidence_values) >= 2
        if not has_replacement:
            action = "require_review"
            reasons.append("replacement_missing")
        elif trace.meaning_lock_status != "PASS":
            action = "suggest"
            reasons.append("meaning_lock_not_verified")
        elif not trace.strong_assertion:
            action = "suggest"
            reasons.append("strong_assertion_gate_not_met")
        elif trace.confidence < 0.93:
            action = "suggest"
            reasons.append("auto_fix_confidence_threshold_not_met")
        else:
            action = "auto_fix"
            reasons.append("deterministic_language_safe_auto_fix")
    else:
        action = "require_review"
        reasons.append("unsupported_finding_requires_review")

    return trace.model_copy(
        update={
            "recommended_action": action,
            "auto_apply_allowed": action == "auto_fix",
            "action_reasons": reasons,
        }
    )


def apply_review_actions(
    traces: list[EvidenceTrace],
) -> list[EvidenceTrace]:
    return [apply_review_action(trace) for trace in traces]
