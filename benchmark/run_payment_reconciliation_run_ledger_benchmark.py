from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
MIG = REPO / "supabase" / "migrations" / "0040_payment_reconciliation_run_ledger.sql"
TEST = REPO / "supabase" / "tests" / "payment_reconciliation_run_ledger.sql"
ROUTE = REPO / "app" / "api" / "internal" / "payments" / "reconcile" / "route.ts"
HEALTH = REPO / "app" / "api" / "internal" / "payments" / "reconcile" / "health" / "route.ts"
ENV = REPO / ".env.example"
DOC = REPO / "docs" / "PAYMENT_RECONCILIATION_RUN_LEDGER.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    migration = MIG.read_text(encoding="utf-8")
    tests = TEST.read_text(encoding="utf-8")
    route = ROUTE.read_text(encoding="utf-8")
    health = HEALTH.read_text(encoding="utf-8")
    env = ENV.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    checks = [
        ("RECON-RUN-001", "create table if not exists public.payment_reconciliation_runs" in migration),
        ("RECON-RUN-002", "start_payment_reconciliation_run" in migration and "finish_payment_reconciliation_run" in migration),
        ("RECON-RUN-003", "where id = p_run_id" in migration and "status = 'running'" in migration and "completed_at is null" in migration),
        ("RECON-RUN-004", "get_payment_reconciliation_health" in migration and "stale_running" in migration),
        ("RECON-RUN-005", "start_payment_reconciliation_run" in route and "finish_payment_reconciliation_run" in route),
        ("RECON-RUN-006", "PAYMENT_RECONCILIATION_AUDIT_FAILED" in route and "{ status: 503 }" in route),
        ("RECON-RUN-007", "PAYMENT_RECONCILIATION_SCHEDULER_STALE" in health and "reconciliationSecretValid" in health),
        ("RECON-RUN-008", "NADID_PAYMENT_RECONCILE_MAX_AGE_MINUTES=2160" in env),
        ("RECON-RUN-009", "RECON-RUN-DB-001" in tests and "RECON-RUN-DB-006" in tests),
        ("RECON-RUN-010", "stale" in doc.lower() and "crash" in doc.lower() and "36" in doc),
        ("RECON-RUN-011", "revoke all on table public.payment_reconciliation_runs" in migration and "to service_role" in migration),
        ("RECON-RUN-012", "partial_failure" in route and "lookup_failure" in route and '"succeeded"' in route),
    ]

    cases = [
        {
            "id": case_id,
            "passed": bool(passed),
            "observed": {"ok": bool(passed)},
            "failures": [] if passed else ["reconciliation_run_ledger_guard_missing"],
        }
        for case_id, passed in checks
    ]
    failed = [case["id"] for case in cases if not case["passed"]]

    report = {
        "schema_version": 1,
        "benchmark": "payment_reconciliation_run_ledger_stale_scheduler_detection_v1",
        "cases": cases,
        "summary": {
            "passed": not failed,
            "passed_cases": len(cases) - len(failed),
            "total_cases": len(cases),
            "failed_cases": failed,
        },
    }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return 1 if args.enforce and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
