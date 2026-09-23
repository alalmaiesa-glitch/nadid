from __future__ import annotations

from hashlib import sha256
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.contracts import (
    AnalyzeResponse,
    ContextPackage,
    ContextRequest,
    DeepAnalyzeResponse,
    ProtectedSpan,
)
from app.pipeline.chunker import build_chunks
from app.pipeline.parser import parse_docx
from app.pipeline.patch_validator import validate_patch
from app.pipeline.protection import extract_protected_spans
from app.pipeline.reviewer import fast_review
from app.pipeline.memory import build_document_memory
from app.pipeline.context import retrieve_context


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


@app.get("/health")
def health():
    return {"status": "ok", "service": "nadid-aee"}


@app.post("/v1/analyze/docx", response_model=AnalyzeResponse)
async def analyze_docx(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=415,
            detail="The current backend accepts DOCX files only.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")

    if len(data) > 100 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="File exceeds the v0.1 operational limit of 100 MB.",
        )

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
def validate_patch_endpoint(request: PatchRequest):
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
async def analyze_docx_deep(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=415, detail="DOCX only.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")

    nodes = parse_docx(data)
    if not nodes:
        raise HTTPException(status_code=422, detail="No reviewable content found.")

    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    suggestions = fast_review(nodes)
    memory = build_document_memory(nodes, chunks, protected)

    text = " ".join(node.text for node in nodes)
    word_count = len([token for token in text.split() if token])

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
def context_endpoint(envelope: ContextEnvelope):
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
