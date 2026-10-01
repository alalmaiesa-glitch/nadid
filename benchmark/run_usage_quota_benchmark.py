from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DEFAULT_CONFIG = ROOT / "usage_quota" / "v1.json"
MIGRATION = REPO / "supabase" / "migrations" / "0029_usage_quota_billing_integrity.sql"
HELPER = REPO / "lib" / "server" / "usage-quota.ts"
ANALYZE = REPO / "app" / "api" / "analyze" / "route.ts"


def _case(case_id, fn):
    failures = []
    try:
        observed = fn()
        failures.extend(observed.pop("_failures", []))
    except Exception as exc:
        observed = {"exception": type(exc).__name__, "message": str(exc)[:300]}
        failures.append("benchmark_exception")
    return {"id": case_id, "observed": observed, "failures": failures, "passed": not failures}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    migration = MIGRATION.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")
    analyze = ANALYZE.read_text(encoding="utf-8")

    def q1():
        req = [
            "create table if not exists public.character_usage_events",
            "unique (user_id, operation_id, action)",
            "primary key",
        ]
        missing = [x for x in req if x not in migration]
        return {"durable_idempotency_ledger": not missing, "missing": missing,
                "_failures": ["quota_ledger_missing"] if missing else []}

    def q2():
        req = [
            "pg_advisory_xact_lock",
            "for update",
            "consume_character_quota",
        ]
        missing = [x for x in req if x not in migration]
        return {"serialized_atomic_consumption": not missing, "missing": missing,
                "_failures": ["quota_atomicity_missing"] if missing else []}

    def q3():
        req = [
            "p_characters > v_included_remaining + v_topup_remaining",
            "return query",
            "false,",
        ]
        missing = [x for x in req if x not in migration]
        return {"rejects_before_partial_debit": not missing, "missing": missing,
                "_failures": ["partial_debit_guard_missing"] if missing else []}

    def q4():
        included_pos = migration.find("v_take := least(p_characters, v_included_remaining)")
        topup_pos = migration.find("for v_credit in")
        ok = included_pos >= 0 and topup_pos > included_pos
        return {"included_before_topup": ok,
                "_failures": [] if ok else ["quota_debit_order_wrong"]}

    def q5():
        req = [
            "already_charged",
            "where user_id = p_user_id",
            "and operation_id = p_operation_id",
            "and action = p_action",
        ]
        missing = [x for x in req if x not in migration]
        return {"idempotent_replay": not missing, "missing": missing,
                "_failures": ["quota_idempotency_missing"] if missing else []}

    def q6():
        req = [
            "from public.subscriptions s",
            "join public.billing_plans bp",
            "monthly_characters",
            "where id = 'free_monthly'",
        ]
        missing = [x for x in req if x not in migration]
        return {"plan_entitlement_resolution": not missing, "missing": missing,
                "_failures": ["plan_quota_resolution_missing"] if missing else []}

    def q7():
        req = [
            "revoke all on function public.consume_character_quota",
            "from public, anon, authenticated",
            "to service_role",
        ]
        missing = [x for x in req if x not in migration]
        return {"rpc_service_role_only": not missing, "missing": missing,
                "_failures": ["quota_rpc_permissions_weak"] if missing else []}

    def q8():
        req = [
            "USAGE_QUOTA_IDENTITY_UNAVAILABLE",
            "USAGE_QUOTA_SERVICE_UNAVAILABLE",
            "USAGE_QUOTA_CHECK_FAILED",
            "CHARACTER_QUOTA_EXCEEDED",
        ]
        missing = [x for x in req if x not in helper]
        return {"server_guard_fail_closed": not missing, "missing": missing,
                "_failures": ["quota_server_guard_missing"] if missing else []}

    def q9():
        count = analyze.count("consumeCharacterQuota(")
        aee = "response.document.id" in analyze
        chars = "block.text.length" in analyze
        ok = count >= 2 and aee and chars
        return {"both_analysis_paths_metered": ok, "calls": count,
                "_failures": [] if ok else ["analysis_quota_enforcement_missing"]}

    def q10():
        first_quota = analyze.find("consumeCharacterQuota(")
        first_persist = analyze.find("persistAnalyzedDocument(")
        ok = first_quota >= 0 and first_persist > first_quota
        return {"quota_before_persistence_and_response": ok,
                "_failures": [] if ok else ["quota_order_wrong"]}

    funcs = [q1,q2,q3,q4,q5,q6,q7,q8,q9,q10]
    cases = [_case(f"QUOTA-{i:03d}", fn) for i, fn in enumerate(funcs, 1)]
    failed = [c["id"] for c in cases if not c["passed"]]
    report = {
        "schema_version": 1,
        "benchmark": "usage_quota_billing_integrity_v1",
        "configuration": config,
        "cases": cases,
        "summary": {
            "passed": not failed,
            "passed_cases": len(cases)-len(failed),
            "total_cases": len(cases),
            "failed_cases": failed
        }
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return 1 if args.enforce and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
