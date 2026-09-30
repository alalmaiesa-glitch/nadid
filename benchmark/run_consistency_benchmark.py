from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from app.contracts import DocumentNode
from app.pipeline.consistency import review_document_set


def _make_nodes(document: dict, filler_text: str) -> list[DocumentNode]:
    texts: list[str] = []

    if "nodes" in document:
        texts.extend(document["nodes"])
    else:
        texts.append(document["head"])
        texts.extend(
            filler_text
            for _ in range(int(document.get("filler_count", 0)))
        )
        texts.append(document["tail"])

    return [
        DocumentNode(
            id=f"n{index + 1}",
            type="paragraph",
            text=text,
            sequence_no=index,
            source_anchor={"benchmark": "consistency_v1"},
        )
        for index, text in enumerate(texts)
    ]


def _fact_conflict_documents(report, conflict) -> list[str]:
    facts = {fact.id: fact for fact in report.memory.facts}
    node_ids = [
        facts[fact_id].node_id
        for fact_id in conflict.fact_ids
        if fact_id in facts
    ]
    return report.evidence_documents(node_ids)


def evaluate_case(case: dict, filler_text: str) -> dict:
    documents = {
        item["id"]: _make_nodes(item, filler_text)
        for item in case["documents"]
    }
    report = review_document_set(documents)
    expected = case.get("expect", {})
    failures: list[str] = []

    semantic_types = [
        issue.issue_type for issue in report.semantic_issues
    ]

    for issue_type in expected.get("semantic_issue_types", []):
        matches = [
            issue
            for issue in report.semantic_issues
            if issue.issue_type == issue_type
        ]
        if not matches:
            failures.append(f"missing_semantic_issue:{issue_type}")
            continue

        if expected.get("cross_document") is True:
            if not any(
                len(report.evidence_documents(issue.evidence_node_ids)) >= 2
                for issue in matches
            ):
                failures.append(
                    f"semantic_issue_not_cross_document:{issue_type}"
                )

    for issue_type in expected.get("semantic_issue_absent", []):
        if issue_type in semantic_types:
            failures.append(
                f"unexpected_semantic_issue:{issue_type}"
            )

    normalized_conflicts = [
        sorted(conflict.values)
        for conflict in report.fact_conflicts
    ]
    for wanted in expected.get("fact_conflict_values", []):
        normalized = sorted(str(value) for value in wanted)
        matching = [
            conflict
            for conflict in report.fact_conflicts
            if sorted(conflict.values) == normalized
        ]
        if not matching:
            failures.append(f"missing_fact_conflict:{wanted}")
            continue

        if expected.get("cross_document") is True:
            if not any(
                len(_fact_conflict_documents(report, conflict)) >= 2
                for conflict in matching
            ):
                failures.append(
                    f"fact_conflict_not_cross_document:{wanted}"
                )

    max_fact_conflicts = expected.get("max_fact_conflicts")
    if (
        max_fact_conflicts is not None
        and len(report.fact_conflicts) > max_fact_conflicts
    ):
        failures.append(
            f"fact_conflicts_above_max:"
            f"{len(report.fact_conflicts)}>{max_fact_conflicts}"
        )

    return {
        "id": case["id"],
        "scope": case["scope"],
        "passed": not failures,
        "failures": failures,
        "counts": {
            "documents": len(documents),
            "nodes": report.node_count,
            "semantic_issues": len(report.semantic_issues),
            "fact_conflicts": len(report.fact_conflicts),
        },
        "semantic_issue_types": sorted(set(semantic_types)),
        "fact_conflict_values": normalized_conflicts,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        default="benchmark/consistency/v1.json",
    )
    parser.add_argument("--report")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    payload = json.loads(
        Path(args.suite).read_text(encoding="utf-8")
    )
    filler_text = payload["filler_text"]
    results = [
        evaluate_case(case, filler_text)
        for case in payload["cases"]
    ]

    grouped = defaultdict(lambda: {"passed": 0, "total": 0})
    for result in results:
        bucket = grouped[result["scope"]]
        bucket["total"] += 1
        if result["passed"]:
            bucket["passed"] += 1

    passed = sum(result["passed"] for result in results)
    total = len(results)
    score = passed / total if total else 0.0

    summary = {
        "schema_version": 1,
        "suite": args.suite,
        "passed": passed,
        "total": total,
        "score": round(score, 4),
        "by_scope": {
            name: {
                **stats,
                "score": round(
                    stats["passed"] / stats["total"]
                    if stats["total"]
                    else 0.0,
                    4,
                ),
            }
            for name, stats in sorted(grouped.items())
        },
        "failures": [
            result for result in results if not result["passed"]
        ],
        "results": results,
    }

    print(
        "Consistency Benchmark V1: "
        f"{passed}/{total} = {score:.1%}"
    )
    for name, stats in summary["by_scope"].items():
        print(
            f"- {name}: {stats['passed']}/{stats['total']} "
            f"= {stats['score']:.1%}"
        )

    if summary["failures"]:
        print("\nFailures:")
        for result in summary["failures"]:
            print(
                f"- {result['id']}: "
                + ", ".join(result["failures"])
            )

    if args.report:
        Path(args.report).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.enforce and summary["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
