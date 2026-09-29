from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from app.contracts import DocumentNode
from app.pipeline.chunker import build_chunks
from app.pipeline.context import retrieve_context
from app.pipeline.memory import build_document_memory
from app.pipeline.protection import extract_protected_spans
from app.pipeline.patch_validator import validate_patch
from app.pipeline.reviewer import fast_review


def load_cases(path: Path):
    cases = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def make_nodes(case):
    nodes = []
    for index, raw in enumerate(case["nodes"]):
        nodes.append(
            DocumentNode(
                id=raw.get("id", f"n{index+1}"),
                type=raw.get("type", "paragraph"),
                text=raw["text"],
                sequence_no=index,
                source_anchor={"benchmark_case": case["id"]},
            )
        )
    return nodes


def normalize_text(value):
    return " ".join((value or "").split())


def evaluate_case(case):
    nodes = make_nodes(case)
    suggestions = fast_review(nodes)
    protected = extract_protected_spans(nodes)
    chunks = build_chunks(nodes)
    memory = build_document_memory(nodes, chunks, protected)

    failures = []
    expected = case.get("expect", {})

    suggestion_text = "\n".join(
        f"{s.title}\n{s.explanation}\n{s.original}\n{s.replacement or ''}"
        for s in suggestions
    )

    for needle in expected.get("suggestion_contains", []):
        if needle not in suggestion_text:
            failures.append(f"missing_suggestion:{needle}")

    for needle in expected.get("suggestion_absent", []):
        if needle in suggestion_text:
            failures.append(f"unexpected_suggestion:{needle}")

    min_suggestions = expected.get("min_suggestions")
    if min_suggestions is not None and len(suggestions) < min_suggestions:
        failures.append(
            f"suggestions_below_min:{len(suggestions)}<{min_suggestions}"
        )

    max_suggestions = expected.get("max_suggestions")
    if max_suggestions is not None and len(suggestions) > max_suggestions:
        failures.append(
            f"suggestions_above_max:{len(suggestions)}>{max_suggestions}"
        )

    protected_values = [normalize_text(item.value) for item in protected]
    for value in expected.get("protected_values", []):
        if normalize_text(value) not in protected_values:
            failures.append(f"missing_protected:{value}")

    for value in expected.get("protected_absent", []):
        if normalize_text(value) in protected_values:
            failures.append(f"unexpected_protected:{value}")

    conflict_values = [
        sorted(normalize_text(v) for v in conflict.values)
        for conflict in memory.conflicts
    ]
    for wanted in expected.get("conflict_values", []):
        normalized = sorted(normalize_text(v) for v in wanted)
        if normalized not in conflict_values:
            failures.append(f"missing_conflict:{wanted}")

    if expected.get("no_conflicts") and memory.conflicts:
        failures.append("unexpected_conflict")

    patch = expected.get("patch")
    if patch:
        result = validate_patch(
            block_text=patch.get("block_text", nodes[0].text if nodes else ""),
            original=patch["original"],
            replacement=patch["replacement"],
            protected_spans=protected,
        )
        wanted_status = patch["status"]
        if result.status != wanted_status:
            failures.append(
                f"patch_status:{result.status}!={wanted_status}"
            )

    context = expected.get("context")
    if context:
        package = retrieve_context(
            target_node_id=context["target_node_id"],
            nodes=nodes,
            chunks=chunks,
            memory=memory,
            query=context.get("query"),
            max_chunks=context.get("max_chunks", 5),
        )
        hit_node_ids = {
            node_id
            for hit in package.hits
            for node_id in hit.node_ids
        }
        for node_id in context.get("expected_node_ids", []):
            if node_id not in hit_node_ids:
                failures.append(f"context_miss:{node_id}")

    return {
        "id": case["id"],
        "dimension": case["dimension"],
        "passed": not failures,
        "failures": failures,
        "counts": {
            "suggestions": len(suggestions),
            "protected": len(protected),
            "conflicts": len(memory.conflicts),
            "chunks": len(chunks),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        default="benchmark/cases/core_v1.jsonl",
    )
    parser.add_argument("--report")
    args = parser.parse_args()

    cases = load_cases(Path(args.suite))
    results = [evaluate_case(case) for case in cases]

    by_dimension = defaultdict(lambda: {"passed": 0, "total": 0})
    for result in results:
        bucket = by_dimension[result["dimension"]]
        bucket["total"] += 1
        if result["passed"]:
            bucket["passed"] += 1

    passed = sum(1 for result in results if result["passed"])
    total = len(results)
    score = passed / total if total else 0.0

    summary = {
        "suite": args.suite,
        "passed": passed,
        "total": total,
        "score": round(score, 4),
        "dimensions": {
            name: {
                **stats,
                "score": round(
                    stats["passed"] / stats["total"]
                    if stats["total"]
                    else 0.0,
                    4,
                ),
            }
            for name, stats in sorted(by_dimension.items())
        },
        "results": results,
    }

    print(f"Nadid Quality Benchmark: {passed}/{total} = {score:.1%}")
    for name, stats in summary["dimensions"].items():
        print(
            f"- {name}: {stats['passed']}/{stats['total']} "
            f"= {stats['score']:.1%}"
        )

    failed = [r for r in results if not r["passed"]]
    if failed:
        print("\nFailures:")
        for result in failed:
            print(
                f"- {result['id']}: "
                + ", ".join(result["failures"])
            )

    if args.report:
        Path(args.report).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
