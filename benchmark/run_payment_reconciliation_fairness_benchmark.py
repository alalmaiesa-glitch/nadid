from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
MIG = REPO / "supabase" / "migrations" / "0039_payment_reconciliation_fairness.sql"
TEST = REPO / "supabase" / "tests" / "payment_reconciliation_fairness.sql"
ROUTE = REPO / "app" / "api" / "internal" / "payments" / "reconcile" / "route.ts"
DOC = REPO / "docs" / "PAYMENT_RECONCILIATION_FAIRNESS.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    migration = MIG.read_text(encoding="utf-8")
    tests = TEST.read_text(encoding="utf-8")
    route = ROUTE.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    checks = [
        ("RECON-FAIR-001", "reconciliation_checked_at" in migration),
        ("RECON-FAIR-002", "claim_payment_reconciliation_batch" in migration),
        ("RECON-FAIR-003", "for update skip locked" in migration.lower()),
        ("RECON-FAIR-004", "reconciliation_checked_at asc nulls first" in migration),
        ("RECON-FAIR-005", "least(greatest(coalesce(p_limit, 25), 1), 100)" in migration),
        ("RECON-FAIR-006", 'claim_payment_reconciliation_batch' in route and ".from("payments")" not in route),
        ("RECON-FAIR-007", "RECON-FAIR-DB-001" in tests and "RECON-FAIR-DB-006" in tests),
        ("RECON-FAIR-008", "tail candidate was starved" in tests),
        ("RECON-FAIR-009", "revoke all on function public.claim_payment_reconciliation_batch(integer)" in migration and "to service_role" in migration),
        ("RECON-FAIR-010", "starvation" in doc.lower() and "skip locked" in doc.lower()),
    ]

    cases = [
        {
            "id": case_id,
            "passed": passed,
            "observed": {"ok": passed},
            "failures": [] if passed else ["reconciliation_fairness_guard_missing"],
        }
        for case_id, passed in checks
    ]
    failed = [case["id"] for case in cases if not case["passed"]]

    report = {
        "schema_version": 1,
        "benchmark": "payment_reconciliation_fairness_claiming_starvation_safety_v1",
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
