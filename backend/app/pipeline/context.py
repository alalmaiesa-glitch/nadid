from __future__ import annotations

import re

from app.contracts import (
    Chunk,
    ContextHit,
    ContextPackage,
    DocumentMemory,
    DocumentNode,
)
from app.pipeline.semantic_utils import semantic_similarity, semantic_tokens


TOKEN_RE = re.compile(r"[\u0600-\u06FFA-Za-z0-9]{2,}")


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


def _score(query: str, chunk: Chunk) -> float:
    query_tokens = _tokens(query)
    semantic_query_tokens = semantic_tokens(query)

    if not query_tokens and not semantic_query_tokens:
        return 0.0

    chunk_tokens = _tokens(chunk.text)
    lexical_overlap = (
        len(query_tokens & chunk_tokens) / max(1, len(query_tokens))
        if query_tokens
        else 0.0
    )

    semantic_score = semantic_similarity(query, chunk.text)
    phrase_bonus = (
        0.25
        if query.strip() and query.strip() in chunk.text
        else 0.0
    )

    # Exact lexical evidence remains strongest, but semantic equivalence can
    # retrieve related passages even when their wording differs.
    return min(
        1.0,
        max(
            lexical_overlap + phrase_bonus,
            semantic_score * 0.9,
        ),
    )


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

    nodes_by_id = {node.id: node for node in nodes}
    ranked: list[ContextHit] = []
    for chunk in chunks:
        candidate_chunk = chunk

        if target_node_id in chunk.node_ids:
            other_node_ids = [
                node_id
                for node_id in chunk.node_ids
                if node_id != target_node_id
            ]
            if not other_node_ids:
                continue

            other_text = "\n".join(
                nodes_by_id[node_id].text
                for node_id in other_node_ids
                if node_id in nodes_by_id
            )
            candidate_chunk = Chunk(
                id=chunk.id,
                node_ids=other_node_ids,
                text=other_text,
                token_estimate=max(1, len(other_text) // 4),
                previous_chunk_id=chunk.previous_chunk_id,
                next_chunk_id=chunk.next_chunk_id,
            )

        score = _score(search_query, candidate_chunk)
        if score <= 0:
            continue
        ranked.append(
            ContextHit(
                chunk_id=candidate_chunk.id,
                score=round(score, 4),
                text=candidate_chunk.text,
                node_ids=candidate_chunk.node_ids,
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
