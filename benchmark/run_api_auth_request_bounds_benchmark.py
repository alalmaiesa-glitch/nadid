from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DEFAULT_CONFIG = ROOT / "api_auth_request_bounds" / "v1.json"
BOUNDS = REPO / "lib" / "server" / "request-bounds.ts"

PROTECTED_API_ROUTES = [
    REPO / "app" / "api" / "account" / "route.ts",
    REPO / "app" / "api" / "analyze" / "route.ts",
    REPO / "app" / "api" / "documents" / "route.ts",
    REPO / "app" / "api" / "documents" / "[id]" / "route.ts",
    REPO / "app" / "api" / "documents" / "[id]" / "context" / "route.ts",
    REPO / "app" / "api" / "documents" / "[id]" / "deep-review" / "route.ts",
    REPO / "app" / "api" / "documents" / "[id]" / "export" / "route.ts",
    REPO / "app" / "api" / "documents" / "[id]" / "finalize-upload" / "route.ts",
    REPO / "app" / "api" / "documents" / "[id]" / "processing-status" / "route.ts",
    REPO / "app" / "api" / "documents" / "[id]" / "status" / "route.ts",
    REPO / "app" / "api" / "documents" / "[id]" / "versions" / "route.ts",
    REPO / "app" / "api" / "suggestions" / "[id]" / "route.ts",
    REPO / "app" / "api" / "uploads" / "route.ts",
    REPO / "app" / "api" / "validate-patch" / "route.ts",
]

JSON_ROUTES = [
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
    bounds = _read(BOUNDS)
    protected = {
        str(path.relative_to(REPO)): _read(path)
        for path in PROTECTED_API_ROUTES
    }
    json_routes = {
        str(path.relative_to(REPO)): _read(path)
        for path in JSON_ROUTES
    }

    def bnd001():
        required = [
            "enforceDeclaredContentLength",
            '"content-length"',
            '"REQUEST_BODY_TOO_LARGE"',
            "{ status: 413 }",
        ]
        missing = [item for item in required if item not in bounds]
        return {
            "declared_length_guard": not missing,
            "missing": missing,
            "_failures": ["declared_length_guard_missing"] if missing else [],
        }

    def bnd002():
        required = [
            "request.body.getReader()",
            "total += value.byteLength",
            "if (total > maxBytes)",
            "await reader.cancel()",
        ]
        missing = [item for item in required if item not in bounds]
        return {
            "streaming_byte_limit": not missing,
            "missing": missing,
            "_failures": ["streaming_limit_missing"] if missing else [],
        }

    def bnd003():
        required = [
            '"application/json"',
            '"+json"',
            '"JSON_CONTENT_TYPE_REQUIRED"',
            '"INVALID_JSON"',
        ]
        missing = [item for item in required if item not in bounds]
        return {
            "json_contract_enforced": not missing,
            "missing": missing,
            "_failures": ["json_contract_missing"] if missing else [],
        }

    def bnd004():
        missing = []
        for path, content in protected.items():
            if (
                "authorizeUser(" not in content
                and "authorizeDocument(" not in content
                and "authorizeSuggestion(" not in content
            ):
                missing.append(path)
        return {
            "protected_api_auth_coverage": not missing,
            "missing_routes": missing,
            "_failures": ["api_auth_coverage_gap"] if missing else [],
        }

    def bnd005():
        content = protected["app/api/validate-patch/route.ts"]
        auth = content.find("authorizeUser()")
        body = content.find("readBoundedJson<PatchRequest>")
        ok = auth >= 0 and body >= 0 and auth < body
        return {
            "validate_patch_auth_before_body": ok,
            "auth_position": auth,
            "body_position": body,
            "_failures": [] if ok else ["validate_patch_auth_order"],
        }

    def bnd006():
        bad = []
        for path, content in json_routes.items():
            if "readBoundedJson" not in content:
                bad.append(path)
            if "request.json()" in content:
                bad.append(path + ":raw_json")
        return {
            "json_routes_bounded": not bad,
            "bad_routes": bad,
            "_failures": ["unbounded_json_route"] if bad else [],
        }

    def bnd007():
        content = protected["app/api/analyze/route.ts"]
        declared = content.find("enforceDeclaredContentLength(")
        form = content.find("request.formData()")
        file_size = content.find("value.size > MAX_FILE_BYTES")
        ok = (
            declared >= 0
            and form >= 0
            and file_size >= 0
            and declared < form < file_size
        )
        return {
            "multipart_preflight_before_parse": ok,
            "declared_position": declared,
            "form_position": form,
            "file_size_position": file_size,
            "_failures": [] if ok else ["multipart_preflight_order"],
        }

    def bnd008():
        content = protected["app/api/documents/[id]/context/route.ts"]
        required = [
            "query.length > 500",
            '"CONTEXT_QUERY_TOO_LONG"',
        ]
        missing = [item for item in required if item not in content]
        return {
            "context_query_bound": not missing,
            "missing": missing,
            "_failures": ["context_query_bound_missing"] if missing else [],
        }

    def bnd009():
        content = protected["app/api/uploads/route.ts"]
        required = [
            "readBoundedJson",
            "8 * 1024",
            "filename.length > 255",
        ]
        missing = [item for item in required if item not in content]
        return {
            "upload_metadata_bounds": not missing,
            "missing": missing,
            "_failures": ["upload_metadata_bound_missing"] if missing else [],
        }

    def bnd010():
        content = protected["app/api/validate-patch/route.ts"]
        required = [
            "256 * 1024",
            "body.blockText.length > 100_000",
            "body.original.length > 20_000",
            "body.replacement.length > 20_000",
            "body.protectedFacts.length > 500",
        ]
        missing = [item for item in required if item not in content]
        return {
            "validate_patch_semantic_bounds": not missing,
            "missing": missing,
            "_failures": ["validate_patch_bounds_missing"] if missing else [],
        }

    def bnd011():
        content = protected["app/api/suggestions/[id]/route.ts"]
        required = [
            "16 * 1024",
            "body.documentId.length > 128",
            "id.length > 128",
        ]
        missing = [item for item in required if item not in content]
        return {
            "suggestion_decision_bounds": not missing,
            "missing": missing,
            "_failures": ["suggestion_bounds_missing"] if missing else [],
        }

    def bnd012():
        content = protected["app/api/documents/[id]/export/route.ts"]
        ok = (
            "!Number.isInteger(versionNo)" in content
            and "Number(versionNo) < 1" in content
        )
        return {
            "export_version_positive_integer": ok,
            "_failures": [] if ok else ["export_version_bound_missing"],
        }

    funcs = [
        bnd001, bnd002, bnd003, bnd004, bnd005, bnd006,
        bnd007, bnd008, bnd009, bnd010, bnd011, bnd012,
    ]
    cases = [
        _case(f"BND-{index:03d}", fn)
        for index, fn in enumerate(funcs, 1)
    ]
    failed = [case["id"] for case in cases if not case["passed"]]

    report = {
        "schema_version": 1,
        "benchmark": "api_auth_request_bounds_v1",
        "configuration": config,
        "cases": cases,
        "summary": {
            "passed": not failed,
            "passed_cases": len(cases) - len(failed),
            "total_cases": len(cases),
            "failed_cases": failed,
            "protected_routes": len(PROTECTED_API_ROUTES),
            "bounded_json_routes": len(JSON_ROUTES),
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
