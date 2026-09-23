from __future__ import annotations

import re
from collections import defaultdict
from uuid import NAMESPACE_URL, uuid5

from app.arabic_numbers import NUMBER_PATTERN, canonical_decimal
from app.contracts import DocumentNode, FactAssertion, FactConflict


VALUE_RE = re.compile(
    rf"(?P<value>{NUMBER_PATTERN})"
    r"\s*(?P<unit>ريال|ر\.س|[%٪]|وحدة|فرع|محور|محاور|صفحة|سنة|سنوات)?"
)
WORD_RE = re.compile(r"[\u0600-\u06FF]{2,}")


def _canonical_number(value: str) -> str:
    return canonical_decimal(value) or value.strip()


def _claim_context(text: str, start: int) -> str:
    prefix = text[max(0, start - 90):start]
    words = WORD_RE.findall(prefix)
    return " ".join(words[-6:])


def extract_facts(nodes: list[DocumentNode]) -> list[FactAssertion]:
    facts: list[FactAssertion] = []

    for node in nodes:
        for match in VALUE_RE.finditer(node.text):
            value = match.group("value")
            unit = match.group("unit") or "number"
            context = _claim_context(node.text, match.start())

            # Years alone are useful context but too weak for conflict detection.
            canonical = canonical
            fact_type = (
                "date"
                if unit == "number"
                and canonical.isdigit()
                and len(canonical) == 4
                and canonical[:2] in {"19", "20"}
                else ("%" if unit == "٪" else unit)
            )
            normalized_context = " ".join(context.split())
            claim_key = f"{normalized_context}|{fact_type}".strip("|")

            facts.append(
                FactAssertion(
                    id=str(
                        uuid5(
                            NAMESPACE_URL,
                            f"{node.id}|{fact_type}|{claim_key}|"
                            f"{canonical}|{match.start()}",
                        )
                    ),
                    node_id=node.id,
                    fact_type=fact_type,
                    claim_key=claim_key,
                    value=(value + (" " + unit if unit != "number" else "")).strip(),
                    canonical_value=canonical,
                    context=node.text[max(0, match.start() - 120):match.end() + 80],
                    confidence=0.92 if unit != "number" else 0.78,
                )
            )

    return facts


def detect_fact_conflicts(facts: list[FactAssertion]) -> list[FactConflict]:
    grouped: dict[str, list[FactAssertion]] = defaultdict(list)

    for fact in facts:
        if not fact.claim_key or fact.fact_type == "date":
            continue
        grouped[fact.claim_key].append(fact)

    conflicts: list[FactConflict] = []

    for claim_key, group in grouped.items():
        values = sorted({fact.canonical_value for fact in group})
        if len(values) <= 1:
            continue

        conflicts.append(
            FactConflict(
                id=str(
                    uuid5(
                        NAMESPACE_URL,
                        claim_key + "|" + "|".join(
                            sorted(fact.id for fact in group)
                        ),
                    )
                ),
                claim_key=claim_key,
                fact_ids=[fact.id for fact in group],
                values=values,
                confidence=min(fact.confidence for fact in group),
            )
        )

    return conflicts
