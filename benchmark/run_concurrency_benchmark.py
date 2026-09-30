from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "concurrency" / "v1.json"


def _docx(text: str, paragraphs: int = 1) -> bytes:
    document = Document()
    for index in range(paragraphs):
        document.add_paragraph(
            text if index == 0 else f"{text} فقرة {index + 1}."
        )
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def _post(payload: bytes, endpoint: str = "analyze"):
    path = {
        "analyze": "/v1/analyze/docx",
        "deep": "/v1/analyze/docx/deep",
    }[endpoint]
    with TestClient(app, raise_server_exceptions=False) as client:
        return client.post(
            path,
            files={
                "file": (
                    "concurrency.docx",
                    payload,
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document",
                )
            },
        )


def _health():
    with TestClient(app, raise_server_exceptions=False) as client:
        return client.get("/health")


def _case(
    case_id: str,
    fn,
) -> dict[str, Any]:
    started = time.perf_counter()
    failures: list[str] = []

    try:
        observed = fn()
        if isinstance(observed, dict):
            failures.extend(observed.pop("_failures", []))
        else:
            observed = {"value": observed}
    except Exception as exc:
        observed = {
            "exception": type(exc).__name__,
            "message": str(exc)[:300],
        }
        failures.append("benchmark_exception")

    return {
        "id": case_id,
        "elapsed_seconds": round(
            time.perf_counter() - started,
            6,
        ),
        "observed": observed,
        "failures": failures,
        "passed": not failures,
    }


def _parallel_isolation(config: dict[str, Any]):
    markers = [
        "مرجان",
        "ياقوت",
        "زمرد",
        "لؤلؤ",
        "فيروز",
        "عقيق",
    ]
    count = min(
        int(config["parallel_isolation_documents"]),
        main_module.AEE_MAX_CONCURRENT_JOBS,
        len(markers),
    )
    selected = markers[:count]

    def work(marker: str):
        response = _post(
            _docx(
                f"هاذا المستند يحمل الرمز {marker} فقط."
            )
        )
        return marker, response

    with ThreadPoolExecutor(max_workers=count) as pool:
        rows = list(pool.map(work, selected))

    failures = []
    statuses = []
    for marker, response in rows:
        statuses.append(response.status_code)
        if response.status_code != 200:
            failures.append(f"status:{marker}:{response.status_code}")
            continue

        node_text = " ".join(
            node["text"]
            for node in response.json()["nodes"]
        )
        if marker not in node_text:
            failures.append(f"own_marker_missing:{marker}")
        for other in selected:
            if other != marker and other in node_text:
                failures.append(
                    f"cross_request_leak:{marker}:{other}"
                )

    return {
        "documents": count,
        "statuses": statuses,
        "_failures": failures,
    }


def _parallel_determinism(config: dict[str, Any]):
    count = min(
        int(config["determinism_requests"]),
        main_module.AEE_MAX_CONCURRENT_JOBS,
    )
    payload = _docx(
        "هاذا التقرير يراجع النتيجة نفسها في كل تشغيل."
    )

    with ThreadPoolExecutor(max_workers=count) as pool:
        responses = list(
            pool.map(
                lambda _: _post(payload),
                range(count),
            )
        )

    failures = []
    signatures = []
    for response in responses:
        if response.status_code != 200:
            failures.append(f"status:{response.status_code}")
            continue
        body = response.json()
        signatures.append(
            {
                "nodes": [node["id"] for node in body["nodes"]],
                "suggestions": [
                    item["id"]
                    for item in body["suggestions"]
                ],
            }
        )

    if signatures and any(
        signature != signatures[0]
        for signature in signatures[1:]
    ):
        failures.append("non_deterministic_parallel_output")

    return {
        "requests": count,
        "unique_signatures": len(
            {
                json.dumps(item, sort_keys=True)
                for item in signatures
            }
        ),
        "_failures": failures,
    }


def _mixed_valid_malformed():
    payloads = [
        _docx("هاذا مستند صحيح يحمل مرجان."),
        b"not-a-docx",
        _docx("هاذا مستند صحيح يحمل زمرد."),
        b"also-not-a-docx",
    ]
    count = min(
        len(payloads),
        main_module.AEE_MAX_CONCURRENT_JOBS,
    )
    selected = payloads[:count]

    with ThreadPoolExecutor(max_workers=count) as pool:
        responses = list(pool.map(_post, selected))

    failures = []
    statuses = []
    for payload, response in zip(selected, responses):
        statuses.append(response.status_code)
        expected = 200 if payload.startswith(b"PK") else 422
        if response.status_code != expected:
            failures.append(
                f"status:{response.status_code}!={expected}"
            )
        if response.status_code >= 500:
            failures.append("server_error_escape")

    return {
        "statuses": statuses,
        "_failures": failures,
    }


def _saturated_backpressure():
    acquired = 0
    try:
        for _ in range(main_module.AEE_MAX_CONCURRENT_JOBS):
            if not main_module._AEE_WORK_SLOTS.acquire(
                blocking=False
            ):
                break
            acquired += 1

        response = _post(_docx("مستند صحيح."))
        failures = []

        if acquired != main_module.AEE_MAX_CONCURRENT_JOBS:
            failures.append("could_not_saturate_gate")
        if response.status_code != 503:
            failures.append(
                f"status:{response.status_code}!=503"
            )
        else:
            body = response.json()
            if body.get("detail", {}).get("code") != "AEE_BUSY":
                failures.append("missing_busy_code")
            if response.headers.get("retry-after") != "1":
                failures.append("missing_retry_after")

        return {
            "slots_acquired": acquired,
            "status": response.status_code,
            "retry_after": response.headers.get("retry-after"),
            "_failures": failures,
        }
    finally:
        for _ in range(acquired):
            main_module._AEE_WORK_SLOTS.release()


def _health_while_saturated():
    acquired = 0
    try:
        for _ in range(main_module.AEE_MAX_CONCURRENT_JOBS):
            if main_module._AEE_WORK_SLOTS.acquire(blocking=False):
                acquired += 1

        response = _health()
        failures = []
        if response.status_code != 200:
            failures.append(
                f"health_status:{response.status_code}"
            )
        return {
            "slots_acquired": acquired,
            "health_status": response.status_code,
            "_failures": failures,
        }
    finally:
        for _ in range(acquired):
            main_module._AEE_WORK_SLOTS.release()


def _recovery_after_saturation():
    first = _post(_docx("هاذا مستند بعد تحرير السعة."))
    failures = []
    if first.status_code != 200:
        failures.append(f"recovery_status:{first.status_code}")
    return {
        "status": first.status_code,
        "_failures": failures,
    }


def _burst(config: dict[str, Any], malformed: bool):
    total = int(config["burst_requests"])
    workers = int(config["burst_workers"])
    allowed = set(
        config[
            "allowed_malformed_burst_statuses"
            if malformed
            else "allowed_burst_statuses"
        ]
    )

    def work(index: int):
        if malformed:
            payload = f"broken-{index}".encode("ascii")
        else:
            payload = _docx(
                f"هاذا طلب متزامن رقم {index}.",
                paragraphs=12,
            )
        return _post(payload)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        responses = list(pool.map(work, range(total)))

    statuses = [response.status_code for response in responses]
    failures = []
    if any(status not in allowed for status in statuses):
        failures.append("unexpected_burst_status")
    if any(status >= 500 for status in statuses):
        failures.append("server_error_escape")
    if not malformed and 200 not in statuses:
        failures.append("no_successful_request")

    busy = [
        response
        for response in responses
        if response.status_code == 503
    ]
    if any(
        response.json().get("detail", {}).get("code") != "AEE_BUSY"
        or response.headers.get("retry-after") != "1"
        for response in busy
    ):
        failures.append("invalid_backpressure_response")

    counts = {
        str(status): statuses.count(status)
        for status in sorted(set(statuses))
    }
    return {
        "requests": total,
        "workers": workers,
        "status_counts": counts,
        "_failures": failures,
    }


def _deep_parallel():
    count = min(2, main_module.AEE_MAX_CONCURRENT_JOBS)
    payloads = [
        _docx("هاذا تحليل عميق مرجان.", paragraphs=20),
        _docx("هاذا تحليل عميق زمرد.", paragraphs=20),
    ][:count]

    with ThreadPoolExecutor(max_workers=count) as pool:
        responses = list(
            pool.map(
                lambda payload: _post(payload, "deep"),
                payloads,
            )
        )

    failures = []
    statuses = [response.status_code for response in responses]
    if any(status != 200 for status in statuses):
        failures.append("deep_parallel_failure")
    if any(status >= 500 for status in statuses):
        failures.append("server_error_escape")

    return {
        "requests": count,
        "statuses": statuses,
        "_failures": failures,
    }


def _malformed_recovery_sequence():
    failures = []
    malformed_statuses = []

    for index in range(12):
        response = _post(f"invalid-{index}".encode("ascii"))
        malformed_statuses.append(response.status_code)
        if response.status_code != 422:
            failures.append(
                f"malformed_status:{response.status_code}"
            )

    recovery = _post(_docx("هاذا المستند يأتي بعد سلسلة فشل."))
    if recovery.status_code != 200:
        failures.append(
            f"post_failure_recovery:{recovery.status_code}"
        )

    return {
        "malformed_statuses": malformed_statuses,
        "recovery_status": recovery.status_code,
        "_failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))

    cases = [
        _case("CON-001", lambda: _parallel_isolation(config)),
        _case("CON-002", lambda: _parallel_determinism(config)),
        _case("CON-003", _mixed_valid_malformed),
        _case("CON-004", _saturated_backpressure),
        _case("CON-005", _health_while_saturated),
        _case("CON-006", _recovery_after_saturation),
        _case("CON-007", lambda: _burst(config, False)),
        _case("CON-008", lambda: _burst(config, True)),
        _case("CON-009", _deep_parallel),
        _case("CON-010", _malformed_recovery_sequence),
    ]

    failed = [case["id"] for case in cases if not case["passed"]]
    report = {
        "schema_version": 1,
        "benchmark": "concurrent_load_failure_isolation_backpressure_v1",
        "configuration": {
            "aee_max_concurrent_jobs": (
                main_module.AEE_MAX_CONCURRENT_JOBS
            ),
            "backpressure_status": 503,
            "retry_after_seconds": 1,
        },
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
