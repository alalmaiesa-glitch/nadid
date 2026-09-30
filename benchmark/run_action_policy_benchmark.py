from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.contracts import (
    DocumentNode,
    EvidenceLocation,
    EvidenceTrace,
    Suggestion,
)
from app.pipeline.action_policy import apply_review_action
from app.pipeline.auto_apply import build_safe_auto_apply_plan
from app.pipeline.chunker import build_chunks
from app.pipeline.confidence import calibrate_evidence_trace
from app.pipeline.evidence import build_evidence_traces
from app.pipeline.memory import build_document_memory
from app.pipeline.protection import extract_protected_spans
from app.pipeline.reviewer import fast_review
from app.pipeline.semantic_review import semantic_review


def node(node_id: str, text: str, sequence: int = 0) -> DocumentNode:
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


def location(node_id: str = "n1") -> EvidenceLocation:
    return EvidenceLocation(
        document_id="benchmark.docx",
        node_id=node_id,
        sequence_no=0,
        node_type="paragraph",
        location_label="paragraph/block:1",
        source_anchor={"kind": "paragraph", "block_index": 0},
        excerpt="نص الدليل",
    )


def integrated(
    nodes: list[DocumentNode],
    *,
    suggestions: list[Suggestion] | None = None,
    with_protection: bool = True,
):
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    review = suggestions if suggestions is not None else fast_review(nodes)
    memory = build_document_memory(nodes, chunks, protected)
    issues = semantic_review(nodes, memory)
    traces = build_evidence_traces(
        nodes,
        suggestions=review,
        semantic_issues=issues,
        memory=memory,
        default_document_id="benchmark.docx",
        protected_spans=protected if with_protection else None,
    )
    return review, protected, traces


def first(
    traces,
    *,
    kind: str | None = None,
    category: str | None = None,
    reason_contains: str | None = None,
):
    for trace in traces:
        if kind is not None and trace.finding_kind != kind:
            continue
        if category is not None and trace.category != category:
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
    locations=None,
    values=None,
    trace_status: str = "complete",
    meaning_lock_status: str = "NOT_APPLICABLE",
):
    trace = EvidenceTrace(
        finding_id=finding_id,
        finding_kind=finding_kind,
        category=category,
        title="اختبار القرار",
        explanation="حالة حاكمة لسياسة الإجراء.",
        confidence=confidence,
        reason_code=reason_code,
        evidence_locations=locations or [],
        evidence_values=values or [],
        trace_status=trace_status,
        meaning_lock_status=meaning_lock_status,
    )
    return apply_review_action(calibrate_evidence_trace(trace))


def scenario_value(name: str):
    if name == "punctuation_auto_fix":
        _, _, traces = integrated([
            node("n1", "تم اعتماد الخطة ، ثم بدأ التنفيذ.")
        ])
        return first(traces, category="language")

    if name == "orthography_auto_fix":
        _, _, traces = integrated([
            node("n1", "هاذا التقرير معتمد.")
        ])
        return first(traces, category="language")

    if name == "style_suggest":
        _, _, traces = integrated([
            node(
                "n1",
                "تمت المعالجة في الوقت الراهن وفق الإجراء المعتمد.",
            )
        ])
        return first(traces, category="style")

    if name in {"semantic_require_review", "semantic_high_never_auto"}:
        _, _, traces = integrated([
            node("n1", "تم اعتماد الخطة التشغيلية للمشروع.", 0),
            node("n2", "تم إلغاء الخطة التشغيلية للمشروع.", 1),
        ])
        return first(
            traces,
            kind="semantic_issue",
            reason_contains="decision_conflict",
        )

    if name in {"fact_require_review", "fact_high_never_auto"}:
        _, _, traces = integrated([
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
        return first(traces, kind="fact_conflict")

    if name == "partial_require_review":
        return direct_trace(
            finding_id="partial",
            category="language",
            confidence=0.99,
            locations=[],
            values=["هاذا", "هذا"],
            trace_status="partial",
            meaning_lock_status="PASS",
        )

    if name == "meaning_lock_block":
        nodes = [node("n1", "تبلغ القيمة 100 ريال.")]
        suggestion = Suggestion(
            id="dangerous",
            node_id="n1",
            category="language",
            title="تعديل تجريبي",
            explanation="اختبار منع تغيير المعنى.",
            original="100 ريال",
            replacement="100 دولار",
            confidence=0.999,
        )
        _, _, traces = integrated(nodes, suggestions=[suggestion])
        return first(traces, kind="suggestion")

    if name == "meaning_lock_unknown":
        _, _, traces = integrated(
            [node("n1", "تم اعتماد الخطة ، ثم بدأ التنفيذ.")],
            with_protection=False,
        )
        return first(traces, category="language")

    if name == "replacement_missing":
        nodes = [node("n1", "هاذا التقرير.")]
        suggestion = Suggestion(
            id="no-replacement",
            node_id="n1",
            category="language",
            title="ملاحظة لغوية",
            explanation="لا يوجد بديل جاهز.",
            original="هاذا",
            replacement=None,
            confidence=0.99,
        )
        _, _, traces = integrated(nodes, suggestions=[suggestion])
        return first(traces, kind="suggestion")

    if name == "low_confidence_language":
        return direct_trace(
            finding_id="low-language",
            category="language",
            confidence=0.65,
            locations=[location()],
            values=["صيغة", "صياغة"],
            meaning_lock_status="PASS",
        )

    if name in {"protection_block", "style_high_source_never_auto"}:
        if name == "protection_block":
            return direct_trace(
                finding_id="protection",
                category="protection",
                confidence=0.99,
                reason_code="meaning_lock:block",
                locations=[location()],
                values=["100 ريال", "100 دولار"],
                meaning_lock_status="BLOCK",
            )
        return direct_trace(
            finding_id="style-high",
            category="style",
            confidence=1.0,
            locations=[location()],
            values=["في الوقت الراهن", "حاليًا"],
            meaning_lock_status="PASS",
        )

    if name == "planner_selects_safe_only":
        nodes = [
            node("n1", "هاذا التقرير ، ثم بدأ التنفيذ.", 0),
            node(
                "n2",
                "تمت المعالجة في الوقت الراهن وفق الإجراء.",
                1,
            ),
        ]
        protected = extract_protected_spans(nodes)
        suggestions = fast_review(nodes)
        return build_safe_auto_apply_plan(
            nodes,
            suggestions,
            protected,
        )

    if name == "planner_blocks_meaning_change":
        nodes = [node("n1", "تبلغ القيمة 100 ريال.")]
        protected = extract_protected_spans(nodes)
        suggestions = [
            Suggestion(
                id="dangerous",
                node_id="n1",
                category="language",
                title="تعديل تجريبي",
                explanation="اختبار الحماية.",
                original="100 ريال",
                replacement="100 دولار",
                confidence=0.999,
            )
        ]
        return build_safe_auto_apply_plan(
            nodes,
            suggestions,
            protected,
        )

    if name == "planner_revalidates_stale":
        nodes = [node("n1", "هاذا التقرير معتمد.")]
        protected = extract_protected_spans(nodes)
        suggestions = [
            Suggestion(
                id="first",
                node_id="n1",
                category="language",
                title="رسم إملائي",
                explanation="التصحيح الأول.",
                original="هاذا",
                replacement="هذا",
                confidence=0.995,
            ),
            Suggestion(
                id="second",
                node_id="n1",
                category="language",
                title="رسم إملائي",
                explanation="التصحيح الثاني.",
                original="هاذا",
                replacement="هذا",
                confidence=0.995,
            ),
        ]
        return build_safe_auto_apply_plan(
            nodes,
            suggestions,
            protected,
        )

    if name == "action_reason_present":
        _, _, traces = integrated([
            node("n1", "هاذا التقرير معتمد.")
        ])
        return first(traces, category="language")

    if name == "auto_flag_equivalence":
        _, _, traces = integrated([
            node("n1", "هاذا التقرير ، ثم بدأ التنفيذ.")
        ])
        return traces

    if name == "safe_punctuation_in_critical_clause":
        _, _, traces = integrated([
            node(
                "n1",
                "لا يتحمل الطرف الأول تكاليف النقل ، وفق العقد.",
            )
        ])
        return first(traces, category="language")

    raise ValueError(f"Unknown scenario: {name}")


def evaluate(case: dict) -> dict:
    value = scenario_value(case["scenario"])
    expected = case.get("expect", {})
    failures: list[str] = []

    if hasattr(value, "patches") and hasattr(value, "skipped"):
        if "patches" in expected and len(value.patches) != expected["patches"]:
            failures.append(
                f"patches:{len(value.patches)}!={expected['patches']}"
            )
        if (
            "min_skipped" in expected
            and len(value.skipped) < expected["min_skipped"]
        ):
            failures.append(
                f"skipped_below_min:{len(value.skipped)}"
            )
        if "skip_reason" in expected:
            reasons = {item.reason for item in value.skipped}
            if expected["skip_reason"] not in reasons:
                failures.append(
                    f"skip_reason_missing:{sorted(reasons)}"
                )
        return {
            "id": case["id"],
            "scenario": case["scenario"],
            "passed": not failures,
            "failures": failures,
            "patches": len(value.patches),
            "skipped": len(value.skipped),
        }

    if isinstance(value, list):
        if expected.get("auto_matches_action"):
            for trace in value:
                if trace.auto_apply_allowed != (
                    trace.recommended_action == "auto_fix"
                ):
                    failures.append(
                        f"auto_flag_mismatch:{trace.finding_id}"
                    )
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

    if (
        "action" in expected
        and trace.recommended_action != expected["action"]
    ):
        failures.append(
            f"action:{trace.recommended_action}!={expected['action']}"
        )

    if (
        "auto" in expected
        and trace.auto_apply_allowed != expected["auto"]
    ):
        failures.append(
            f"auto:{trace.auto_apply_allowed}!={expected['auto']}"
        )

    if (
        "meaning_lock" in expected
        and trace.meaning_lock_status != expected["meaning_lock"]
    ):
        failures.append(
            f"meaning_lock:{trace.meaning_lock_status}"
        )

    if (
        "min_action_reasons" in expected
        and len(trace.action_reasons)
        < expected["min_action_reasons"]
    ):
        failures.append("action_reasons_missing")

    if trace.auto_apply_allowed:
        if trace.recommended_action != "auto_fix":
            failures.append("auto_without_auto_fix_action")
        if trace.meaning_lock_status != "PASS":
            failures.append("auto_without_meaning_lock_pass")
        if trace.trace_status != "complete":
            failures.append("auto_with_partial_evidence")
        if trace.category != "language":
            failures.append("auto_non_language")
        if trace.severity in {"critical", "high"}:
            failures.append("auto_high_impact")

    return {
        "id": case["id"],
        "scenario": case["scenario"],
        "passed": not failures,
        "failures": failures,
        "action": trace.recommended_action,
        "auto": trace.auto_apply_allowed,
        "meaning_lock": trace.meaning_lock_status,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        default="benchmark/action_policy/v1.json",
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
        "Review Action & Auto-Apply Benchmark V1: "
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
