from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DEFAULT_CONFIG = ROOT / "api_rate_limits" / "v1.json"
MIGRATION = REPO / "supabase" / "migrations" / "0028_api_rate_limits.sql"
HELPER = REPO / "lib" / "server" / "rate-limit.ts"

RATE_ROUTES = {
    "analyze": REPO / "app" / "api" / "analyze" / "route.ts",
    "validatePatch": REPO / "app" / "api" / "validate-patch" / "route.ts",
    "uploadCreate": REPO / "app" / "api" / "uploads" / "route.ts",
    "contextSearch": REPO / "app" / "api" / "documents" / "[id]" / "context" / "route.ts",
    "deepReview": REPO / "app" / "api" / "documents" / "[id]" / "deep-review" / "route.ts",
    "finalizeUpload": REPO / "app" / "api" / "documents" / "[id]" / "finalize-upload" / "route.ts",
    "createVersion": REPO / "app" / "api" / "documents" / "[id]" / "versions" / "route.ts",
    "suggestionDecision": REPO / "app" / "api" / "suggestions" / "[id]" / "route.ts",
}


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    migration = MIGRATION.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")
    routes = {
        name: path.read_text(encoding="utf-8")
        for name, path in RATE_ROUTES.items()
    }

    def rate001():
        required = [
            "create table if not exists public.api_rate_windows",
            "primary key (user_id, action)",
        ]
        missing = [item for item in required if item not in migration]
        return {
            "single_row_window_model": not missing,
            "missing": missing,
            "_failures": ["rate_window_model_missing"] if missing else [],
        }

    def rate002():
        required = [
            "on conflict (user_id, action)",
            "request_count = case",
            "window_started_at = case",
            "clock_timestamp()",
        ]
        missing = [item for item in required if item not in migration]
        return {
            "atomic_window_update": not missing,
            "missing": missing,
            "_failures": ["atomic_rate_update_missing"] if missing else [],
        }

    def rate003():
        required = [
            "security definer",
            "revoke all on function public.consume_api_rate_limit",
            "grant execute on function public.consume_api_rate_limit",
            "to service_role",
        ]
        missing = [item for item in required if item not in migration]
        return {
            "privileged_rpc_restricted": not missing,
            "missing": missing,
            "_failures": ["rate_rpc_permissions_weak"] if missing else [],
        }

    def rate004():
        required = [
            'process.env.NODE_ENV === "production"',
            '"RATE_LIMIT_IDENTITY_UNAVAILABLE"',
            '"RATE_LIMIT_SERVICE_UNAVAILABLE"',
            '"RATE_LIMIT_CHECK_FAILED"',
            "{ status: 503 }",
        ]
        missing = [item for item in required if item not in helper]
        return {
            "production_fail_closed": not missing,
            "missing": missing,
            "_failures": ["rate_limit_fail_closed_missing"] if missing else [],
        }

    def rate005():
        required = [
            '"RATE_LIMITED"',
            "status: 429",
            '"Retry-After"',
            "retryAfterSeconds",
        ]
        missing = [item for item in required if item not in helper]
        return {
            "standard_429_response": not missing,
            "missing": missing,
            "_failures": ["rate_limit_response_missing"] if missing else [],
        }

    def rate006():
        required = [
            "analyze:",
            "validatePatch:",
            "contextSearch:",
            "deepReview:",
            "uploadCreate:",
            "finalizeUpload:",
            "suggestionDecision:",
            "createVersion:",
        ]
        missing = [item for item in required if item not in helper]
        return {
            "expensive_action_policies_present": not missing,
            "missing": missing,
            "_failures": ["rate_policy_missing"] if missing else [],
        }

    def rate007():
        missing = []
        for policy, content in routes.items():
            if "enforceUserRateLimit(" not in content:
                missing.append(policy)
            if f"API_RATE_LIMITS.{policy}" not in content:
                missing.append(policy + ":policy")
        return {
            "target_routes_rate_limited": not missing,
            "missing": missing,
            "_failures": ["route_rate_limit_missing"] if missing else [],
        }

    def rate008():
        bad = []
        expensive = [
            "request.formData()",
            "readBoundedJson",
            "searchStoredContext(",
            "enqueueDeepReview(",
            "enqueueDocumentProcessing(",
            "applyDocxPatchesWithAee(",
            'supabase.rpc(',
        ]
        for policy, content in routes.items():
            limiter = content.find("enforceUserRateLimit(")
            if limiter < 0:
                bad.append(policy)
                continue

            auth_positions = [
                pos
                for marker in ("authorizeUser(", "authorizeDocument(")
                if (pos := content.find(marker)) >= 0
            ]
            if auth_positions and limiter < min(auth_positions):
                bad.append(policy + ":before_auth")

            later = [
                content.find(marker)
                for marker in expensive
                if content.find(marker) >= 0
            ]
            if later and limiter > min(later):
                bad.append(policy + ":after_expensive_work")

        return {
            "limiter_after_auth_before_expensive_work": not bad,
            "bad": bad,
            "_failures": ["rate_limit_order_wrong"] if bad else [],
        }

    def rate009():
        content = routes["deepReview"]
        get_start = content.find("export async function GET")
        post_start = content.find("export async function POST")
        if get_start < 0 or post_start < 0:
            return {
                "deep_review_polling_unlimited": False,
                "_failures": ["deep_review_handler_missing"],
            }
        get_body = content[get_start:post_start]
        post_body = content[post_start:]
        ok = (
            "enforceUserRateLimit(" not in get_body
            and "API_RATE_LIMITS.deepReview" in post_body
        )
        return {
            "deep_review_polling_unlimited": ok,
            "_failures": [] if ok else ["deep_review_get_rate_limited"],
        }

    def rate010():
        forbidden = [
            "new Map(",
            "setInterval(",
            "globalThis.",
        ]
        found = [item for item in forbidden if item in helper]
        return {
            "no_process_local_rate_state": not found,
            "forbidden": found,
            "_failures": ["serverless_local_limiter_state"] if found else [],
        }

    funcs = [
        rate001, rate002, rate003, rate004, rate005,
        rate006, rate007, rate008, rate009, rate010,
    ]
    cases = [
        _case(f"RATE-{index:03d}", fn)
        for index, fn in enumerate(funcs, 1)
    ]
    failed = [case["id"] for case in cases if not case["passed"]]

    report = {
        "schema_version": 1,
        "benchmark": "api_rate_limits_abuse_v1",
        "configuration": config,
        "cases": cases,
        "summary": {
            "passed": not failed,
            "passed_cases": len(cases) - len(failed),
            "total_cases": len(cases),
            "failed_cases": failed,
            "rate_limited_routes": len(RATE_ROUTES),
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
