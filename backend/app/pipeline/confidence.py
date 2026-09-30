from __future__ import annotations

from app.contracts import EvidenceTrace


SEVERITY_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}


def _evidence_sufficient(trace: EvidenceTrace) -> bool:
    if trace.trace_status != "complete":
        return False

    locations = len(trace.evidence_locations)
    values = len(trace.evidence_values)

    if trace.finding_kind == "suggestion":
        return locations >= 1 and values >= 1

    if trace.finding_kind in {"semantic_issue", "fact_conflict"}:
        return locations >= 2 and values >= 2

    return False


def _confidence_level(score: float) -> str:
    if score >= 0.90:
        return "high"
    if score >= 0.70:
        return "medium"
    return "low"


def _semantic_issue_type(trace: EvidenceTrace) -> str:
    prefix = "semantic:"
    if trace.reason_code.startswith(prefix):
        return trace.reason_code[len(prefix):]
    return ""


def _severity(
    trace: EvidenceTrace,
    calibrated: float,
    sufficient: bool,
) -> str:
    if trace.category == "protection":
        if sufficient and calibrated >= 0.95:
            return "critical"
        if sufficient and calibrated >= 0.85:
            return "high"
        return "medium"

    if trace.finding_kind == "fact_conflict":
        if sufficient and calibrated >= 0.85:
            return "high"
        return "medium"

    if trace.finding_kind == "semantic_issue":
        issue_type = _semantic_issue_type(trace)
        if (
            issue_type in {"polarity_conflict", "decision_conflict"}
            and sufficient
            and calibrated >= 0.90
        ):
            return "high"
        return "medium"

    if trace.category == "language":
        return "medium" if calibrated >= 0.70 else "low"

    return "low"


def calibrate_evidence_trace(trace: EvidenceTrace) -> EvidenceTrace:
    """
    Apply Nadid operational confidence policy V1.

    The resulting confidence is a deterministic product score, not an
    empirically calibrated probability. Human Gold is required before
    interpreting it as observed correctness probability.
    """
    source = (
        trace.source_confidence
        if trace.source_confidence is not None
        else trace.confidence
    )
    calibrated = float(source)
    reasons: list[str] = []
    sufficient = _evidence_sufficient(trace)

    if not sufficient:
        calibrated = min(calibrated, 0.59)
        reasons.append("insufficient_or_partial_evidence")
    elif trace.category == "style":
        calibrated = min(calibrated, 0.79)
        reasons.append("style_judgment_cap")
    elif trace.finding_kind == "suggestion":
        if trace.category == "language":
            calibrated = min(calibrated, 0.94)
            reasons.append("deterministic_language_rule_cap")
        elif trace.category == "protection":
            calibrated = min(calibrated, 0.99)
            reasons.append("complete_protection_evidence")
    elif trace.finding_kind == "semantic_issue":
        issue_type = _semantic_issue_type(trace)
        if issue_type in {"definition_conflict", "abbreviation_conflict"}:
            calibrated = min(calibrated, 0.93)
            reasons.append("semantic_equivalence_uncertainty_cap")
        else:
            calibrated = min(calibrated, 0.96)
            reasons.append("complete_semantic_conflict_cap")
    elif trace.finding_kind == "fact_conflict":
        calibrated = min(0.95, calibrated + 0.02)
        reasons.append("two_sided_fact_evidence_boost")

    calibrated = round(max(0.0, min(1.0, calibrated)), 4)
    severity = _severity(trace, calibrated, sufficient)

    # Strong wording is gated separately from impact severity. A finding
    # may be important but still presented tentatively if evidence is weak.
    strong_assertion = bool(
        sufficient
        and calibrated >= 0.90
        and trace.category != "style"
    )

    if strong_assertion:
        reasons.append("strong_assertion_gate_passed")
    else:
        reasons.append("strong_assertion_gate_not_met")

    return trace.model_copy(
        update={
            "source_confidence": source,
            "confidence": calibrated,
            "confidence_level": _confidence_level(calibrated),
            "severity": severity,
            "strong_assertion": strong_assertion,
            "calibration_method": "policy_v1_unvalidated",
            "calibration_reasons": reasons,
        }
    )


def calibrate_evidence_traces(
    traces: list[EvidenceTrace],
) -> list[EvidenceTrace]:
    calibrated = [calibrate_evidence_trace(trace) for trace in traces]
    calibrated.sort(
        key=lambda trace: (
            -SEVERITY_ORDER[trace.severity],
            not trace.strong_assertion,
            -trace.confidence,
            trace.finding_kind,
            trace.finding_id,
        )
    )
    return calibrated
