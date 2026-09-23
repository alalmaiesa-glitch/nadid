from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from app.contracts import Chunk, DocumentNode


def _estimate_tokens(text: str) -> int:
    # Conservative v0.1 estimate; replace with model tokenizer per provider later.
    return max(1, int(len(text.split()) * 1.7))


def build_chunks(
    nodes: list[DocumentNode],
    target_tokens: int = 900,
    hard_limit: int = 1300,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    current_nodes: list[DocumentNode] = []
    current_text: list[str] = []
    current_tokens = 0

    def flush():
        nonlocal current_nodes, current_text, current_tokens
        if not current_nodes:
            return
        node_ids = [node.id for node in current_nodes]
        chunk_text = "\n\n".join(current_text)
        chunk_identity = "|".join(node_ids) + "|" + chunk_text
        chunks.append(
            Chunk(
                id=str(uuid5(NAMESPACE_URL, chunk_identity)),
                node_ids=node_ids,
                text=chunk_text,
                token_estimate=current_tokens,
            )
        )
        current_nodes = []
        current_text = []
        current_tokens = 0

    for node in nodes:
        node_tokens = _estimate_tokens(node.text)

        if node.type == "heading" and current_nodes:
            flush()

        if current_nodes and current_tokens + node_tokens > hard_limit:
            flush()

        current_nodes.append(node)
        current_text.append(node.text)
        current_tokens += node_tokens

        if current_tokens >= target_tokens and node.type != "heading":
            flush()

    flush()

    for index, chunk in enumerate(chunks):
        chunk.previous_chunk_id = chunks[index - 1].id if index > 0 else None
        chunk.next_chunk_id = (
            chunks[index + 1].id if index < len(chunks) - 1 else None
        )

    return chunks
