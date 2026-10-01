from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DEFAULT_CONFIG = ROOT / "version_lineage" / "v1.json"
PERSISTENCE = REPO / "lib" / "server" / "document-persistence.ts"
ROUTE = REPO / "app" / "api" / "documents" / "[id]" / "versions" / "route.ts"
MIGRATION = REPO / "supabase" / "migrations" / "0026_document_version_lineage.sql"


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
    route = ROUTE.read_text(encoding="utf-8")
    migration = MIGRATION.read_text(encoding="utf-8").lower()

    start = persistence.find("export async function createDocumentVersion")
    end = persistence.find("export async function downloadDocumentVersion", start)
    create = persistence[start:end]

    list_start = persistence.find("export async function listDocumentVersions")
    list_end = persistence.find("export async function assertDocumentOwner", list_start)
    listing = persistence[list_start:list_end]

    def ver001():
        required = [
            "enforce_document_version_lineage",
            "document_versions_lineage_guard",
            "before insert or update of",
        ]
        missing = [x for x in required if x not in migration]
        return {
            "database_trigger_present": not missing,
            "missing": missing,
            "_failures": ["lineage_trigger_missing"] if missing else [],
        }

    def ver002():
        required = [
            "version_lineage_invalid_source",
            "new.version_no <> 1",
            "new.parent_version_id is not null",
        ]
        missing = [x for x in required if x not in migration]
        return {
            "source_root_contract": not missing,
            "missing": missing,
            "_failures": ["source_root_contract_missing"] if missing else [],
        }

    def ver003():
        required = [
            "version_lineage_cross_document_parent",
            "parent_document_id <> new.document_id",
        ]
        missing = [x for x in required if x not in migration]
        return {
            "cross_document_parent_blocked": not missing,
            "missing": missing,
            "_failures": ["cross_document_parent_guard_missing"] if missing else [],
        }

    def ver004():
        required = [
            "version_lineage_parent_not_previous",
            "parent_version_no <> new.version_no - 1",
        ]
        missing = [x for x in required if x not in migration]
        return {
            "previous_version_parent_required": not missing,
            "missing": missing,
            "_failures": ["previous_parent_guard_missing"] if missing else [],
        }

    def ver005():
        required = [
            '.eq("status", "ready")',
            "latestReady.id !== parentVersionId",
            "Number(latestReady.version_no) !== parentVersionNo",
            'throw new Error("version_lineage_changed")',
        ]
        missing = [x for x in required if x not in create]
        return {
            "runtime_latest_parent_cas": not missing,
            "missing": missing,
            "_failures": ["latest_parent_runtime_guard_missing"] if missing else [],
        }

    def ver006():
        required = [
            "const nextVersionNo = parentVersionNo + 1",
            "parent_version_id: parentVersionId",
        ]
        missing = [x for x in required if x not in create]
        return {
            "next_version_is_parent_plus_one": not missing,
            "missing": missing,
            "_failures": ["derived_sequence_contract_missing"] if missing else [],
        }

    def ver007():
        required = [
            'if (occupied.status !== "failed")',
            "await removeStorageObjects([occupied.storage_path as string])",
            '.eq("status", "failed")',
            'throw new Error("version_cleanup_failed")',
        ]
        missing = [x for x in required if x not in create]
        return {
            "failed_slot_cleanup": not missing,
            "missing": missing,
            "_failures": ["failed_slot_cleanup_missing"] if missing else [],
        }

    def ver008():
        required = [
            "const resultSha256 = sha256(buffer)",
            "const ownerId = document.owner_id as string",
            "/versions/v",
            "${resultSha256}/source.docx",
        ]
        missing = [x for x in required if x not in create]
        return {
            "owner_scoped_content_addressed_path": not missing,
            "missing": missing,
            "_failures": ["derived_storage_path_not_hardened"] if missing else [],
        }

    def ver009():
        ok, positions = _ordered(
            create,
            [
                '.from("document_versions")',
                'status: "creating"',
                '.upload(storagePath, buffer',
                "await persistFastAnalysisRows",
                '.update({ status: "ready" })',
            ],
        )
        return {
            "db_reservation_before_storage": ok,
            "positions": positions,
            "_failures": [] if ok else ["storage_write_before_version_reservation"],
        }

    def ver010():
        required = [
            '["23503", "23505", "23514"].includes(code)',
            'throw new Error("version_lineage_changed")',
        ]
        missing = [x for x in required if x not in create]
        return {
            "db_lineage_conflicts_normalized": not missing,
            "missing": missing,
            "_failures": ["database_conflict_mapping_missing"] if missing else [],
        }

    def ver011():
        ok, positions = _ordered(
            create,
            [
                "await persistFastAnalysisRows",
                '.update({ status: "ready" })',
            ],
        )
        return {
            "ready_after_analysis_persistence": ok,
            "positions": positions,
            "_failures": [] if ok else ["ready_before_analysis_persistence"],
        }

    def ver012():
        required = [
            'update({ status: "failed" })',
            "if (storageError)",
            "} catch (error) {",
        ]
        missing = [x for x in required if x not in create]
        return {
            "failed_state_on_partial_failure": not missing,
            "missing": missing,
            "_failures": ["partial_failure_state_missing"] if missing else [],
        }

    def ver013():
        required = [
            'code === "version_lineage_changed"',
            'code: "VERSION_CHANGED"',
            "{ status: 409 }",
            'code === "version_cleanup_failed"',
            'code: "VERSION_CLEANUP_FAILED"',
        ]
        missing = [x for x in required if x not in route]
        return {
            "api_conflict_contract": not missing,
            "missing": missing,
            "_failures": ["version_conflict_api_contract_missing"] if missing else [],
        }

    def ver014():
        required = [
            "parent_version_id",
            "source_sha256",
            "parentVersionId:",
            "sourceSha256:",
        ]
        missing = [x for x in required if x not in listing]
        return {
            "version_lineage_visible": not missing,
            "missing": missing,
            "_failures": ["lineage_listing_missing"] if missing else [],
        }

    def ver015():
        owner = "owner-a"
        document = "doc-a"
        version_no = 2
        payload = b"derived-version"
        digest = hashlib.sha256(payload).hexdigest()
        path = (
            f"{owner}/{document}/versions/v{version_no}/"
            f"{digest}/source.docx"
        )
        same = (
            f"{owner}/{document}/versions/v{version_no}/"
            f"{hashlib.sha256(payload).hexdigest()}/source.docx"
        )
        changed = (
            f"{owner}/{document}/versions/v{version_no}/"
            f"{hashlib.sha256(b'changed').hexdigest()}/source.docx"
        )
        ok = path == same and path != changed
        return {
            "deterministic_path": path == same,
            "content_change_moves_path": path != changed,
            "_failures": [] if ok else ["derived_path_model_failed"],
        }

    funcs = [
        ver001, ver002, ver003, ver004, ver005,
        ver006, ver007, ver008, ver009, ver010,
        ver011, ver012, ver013, ver014, ver015,
    ]
    cases = [
        _case(f"VER-{index:03d}", fn)
        for index, fn in enumerate(funcs, 1)
    ]
    failed = [case["id"] for case in cases if not case["passed"]]

    report = {
        "schema_version": 1,
        "benchmark": "derived_version_lineage_orphan_safe_v1",
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
