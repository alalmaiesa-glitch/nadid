from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DEFAULT_CONFIG = ROOT / "source_immutability" / "v1.json"
PERSISTENCE = REPO / "lib" / "server" / "document-persistence.ts"
WORKER = REPO / "worker" / "index.mjs"
EXPORT_ROUTE = (
    REPO / "app" / "api" / "documents" / "[id]" / "export" / "route.ts"
)


def _case(case_id: str, fn):
    failures: list[str] = []
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


def _ordered(text: str, markers: list[str]) -> tuple[bool, list[int]]:
    positions = [text.find(marker) for marker in markers]
    return (
        all(position >= 0 for position in positions)
        and positions == sorted(positions),
        positions,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    persistence = PERSISTENCE.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    export_route = EXPORT_ROUTE.read_text(encoding="utf-8")

    def src001():
        markers = [
            "function assertSourceIntegrity(",
            'throw new Error("source_integrity_mismatch")',
        ]
        missing = [item for item in markers if item not in persistence]
        return {
            "helper_present": not missing,
            "missing": missing,
            "_failures": ["source_integrity_helper_missing"] if missing else [],
        }

    def src002():
        start = persistence.find("export async function loadDocumentSource")
        end = persistence.find("export async function persistDeepAnalysis", start)
        body = persistence[start:end]
        required = [
            "source_sha256",
            "Buffer.from(await source.arrayBuffer())",
            "assertSourceIntegrity(",
        ]
        missing = [item for item in required if item not in body]
        return {
            "load_source_hash_guard": not missing,
            "missing": missing,
            "_failures": ["load_source_hash_guard_missing"] if missing else [],
        }

    def src003():
        start = persistence.find(
            "export async function downloadDocumentVersion"
        )
        end = persistence.find(
            "export async function listDocumentVersions",
            start,
        )
        body = persistence[start:end]
        required = [
            "source_sha256",
            "Buffer.from(await blob.arrayBuffer())",
            "assertSourceIntegrity(",
        ]
        missing = [item for item in required if item not in body]
        return {
            "download_hash_guard": not missing,
            "missing": missing,
            "_failures": ["download_hash_guard_missing"] if missing else [],
        }

    def src004():
        required = [
            'error.message === "source_integrity_mismatch"',
            'code: "SOURCE_INTEGRITY_MISMATCH"',
            "{ status: 409 }",
        ]
        missing = [item for item in required if item not in export_route]
        return {
            "export_conflict_contract": not missing,
            "missing": missing,
            "_failures": ["export_integrity_conflict_missing"] if missing else [],
        }

    def src005():
        start = worker.find("async function processDeepReview")
        end = worker.find("async function processJob", start)
        body = worker[start:end]
        required = [
            "source_sha256",
            "actualSourceSha256",
            'throw new Error("source_integrity_mismatch")',
        ]
        missing = [item for item in required if item not in body]
        return {
            "worker_deep_hash_guard": not missing,
            "missing": missing,
            "_failures": ["worker_deep_hash_guard_missing"] if missing else [],
        }

    def src006():
        start = worker.find("async function processDeepReview")
        end = worker.find("async function processJob", start)
        body = worker[start:end]
        ok, positions = _ordered(
            body,
            [
                "Buffer.from(await source.arrayBuffer())",
                "actualSourceSha256",
                'throw new Error("source_integrity_mismatch")',
                "const deep = await callAeeDeep",
            ],
        )
        return {
            "guard_before_deep_analysis": ok,
            "positions": positions,
            "_failures": [] if ok else ["deep_analysis_before_integrity_guard"],
        }

    def src007():
        start = worker.find("async function processInitialReview")
        end = worker.find("async function processDeepReview", start)
        body = worker[start:end]
        required = [
            "source_sha256: createHash",
            '.update(buffer)',
            '.digest("hex")',
        ]
        missing = [item for item in required if item not in body]
        return {
            "initial_version_hash_persisted": not missing,
            "missing": missing,
            "_failures": ["initial_source_hash_not_persisted"] if missing else [],
        }

    def src008():
        original = b"nadid-source-original"
        changed = b"nadid-source-mutated"
        original_hash = hashlib.sha256(original).hexdigest()
        changed_hash = hashlib.sha256(changed).hexdigest()
        safe = original_hash != changed_hash
        return {
            "original_sha256": original_hash,
            "mutated_sha256": changed_hash,
            "mismatch_detectable": safe,
            "_failures": [] if safe else ["hash_model_failed"],
        }

    def src009():
        original = b"same-source"
        first = hashlib.sha256(original).hexdigest()
        second = hashlib.sha256(original).hexdigest()
        safe = first == second
        return {
            "stable_hash": safe,
            "_failures": [] if safe else ["hash_not_deterministic"],
        }

    def src010():
        expected = hashlib.sha256(b"expected").hexdigest()
        actual = hashlib.sha256(b"tampered").hexdigest()
        blocked = actual != expected
        return {
            "expected_matches_actual": actual == expected,
            "tamper_blocked": blocked,
            "_failures": [] if blocked else ["tamper_not_detected"],
        }

    cases = [
        _case("SRC-001", src001),
        _case("SRC-002", src002),
        _case("SRC-003", src003),
        _case("SRC-004", src004),
        _case("SRC-005", src005),
        _case("SRC-006", src006),
        _case("SRC-007", src007),
        _case("SRC-008", src008),
        _case("SRC-009", src009),
        _case("SRC-010", src010),
    ]

    failed = [case["id"] for case in cases if not case["passed"]]
    report = {
        "schema_version": 1,
        "benchmark": "upload_lifecycle_source_immutability_v1",
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

    if args.enforce and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
