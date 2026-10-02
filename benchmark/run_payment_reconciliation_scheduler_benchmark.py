from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
CONFIG = REPO / "vercel.json"
ROUTE = REPO / "app" / "api" / "internal" / "payments" / "reconcile" / "route.ts"
ENV = REPO / ".env.example"
DOC = REPO / "docs" / "PAYMENT_RECONCILIATION_SCHEDULER.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    route = ROUTE.read_text(encoding="utf-8")
    env = ENV.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    crons = config.get("crons", [])
    target = [
        c for c in crons
        if c.get("path") == "/api/internal/payments/reconcile"
    ]

    checks = [
        ("RECON-SCHED-001", len(target) == 1),
        ("RECON-SCHED-002", target and target[0].get("schedule") == "17 0 * * *"),
        ("RECON-SCHED-003", '"$schema"' in CONFIG.read_text(encoding="utf-8") and "openapi.vercel.sh/vercel.json" in CONFIG.read_text(encoding="utf-8")),
        ("RECON-SCHED-004", "process.env.CRON_SECRET" in route and "reconciliationSecretValid" in route),
        ("RECON-SCHED-005", "CRON_SECRET=" in env),
        ("RECON-SCHED-006", "NADID_PAYMENT_RECONCILE_BATCH=25" in env),
        ("RECON-SCHED-007", "PAYMENT_RECONCILIATION_PARTIAL_FAILURE" in route and "{ status: 503 }" in route),
        ("RECON-SCHED-008", "Hobby" in doc and "daily" in doc.lower()),
        ("RECON-SCHED-009", "Authorization" in doc and "CRON_SECRET" in doc),
        ("RECON-SCHED-010", "production" in doc.lower() and "Preview" in doc),
    ]

    cases = [
        {
            "id": case_id,
            "passed": bool(passed),
            "observed": {"ok": bool(passed)},
            "failures": [] if passed else ["reconciliation_scheduler_guard_missing"],
        }
        for case_id, passed in checks
    ]
    failed = [case["id"] for case in cases if not case["passed"]]

    report = {
        "schema_version": 1,
        "benchmark": "payment_reconciliation_scheduler_liveness_v1",
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
