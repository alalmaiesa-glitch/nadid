from __future__ import annotations

import os
import secrets
from hashlib import sha256
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from pydantic import BaseModel, TypeAdapter

from app.contracts import (
    AnalyzeResponse,
    ContextPackage,
    ContextRequest,
    DeepAnalyzeResponse,
    PatchOperation,
    ProtectedSpan,
)
from app.pipeline.chunker import build_chunks
from app.pipeline.parser import parse_docx
from app.pipeline.patch_validator import validate_patch
from app.pipeline.protection import extract_protected_spans
from app.pipeline.reviewer import fast_review
from app.pipeline.memory import build_document_memory
from app.pipeline.context import retrieve_context
from app.pipeline.docx_patch import apply_patches_to_docx
from app.docx_security import UnsafeDocxError, validate_docx_payload, validate_word_count


app = FastAPI(
    title="Nadid AEE",
    version="0.1.0",
    description="Arabic Editorial Engine for long Arabic documents.",
)


class PatchRequest(BaseModel):
    block_text: str
    original: str
    replacement: str
    protected_spans: list[ProtectedSpan]


def require_internal_auth(
    authorization: str | None = Header(default=None),
):
    environment = os.getenv("NADID_ENV", "development").lower()
    expected = os.getenv("AEE_INTERNAL_TOKEN")

    if not expected:
        if environment == "production":
            raise HTTPException(
                status_code=503,
                detail="AEE internal authentication is not configured.",
            )
        return

    scheme, _, supplied = (authorization or "").partition(" ")

    if scheme.lower() != "bearer" or not secrets.compare_digest(
        supplied,
        expected,
    ):
        raise HTTPException(status_code=401, detail="Unauthorized.")


@app.get("/health")
def health():
    return {"status": "ok", "service": "nadid-aee"}


@app.post("/v1/analyze/docx", response_model=AnalyzeResponse)
async def analyze_docx(
    file: UploadFile = File(...),
    _auth: None = Depends(require_internal_auth),
):
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=415,
            detail="The current backend accepts DOCX files only.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")

    try:
        validate_docx_payload(data)
    except UnsafeDocxError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Unsafe or invalid DOCX: {exc}",
        ) from exc

    try:
        nodes = parse_docx(data)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="Could not parse the DOCX file.",
        ) from exc

    if not nodes:
        raise HTTPException(
            status_code=422,
            detail="No reviewable content found.",
        )

    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    suggestions = fast_review(nodes)

    text = " ".join(node.text for node in nodes)
    word_count = len([token for token in text.split() if token])

    try:
        validate_word_count(word_count)
    except UnsafeDocxError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    return AnalyzeResponse(
        document={
            "filename": file.filename,
            "word_count": word_count,
            "paragraph_count": sum(
                1 for node in nodes if node.type == "paragraph"
            ),
            "heading_count": sum(
                1 for node in nodes if node.type == "heading"
            ),
        },
        nodes=nodes,
        chunks=chunks,
        suggestions=suggestions,
        protected_spans=protected,
    )


@app.post("/v1/validate-patch")
def validate_patch_endpoint(
    request: PatchRequest,
    _auth: None = Depends(require_internal_auth),
):
    result = validate_patch(
        block_text=request.block_text,
        original=request.original,
        replacement=request.replacement,
        protected_spans=request.protected_spans,
    )

    return {
        "status": result.status,
        "candidate": result.candidate,
        "reason": result.reason,
        "checks": [
            {
                "protected_id": check.protected_id,
                "value": check.value,
                "status": check.status,
            }
            for check in result.checks
        ],
    }


@app.post("/v1/analyze/docx/deep", response_model=DeepAnalyzeResponse)
async def analyze_docx_deep(
    file: UploadFile = File(...),
    _auth: None = Depends(require_internal_auth),
):
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=415, detail="DOCX only.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")

    try:
        validate_docx_payload(data)
    except UnsafeDocxError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Unsafe or invalid DOCX: {exc}",
        ) from exc

    nodes = parse_docx(data)
    if not nodes:
        raise HTTPException(status_code=422, detail="No reviewable content found.")

    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    suggestions = fast_review(nodes)
    memory = build_document_memory(nodes, chunks, protected)

    text = " ".join(node.text for node in nodes)
    word_count = len([token for token in text.split() if token])

    try:
        validate_word_count(word_count)
    except UnsafeDocxError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    base = AnalyzeResponse(
        document={
            "filename": file.filename,
            "word_count": word_count,
            "paragraph_count": sum(
                1 for node in nodes if node.type == "paragraph"
            ),
            "heading_count": sum(
                1 for node in nodes if node.type == "heading"
            ),
        },
        nodes=nodes,
        chunks=chunks,
        suggestions=suggestions,
        protected_spans=protected,
    )

    return DeepAnalyzeResponse(base=base, memory=memory)


class ContextEnvelope(BaseModel):
    nodes: list
    chunks: list
    memory: dict
    request: ContextRequest


@app.post("/v1/context", response_model=ContextPackage)
def context_endpoint(
    envelope: ContextEnvelope,
    _auth: None = Depends(require_internal_auth),
):
    from app.contracts import Chunk, DocumentMemory, DocumentNode

    nodes = [DocumentNode.model_validate(item) for item in envelope.nodes]
    chunks = [Chunk.model_validate(item) for item in envelope.chunks]
    memory = DocumentMemory.model_validate(envelope.memory)

    try:
        return retrieve_context(
            target_node_id=envelope.request.target_node_id,
            nodes=nodes,
            chunks=chunks,
            memory=memory,
            query=envelope.request.query,
            max_chunks=envelope.request.max_chunks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/v1/apply/docx")
async def apply_docx_patches(
    file: UploadFile = File(...),
    patches: str = Form(...),
    _auth: None = Depends(require_internal_auth),
):
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=415, detail="DOCX only.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")

    try:
        validate_docx_payload(data)
    except UnsafeDocxError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Unsafe or invalid DOCX: {exc}",
        ) from exc

    try:
        patch_list = TypeAdapter(list[PatchOperation]).validate_json(patches)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid patch payload.",
        ) from exc

    nodes = parse_docx(data)
    node_map = {node.id: node for node in nodes}
    protected = extract_protected_spans(nodes)
    protected_by_node: dict[str, list[ProtectedSpan]] = {}

    for span in protected:
        protected_by_node.setdefault(span.node_id, []).append(span)

    working_text = {node.id: node.text for node in nodes}
    validated: list[PatchOperation] = []
    blocked: list[dict] = []

    for patch in patch_list:
        source_text = working_text.get(patch.node_id)

        if source_text is None:
            blocked.append(
                {
                    "node_id": patch.node_id,
                    "reason": "NODE_NOT_FOUND",
                }
            )
            continue

        result = validate_patch(
            block_text=source_text,
            original=patch.original,
            replacement=patch.replacement,
            protected_spans=protected_by_node.get(patch.node_id, []),
        )

        if result.status != "PASS":
            blocked.append(
                {
                    "node_id": patch.node_id,
                    "reason": result.reason,
                }
            )
            continue

        working_text[patch.node_id] = result.candidate
        validated.append(patch)

    if blocked:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PATCH_SET_REJECTED",
                "blocked": blocked,
            },
        )

    output, report = apply_patches_to_docx(data, validated)

    if report.skipped:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PATCH_APPLICATION_INCOMPLETE",
                "skipped": report.skipped,
            },
        )

    filename = file.filename.rsplit(".", 1)[0] + "-nadid.docx"

    return Response(
        content=output,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Nadid-Applied-Patches": str(len(report.applied)),
        },
    )
