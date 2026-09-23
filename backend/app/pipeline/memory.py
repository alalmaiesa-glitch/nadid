from __future__ import annotations

import re
from collections import defaultdict

from app.contracts import (
    Chunk,
    DocumentMemory,
    DocumentNode,
    MemoryTerm,
    ProtectedSpan,
)
from app.pipeline.facts import detect_fact_conflicts, extract_facts


WORD_RE = re.compile(r"[\u0600-\u06FF]{4,}")
STOPWORDS = {
    "التي",
    "الذي",
    "هذه",
    "هذا",
    "ذلك",
    "تلك",
    "على",
    "إلى",
    "منها",
    "منهم",
    "فيها",
    "عليه",
    "عليها",
    "بين",
    "ضمن",
    "كما",
    "وقد",
    "ومن",
    "وذلك",
    "هناك",
    "أكثر",
    "يمكن",
    "يكون",
}


def build_document_memory(
    nodes: list[DocumentNode],
    chunks: list[Chunk],
    protected: list[ProtectedSpan],
) -> DocumentMemory:
    headings = [node.text for node in nodes if node.type == "heading"]
    occurrences: dict[str, list[str]] = defaultdict(list)

    for node in nodes:
        for word in WORD_RE.findall(node.text):
            normalized = word.strip("ـ").lower()
            if normalized in STOPWORDS or len(normalized) < 4:
                continue
            occurrences[normalized].append(node.id)

    terms = [
        MemoryTerm(
            term=term,
            count=len(node_ids),
            node_ids=list(dict.fromkeys(node_ids)),
        )
        for term, node_ids in occurrences.items()
        if len(node_ids) >= 2
    ]
    terms.sort(key=lambda item: (-item.count, item.term))
    terms = terms[:80]

    facts = extract_facts(nodes)
    conflicts = detect_fact_conflicts(facts)

    return DocumentMemory(
        headings=headings,
        terms=terms,
        facts=facts,
        conflicts=conflicts,
        protected_count=len(protected),
        chunk_count=len(chunks),
    )
