from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DEFAULT_CONFIG = ROOT / "queue_recovery" / "v1.json"
MIGRATION = REPO / "supabase" / "migrations" / "0022_queue_lease_crash_recovery.sql"
WORKER = REPO / "worker" / "index.mjs"
LEASE_TIMEOUT = timedelta(minutes=15)


@dataclass(frozen=True)
class Job:
    status: str
    attempts: int
    max_attempts: int
    available_at: datetime
    locked_at: datetime | None = None
    locked_by: str | None = None
    job_type: str = "initial_review"


def _claimable(job: Job, now: datetime) -> bool:
    if job.attempts >= job.max_attempts:
        return False
    if job.status == "queued":
        return job.available_at <= now
    if job.status == "processing":
        return bool(
            job.locked_at
            and job.locked_at < now - LEASE_TIMEOUT
        )
    return False


def _reap(job: Job, now: datetime) -> tuple[Job, str | None]:
    if (
        job.status == "processing"
        and job.attempts >= job.max_attempts
        and job.locked_at
        and job.locked_at < now - LEASE_TIMEOUT
    ):
        document_status = (
            "partial_ready"
            if job.job_type == "deep_review"
            else "failed"
        )
        return (
            replace(
                job,
                status="failed",
                locked_at=None,
                locked_by=None,
            ),
            document_status,
        )
    return job, None


def _claim(job: Job, worker: str, now: datetime) -> Job | None:
    if not _claimable(job, now):
        return None
    return replace(
        job,
        status="processing",
        attempts=job.attempts + 1,
        locked_at=now,
        locked_by=worker,
    )


def _renew(job: Job, worker: str, now: datetime) -> Job | None:
    if (
        job.status != "processing"
        or job.locked_by != worker
    ):
        return None
    return replace(job, locked_at=now)


def _complete(job: Job, worker: str) -> Job | None:
    if (
        job.status != "processing"
        or job.locked_by != worker
    ):
        return None
    return replace(
        job,
        status="complete",
        locked_at=None,
        locked_by=None,
    )


def _case(case_id: str, fn):
    failures: list[str] = []
    observed: dict[str, Any] = {}
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
    now = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    old = now - timedelta(minutes=16)
    fresh = now - timedelta(minutes=1)

    def con001():
        job = Job("processing", 1, 3, now, old, "worker-a")
        claimed = _claim(job, "worker-b", now)
        failures = []
        if not claimed:
            failures.append("stale_retry_not_reclaimed")
        elif claimed.attempts != 2 or claimed.locked_by != "worker-b":
            failures.append("stale_retry_claim_state_wrong")
        return {
            "claimed": bool(claimed),
            "attempts": claimed.attempts if claimed else None,
            "owner": claimed.locked_by if claimed else None,
            "_failures": failures,
        }

    def con002():
        job = Job("processing", 3, 3, now, old, "dead-worker")
        reaped, document_status = _reap(job, now)
        failures = []
        if reaped.status != "failed":
            failures.append("final_attempt_not_failed")
        if reaped.locked_by is not None or reaped.locked_at is not None:
            failures.append("final_attempt_lock_not_cleared")
        if document_status != "failed":
            failures.append("initial_document_not_failed")
        return {
            "job_status": reaped.status,
            "document_status": document_status,
            "_failures": failures,
        }

    def con003():
        job = Job(
            "processing", 3, 3, now, old, "dead-worker", "deep_review"
        )
        reaped, document_status = _reap(job, now)
        failures = []
        if reaped.status != "failed":
            failures.append("deep_final_attempt_not_failed")
        if document_status != "partial_ready":
            failures.append("deep_document_should_remain_partial_ready")
        return {
            "job_status": reaped.status,
            "document_status": document_status,
            "_failures": failures,
        }

    def con004():
        job = Job("processing", 1, 3, now, fresh, "worker-a")
        failures = []
        if _claim(job, "worker-b", now) is not None:
            failures.append("fresh_lease_reclaimed")
        return {"claimable": _claimable(job, now), "_failures": failures}

    def con005():
        job = Job("queued", 0, 3, now + timedelta(minutes=5))
        failures = []
        if _claim(job, "worker-a", now) is not None:
            failures.append("future_job_claimed_early")
        return {"claimable": _claimable(job, now), "_failures": failures}

    def con006():
        job = Job("queued", 0, 3, now - timedelta(seconds=1))
        claimed = _claim(job, "worker-a", now)
        failures = []
        if not claimed or claimed.attempts != 1:
            failures.append("queued_claim_did_not_increment_attempt")
        return {
            "attempts": claimed.attempts if claimed else None,
            "owner": claimed.locked_by if claimed else None,
            "_failures": failures,
        }

    def con007():
        job = Job("processing", 1, 3, now, fresh, "worker-a")
        renewed = _renew(job, "worker-a", now)
        failures = []
        if not renewed or renewed.locked_at != now:
            failures.append("owner_could_not_renew")
        return {"renewed": bool(renewed), "_failures": failures}

    def con008():
        job = Job("processing", 1, 3, now, fresh, "worker-a")
        failures = []
        if _renew(job, "worker-b", now) is not None:
            failures.append("wrong_worker_renewed_lease")
        return {"renewed": False, "_failures": failures}

    def con009():
        job = Job("processing", 1, 3, now, fresh, "worker-a")
        completed = _complete(job, "worker-a")
        failures = []
        if not completed or completed.status != "complete":
            failures.append("owner_completion_failed")
        return {
            "status": completed.status if completed else None,
            "_failures": failures,
        }

    def con010():
        job = Job("processing", 2, 3, now, fresh, "worker-b")
        failures = []
        if _complete(job, "worker-a") is not None:
            failures.append("stale_worker_completed_foreign_lease")
        return {"completed": False, "_failures": failures}

    def con011():
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        required = [
            "renew_processing_job_lease",
            "worker_lease_expired_after_final_attempt",
            "attempts >= max_attempts",
            "locked_at < now() - v_lease_timeout",
            "grant execute on function public.renew_processing_job_lease",
            "grant execute on function public.claim_processing_job",
            "to service_role",
        ]
        missing = [item for item in required if item not in sql]
        return {
            "required_contracts": len(required),
            "missing": missing,
            "_failures": (
                ["migration_contract_incomplete:" + ",".join(missing)]
                if missing else []
            ),
        }

    def con012():
        worker = WORKER.read_text(encoding="utf-8")
        required = [
            "WORKER_JOB_LEASE_RENEW_INTERVAL_MS",
            "renew_processing_job_lease",
            'eq("locked_by", WORKER_ID)',
            "job_lease_lost_before_complete",
            "job_failure_ignored_after_lease_loss",
            "lease.stop()",
        ]
        missing = [item for item in required if item not in worker]
        return {
            "required_contracts": len(required),
            "missing": missing,
            "_failures": (
                ["worker_fencing_contract_incomplete:" + ",".join(missing)]
                if missing else []
            ),
        }

    cases = [
        _case("QRC-001", con001),
        _case("QRC-002", con002),
        _case("QRC-003", con003),
        _case("QRC-004", con004),
        _case("QRC-005", con005),
        _case("QRC-006", con006),
        _case("QRC-007", con007),
        _case("QRC-008", con008),
        _case("QRC-009", con009),
        _case("QRC-010", con010),
        _case("QRC-011", con011),
        _case("QRC-012", con012),
    ]

    failed = [case["id"] for case in cases if not case["passed"]]
    report = {
        "schema_version": 1,
        "benchmark": "queue_lease_retry_crash_recovery_v1",
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

    if args.enforce and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
