from __future__ import annotations

import re
from uuid import uuid4

from app.contracts import DocumentNode, ProtectedSpan


CURRENCY_RE = re.compile(
    r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\s*(?:ريال|ر\.س)"
)
NUMBER_RE = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b")
PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*%")
DATE_RE = re.compile(r"\b(?:19|20)\d{2}\b")
STANDARD_RE = re.compile(r"\bISO\s*\d{3,6}(?::\d{4})?\b", re.IGNORECASE)
NEGATION_RE = re.compile(
    r"(?:^|\s)(?:و|ف)?(?:لا|لم|لن|ليس|ليست)\s+[^،؛.!؟\n]{1,55}"
)


def _span(
    node_id: str,
    span_type: str,
    value: str,
    validator_key: str,
    lock_policy: str = "normalize_only",
) -> ProtectedSpan:
    return ProtectedSpan(
        id=str(uuid4()),
        node_id=node_id,
        type=span_type,
        value=value.strip(),
        validator_key=validator_key,
        lock_policy=lock_policy,
    )


def extract_protected_spans(nodes: list[DocumentNode]) -> list[ProtectedSpan]:
    output: list[ProtectedSpan] = []
    seen: set[tuple[str, str, str]] = set()

    for node in nodes:
        text = node.text
        candidates: list[ProtectedSpan] = []

        candidates += [
            _span(node.id, "currency", m.group(), "numeric_equivalence")
            for m in CURRENCY_RE.finditer(text)
        ]
        candidates += [
            _span(node.id, "number", m.group(), "numeric_equivalence")
            for m in NUMBER_RE.finditer(text)
        ]
        candidates += [
            _span(node.id, "percentage", m.group(), "numeric_equivalence")
            for m in PERCENT_RE.finditer(text)
        ]
        candidates += [
            _span(node.id, "date", m.group(), "date_equivalence")
            for m in DATE_RE.finditer(text)
        ]
        candidates += [
            _span(
                node.id,
                "standard",
                m.group(),
                "exact_or_normalized_identifier",
                "exact",
            )
            for m in STANDARD_RE.finditer(text)
        ]
        candidates += [
            _span(
                node.id,
                "negation",
                m.group(),
                "negation_preservation",
                "semantic_exact",
            )
            for m in NEGATION_RE.finditer(text)
        ]

        for candidate in candidates:
            key = (candidate.node_id, candidate.type, candidate.value)
            if key in seen:
                continue
            seen.add(key)
            output.append(candidate)

    return output
