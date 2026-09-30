from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DEFAULT_CONFIG = ROOT / "worker_idempotency" / "v1.json"
WORKER = REPO / "worker" / "index.mjs"


DEEP_TABLES = (
    "document_chunks",
    "memory_terms",
    "fact_assertions",
    "fact_conflicts",
    "document_memory_items",
)


def _case(case_id: str, fn):
    failures: list[str] = []
    try:
        observed = fn()
        failures.extend(observed.pop("_failures", []))
    except Exception as exc:
        observed = {
            "exception": type(exc).__name__,
            "message": str(exc)[:300],
        }
        failures.append("benchmark_exception")

    return {
        "id": case_id,
        "observed": observed,
        "failures": failures,
        "passed": not failures,
    }


def _retry_deep_state(
    partial: dict[str, list[str]],
    target: dict[str, list[str]],
) -> dict[str, list[str]]:
    state = deepcopy(partial)
    for table in DEEP_TABLES:
        state[table] = []
    state["deep_suggestions"] = []
    state["analysis_runs"] = [
        run
        for run in state.get("analysis_runs", [])
        if run != "deep"
    ]

    for table in DEEP_TABLES:
        state[table] = list(target.get(table, []))

    state["deep_suggestions"] = list(
        target.get("deep_suggestions", [])
    )
    state.setdefault("analysis_runs", []).append("deep")
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    worker = WORKER.read_text(encoding="utf-8")

    def wid001():
        required = [
            "const terms = memory.terms ?? [];",
            "const facts = memory.facts ?? [];",
            "const conflicts = memory.conflicts ?? [];",
            "const knowledgeItems = memory.knowledge_items ?? [];",
        ]
        missing = [item for item in required if item not in worker]
        return {
            "bindings": len(required),
            "missing": missing,
            "_failures": (
                ["deep_result_bindings_missing:" + ",".join(missing)]
                if missing else []
            ),
        }

    def wid002():
        required = [
            '.from("document_chunks")',
            '.from("memory_terms")',
            '.from("fact_assertions")',
            '.from("fact_conflicts")',
            '.from("document_memory_items")',
        ]
        missing = [item for item in required if item not in worker]
        return {
            "deep_tables": len(required),
            "missing": missing,
            "_failures": (
                ["deep_table_persistence_missing:" + ",".join(missing)]
                if missing else []
            ),
        }

    def wid003():
        bindings = {
            "document_chunks": "chunk_key: chunk.id",
            "memory_terms": "term: term.term",
            "fact_assertions": "client_fact_id: fact.id",
            "fact_conflicts": "client_conflict_id: conflict.id",
            "document_memory_items": "client_item_id: item.id",
        }
        missing = [
            table
            for table, marker in bindings.items()
            if marker not in worker
        ]
        return {
            "identity_bindings": len(bindings),
            "missing": missing,
            "_failures": (
                ["deterministic_identity_missing:" + ",".join(missing)]
                if missing else []
            ),
        }

    def wid004():
        delete_loop = worker.find(
            'for (const table of [\n    "fact_conflicts",'
        )
        chunk_insert = worker.find(
            'const { error: chunkInsertError }'
        )
        ready = worker.find(
            '.update({\n      state: "ready",'
        )
        failures = []
        if min(delete_loop, chunk_insert, ready) < 0:
            failures.append("deep_rebuild_markers_missing")
        elif not (delete_loop < chunk_insert < ready):
            failures.append("deep_rebuild_order_wrong")
        return {
            "delete_index": delete_loop,
            "insert_index": chunk_insert,
            "ready_index": ready,
            "_failures": failures,
        }

    def wid005():
        partial = {
            "document_chunks": ["old-c1"],
            "memory_terms": ["old-t1", "old-t2"],
            "fact_assertions": ["old-f1"],
            "fact_conflicts": ["old-x1"],
            "document_memory_items": ["old-m1"],
            "deep_suggestions": ["old-s1"],
            "analysis_runs": ["fast", "deep"],
        }
        target = {
            "document_chunks": ["c1", "c2"],
            "memory_terms": ["t1"],
            "fact_assertions": ["f1", "f2"],
            "fact_conflicts": ["x1"],
            "document_memory_items": ["m1", "m2"],
            "deep_suggestions": ["s1"],
        }
        first = _retry_deep_state(partial, target)
        second = _retry_deep_state(first, target)
        failures = []
        if first != second:
            failures.append("deep_retry_not_idempotent")
        if second["analysis_runs"].count("deep") != 1:
            failures.append("duplicate_deep_analysis_run")
        return {
            "idempotent": first == second,
            "deep_runs": second["analysis_runs"].count("deep"),
            "_failures": failures,
        }

    def wid006():
        markers = [
            '.from("suggestions")\n    .delete()',
            '"deep_consistency_v0.1"',
            '"semantic_review_v0.1"',
            '.from("analysis_runs")\n    .delete()',
            '.eq("run_type", "deep")',
        ]
        missing = [item for item in markers if item not in worker]
        return {
            "replacement_markers": len(markers),
            "missing": missing,
            "_failures": (
                ["deep_replace_cleanup_missing:" + ",".join(missing)]
                if missing else []
            ),
        }

    def wid007():
        marker = 'if (existingMemory?.state === "ready")'
        idx = worker.find(marker)
        complete_idx = worker.find(
            "await markComplete(job.id, document.id, \"ready\");",
            idx,
        )
        deep_call = worker.find(
            "const deep = await callAeeDeep",
            idx,
        )
        failures = []
        if idx < 0 or complete_idx < 0 or deep_call < 0:
            failures.append("ready_memory_reuse_contract_missing")
        elif not (idx < complete_idx < deep_call):
            failures.append("ready_memory_not_reused_before_recompute")
        return {
            "reuse_before_recompute": (
                idx >= 0
                and complete_idx >= 0
                and deep_call >= 0
                and idx < complete_idx < deep_call
            ),
            "_failures": failures,
        }

    def wid008():
        existing = worker.find("if (existingVersion?.status === \"ready\")")
        cleanup = worker.find("if (existingVersion?.id)")
        delete = worker.find(
            '.from("document_versions")\n      .delete()',
            cleanup,
        )
        insert = worker.find(
            '.from("document_versions")\n    .insert(',
            cleanup,
        )
        failures = []
        if min(existing, cleanup, delete, insert) < 0:
            failures.append("initial_retry_contract_missing")
        elif not (existing < cleanup < delete < insert):
            failures.append("initial_retry_cleanup_order_wrong")
        return {
            "partial_version_deleted_before_rebuild": not failures,
            "_failures": failures,
        }

    def wid009():
        try_idx = worker.find("  try {\n    const nodeRows")
        catch_idx = worker.find("  } catch (error) {", try_idx)
        failed_update = worker.find(
            '.update({ status: "failed" })',
            catch_idx,
        )
        failures = []
        if min(try_idx, catch_idx, failed_update) < 0:
            failures.append("initial_partial_failure_cleanup_missing")
        return {
            "version_marked_failed_on_partial_write": not failures,
            "_failures": failures,
        }

    def wid010():
        target_markers = {
            "chunks": "chunks.map((chunk, index) => ({",
            "terms": "terms.map((term) => ({",
            "facts": "facts.map((fact) => ({",
            "conflicts": "conflicts.map((conflict) => ({",
            "knowledge_items": "knowledgeItems.map((item) => ({",
        }
        missing = [
            key for key, marker in target_markers.items()
            if marker not in worker
        ]
        return {
            "mapped_artifact_groups": len(target_markers),
            "missing": missing,
            "_failures": (
                ["artifact_mapping_missing:" + ",".join(missing)]
                if missing else []
            ),
        }

    def wid011():
        markers = [
            'version_id: version.id,\n          chunk_key:',
            'version_id: version.id,\n          term:',
            'version_id: version.id,\n          client_fact_id:',
            'version_id: version.id,\n          client_conflict_id:',
            'version_id: version.id,\n          client_item_id:',
        ]
        missing = [marker for marker in markers if marker not in worker]
        return {
            "version_scoped_writes": len(markers),
            "missing_count": len(missing),
            "_failures": (
                ["deep_write_not_version_scoped"]
                if missing else []
            ),
        }

    def wid012():
        ready_idx = worker.find(
            '.update({\n      state: "ready",'
        )
        run_insert = worker.find(
            '.from("analysis_runs")\n    .insert({',
        )
        item_insert = worker.find(
            'const { error: memoryItemInsertError }'
        )
        failures = []
        if min(ready_idx, run_insert, item_insert) < 0:
            failures.append("finalization_markers_missing")
        elif not (item_insert < run_insert < ready_idx):
            failures.append("memory_ready_before_all_writes")
        return {
            "ready_after_artifacts_and_run": not failures,
            "_failures": failures,
        }

    cases = [
        _case("WID-001", wid001),
        _case("WID-002", wid002),
        _case("WID-003", wid003),
        _case("WID-004", wid004),
        _case("WID-005", wid005),
        _case("WID-006", wid006),
        _case("WID-007", wid007),
        _case("WID-008", wid008),
        _case("WID-009", wid009),
        _case("WID-010", wid010),
        _case("WID-011", wid011),
        _case("WID-012", wid012),
    ]

    failed = [case["id"] for case in cases if not case["passed"]]
    report = {
        "schema_version": 1,
        "benchmark": "partial_write_idempotent_worker_persistence_v1",
        "configuration": config,
        "cases": cases,
        "summary": {
            "passed": not failed,
            "passed_cases": len(cases) - len(failed),
            "total_cases": len(cases),
            "failed_cases": failed,
        },
    }

    rendered = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    print(rendered)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")

    if args.enforce and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
