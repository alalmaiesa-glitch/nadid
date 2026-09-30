from __future__ import annotations

import argparse
import json
from collections import Counter, deque
from pathlib import Path

from app.contracts import DocumentNode
from app.pipeline.patch_validator import validate_patch
from app.pipeline.protection import extract_protected_spans
from app.pipeline.reviewer import fast_review


def _node(text: str) -> DocumentNode:
    return DocumentNode(
        id="mutation-node",
        type="paragraph",
        text=text,
        sequence_no=0,
        source_anchor={"benchmark": "mutation_v1"},
    )


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _reachable_clean(mutated: str, clean: str, suggestions) -> bool:
    """Can a bounded subset of engine suggestions repair this mutant?"""
    target = _normalize(clean)
    if _normalize(mutated) == target:
        return False

    queue = deque([(mutated, frozenset())])
    seen = {mutated}
    max_depth = min(8, len(suggestions))

    while queue:
        text, used = queue.popleft()
        if _normalize(text) == target:
            return True
        if len(used) >= max_depth:
            continue

        for index, suggestion in enumerate(suggestions):
            if index in used:
                continue
            original = suggestion.original
            replacement = suggestion.replacement or ""
            if not original or original not in text:
                continue
            candidate = text.replace(original, replacement, 1)
            if candidate in seen:
                continue
            seen.add(candidate)
            queue.append((candidate, used | {index}))
            if len(seen) > 512:
                break

    return False


def evaluate_case(case: dict) -> dict:
    kind = case["kind"]

    if kind == "review":
        node = _node(case["mutated"])
        suggestions = fast_review([node])
        passed = _reachable_clean(
            case["mutated"],
            case["clean"],
            suggestions,
        )
        return {
            "id": case["id"],
            "kind": kind,
            "passed": passed,
            "mutant_status": "killed" if passed else "survived",
            "suggestions": len(suggestions),
            "suggestion_titles": sorted(
                {suggestion.title for suggestion in suggestions}
            ),
        }

    if kind == "meaning_lock":
        node = _node(case["text"])
        protected = extract_protected_spans([node])
        result = validate_patch(
            block_text=case["text"],
            original=case["original"],
            replacement=case["replacement"],
            protected_spans=protected,
        )
        expected = case["expect"]
        passed = result.status == expected
        return {
            "id": case["id"],
            "kind": kind,
            "passed": passed,
            "mutant_status": "killed" if passed else "survived",
            "expected": expected,
            "actual": result.status,
            "reason": result.reason,
            "protected_types": sorted({span.type for span in protected}),
        }

    raise ValueError(f"Unsupported mutation kind: {kind}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        default="benchmark/mutations/v1.json",
    )
    parser.add_argument("--report")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    payload = json.loads(
        Path(args.suite).read_text(encoding="utf-8")
    )
    results = [evaluate_case(case) for case in payload["cases"]]

    passed = sum(item["passed"] for item in results)
    total = len(results)
    score = passed / total if total else 0.0

    by_kind = Counter()
    passed_by_kind = Counter()
    for item in results:
        by_kind[item["kind"]] += 1
        if item["passed"]:
            passed_by_kind[item["kind"]] += 1

    summary = {
        "schema_version": 1,
        "suite": args.suite,
        "passed": passed,
        "total": total,
        "mutation_kill_rate": round(score, 4),
        "by_kind": {
            kind: {
                "passed": passed_by_kind[kind],
                "total": count,
                "score": round(
                    passed_by_kind[kind] / count if count else 0.0,
                    4,
                ),
            }
            for kind, count in sorted(by_kind.items())
        },
        "survivors": [
            item for item in results if not item["passed"]
        ],
        "results": results,
    }

    print(
        f"Mutation Benchmark V1: {passed}/{total} = {score:.1%}"
    )
    for kind, stats in summary["by_kind"].items():
        print(
            f"- {kind}: {stats['passed']}/{stats['total']} "
            f"= {stats['score']:.1%}"
        )

    if summary["survivors"]:
        print("\nSurviving mutants:")
        for item in summary["survivors"]:
            print(
                f"- {item['id']}: "
                f"{item.get('actual', 'review_not_repaired')}"
            )

    if args.report:
        Path(args.report).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.enforce and summary["survivors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
