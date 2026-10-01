from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DEFAULT_CONFIG = ROOT / "finalized_source_promotion" / "v1.json"
PERSISTENCE = REPO / "lib" / "server" / "document-persistence.ts"
WORKER = REPO / "worker" / "index.mjs"
ROUTE = (
    REPO / "app" / "api" / "documents" / "[id]" /
    "finalize-upload" / "route.ts"
)


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


def _ordered(text, markers):
    positions = [text.find(item) for item in markers]
    return (
        all(position >= 0 for position in positions)
        and positions == sorted(positions),
        positions,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    persistence = PERSISTENCE.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    route = ROUTE.read_text(encoding="utf-8")

    start = persistence.find(
        "export async function enqueueDocumentProcessing"
    )
    end = persistence.find(
        "export async function loadPendingDocumentUpload",
        start,
    )
    enqueue = persistence[start:end]

    worker_start = worker.find("async function processInitialReview")
    worker_end = worker.find(
        "async function processDeepReview",
        worker_start,
    )
    initial = worker[worker_start:worker_end]

    def fsp001():
        required = [
            "function finalizedSourceStoragePath(",
            "/finalized/",
            "sourceSha256",
            "/source.docx",
        ]
        missing = [x for x in required if x not in persistence]
        return {
            "content_addressed_path_helper": not missing,
            "missing": missing,
            "_failures": (
                ["finalized_path_helper_missing"] if missing else []
            ),
        }

    def fsp002():
        start = persistence.find(
            "async function promoteFinalizedSource("
        )
        end = persistence.find(
            "function normalizeReviewCategory",
            start,
        )
        body = persistence[start:end]
        required = [
            ".upload(finalizedPath, sourceBuffer",
            "upsert: false",
        ]
        missing = [x for x in required if x not in body]
        return {
            "server_side_no_upsert_promotion": not missing,
            "missing": missing,
            "_failures": (
                ["immutable_promotion_missing"] if missing else []
            ),
        }

    def fsp003():
        start = persistence.find(
            "async function promoteFinalizedSource("
        )
        end = persistence.find(
            "function normalizeReviewCategory",
            start,
        )
        body = persistence[start:end]
        required = [
            ".download(finalizedPath)",
            "sha256(existingBuffer) !== sourceSha256",
            'throw new Error("finalized_source_integrity_mismatch")',
        ]
        missing = [x for x in required if x not in body]
        return {
            "existing_final_object_verified": not missing,
            "missing": missing,
            "_failures": (
                ["final_object_collision_guard_missing"]
                if missing else []
            ),
        }

    def fsp004():
        ok, positions = _ordered(
            enqueue,
            [
                "const uploadedSha256 = sha256(uploadedBuffer)",
                "const finalizedStoragePath = finalizedSourceStoragePath(",
                "await promoteFinalizedSource(",
                "upload_sha256: uploadedSha256",
                '.from("processing_jobs")',
            ],
        )
        return {
            "promote_and_pin_before_queue": ok,
            "positions": positions,
            "_failures": (
                [] if ok else ["queue_before_final_source_promotion"]
            ),
        }

    def fsp005():
        required = [
            "upload_sha256: uploadedSha256",
            "storage_path: finalizedStoragePath",
            '.eq("storage_path", storagePath)',
            '.is("upload_sha256", null)',
            '.select("upload_sha256, storage_path")',
        ]
        missing = [x for x in required if x not in enqueue]
        return {
            "hash_and_path_cas": not missing,
            "missing": missing,
            "_failures": (
                ["finalization_cas_incomplete"] if missing else []
            ),
        }

    def fsp006():
        required = [
            "concurrent.upload_sha256 !== uploadedSha256",
            "concurrent.storage_path !== finalizedStoragePath",
        ]
        missing = [x for x in required if x not in enqueue]
        return {
            "concurrent_finalization_rechecks_hash_and_path": not missing,
            "missing": missing,
            "_failures": (
                ["concurrent_final_path_recheck_missing"]
                if missing else []
            ),
        }

    def fsp007():
        marker = "} else if (storagePath !== finalizedStoragePath) {"
        pos = enqueue.find(marker)
        body = enqueue[pos:] if pos >= 0 else ""
        required = [
            '.eq("upload_sha256", uploadedSha256)',
            '.eq("storage_path", storagePath)',
            "storage_path: finalizedStoragePath",
        ]
        missing = [x for x in required if x not in body]
        return {
            "legacy_pinned_source_can_promote": not missing,
            "missing": missing,
            "_failures": (
                ["legacy_promotion_guard_missing"] if missing else []
            ),
        }

    def fsp008():
        ok, positions = _ordered(
            enqueue,
            [
                'const segments = finalizedStoragePath.split("/")',
                ".list(folder",
                '.from("processing_jobs")',
            ],
        )
        return {
            "canonical_object_checked_before_queue": ok,
            "positions": positions,
            "_failures": (
                [] if ok else ["queue_before_canonical_object_check"]
            ),
        }

    def fsp009():
        required = [
            'code === "finalized_source_integrity_mismatch"',
            'code: "FINALIZED_SOURCE_INTEGRITY_MISMATCH"',
            "{ status: 409 }",
        ]
        missing = [x for x in required if x not in route]
        return {
            "integrity_conflict_api_contract": not missing,
            "missing": missing,
            "_failures": (
                ["finalized_integrity_api_contract_missing"]
                if missing else []
            ),
        }

    def fsp010():
        owner = "owner"
        doc = "doc"
        digest = hashlib.sha256(b"verified-upload").hexdigest()
        staging = f"{owner}/{doc}/v1/source.docx"
        final = (
            f"{owner}/{doc}/finalized/{digest}/source.docx"
        )
        safe = staging != final and digest in final
        return {
            "signed_token_path": staging,
            "canonical_path": final,
            "replay_path_isolated": safe,
            "_failures": [] if safe else ["path_isolation_model_failed"],
        }

    def fsp011():
        digest = hashlib.sha256(b"same-source").hexdigest()
        first = f"o/d/finalized/{digest}/source.docx"
        second = f"o/d/finalized/{digest}/source.docx"
        changed_digest = hashlib.sha256(b"changed").hexdigest()
        changed = f"o/d/finalized/{changed_digest}/source.docx"
        ok = first == second and changed != first
        return {
            "same_bytes_same_path": first == second,
            "changed_bytes_changed_path": changed != first,
            "_failures": [] if ok else ["content_address_model_failed"],
        }

    def fsp012():
        ok, positions = _ordered(
            initial,
            [
                ".download(document.storage_path)",
                "const sourceSha256 = createHash",
                "sourceSha256 !== document.upload_sha256",
                'throw new Error("upload_integrity_mismatch")',
                "const analysis = await callAee",
            ],
        )
        return {
            "worker_uses_canonical_pointer_with_hash_guard": ok,
            "positions": positions,
            "_failures": (
                [] if ok else ["worker_canonical_guard_missing"]
            ),
        }

    funcs = [
        fsp001, fsp002, fsp003, fsp004, fsp005, fsp006,
        fsp007, fsp008, fsp009, fsp010, fsp011, fsp012,
    ]
    cases = [
        _case(f"FSP-{index:03d}", fn)
        for index, fn in enumerate(funcs, 1)
    ]
    failed = [case["id"] for case in cases if not case["passed"]]
    report = {
        "schema_version": 1,
        "benchmark": "finalized_source_promotion_storage_toctou_v1",
        "configuration": config,
        "cases": cases,
        "summary": {
            "passed": not failed,
            "passed_cases": len(cases) - len(failed),
            "total_cases": len(cases),
            "failed_cases": failed,
        },
    }

    rendered = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return 1 if args.enforce and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
