from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DEFAULT_CONFIG = ROOT / "api_origin_csrf" / "v1.json"
HELPER = REPO / "lib" / "server" / "request-integrity.ts"

MUTATING_ROUTES = [
    REPO / "app" / "api" / "account" / "route.ts",
    REPO / "app" / "api" / "analyze" / "route.ts",
    REPO / "app" / "api" / "documents" / "[id]" / "deep-review" / "route.ts",
    REPO / "app" / "api" / "documents" / "[id]" / "finalize-upload" / "route.ts",
    REPO / "app" / "api" / "documents" / "[id]" / "route.ts",
    REPO / "app" / "api" / "documents" / "[id]" / "versions" / "route.ts",
    REPO / "app" / "api" / "suggestions" / "[id]" / "route.ts",
    REPO / "app" / "api" / "uploads" / "route.ts",
    REPO / "app" / "api" / "validate-patch" / "route.ts",
]


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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    helper = _read(HELPER)
    route_text = {str(path.relative_to(REPO)): _read(path) for path in MUTATING_ROUTES}

    def api001():
        required = [
            'SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"])',
            'SAFE_METHODS.has(request.method.toUpperCase())',
        ]
        missing = [item for item in required if item not in helper]
        return {
            "safe_methods_exempt": not missing,
            "missing": missing,
            "_failures": ["safe_method_contract_missing"] if missing else [],
        }

    def api002():
        required = [
            'fetchSite === "cross-site"',
            '"CROSS_SITE_REQUEST_BLOCKED"',
            '{ status: 403 }',
        ]
        missing = [item for item in required if item not in helper]
        return {
            "cross_site_fetch_metadata_blocked": not missing,
            "missing": missing,
            "_failures": ["cross_site_guard_missing"] if missing else [],
        }

    def api003():
        required = [
            'request.headers.get("origin")',
            'suppliedOrigin !== expectedOrigin',
            '"REQUEST_ORIGIN_MISMATCH"',
        ]
        missing = [item for item in required if item not in helper]
        return {
            "origin_exact_match_enforced": not missing,
            "missing": missing,
            "_failures": ["origin_match_guard_missing"] if missing else [],
        }

    def api004():
        required = [
            'process.env.NEXT_PUBLIC_APP_URL',
            'process.env.NODE_ENV === "production"',
            '"APP_ORIGIN_NOT_CONFIGURED"',
            '{ status: 503 }',
        ]
        missing = [item for item in required if item not in helper]
        return {
            "production_origin_fail_closed": not missing,
            "missing": missing,
            "_failures": ["production_origin_fail_closed_missing"] if missing else [],
        }

    def api005():
        required = [
            '"REQUEST_ORIGIN_REQUIRED"',
            'if (process.env.NODE_ENV === "production")',
        ]
        missing = [item for item in required if item not in helper]
        return {
            "production_missing_origin_blocked": not missing,
            "missing": missing,
            "_failures": ["missing_origin_guard_missing"] if missing else [],
        }

    def api006():
        missing = []
        for path, content in route_text.items():
            if 'enforceSameOriginMutation' not in content:
                missing.append(path)
        return {
            "mutating_routes_guarded": not missing,
            "missing_routes": missing,
            "_failures": ["mutating_route_guard_missing"] if missing else [],
        }

    def api007():
        bad = []
        for path, content in route_text.items():
            starts = [
                content.find(f"export async function {method}")
                for method in ("POST", "PATCH", "DELETE")
                if content.find(f"export async function {method}") >= 0
            ]

            for start in starts:
                later_exports = [
                    pos
                    for pos in (
                        content.find("export async function ", start + 1),
                    )
                    if pos >= 0
                ]
                end = min(later_exports) if later_exports else len(content)
                handler = content[start:end]

                guard = handler.find("enforceSameOriginMutation(request)")
                if guard < 0:
                    bad.append(path)
                    continue

                sensitive_markers = [
                    "authorizeUser(",
                    "authorizeDocument(",
                    "request.json()",
                    "request.formData()",
                    "enqueue",
                    "deleteDocumentFully(",
                    "createDocumentVersion(",
                ]
                positions = [
                    handler.find(marker)
                    for marker in sensitive_markers
                    if handler.find(marker) >= 0
                ]
                if positions and guard > min(positions):
                    bad.append(path)

        bad = sorted(set(bad))
        return {
            "guard_precedes_auth_body_and_mutation": not bad,
            "bad_routes": bad,
            "_failures": ["guard_order_incorrect"] if bad else [],
        }

    def api008():
        bad = []
        for path, content in route_text.items():
            mutation_count = sum(
                content.count(f"export async function {method}")
                for method in ("POST", "PATCH", "DELETE")
            )
            guard_count = content.count("enforceSameOriginMutation(request)")
            if guard_count != mutation_count:
                bad.append(
                    {
                        "route": path,
                        "mutations": mutation_count,
                        "guards": guard_count,
                    }
                )

        return {
            "one_guard_per_mutating_handler": not bad,
            "mismatches": bad,
            "_failures": ["guard_coverage_mismatch"] if bad else [],
        }

    def api009():
        required = [
            "new URL(value).origin",
            "return normalizedOrigin(request.url)",
        ]
        missing = [item for item in required if item not in helper]
        return {
            "origin_normalization_present": not missing,
            "missing": missing,
            "_failures": ["origin_normalization_missing"] if missing else [],
        }

    def api010():
        forbidden = [
            'Access-Control-Allow-Origin: "*"',
            '"Access-Control-Allow-Origin": "*"',
            "origin.includes(",
            "origin.endsWith(",
        ]
        found = [item for item in forbidden if item in helper]
        return {
            "no_wildcard_or_suffix_origin_acceptance": not found,
            "forbidden_found": found,
            "_failures": ["weak_origin_acceptance"] if found else [],
        }

    def api011():
        required = [
            'process.env.VERCEL_ENV === "preview"',
            "return normalizedOrigin(request.url)",
        ]
        missing = [item for item in required if item not in helper]
        return {
            "vercel_preview_uses_request_origin": not missing,
            "missing": missing,
            "_failures": ["preview_origin_policy_missing"] if missing else [],
        }

    cases = [
        _case(f"API-{index:03d}", fn)
        for index, fn in enumerate(
            [
                api001,
                api002,
                api003,
                api004,
                api005,
                api006,
                api007,
                api008,
                api009,
                api010,
                api011,
            ],
            1,
        )
    ]

    failed = [case["id"] for case in cases if not case["passed"]]
    report = {
        "schema_version": 1,
        "benchmark": "api_origin_csrf_integrity_v1",
        "configuration": config,
        "cases": cases,
        "summary": {
            "passed": not failed,
            "passed_cases": len(cases) - len(failed),
            "total_cases": len(cases),
            "failed_cases": failed,
            "guarded_routes": len(MUTATING_ROUTES),
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
