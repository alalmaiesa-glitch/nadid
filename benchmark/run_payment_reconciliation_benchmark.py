from __future__ import annotations
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
ROUTE = REPO / "app" / "api" / "internal" / "payments" / "reconcile" / "route.ts"
CORE = REPO / "lib" / "server" / "payment-reconciliation.ts"
ENV = REPO / ".env.example"
DOC = REPO / "docs" / "PAYMENT_RECONCILIATION.md"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report", type=Path)
    p.add_argument("--enforce", action="store_true")
    a = p.parse_args()

    route = ROUTE.read_text(encoding="utf-8")
    core = CORE.read_text(encoding="utf-8")
    env = ENV.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    checks = [
        ("RECON-001", 'process.env.CRON_SECRET' in route and 'reconciliationSecretValid' in route),
        ("RECON-002", 'timingSafeEqual' in core and 'if (!expected) return false' in core),
        ("RECON-003", 'RECONCILABLE_PAYMENT_STATUSES' in core and '"pending"' in core and '"paid"' in core and '"partially_refunded"' in core),
        ("RECON-004", '.eq("provider", "moyasar")' in route and '.in("status"' in route),
        ("RECON-005", 'Math.min(parsed, 100)' in route and 'NADID_PAYMENT_RECONCILE_BATCH' in route),
        ("RECON-006", 'fetchMoyasarPayment(paymentId)' in core and 'callbackEventType(payment.status)' in core),
        ("RECON-007", 'applyMoyasarPaymentWebhook' in core and 'canonicalRemoteState' in core),
        ("RECON-008", 'payment.status.toLowerCase()' in core and 'String(payment.captured)' in core and 'String(payment.refunded)' in core),
        ("RECON-009", 'PAYMENT_RECONCILIATION_PARTIAL_FAILURE' in route and '{ status: 503 }' in route),
        ("RECON-010", 'CRON_SECRET=' in env and 'NADID_PAYMENT_RECONCILE_BATCH=25' in env),
        ("RECON-011", 'لا يقبل Payment ID من العميل' in doc),
        ("RECON-012", 'rejected_mismatch' in route and 'ignored_status' in core),
    ]

    cases = [
        {
            "id": case_id,
            "passed": ok,
            "observed": {"ok": ok},
            "failures": [] if ok else ["reconciliation_guard_missing"],
        }
        for case_id, ok in checks
    ]
    failed = [case["id"] for case in cases if not case["passed"]]
    report = {
        "schema_version": 1,
        "benchmark": "payment_reconciliation_missing_webhook_recovery_v1",
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
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(rendered + "\n", encoding="utf-8")
    return 1 if a.enforce and failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
