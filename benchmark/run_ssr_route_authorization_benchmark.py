from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DEFAULT_CONFIG = ROOT / "ssr_route_authorization" / "v1.json"
AUTH_ROUTING = REPO / "lib" / "auth-routing.ts"
MIDDLEWARE = REPO / "middleware.ts"
CALLBACK = REPO / "app" / "auth" / "callback" / "route.ts"
LOGIN = REPO / "app" / "login" / "page.tsx"


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    routing = AUTH_ROUTING.read_text(encoding="utf-8")
    middleware = MIDDLEWARE.read_text(encoding="utf-8")
    callback = CALLBACK.read_text(encoding="utf-8")
    login = LOGIN.read_text(encoding="utf-8")

    def ssr001():
        required = ['"/documents"', '"/upload"', '"/editor"']
        missing = [item for item in required if item not in routing]
        return {
            "protected_routes_centralized": not missing,
            "missing": missing,
            "_failures": ["protected_route_catalog_missing"] if missing else [],
        }

    def ssr002():
        required = [
            'value.startsWith("//")',
            'value.startsWith("/\\\\")',
            'value.includes("\\\\")',
            "ENCODED_PATH_SEPARATOR",
            "ENCODED_CONTROL",
            "ENCODED_PATH_SEPARATOR.test(pathPart)",
            "ENCODED_CONTROL.test(value)",
            r"/[\u0000-\u001F\u007F]/",
        ]
        missing = [item for item in required if item not in routing]
        return {
            "unsafe_redirect_forms_rejected": not missing,
            "missing": missing,
            "_failures": ["redirect_guard_incomplete"] if missing else [],
        }

    def ssr003():
        required = [
            'isProtectedRoute(pathname)',
            'safeInternalNext(pathname + request.nextUrl.search)',
            'loginUrl.pathname = "/login"',
        ]
        missing = [item for item in required if item not in middleware]
        return {
            "middleware_uses_central_guards": not missing,
            "missing": missing,
            "_failures": ["middleware_guard_not_centralized"] if missing else [],
        }

    def ssr004():
        required = [
            'pathname === "/login" && user',
            'documentsUrl.pathname = "/documents"',
        ]
        missing = [item for item in required if item not in middleware]
        return {
            "authenticated_login_redirect": not missing,
            "missing": missing,
            "_failures": ["authenticated_login_redirect_missing"] if missing else [],
        }

    def ssr005():
        required = [
            'process.env.NODE_ENV === "production" && needsAuthConfig',
            '{ status: 503 }',
        ]
        missing = [item for item in required if item not in middleware]
        return {
            "production_auth_config_fail_closed": not missing,
            "missing": missing,
            "_failures": ["auth_config_fail_closed_missing"] if missing else [],
        }

    def ssr006():
        required = [
            'safeInternalNext(',
            'url.searchParams.get("next")',
            'new URL(next, url.origin)',
        ]
        missing = [item for item in required if item not in callback]
        return {
            "callback_uses_safe_redirect": not missing,
            "missing": missing,
            "_failures": ["callback_redirect_guard_missing"] if missing else [],
        }

    def ssr007():
        forbidden = [
            'requestedNext.startsWith("/")',
            '!requestedNext.startsWith("//")',
        ]
        found = [item for item in forbidden if item in callback]
        return {
            "callback_duplicate_guard_removed": not found,
            "forbidden_found": found,
            "_failures": ["callback_duplicate_redirect_logic"] if found else [],
        }

    def ssr008():
        required = [
            'safeInternalNext(',
            'new URLSearchParams(window.location.search).get("next")',
        ]
        missing = [item for item in required if item not in login]
        return {
            "login_uses_same_safe_redirect": not missing,
            "missing": missing,
            "_failures": ["login_redirect_guard_missing"] if missing else [],
        }

    def ssr009():
        forbidden = [
            'requested.startsWith("/")',
            '!requested.startsWith("//")',
        ]
        found = [item for item in forbidden if item in login]
        return {
            "login_duplicate_guard_removed": not found,
            "forbidden_found": found,
            "_failures": ["login_duplicate_redirect_logic"] if found else [],
        }

    def ssr010():
        required = [
            'pathname === prefix',
            'pathname.startsWith(prefix + "/")',
        ]
        missing = [item for item in required if item not in routing]
        return {
            "prefix_boundary_enforced": not missing,
            "missing": missing,
            "_failures": ["protected_prefix_boundary_missing"] if missing else [],
        }

    funcs = [
        ssr001, ssr002, ssr003, ssr004, ssr005,
        ssr006, ssr007, ssr008, ssr009, ssr010,
    ]
    cases = [
        _case(f"SSR-{index:03d}", fn)
        for index, fn in enumerate(funcs, 1)
    ]
    failed = [case["id"] for case in cases if not case["passed"]]

    report = {
        "schema_version": 1,
        "benchmark": "ssr_route_authorization_v1",
        "configuration": config,
        "cases": cases,
        "summary": {
            "passed": not failed,
            "passed_cases": len(cases) - len(failed),
            "total_cases": len(cases),
            "failed_cases": failed,
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
