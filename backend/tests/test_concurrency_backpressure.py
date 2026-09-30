from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from docx import Document
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


def _docx(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def _post(payload: bytes, filename: str = "test.docx"):
    with TestClient(app, raise_server_exceptions=False) as client:
        return client.post(
            "/v1/analyze/docx",
            files={
                "file": (
                    filename,
                    payload,
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document",
                )
            },
        )


def test_capacity_guard_returns_503_when_all_slots_are_occupied():
    acquired = 0
    try:
        for _ in range(main_module.AEE_MAX_CONCURRENT_JOBS):
            assert main_module._AEE_WORK_SLOTS.acquire(blocking=False)
            acquired += 1

        response = _post(_docx("مستند صحيح."))

        assert response.status_code == 503
        assert response.headers["retry-after"] == "1"
        assert response.json()["detail"]["code"] == "AEE_BUSY"
    finally:
        for _ in range(acquired):
            main_module._AEE_WORK_SLOTS.release()


def test_health_endpoint_is_not_blocked_by_document_capacity():
    acquired = 0
    try:
        for _ in range(main_module.AEE_MAX_CONCURRENT_JOBS):
            assert main_module._AEE_WORK_SLOTS.acquire(blocking=False)
            acquired += 1

        with TestClient(app) as client:
            response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        for _ in range(acquired):
            main_module._AEE_WORK_SLOTS.release()


def test_concurrent_requests_do_not_leak_document_text():
    markers = ["مرجان", "ياقوت", "زمرد", "لؤلؤ"]
    workers = min(
        len(markers),
        main_module.AEE_MAX_CONCURRENT_JOBS,
    )
    selected = markers[:workers]

    def analyze(marker: str):
        response = _post(
            _docx(
                f"هاذا المستند يحمل الرمز {marker} فقط."
            )
        )
        return marker, response

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(analyze, selected))

    for marker, response in results:
        assert response.status_code == 200, response.text
        node_text = " ".join(
            node["text"]
            for node in response.json()["nodes"]
        )
        assert marker in node_text
        assert all(
            other == marker or other not in node_text
            for other in selected
        )


def test_malformed_request_does_not_poison_parallel_valid_requests():
    valid_a = _docx("هاذا مستند صحيح يحمل مرجان.")
    valid_b = _docx("هاذا مستند صحيح يحمل زمرد.")

    payloads = [
        valid_a,
        b"not-a-docx",
        valid_b,
        b"also-not-a-docx",
    ]
    workers = min(
        len(payloads),
        main_module.AEE_MAX_CONCURRENT_JOBS,
    )

    # Keep the test deterministic when an operator configures fewer than four
    # slots: run only as many simultaneous requests as the configured gate.
    selected = payloads[:workers]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        responses = list(pool.map(_post, selected))

    statuses = [response.status_code for response in responses]
    assert all(status in {200, 422} for status in statuses)
    assert 500 not in statuses

    for payload, response in zip(selected, responses):
        if payload.startswith(b"PK"):
            assert response.status_code == 200
        else:
            assert response.status_code == 422
