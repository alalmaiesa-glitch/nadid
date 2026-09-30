from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.contracts import DocumentNode, SemanticIssue, Suggestion
from app.pipeline.chunker import build_chunks
from app.pipeline.consistency import review_document_set
from app.pipeline.evidence import build_evidence_traces
from app.pipeline.memory import build_document_memory
from app.pipeline.protection import extract_protected_spans
from app.pipeline.reviewer import fast_review
from app.pipeline.semantic_review import semantic_review


FILLER = "محتوى فاصل لا يتضمن ادعاءً متعارضًا أو قرارًا متعلقًا بالحالة."


def node(
    node_id: str,
    text: str,
    sequence: int,
    node_type: str = "paragraph",
    source_anchor: dict | None = None,
) -> DocumentNode:
    return DocumentNode(
        id=node_id,
        type=node_type,
        text=text,
        sequence_no=sequence,
        source_anchor=source_anchor or {
            "kind": node_type,
            "block_index": sequence,
        },
    )


def analyze(nodes: list[DocumentNode], document_id: str = "single.docx"):
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    suggestions = fast_review(nodes)
    memory = build_document_memory(nodes, chunks, protected)
    issues = semantic_review(nodes, memory)
    traces = build_evidence_traces(
        nodes,
        suggestions=suggestions,
        semantic_issues=issues,
        memory=memory,
        default_document_id=document_id,
    )
    return suggestions, memory, issues, traces


def pick(traces, kind: str, reason_contains: str | None = None):
    matches = [
        trace
        for trace in traces
        if trace.finding_kind == kind
        and (
            reason_contains is None
            or reason_contains in trace.reason_code
        )
    ]
    return matches[0] if matches else None


def build_case(case: dict):
    scenario = case["scenario"]

    if scenario == "suggestion":
        nodes = [node("n1", case["text"], 0)]
        _, _, _, traces = analyze(nodes)
        return pick(traces, "suggestion"), {}

    if scenario == "definition_conflict":
        nodes = [
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
        ]
        _, _, _, traces = analyze(nodes)
        return pick(traces, "semantic_issue", "definition_conflict"), {}

    if scenario == "fact_conflict":
        nodes = [
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
        ]
        _, _, _, traces = analyze(nodes)
        return pick(traces, "fact_conflict"), {}

    if scenario in {
        "cross_document_definition",
        "cross_document_node_identity",
    }:
        report = review_document_set(
            {
                "A": [
                    node(
                        "n1",
                        "يقصد بمصطلح «مقدم الخدمة»: الجهة المتعاقدة لتنفيذ الأعمال.",
                        0,
                    )
                ],
                "B": [
                    node(
                        "n1",
                        "يقصد بمصطلح «مقدم الخدمة»: الجهة الحكومية المالكة للمشروع.",
                        0,
                    )
                ],
            }
        )
        return pick(
            report.evidence_traces,
            "semantic_issue",
            "definition_conflict",
        ), {}

    if scenario == "cross_document_fact":
        report = review_document_set(
            {
                "A": [
                    node(
                        "n1",
                        "بلغت الطاقة التشغيلية السنوية للمصنع 2000000 وحدة.",
                        0,
                    )
                ],
                "B": [
                    node(
                        "n1",
                        "إجمالي القدرة الإنتاجية للمصنع سنويًا تساوي 1800000 وحدة.",
                        0,
                    )
                ],
            }
        )
        return pick(report.evidence_traces, "fact_conflict"), {}

    if scenario == "long_range_decision":
        filler_count = int(case.get("filler_count", 420))
        nodes = [
            node("n1", "تم اعتماد الخطة التشغيلية للمشروع.", 0),
            *[
                node(f"f{index}", FILLER, index)
                for index in range(1, filler_count + 1)
            ],
            node(
                "n-last",
                "تم إلغاء الخطة التشغيلية للمشروع.",
                filler_count + 1,
            ),
        ]
        report = review_document_set({"D1": nodes})
        return pick(
            report.evidence_traces,
            "semantic_issue",
            "decision_conflict",
        ), {}

    if scenario == "long_range_fact":
        filler_count = int(case.get("filler_count", 420))
        nodes = [
            node(
                "n1",
                "بلغت الطاقة التشغيلية السنوية للمصنع 2000000 وحدة.",
                0,
            ),
            *[
                node(f"f{index}", FILLER, index)
                for index in range(1, filler_count + 1)
            ],
            node(
                "n-last",
                "إجمالي القدرة الإنتاجية للمصنع سنويًا تساوي 1800000 وحدة.",
                filler_count + 1,
            ),
        ]
        report = review_document_set({"D1": nodes})
        return pick(report.evidence_traces, "fact_conflict"), {}

    if scenario == "table_cell_suggestion":
        nodes = [
            node(
                "t1",
                "هاذا",
                0,
                node_type="table_cell",
                source_anchor={
                    "kind": "table_cell",
                    "block_index": 3,
                    "row": 1,
                    "cell": 2,
                },
            )
        ]
        _, _, _, traces = analyze(nodes)
        return pick(traces, "suggestion"), {}

    if scenario == "paragraph_block_anchor":
        nodes = [
            node(
                "p1",
                "هاذا التقرير معتمد.",
                0,
                source_anchor={
                    "kind": "paragraph",
                    "block_index": 5,
                    "style": "Normal",
                },
            )
        ]
        _, _, _, traces = analyze(nodes)
        return pick(traces, "suggestion"), {}

    if scenario == "missing_suggestion_source":
        suggestion = Suggestion(
            id="missing-suggestion",
            node_id="missing",
            category="language",
            title="اختبار",
            explanation="اختبار مسار الدليل المفقود.",
            original="هاذا",
            replacement="هذا",
            confidence=0.99,
        )
        traces = build_evidence_traces([], suggestions=[suggestion])
        return pick(traces, "suggestion"), {}

    if scenario == "missing_semantic_evidence":
        nodes = [node("n1", "المشروع معتمد.", 0)]
        issue = SemanticIssue(
            id="missing-semantic",
            node_id="n1",
            issue_type="polarity_conflict",
            title="اختبار تعارض",
            explanation="اختبار اكتمال الدليل.",
            original="المشروع معتمد.",
            evidence_node_ids=["n1", "missing"],
            evidence_values=["معتمد", "غير معتمد"],
            confidence=0.98,
        )
        traces = build_evidence_traces(
            nodes,
            semantic_issues=[issue],
            default_document_id="single.docx",
        )
        return pick(traces, "semantic_issue"), {}

    raise ValueError(f"Unknown scenario: {scenario}")


def evaluate(case: dict) -> dict:
    trace, metadata = build_case(case)
    failures: list[str] = []
    expected = case.get("expect", {})

    if trace is None:
        failures.append("trace_missing")
        return {
            "id": case["id"],
            "scenario": case["scenario"],
            "passed": False,
            "failures": failures,
        }

    want_complete = expected.get("complete")
    if want_complete is not None:
        actual_complete = trace.trace_status == "complete"
        if actual_complete != want_complete:
            failures.append(
                f"complete:{actual_complete}!={want_complete}"
            )

    if expected.get("status") and trace.trace_status != expected["status"]:
        failures.append(
            f"status:{trace.trace_status}!={expected['status']}"
        )

    if "locations" in expected:
        if len(trace.evidence_locations) != expected["locations"]:
            failures.append(
                f"locations:{len(trace.evidence_locations)}"
                f"!={expected['locations']}"
            )

    if "min_locations" in expected:
        if len(trace.evidence_locations) < expected["min_locations"]:
            failures.append(
                f"locations_below_min:{len(trace.evidence_locations)}"
            )

    if "values" in expected:
        if len(trace.evidence_values) < expected["values"]:
            failures.append(
                f"values_below_min:{len(trace.evidence_values)}"
            )

    if "document_ids" in expected:
        actual = sorted({
            location.document_id
            for location in trace.evidence_locations
            if location.document_id
        })
        if actual != sorted(expected["document_ids"]):
            failures.append(f"document_ids:{actual}")

    if "min_documents" in expected:
        documents = {
            location.document_id
            for location in trace.evidence_locations
            if location.document_id
        }
        if len(documents) < expected["min_documents"]:
            failures.append(
                f"documents_below_min:{len(documents)}"
            )

    if "excerpt_contains" in expected:
        if not any(
            expected["excerpt_contains"] in location.excerpt
            for location in trace.evidence_locations
        ):
            failures.append("excerpt_missing_expected_text")

    if "reason_code" in expected:
        if trace.reason_code != expected["reason_code"]:
            failures.append(
                f"reason_code:{trace.reason_code}"
            )

    if "reason_prefix" in expected:
        if not trace.reason_code.startswith(expected["reason_prefix"]):
            failures.append(
                f"reason_prefix:{trace.reason_code}"
            )

    if "location_contains" in expected:
        labels = " ".join(
            location.location_label
            for location in trace.evidence_locations
        )
        for needle in expected["location_contains"]:
            if needle not in labels:
                failures.append(f"location_missing:{needle}")

    if "min_sequence_distance" in expected:
        sequences = sorted(
            location.sequence_no
            for location in trace.evidence_locations
        )
        distance = sequences[-1] - sequences[0] if len(sequences) >= 2 else 0
        if distance < expected["min_sequence_distance"]:
            failures.append(
                f"sequence_distance:{distance}"
            )

    if "original_node_ids" in expected:
        originals = {
            location.original_node_id
            for location in trace.evidence_locations
            if location.original_node_id
        }
        for wanted in expected["original_node_ids"]:
            if wanted not in originals:
                failures.append(
                    f"missing_original_node_id:{wanted}"
                )

    if not trace.title:
        failures.append("title_missing")
    if not trace.explanation:
        failures.append("explanation_missing")
    if not trace.reason_code:
        failures.append("reason_missing")
    if not 0 <= trace.confidence <= 1:
        failures.append("confidence_invalid")

    return {
        "id": case["id"],
        "scenario": case["scenario"],
        "passed": not failures,
        "failures": failures,
        "trace_status": trace.trace_status,
        "finding_kind": trace.finding_kind,
        "locations": len(trace.evidence_locations),
        "documents": sorted({
            location.document_id
            for location in trace.evidence_locations
            if location.document_id
        }),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        default="benchmark/evidence/v1.json",
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
        f"Evidence Benchmark V1: {passed}/{total} = {score:.1%}"
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
