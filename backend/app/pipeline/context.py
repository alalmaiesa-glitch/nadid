from __future__ import annotations

import re

from app.contracts import (
    Chunk,
    ContextHit,
    ContextPackage,
    DocumentMemory,
    DocumentNode,
)


TOKEN_RE = re.compile(r"[\u0600-\u06FFA-Za-z0-9]{2,}")


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


def _score(query: str, chunk: Chunk) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0

    chunk_tokens = _tokens(chunk.text)
    overlap = len(query_tokens & chunk_tokens) / max(1, len(query_tokens))

    phrase_bonus = 0.25 if query.strip() and query.strip() in chunk.text else 0.0
    return min(1.0, overlap + phrase_bonus)


def retrieve_context(
    target_node_id: str,
    nodes: list[DocumentNode],
    chunks: list[Chunk],
    memory: DocumentMemory,
    query: str | None = None,
    max_chunks: int = 5,
) -> ContextPackage:
    node_index = {node.id: index for index, node in enumerate(nodes)}
    target_index = node_index.get(target_node_id)

    if target_index is None:
        raise ValueError("target_node_not_found")

    target = nodes[target_index]
    search_query = query or target.text

    start = max(0, target_index - 1)
    end = min(len(nodes), target_index + 2)
    local_nodes = nodes[start:end]

    ranked: list[ContextHit] = []
    for chunk in chunks:
        if target_node_id in chunk.node_ids:
            continue
        score = _score(search_query, chunk)
        if score <= 0:
            continue
        ranked.append(
            ContextHit(
                chunk_id=chunk.id,
                score=round(score, 4),
                text=chunk.text,
                node_ids=chunk.node_ids,
            )
        )

    ranked.sort(key=lambda hit: hit.score, reverse=True)
    hits = ranked[:max_chunks]

    related_facts = [
        fact
        for fact in memory.facts
        if fact.node_id == target_node_id
        or bool(_tokens(fact.context) & _tokens(search_query))
    ][:20]

    return ContextPackage(
        target_node_id=target_node_id,
        local_nodes=local_nodes,
        hits=hits,
        related_facts=related_facts,
    )
