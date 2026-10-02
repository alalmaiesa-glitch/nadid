from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
MIG = REPO / "supabase" / "migrations" / "0038_billing_cycle_quota_windows.sql"
TEST = REPO / "supabase" / "tests" / "billing_cycle_quota_windows.sql"
DOC = REPO / "docs" / "BILLING_CYCLE_QUOTA_WINDOWS.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    migration = MIG.read_text(encoding="utf-8")
    tests = TEST.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    checks = [
        ("QUOTA-CYCLE-001",
         "resolve_character_quota_window" in migration
         and "current_period_start::date" in migration),
        ("QUOTA-CYCLE-002",
         "billing_interval = 'year'" in migration
         and "make_interval(months => v_elapsed_months)" in migration),
        ("QUOTA-CYCLE-003",
         "date_trunc('month', v_now)::date" in migration
         and "free_monthly" in migration),
        ("QUOTA-CYCLE-004",
         "s.current_period_start <= v_now" in migration
         and "s.current_period_end > v_now" in migration),
        ("QUOTA-CYCLE-005",
         "from public.resolve_character_quota_window(p_user_id)" in migration),
        ("QUOTA-CYCLE-006",
         "QUOTA-CYCLE-DB-001" in tests
         and "duplicate included quota" in tests),
        ("QUOTA-CYCLE-007",
         "QUOTA-CYCLE-DB-002" in tests
         and "annual monthly window" in tests),
        ("QUOTA-CYCLE-008",
         "QUOTA-CYCLE-DB-003" in tests
         and "future renewal activated quota early" in tests),
        ("QUOTA-CYCLE-009",
         "revoke all on function public.resolve_character_quota_window(uuid)" in migration
         and "to service_role" in migration),
        ("QUOTA-CYCLE-010",
         "calendar" in doc.lower()
         and "annual" in doc.lower()
         and "billing" in doc.lower()),
    ]

    cases = [
        {
            "id": case_id,
            "passed": passed,
            "observed": {"ok": passed},
            "failures": [] if passed else ["billing_cycle_quota_guard_missing"],
        }
        for case_id, passed in checks
    ]
    failed = [case["id"] for case in cases if not case["passed"]]

    report = {
        "schema_version": 1,
        "benchmark": "billing_cycle_aligned_character_quota_windows_v1",
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
