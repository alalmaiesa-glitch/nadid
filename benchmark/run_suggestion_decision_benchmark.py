from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DEFAULT_CONFIG = ROOT / "suggestion_decision" / "v1.json"
MIGRATION = (
    REPO / "supabase" / "migrations" /
    "0027_suggestion_decision_audit.sql"
)
ROUTE = REPO / "app" / "api" / "suggestions" / "[id]" / "route.ts"
EDITOR = REPO / "app" / "editor" / "page.tsx"
TYPES = REPO / "lib" / "database.types.ts"


def _case(case_id, fn):
    failures = []
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


def _ordered(text, markers):
    positions = [text.find(item) for item in markers]
    return (
        all(position >= 0 for position in positions)
        and positions == sorted(positions),
        positions,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    migration = MIGRATION.read_text(encoding="utf-8").lower()
    route = ROUTE.read_text(encoding="utf-8")
    editor = EDITOR.read_text(encoding="utf-8")
    types = TYPES.read_text(encoding="utf-8")

    def dec001():
        required = [
            "create table if not exists public.suggestion_decisions",
            "suggestion_snapshot jsonb not null",
            "previous_status text not null",
            "decided_at timestamptz not null",
        ]
        missing = [x for x in required if x not in migration]
        return {
            "audit_snapshot_table": not missing,
            "missing": missing,
            "_failures": ["audit_table_missing"] if missing else [],
        }

    def dec002():
        required = [
            "create or replace function public.record_suggestion_decision",
            "security definer",
            "set search_path = public",
        ]
        missing = [x for x in required if x not in migration]
        return {
            "atomic_decision_rpc": not missing,
            "missing": missing,
            "_failures": ["atomic_decision_rpc_missing"] if missing else [],
        }

    def dec003():
        required = [
            "d.id = p_document_id",
            "d.owner_id = p_owner_id",
            "v.version_no = p_version_no",
            "v.status = 'ready'",
            "s.version_id = target_version_id",
            "s.client_suggestion_id = p_client_suggestion_id",
        ]
        missing = [x for x in required if x not in migration]
        return {
            "document_version_suggestion_scope": not missing,
            "missing": missing,
            "_failures": ["suggestion_scope_incomplete"] if missing else [],
        }

    def dec004():
        required = [
            "select max(v.version_no)",
            "latest_ready_version is distinct from p_version_no",
            "suggestion_version_changed",
        ]
        missing = [x for x in required if x not in migration]
        return {
            "latest_version_guard": not missing,
            "missing": missing,
            "_failures": ["latest_version_guard_missing"] if missing else [],
        }

    def dec005():
        required = [
            "for update",
            "where id = target_suggestion.id",
        ]
        missing = [x for x in required if x not in migration]
        return {
            "row_locked_exact_update": not missing,
            "missing": missing,
            "_failures": ["exact_locked_update_missing"] if missing else [],
        }

    def dec006():
        ok, positions = _ordered(
            migration,
            [
                "update public.suggestions",
                "insert into public.suggestion_decisions",
                "return query",
            ],
        )
        return {
            "status_and_audit_same_function": ok,
            "positions": positions,
            "_failures": [] if ok else ["status_audit_order_missing"],
        }

    def dec007():
        required = [
            "'original_text', target_suggestion.original_text",
            "'replacement_text', target_suggestion.replacement_text",
            "'confidence', target_suggestion.confidence",
            "'source_engine', target_suggestion.source_engine",
            "'evidence', target_suggestion.evidence",
            "'status_before', target_suggestion.status",
        ]
        missing = [x for x in required if x not in migration]
        return {
            "audit_snapshot_complete": not missing,
            "missing": missing,
            "_failures": ["audit_snapshot_incomplete"] if missing else [],
        }

    def dec008():
        required = [
            "from public, anon, authenticated",
            "to service_role",
            "suggestion_decisions_select_own",
        ]
        missing = [x for x in required if x not in migration]
        return {
            "rpc_and_audit_permissions": not missing,
            "missing": missing,
            "_failures": ["decision_permissions_missing"] if missing else [],
        }

    def dec009():
        required = [
            'authorizeDocument(body.documentId)',
            '"record_suggestion_decision"',
            "p_version_no: Number(body.versionNo)",
            "p_client_suggestion_id: id",
            "p_owner_id: auth.userId",
        ]
        missing = [x for x in required if x not in route]
        return {
            "route_uses_scoped_rpc": not missing,
            "missing": missing,
            "_failures": ["route_scope_rpc_missing"] if missing else [],
        }

    def dec010():
        forbidden = [
            '.from("suggestions")\n    .update',
            '.eq("client_suggestion_id", id)',
            "authorizeSuggestion(id)",
        ]
        found = [x for x in forbidden if x in route]
        return {
            "global_id_update_removed": not found,
            "forbidden_found": found,
            "_failures": ["global_suggestion_update_still_present"] if found else [],
        }

    def dec011():
        required = [
            'code: "VERSION_CHANGED"',
            "{ status: 409 }",
            'code: "SUGGESTION_NOT_FOUND"',
            "{ status: 404 }",
            'code: "SUGGESTION_SCOPE_REQUIRED"',
        ]
        missing = [x for x in required if x not in route]
        return {
            "api_scope_error_contract": not missing,
            "missing": missing,
            "_failures": ["scope_error_contract_missing"] if missing else [],
        }

    def dec012():
        required = [
            "async function persistSuggestionDecision(",
            "documentId,",
            "versionNo: analysis.document.versionNo ?? 1",
            'item,\n        "accepted"',
            'item,\n        "rejected"',
        ]
        missing = [x for x in required if x not in editor]
        return {
            "editor_sends_document_version_scope": not missing,
            "missing": missing,
            "_failures": ["editor_scope_missing"] if missing else [],
        }

    def dec013():
        accept_pos = editor.find(
            'const persisted = await persistSuggestionDecision(\n'
            '        item,\n'
            '        "accepted"'
        )
        block_pos = editor.find("setBlocks((current)", accept_pos)
        reject_call = editor.find(
            'const persisted = await persistSuggestionDecision(\n'
            '        item,\n'
            '        "rejected"'
        )
        reject_state = editor.find("setRejected((current)", reject_call)
        ok = (
            accept_pos >= 0
            and block_pos > accept_pos
            and reject_call >= 0
            and reject_state > reject_call
        )
        return {
            "local_state_after_persistence": ok,
            "_failures": [] if ok else ["optimistic_decision_before_persistence"],
        }

    def dec014():
        required = [
            "suggestion_decisions: {",
            "record_suggestion_decision: {",
            "p_client_suggestion_id: string",
            "decision_id: string",
        ]
        missing = [x for x in required if x not in types]
        return {
            "typed_audit_rpc": not missing,
            "missing": missing,
            "_failures": ["database_types_missing"] if missing else [],
        }

    funcs = [
        dec001, dec002, dec003, dec004, dec005, dec006, dec007,
        dec008, dec009, dec010, dec011, dec012, dec013, dec014,
    ]
    cases = [
        _case(f"DEC-{index:03d}", fn)
        for index, fn in enumerate(funcs, 1)
    ]
    failed = [case["id"] for case in cases if not case["passed"]]

    report = {
        "schema_version": 1,
        "benchmark": "suggestion_decision_scope_audit_v1",
        "configuration": config,
        "cases": cases,
        "summary": {
            "passed": not failed,
            "passed_cases": len(cases) - len(failed),
            "total_cases": len(cases),
            "failed_cases": failed,
        },
    }

    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return 1 if args.enforce and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
