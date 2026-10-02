from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
ROUTE = REPO / "app" / "api" / "internal" / "payments" / "reconcile" / "route.ts"
ENV = REPO / ".env.example"
DOC = REPO / "docs" / "PAYMENT_RECONCILIATION_TIME_BUDGET.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    route = ROUTE.read_text(encoding="utf-8")
    env = ENV.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    checks = [
        ("RECON-TIME-001", "NADID_PAYMENT_RECONCILE_RUN_BUDGET_MS" in route),
        ("RECON-TIME-002", "240000" in route and "60000" in route and "900000" in route),
        ("RECON-TIME-003", "moyasarFetchTimeoutMs" in route and "moyasarFetchMaxAttempts" in route),
        ("RECON-TIME-004", "nextItemReserveMs" in route and "Date.now() + nextItemReserveMs() >= deadline" in route),
        ("RECON-TIME-005", "p_limit: 1" in route),
        ("RECON-TIME-006", "while (summary.scanned < limit)" in route),
        ("RECON-TIME-007", "PAYMENT_RECONCILIATION_TIME_BUDGET_EXHAUSTED" in route),
        ("RECON-TIME-008", "budgetExhausted" in route and '"partial_failure"' in route),
        ("RECON-TIME-009", "NADID_PAYMENT_RECONCILE_RUN_BUDGET_MS=240000" in env),
        ("RECON-TIME-010", "unclaimed" in doc.lower() and "lease" in doc.lower()),
        ("RECON-TIME-011", "503" in doc and "idempot" in doc.lower()),
        ("RECON-TIME-012", "lookupFailed" in route and "PAYMENT_RECONCILIATION_LOOKUP_FAILED" in route),
    ]

    cases = [
        {
            "id": case_id,
            "passed": bool(passed),
            "observed": {"ok": bool(passed)},
            "failures": [] if passed else ["reconciliation_time_budget_guard_missing"],
        }
        for case_id, passed in checks
    ]
    failed = [case["id"] for case in cases if not case["passed"]]

    report = {
        "schema_version": 1,
        "benchmark": "payment_reconciliation_run_time_budget_graceful_yield_v1",
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
