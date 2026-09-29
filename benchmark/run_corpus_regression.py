from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from app.pipeline.chunker import build_chunks
from app.pipeline.memory import build_document_memory
from app.pipeline.parser import parse_docx
from app.pipeline.protection import extract_protected_spans
from app.pipeline.reviewer import fast_review
from app.pipeline.semantic_review import semantic_review


def _word_count(nodes) -> int:
    return sum(
        len([token for token in node.text.split() if token])
        for node in nodes
    )


def _stable_digest(items: list[str]) -> str:
    payload = "\n".join(sorted(items)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def analyze_document(path: Path) -> dict:
    data = path.read_bytes()
    nodes = parse_docx(data)
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    suggestions = fast_review(nodes)
    memory = build_document_memory(nodes, chunks, protected)
    semantic_issues = semantic_review(nodes, memory)

    rerun_suggestions = fast_review(nodes)
    rerun_protected = extract_protected_spans(nodes)
    rerun_memory = build_document_memory(nodes, chunks, rerun_protected)
    rerun_semantic = semantic_review(nodes, rerun_memory)

    suggestion_categories = Counter(
        suggestion.category for suggestion in suggestions
    )
    protected_types = Counter(span.type for span in protected)
    memory_kinds = Counter(
        item.kind for item in memory.knowledge_items
    )
    semantic_types = Counter(
        issue.issue_type for issue in semantic_issues
    )

    deterministic = {
        "suggestions": _stable_digest(
            [suggestion.id for suggestion in suggestions]
        ) == _stable_digest(
            [suggestion.id for suggestion in rerun_suggestions]
        ),
        "protected": _stable_digest(
            [span.id for span in protected]
        ) == _stable_digest(
            [span.id for span in rerun_protected]
        ),
        "memory": _stable_digest(
            [item.id for item in memory.knowledge_items]
        ) == _stable_digest(
            [item.id for item in rerun_memory.knowledge_items]
        ),
        "semantic": _stable_digest(
            [issue.id for issue in semantic_issues]
        ) == _stable_digest(
            [issue.id for issue in rerun_semantic]
        ),
    }

    return {
        "id": path.stem,
        "filename": path.name,
        "bytes": len(data),
        "nodes": len(nodes),
        "word_count": _word_count(nodes),
        "headings": sum(node.type == "heading" for node in nodes),
        "paragraphs": sum(node.type == "paragraph" for node in nodes),
        "table_cells": sum(node.type == "table_cell" for node in nodes),
        "chunks": len(chunks),
        "suggestions": len(suggestions),
        "suggestion_categories": dict(sorted(suggestion_categories.items())),
        "protected": len(protected),
        "protected_types": dict(sorted(protected_types.items())),
        "facts": len(memory.facts),
        "conflicts": len(memory.conflicts),
        "knowledge_items": len(memory.knowledge_items),
        "memory_kinds": dict(sorted(memory_kinds.items())),
        "semantic_issues": len(semantic_issues),
        "semantic_types": dict(sorted(semantic_types.items())),
        "deterministic": deterministic,
        "deterministic_pass": all(deterministic.values()),
    }


def load_manifest(path: Path) -> list[Path]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent
    files = []
    for item in payload.get("documents", []):
        raw = Path(item["path"])
        files.append(raw if raw.is_absolute() else (base / raw))
    return files


def compare_baseline(current: dict, baseline: dict) -> list[str]:
    failures: list[str] = []
    baseline_docs = {
        item["id"]: item for item in baseline.get("documents", [])
    }

    for item in current["documents"]:
        expected = baseline_docs.get(item["id"])
        if not expected:
            failures.append(f"missing_baseline:{item['id']}")
            continue

        for key in ("nodes", "headings", "paragraphs", "table_cells"):
            if item[key] != expected[key]:
                failures.append(
                    f"{item['id']}:{key}:{item[key]}!={expected[key]}"
                )

        if not item["deterministic_pass"]:
            failures.append(f"{item['id']}:non_deterministic")

        max_growth = expected.get("suggestion_growth_limit", 0.35)
        old_count = expected.get("suggestions", 0)
        allowed = max(5, int(old_count * (1 + max_growth)))
        if item["suggestions"] > allowed:
            failures.append(
                f"{item['id']}:suggestion_explosion:"
                f"{item['suggestions']}>{allowed}"
            )

    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--baseline")
    parser.add_argument("--write-baseline")
    args = parser.parse_args()

    paths = load_manifest(Path(args.manifest))
    documents = []
    errors = []

    for path in paths:
        try:
            documents.append(analyze_document(path))
        except Exception as exc:
            errors.append(
                {
                    "file": path.name,
                    "error": type(exc).__name__,
                    "detail": str(exc),
                }
            )

    report = {
        "schema_version": 1,
        "privacy": "aggregate-only; no document text is stored",
        "documents": documents,
        "errors": errors,
        "summary": {
            "documents": len(documents),
            "errors": len(errors),
            "word_count": sum(item["word_count"] for item in documents),
            "nodes": sum(item["nodes"] for item in documents),
            "suggestions": sum(item["suggestions"] for item in documents),
            "protected": sum(item["protected"] for item in documents),
            "knowledge_items": sum(
                item["knowledge_items"] for item in documents
            ),
            "semantic_issues": sum(
                item["semantic_issues"] for item in documents
            ),
            "deterministic_documents": sum(
                item["deterministic_pass"] for item in documents
            ),
        },
    }

    failures = []
    if errors:
        failures.append(f"processing_errors:{len(errors)}")

    if args.baseline:
        baseline = json.loads(
            Path(args.baseline).read_text(encoding="utf-8")
        )
        failures.extend(compare_baseline(report, baseline))

    report["failures"] = failures
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if args.write_baseline:
        baseline = {
            "schema_version": 1,
            "documents": [
                {
                    **item,
                    "suggestion_growth_limit": 0.35,
                }
                for item in documents
            ],
        }
        Path(args.write_baseline).write_text(
            json.dumps(baseline, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(
        "Private corpus regression: "
        f"{len(documents)} docs, "
        f"{report['summary']['word_count']} words, "
        f"{len(failures)} failures"
    )

    if failures:
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
