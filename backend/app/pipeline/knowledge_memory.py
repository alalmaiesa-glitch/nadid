from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from uuid import NAMESPACE_URL, uuid5

from app.contracts import DocumentNode, MemoryItem, ProtectedSpan


ARABIC_WORD_RE = re.compile(r"[\u0600-\u06FF]{2,}")
LATIN_ACRONYM_RE = re.compile(
    r"(?P<long>[\u0600-\u06FF][\u0600-\u06FF\s]{3,90}?)"
    r"\s*[\(（](?P<short>[A-Z][A-Z0-9\-]{1,12})[\)）]"
)
DEFINITION_RE = re.compile(
    r"(?:يقصد\s+ب(?:مصطلح\s+)?|يُقصد\s+ب(?:مصطلح\s+)?|"
    r"يعني\s+مصطلح\s+|يعرف\s+مصطلح\s+|يُعرّف\s+مصطلح\s+)"
    r"[«\"]?(?P<term>[\u0600-\u06FF][^:،؛.!؟\n]{1,50}?)[»\"]?"
    r"\s*(?:بأنه|بأنها|أنه|أنها|:|،)\s*"
    r"(?P<definition>[^\n.!؟؛]{3,240})"
)
COLON_DEFINITION_RE = re.compile(
    r"^[«\"]?(?P<term>[\u0600-\u06FF][\u0600-\u06FF\s]{1,45}?)[»\"]?"
    r"\s*:\s*(?P<definition>[^\n]{4,240})$"
)
COLON_DEFINITION_TERM_RE = re.compile(
    r"\b(?:نطاق|مفهوم|تعريف|مصطلح|المقصود|المراد)\b"
)
DECISION_MARKERS = re.compile(
    r"\b(?:تم\s+اعتماد|تم\s+إقرار|تمت\s+الموافقة\s+على|"
    r"قرر|اعتمد|أقر|وافق\s+على)\b"
)
RELATION_RE = re.compile(
    r"^(?P<subject>[\u0600-\u06FF][\u0600-\u06FF\s]{1,70}?)\s+"
    r"(?P<predicate>تشرف\s+على|يشرف\s+على|تتبع|يتبع|"
    r"تدير|يدير|تملك|يملك|مسؤولة\s+عن|مسؤول\s+عن)\s+"
    r"(?P<object>[^،؛.!؟\n]{2,120})"
)
OBLIGATION_MARKERS = re.compile(
    r"\b(?:يجب|يتعين|يتوجب|يلتزم|تلتزم|يلزم|يحظر|لا\s+يجوز)\b"
)
CONDITION_MARKERS = re.compile(
    r"\b(?:إذا|في\s+حال|في\s+حالة|بشرط|شريطة|ما\s+لم)\b"
)
CLAUSE_RE = re.compile(r"[^.!؟؛\n]+(?:[.!؟؛]|$)")


STOPWORDS = {
    "التي",
    "الذي",
    "الذين",
    "هذا",
    "هذه",
    "ذلك",
    "تلك",
    "على",
    "إلى",
    "الى",
    "من",
    "في",
    "عن",
    "مع",
    "كما",
    "وقد",
    "ومن",
    "وذلك",
    "هناك",
    "يمكن",
    "يكون",
    "تكون",
    "بين",
    "ضمن",
    "عند",
    "بعد",
    "قبل",
    "حتى",
    "كل",
    "أو",
    "او",
    "ثم",
    "هو",
    "هي",
    "تم",
    "يتم",
    "لدى",
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("ـ", "")
    value = value.translate(
        str.maketrans(
            {
                "أ": "ا",
                "إ": "ا",
                "آ": "ا",
                "ٱ": "ا",
                "ى": "ي",
            }
        )
    )
    return " ".join(value.casefold().split())


def _stable_id(kind: str, key: str, value: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"nadid-memory|{kind}|{_normalize(key)}|{_normalize(value)}",
        )
    )


def _item(
    kind: str,
    key: str,
    value: str,
    node_ids: list[str],
    confidence: float,
    aliases: list[str] | None = None,
    metadata: dict | None = None,
) -> MemoryItem:
    return MemoryItem(
        id=_stable_id(kind, key, value),
        kind=kind,
        key=key.strip(),
        value=value.strip(),
        node_ids=list(dict.fromkeys(node_ids)),
        aliases=list(dict.fromkeys(aliases or [])),
        confidence=confidence,
        metadata=metadata or {},
    )


def _aggregate_protected(
    protected: list[ProtectedSpan],
) -> list[MemoryItem]:
    grouped: dict[tuple[str, str], list[ProtectedSpan]] = defaultdict(list)

    type_map = {
        "entity": "entity",
        "legal_reference": "reference",
        "standard": "reference",
    }

    for span in protected:
        kind = type_map.get(span.type)
        if not kind:
            continue
        grouped[(kind, _normalize(span.value))].append(span)

    output: list[MemoryItem] = []
    for (kind, _), spans in grouped.items():
        representative = spans[0].value
        metadata = {
            "source_type": spans[0].type,
            "mention_count": len(spans),
        }
        output.append(
            _item(
                kind=kind,
                key=representative,
                value=representative,
                node_ids=[span.node_id for span in spans],
                confidence=0.94 if kind == "entity" else 0.99,
                metadata=metadata,
            )
        )

    return output


def _extract_abbreviations(nodes: list[DocumentNode]) -> list[MemoryItem]:
    grouped: dict[tuple[str, str], dict] = {}

    for node in nodes:
        for match in LATIN_ACRONYM_RE.finditer(node.text):
            long_name = " ".join(match.group("long").split())
            words = long_name.split()
            if len(words) > 8:
                long_name = " ".join(words[-8:])

            short = match.group("short").strip()
            group_key = (
                short.casefold(),
                _normalize(long_name),
            )
            entry = grouped.setdefault(
                group_key,
                {
                    "short": short,
                    "long": long_name,
                    "node_ids": [],
                },
            )
            entry["node_ids"].append(node.id)

    return [
        _item(
            kind="abbreviation",
            key=entry["short"],
            value=entry["long"],
            node_ids=entry["node_ids"],
            confidence=0.97,
            aliases=[entry["short"], entry["long"]],
        )
        for entry in grouped.values()
    ]


def _extract_definitions(nodes: list[DocumentNode]) -> list[MemoryItem]:
    output: list[MemoryItem] = []
    seen: set[tuple[str, str]] = set()

    for node in nodes:
        patterns = [DEFINITION_RE]
        if node.type == "paragraph":
            patterns.append(COLON_DEFINITION_RE)

        for pattern in patterns:
            for match in pattern.finditer(node.text.strip()):
                term = " ".join(match.group("term").split()).strip("«»\" ")
                definition = " ".join(
                    match.group("definition").split()
                ).strip(" .،؛")
                if not term or not definition:
                    continue
                if len(term.split()) > 8:
                    continue
                if (
                    pattern is COLON_DEFINITION_RE
                    and not COLON_DEFINITION_TERM_RE.search(term)
                ):
                    continue
                key = (_normalize(term), _normalize(definition))
                if key in seen:
                    continue
                seen.add(key)
                output.append(
                    _item(
                        kind="definition",
                        key=term,
                        value=definition,
                        node_ids=[node.id],
                        confidence=0.96 if pattern is DEFINITION_RE else 0.86,
                        aliases=[term],
                    )
                )

    return output


def _extract_relations(nodes: list[DocumentNode]) -> list[MemoryItem]:
    output: list[MemoryItem] = []
    seen: set[tuple[str, str, str]] = set()

    for node in nodes:
        for clause_match in CLAUSE_RE.finditer(node.text):
            clause = clause_match.group().strip().rstrip(".!؟؛").strip()
            relation = RELATION_RE.match(clause)
            if not relation:
                continue

            subject = " ".join(relation.group("subject").split())
            predicate = " ".join(relation.group("predicate").split())
            obj = " ".join(relation.group("object").split())

            if len(subject.split()) > 10 or len(obj) > 140:
                continue

            key = (_normalize(subject), _normalize(predicate), _normalize(obj))
            if key in seen:
                continue
            seen.add(key)

            output.append(
                _item(
                    kind="relation",
                    key=subject,
                    value=obj,
                    node_ids=[node.id],
                    confidence=0.9,
                    metadata={
                        "subject": subject,
                        "predicate": predicate,
                        "object": obj,
                    },
                )
            )

    return output


def _extract_clause_items(nodes: list[DocumentNode]) -> list[MemoryItem]:
    output: list[MemoryItem] = []
    seen: set[tuple[str, str]] = set()

    kinds = (
        ("decision", DECISION_MARKERS, 0.92),
        ("obligation", OBLIGATION_MARKERS, 0.93),
        ("condition", CONDITION_MARKERS, 0.92),
    )

    for node in nodes:
        for clause_match in CLAUSE_RE.finditer(node.text):
            clause = clause_match.group().strip().rstrip(".!؟؛").strip()
            if not clause:
                continue

            for kind, pattern, confidence in kinds:
                if not pattern.search(clause):
                    continue
                normalized = _normalize(clause)
                key = (kind, normalized)
                if key in seen:
                    continue
                seen.add(key)
                output.append(
                    _item(
                        kind=kind,
                        key=clause[:80],
                        value=clause,
                        node_ids=[node.id],
                        confidence=confidence,
                    )
                )

    return output


def _extract_concepts(nodes: list[DocumentNode]) -> list[MemoryItem]:
    occurrences: dict[str, set[str]] = defaultdict(set)
    surface: dict[str, str] = {}

    for node in nodes:
        words = ARABIC_WORD_RE.findall(node.text)
        normalized_words = [_normalize(word) for word in words]

        for size in (2, 3):
            for index in range(0, len(words) - size + 1):
                raw = words[index:index + size]
                norm = normalized_words[index:index + size]
                if norm[0] in STOPWORDS or norm[-1] in STOPWORDS:
                    continue
                if sum(1 for token in norm if token in STOPWORDS) > 1:
                    continue
                phrase = " ".join(norm)
                if len(phrase) < 7:
                    continue
                occurrences[phrase].add(node.id)
                surface.setdefault(phrase, " ".join(raw))

    candidates = [
        (phrase, node_ids)
        for phrase, node_ids in occurrences.items()
        if len(node_ids) >= 2
    ]
    candidates.sort(
        key=lambda item: (
            -len(item[1]),
            -len(item[0].split()),
            item[0],
        )
    )

    # Remove shorter concepts fully contained in a stronger longer concept
    # with the same node set.
    selected: list[tuple[str, set[str]]] = []
    for phrase, node_ids in candidates:
        if any(
            phrase in other
            and node_ids == other_nodes
            for other, other_nodes in selected
        ):
            continue
        selected.append((phrase, node_ids))
        if len(selected) >= 40:
            break

    return [
        _item(
            kind="concept",
            key=surface[phrase],
            value=surface[phrase],
            node_ids=sorted(node_ids),
            confidence=0.84,
            metadata={
                "mentioning_nodes": len(node_ids),
                "word_count": len(phrase.split()),
            },
        )
        for phrase, node_ids in selected
    ]


def build_knowledge_memory(
    nodes: list[DocumentNode],
    protected: list[ProtectedSpan],
) -> list[MemoryItem]:
    items: list[MemoryItem] = []
    items.extend(_aggregate_protected(protected))
    items.extend(_extract_abbreviations(nodes))
    items.extend(_extract_definitions(nodes))
    items.extend(_extract_relations(nodes))
    items.extend(_extract_clause_items(nodes))
    items.extend(_extract_concepts(nodes))

    deduped: dict[str, MemoryItem] = {}
    for item in items:
        existing = deduped.get(item.id)
        if not existing:
            deduped[item.id] = item
            continue

        merged_nodes = list(
            dict.fromkeys(existing.node_ids + item.node_ids)
        )
        merged_aliases = list(
            dict.fromkeys(existing.aliases + item.aliases)
        )
        deduped[item.id] = existing.model_copy(
            update={
                "node_ids": merged_nodes,
                "aliases": merged_aliases,
                "confidence": max(existing.confidence, item.confidence),
            }
        )

    priority = {
        "definition": 0,
        "abbreviation": 1,
        "entity": 2,
        "reference": 3,
        "decision": 4,
        "obligation": 5,
        "condition": 6,
        "relation": 7,
        "concept": 8,
    }

    result = list(deduped.values())
    result.sort(
        key=lambda item: (
            priority.get(item.kind, 99),
            -len(item.node_ids),
            item.key,
        )
    )
    return result[:240]
