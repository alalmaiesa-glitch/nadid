from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.contracts import DocumentNode, EvidenceLocation, EvidenceTrace
from app.pipeline.chunker import build_chunks
from app.pipeline.confidence import (
    calibrate_evidence_trace,
    calibrate_evidence_traces,
)
from app.pipeline.evidence import build_evidence_traces
from app.pipeline.memory import build_document_memory
from app.pipeline.protection import extract_protected_spans
from app.pipeline.reviewer import fast_review
from app.pipeline.semantic_review import semantic_review


def node(node_id: str, text: str, sequence: int) -> DocumentNode:
    return DocumentNode(
        id=node_id,
        type="paragraph",
        text=text,
        sequence_no=sequence,
        source_anchor={
            "kind": "paragraph",
            "block_index": sequence,
        },
    )


def location(
    node_id: str = "n1",
    sequence: int = 0,
    excerpt: str = "نص الدليل",
) -> EvidenceLocation:
    return EvidenceLocation(
        document_id="benchmark.docx",
        node_id=node_id,
        sequence_no=sequence,
        node_type="paragraph",
        location_label=f"paragraph/block:{sequence + 1}",
        source_anchor={
            "kind": "paragraph",
            "block_index": sequence,
        },
        excerpt=excerpt,
    )


def integrated_traces(nodes: list[DocumentNode]):
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    suggestions = fast_review(nodes)
    memory = build_document_memory(nodes, chunks, protected)
    semantic_issues = semantic_review(nodes, memory)
    return build_evidence_traces(
        nodes,
        suggestions=suggestions,
        semantic_issues=semantic_issues,
        memory=memory,
        default_document_id="benchmark.docx",
    )


def first_kind(traces, kind: str, reason_contains: str | None = None):
    for trace in traces:
        if trace.finding_kind != kind:
            continue
        if (
            reason_contains is not None
            and reason_contains not in trace.reason_code
        ):
            continue
        return trace
    return None


def direct_trace(
    *,
    finding_id: str,
    finding_kind: str = "suggestion",
    category: str = "language",
    confidence: float = 0.99,
    reason_code: str = "review_rule_match",
    locations: list[EvidenceLocation] | None = None,
    values: list[str] | None = None,
    trace_status: str = "complete",
) -> EvidenceTrace:
    return EvidenceTrace(
        finding_id=finding_id,
        finding_kind=finding_kind,
        category=category,
        title="اختبار المعايرة",
        explanation="حالة اختبار لسياسة الثقة والخطورة.",
        confidence=confidence,
        reason_code=reason_code,
        evidence_locations=locations or [],
        evidence_values=values or [],
        trace_status=trace_status,
    )


def scenario_trace(name: str):
    if name in {
        "language_suggestion",
        "method_marker",
        "source_confidence_preserved",
    }:
        traces = integrated_traces([
            node("n1", "هاذا التقرير معتمد.", 0)
        ])
        return first_kind(traces, "suggestion")

    if name == "style_suggestion":
        traces = integrated_traces([
            node(
                "n1",
                "تمت المعالجة في الوقت الراهن وفق الإجراء المعتمد.",
                0,
            )
        ])
        return first_kind(traces, "suggestion")

    if name == "definition_conflict":
        traces = integrated_traces([
            node(
                "n1",
                "يقصد بمصطلح «مقدم الخدمة»: الجهة المتعاقدة لتنفيذ الأعمال.",
                0,
            ),
            node(
                "n2",
                "يقصد بمصطلح «مقدم الخدمة»: الجهة الحكومية المالكة للمشروع.",
                1,
            ),
        ])
        return first_kind(
            traces,
            "semantic_issue",
            "definition_conflict",
        )

    if name == "decision_conflict":
        traces = integrated_traces([
            node("n1", "تم اعتماد الخطة التشغيلية للمشروع.", 0),
            node("n2", "تم إلغاء الخطة التشغيلية للمشروع.", 1),
        ])
        return first_kind(
            traces,
            "semantic_issue",
            "decision_conflict",
        )

    if name == "polarity_conflict":
        traces = integrated_traces([
            node("n1", "المشروع معتمد وفق المحضر النهائي.", 0),
            node("n2", "المشروع غير معتمد وفق النسخة الأخيرة.", 1),
        ])
        return first_kind(
            traces,
            "semantic_issue",
            "polarity_conflict",
        )

    if name == "fact_conflict":
        traces = integrated_traces([
            node(
                "n1",
                "بلغت الطاقة التشغيلية السنوية للمصنع 2000000 وحدة.",
                0,
            ),
            node(
                "n2",
                "إجمالي القدرة الإنتاجية للمصنع سنويًا تساوي 1800000 وحدة.",
                1,
            ),
        ])
        return first_kind(traces, "fact_conflict")

    if name == "partial_semantic":
        return calibrate_evidence_trace(
            direct_trace(
                finding_id="partial-semantic",
                finding_kind="semantic_issue",
                category="consistency",
                confidence=0.99,
                reason_code="semantic:decision_conflict",
                locations=[location()],
                values=["اعتماد", "إلغاء"],
                trace_status="partial",
            )
        )

    if name == "partial_language":
        return calibrate_evidence_trace(
            direct_trace(
                finding_id="partial-language",
                category="language",
                confidence=0.99,
                locations=[],
                values=["هاذا", "هذا"],
                trace_status="partial",
            )
        )

    if name == "protection_complete":
        return calibrate_evidence_trace(
            direct_trace(
                finding_id="protection-complete",
                category="protection",
                confidence=0.99,
                reason_code="meaning_lock:block",
                locations=[location()],
                values=["100 ريال", "100 دولار"],
            )
        )

    if name == "protection_partial":
        return calibrate_evidence_trace(
            direct_trace(
                finding_id="protection-partial",
                category="protection",
                confidence=0.99,
                reason_code="meaning_lock:block",
                locations=[],
                values=["100 ريال", "100 دولار"],
                trace_status="partial",
            )
        )

    if name == "low_confidence_language":
        return calibrate_evidence_trace(
            direct_trace(
                finding_id="low-language",
                category="language",
                confidence=0.65,
                locations=[location()],
                values=["صيغة", "صياغة"],
            )
        )

    if name == "partial_fact":
        return calibrate_evidence_trace(
            direct_trace(
                finding_id="partial-fact",
                finding_kind="fact_conflict",
                category="consistency",
                confidence=0.99,
                reason_code="fact:value_conflict",
                locations=[location()],
                values=["12", "18"],
                trace_status="partial",
            )
        )

    if name == "style_raw_one":
        return calibrate_evidence_trace(
            direct_trace(
                finding_id="style-one",
                category="style",
                confidence=1.0,
                locations=[location()],
                values=["في الوقت الراهن", "حاليًا"],
            )
        )

    if name == "semantic_insufficient_locations":
        return calibrate_evidence_trace(
            direct_trace(
                finding_id="semantic-insufficient",
                finding_kind="semantic_issue",
                category="consistency",
                confidence=0.99,
                reason_code="semantic:polarity_conflict",
                locations=[location()],
                values=["معتمد", "غير معتمد"],
                trace_status="complete",
            )
        )

    if name == "non_protection_never_critical":
        traces = [
            calibrate_evidence_trace(
                direct_trace(
                    finding_id="language-high",
                    category="language",
                    confidence=1.0,
                    locations=[location()],
                    values=["هاذا", "هذا"],
                )
            ),
            calibrate_evidence_trace(
                direct_trace(
                    finding_id="fact-high",
                    finding_kind="fact_conflict",
                    category="consistency",
                    confidence=1.0,
                    reason_code="fact:value_conflict",
                    locations=[location("a"), location("b", 1)],
                    values=["12", "18"],
                )
            ),
            calibrate_evidence_trace(
                direct_trace(
                    finding_id="semantic-high",
                    finding_kind="semantic_issue",
                    category="consistency",
                    confidence=1.0,
                    reason_code="semantic:decision_conflict",
                    locations=[location("a"), location("b", 1)],
                    values=["اعتماد", "إلغاء"],
                )
            ),
        ]
        return traces

    if name == "severity_sort":
        traces = [
            direct_trace(
                finding_id="low",
                category="style",
                confidence=1.0,
                locations=[location("l")],
                values=["أ", "ب"],
            ),
            direct_trace(
                finding_id="medium",
                category="language",
                confidence=0.99,
                locations=[location("m")],
                values=["هاذا", "هذا"],
            ),
            direct_trace(
                finding_id="high",
                finding_kind="semantic_issue",
                category="consistency",
                confidence=0.98,
                reason_code="semantic:decision_conflict",
                locations=[location("h1"), location("h2", 1)],
                values=["اعتماد", "إلغاء"],
            ),
            direct_trace(
                finding_id="critical",
                category="protection",
                confidence=0.99,
                reason_code="meaning_lock:block",
                locations=[location("c")],
                values=["100 ريال", "100 دولار"],
            ),
        ]
        return calibrate_evidence_traces(traces)

    raise ValueError(f"Unknown scenario: {name}")


def evaluate(case: dict) -> dict:
    value = scenario_trace(case["scenario"])
    expected = case.get("expect", {})
    failures: list[str] = []

    if isinstance(value, list):
        if "ordered_severity" in expected:
            actual = [trace.severity for trace in value]
            if actual != expected["ordered_severity"]:
                failures.append(f"severity_order:{actual}")
        if "not_severity" in expected:
            if any(
                trace.severity == expected["not_severity"]
                for trace in value
            ):
                failures.append("unexpected_critical_non_protection")
        return {
            "id": case["id"],
            "scenario": case["scenario"],
            "passed": not failures,
            "failures": failures,
        }

    trace = value
    if trace is None:
        return {
            "id": case["id"],
            "scenario": case["scenario"],
            "passed": False,
            "failures": ["trace_missing"],
        }

    scalar_checks = {
        "severity": trace.severity,
        "confidence_level": trace.confidence_level,
        "strong_assertion": trace.strong_assertion,
        "calibration_method": trace.calibration_method,
    }
    for key, actual in scalar_checks.items():
        if key in expected and actual != expected[key]:
            failures.append(
                f"{key}:{actual}!={expected[key]}"
            )

    if (
        "not_severity" in expected
        and trace.severity == expected["not_severity"]
    ):
        failures.append(f"forbidden_severity:{trace.severity}")

    if (
        "confidence_min" in expected
        and trace.confidence < expected["confidence_min"]
    ):
        failures.append(
            f"confidence_below_min:{trace.confidence}"
        )

    if (
        "confidence_max" in expected
        and trace.confidence > expected["confidence_max"]
    ):
        failures.append(
            f"confidence_above_max:{trace.confidence}"
        )

    if (
        "source_confidence_min" in expected
        and (
            trace.source_confidence is None
            or trace.source_confidence
            < expected["source_confidence_min"]
        )
    ):
        failures.append(
            f"source_confidence_below_min:{trace.source_confidence}"
        )

    if (
        trace.strong_assertion
        and (
            trace.trace_status != "complete"
            or trace.confidence < 0.90
        )
    ):
        failures.append("strong_assertion_without_gate")

    if (
        trace.severity == "critical"
        and trace.category != "protection"
    ):
        failures.append("critical_non_protection")

    return {
        "id": case["id"],
        "scenario": case["scenario"],
        "passed": not failures,
        "failures": failures,
        "severity": trace.severity,
        "confidence": trace.confidence,
        "source_confidence": trace.source_confidence,
        "confidence_level": trace.confidence_level,
        "strong_assertion": trace.strong_assertion,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        default="benchmark/confidence/v1.json",
    )
    parser.add_argument("--report")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    payload = json.loads(
        Path(args.suite).read_text(encoding="utf-8")
    )
    results = [evaluate(case) for case in payload["cases"]]
    passed = sum(item["passed"] for item in results)
    total = len(results)
    score = passed / total if total else 0.0

    report = {
        "schema_version": 1,
        "suite": args.suite,
        "passed": passed,
        "total": total,
        "score": round(score, 4),
        "failures": [
            item for item in results if not item["passed"]
        ],
        "results": results,
    }

    print(
        f"Confidence & Severity Benchmark V1: "
        f"{passed}/{total} = {score:.1%}"
    )
    if report["failures"]:
        print("\nFailures:")
        for item in report["failures"]:
            print(
                f"- {item['id']}: "
                + ", ".join(item["failures"])
            )

    if args.report:
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.enforce and report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
