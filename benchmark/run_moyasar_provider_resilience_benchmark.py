from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
CLIENT = REPO / "lib" / "server" / "moyasar-client.ts"
ENV = REPO / ".env.example"
DOC = REPO / "docs" / "MOYASAR_PROVIDER_RESILIENCE.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    client = CLIENT.read_text(encoding="utf-8")
    env = ENV.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    checks = [
        ("MOY-RES-001", "AbortController" in client and "controller.abort()" in client),
        ("MOY-RES-002", "NADID_MOYASAR_FETCH_TIMEOUT_MS" in client and "8000" in client),
        ("MOY-RES-003", "NADID_MOYASAR_FETCH_MAX_ATTEMPTS" in client and "3" in client),
        ("MOY-RES-004", "Math.min(Math.max(parsed, minimum), maximum)" in client),
        ("MOY-RES-005", "408" in client and "429" in client and "500" in client and "503" in client and "504" in client),
        ("MOY-RES-006", "response.status === 404 ? 404 : 503" in client),
        ("MOY-RES-007", "MOYASAR_FETCH_TIMEOUT" in client and "MOYASAR_RATE_LIMITED" in client),
        ("MOY-RES-008", 'headers.get("retry-after")' in client and "2000" in client),
        ("MOY-RES-009", "attempt < maxAttempts" in client and "retryDelayMs" in client),
        ("MOY-RES-010", "NADID_MOYASAR_FETCH_TIMEOUT_MS=8000" in env and "NADID_MOYASAR_FETCH_MAX_ATTEMPTS=3" in env),
        ("MOY-RES-011", "\\n# 36h" not in env and "\\nNADID_PAYMENT_RECONCILE_MAX_AGE_MINUTES" not in env),
        ("MOY-RES-012", "idempotent" in doc.lower() and "429" in doc and "404" in doc and "timeout" in doc.lower()),
    ]

    cases = [
        {
            "id": case_id,
            "passed": bool(passed),
            "observed": {"ok": bool(passed)},
            "failures": [] if passed else ["moyasar_provider_resilience_guard_missing"],
        }
        for case_id, passed in checks
    ]
    failed = [case["id"] for case in cases if not case["passed"]]

    report = {
        "schema_version": 1,
        "benchmark": "moyasar_provider_timeout_retry_failure_classification_v1",
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
