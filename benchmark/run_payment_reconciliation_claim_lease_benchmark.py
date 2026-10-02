from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
MIG = REPO / "supabase" / "migrations" / "0041_payment_reconciliation_claim_lease.sql"
TEST = REPO / "supabase" / "tests" / "payment_reconciliation_claim_lease.sql"
ROUTE = REPO / "app" / "api" / "internal" / "payments" / "reconcile" / "route.ts"
ENV = REPO / ".env.example"
DOC = REPO / "docs" / "PAYMENT_RECONCILIATION_CLAIM_LEASE.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    migration = MIG.read_text(encoding="utf-8")
    tests = TEST.read_text(encoding="utf-8")
    route = ROUTE.read_text(encoding="utf-8")
    env = ENV.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    checks = [
        ("RECON-LEASE-001", "reconciliation_claimed_until" in migration),
        ("RECON-LEASE-002", "reconciliation_claimed_until is null" in migration and "reconciliation_claimed_until <= v_now" in migration),
        ("RECON-LEASE-003", "make_interval(secs => v_lease_seconds)" in migration),
        ("RECON-LEASE-004", "greatest(coalesce(p_lease_seconds, 900), 60)" in migration and "3600" in migration),
        ("RECON-LEASE-005", "for update skip locked" in migration.lower()),
        ("RECON-LEASE-006", "drop function if exists public.claim_payment_reconciliation_batch(integer)" in migration),
        ("RECON-LEASE-007", "p_lease_seconds: claimLeaseSeconds()" in route),
        ("RECON-LEASE-008", "NADID_PAYMENT_RECONCILE_CLAIM_LEASE_SECONDS=900" in env),
        ("RECON-LEASE-009", "RECON-LEASE-DB-001" in tests and "RECON-LEASE-DB-007" in tests),
        ("RECON-LEASE-010", "crash" in doc.lower() and "overlap" in doc.lower()),
        ("RECON-LEASE-011", "to service_role" in migration and "authenticated" in migration),
        ("RECON-LEASE-012", "reconciliation_checked_at = v_now" in migration),
    ]

    cases = [
        {
            "id": case_id,
            "passed": bool(passed),
            "observed": {"ok": bool(passed)},
            "failures": [] if passed else ["reconciliation_claim_lease_guard_missing"],
        }
        for case_id, passed in checks
    ]
    failed = [case["id"] for case in cases if not case["passed"]]

    report = {
        "schema_version": 1,
        "benchmark": "payment_reconciliation_claim_lease_overlap_suppression_v1",
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
