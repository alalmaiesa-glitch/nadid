from __future__ import annotations

import re
from uuid import NAMESPACE_URL, uuid5

from app.arabic_numbers import DIGITS, NUMBER_PATTERN
from app.contracts import DocumentNode, ProtectedSpan


CURRENCY_RE = re.compile(
    rf"(?P<number>{NUMBER_PATTERN})\s*(?P<unit>ريال|ر\.س|SAR|دولار|USD|يورو|EUR)",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(NUMBER_PATTERN)
PERCENT_RE = re.compile(rf"{NUMBER_PATTERN}\s*[%٪]")
DATE_RE = re.compile(
    rf"(?<![{DIGITS}])(?:19|20|١٩|٢٠|۱۹|۲۰)[{DIGITS}]{{2}}(?![{DIGITS}])"
)
STANDARD_RE = re.compile(
    rf"\bISO\s*[{DIGITS}]{{3,6}}(?::[{DIGITS}]{{4}})?\b",
    re.IGNORECASE,
)
LEGAL_REFERENCE_RE = re.compile(
    rf"(?:المادة|مادة|البند|بند|الفقرة|فقرة|الفصل|فصل)"
    rf"\s*(?:رقم\s*)?[\(\[]?\s*{NUMBER_PATTERN}\s*[\)\]]?"
)
ROLE_RE = re.compile(
    r"\bالطرف\s+(?:الأول|الثاني|الثالث|الرابع)\b"
)
QUOTE_RE = re.compile(r"«[^»\n]{1,500}»")

NEGATION_MARKERS = re.compile(
    r"(?:^|\s)(?:و|ف)?(?:لا|لم|لن|ليس|ليست|غير|دون|ما\s+لم)\b"
)
OBLIGATION_MARKERS = re.compile(
    r"\b(?:يجب|يتعين|يلتزم|تلتزم|يلزم|يحظر|"
    r"لا\s+يجوز|يحق|يتحمل|تتحمل|يتولى|تتولى)\b"
)
CONDITION_MARKERS = re.compile(
    r"\b(?:إذا|في\s+حال|في\s+حالة|بشرط|شريطة|ما\s+لم)\b"
)
QUALIFIER_RE = re.compile(
    r"\b(?:فقط|حصراً|حصرًا|جميع|كافة|باستثناء|"
    r"بحد\s+أقصى|بحد\s+أدنى|لا\s+يقل\s+عن|لا\s+يزيد\s+عن)\b"
)

ENTITY_HEADS = {
    "وزارة",
    "الوزارة",
    "هيئة",
    "الهيئة",
    "شركة",
    "الشركة",
    "مؤسسة",
    "المؤسسة",
    "جمعية",
    "الجمعية",
    "جامعة",
    "الجامعة",
    "صندوق",
    "الصندوق",
    "مركز",
    "المركز",
    "مجلس",
    "المجلس",
    "بنك",
    "البنك",
}

ENTITY_STOPWORDS = {
    "تتولى",
    "يتولى",
    "تقوم",
    "يقوم",
    "تعمل",
    "يعمل",
    "تشرف",
    "يشرف",
    "الإشراف",
    "مسؤولة",
    "مسؤول",
    "هي",
    "هو",
    "تم",
    "يتم",
    "على",
    "في",
    "من",
    "إلى",
    "عن",
    "وفق",
    "بموجب",
}

ARABIC_WORD_RE = re.compile(r"[\u0600-\u06FF]+")
CLAUSE_RE = re.compile(r"[^.!؟؛\n]+(?:[.!؟؛]|$)")


def _span(
    node_id: str,
    span_type: str,
    value: str,
    validator_key: str,
    lock_policy: str = "normalize_only",
) -> ProtectedSpan:
    clean_value = value.strip()
    stable_id = str(
        uuid5(
            NAMESPACE_URL,
            f"{node_id}|{span_type}|{validator_key}|{clean_value}",
        )
    )
    return ProtectedSpan(
        id=stable_id,
        node_id=node_id,
        type=span_type,
        value=clean_value,
        validator_key=validator_key,
        lock_policy=lock_policy,
    )


def _extract_entities(node_id: str, text: str) -> list[ProtectedSpan]:
    matches = list(ARABIC_WORD_RE.finditer(text))
    output: list[ProtectedSpan] = []

    for index, token in enumerate(matches):
        if token.group() not in ENTITY_HEADS:
            continue

        selected = [token]
        for next_token in matches[index + 1:index + 6]:
            word = next_token.group()
            if word in ENTITY_STOPWORDS:
                break
            selected.append(next_token)

        if len(selected) < 2:
            continue

        value = text[selected[0].start():selected[-1].end()].strip()
        output.append(
            _span(
                node_id,
                "entity",
                value,
                "exact_or_normalized_identifier",
                "identity",
            )
        )

    return output


def _critical_clause_spans(
    node_id: str,
    text: str,
) -> list[ProtectedSpan]:
    output: list[ProtectedSpan] = []

    for match in CLAUSE_RE.finditer(text):
        clause = match.group().strip()
        clause = clause.rstrip(".!?;").strip()
        if not clause:
            continue

        if NEGATION_MARKERS.search(clause):
            output.append(
                _span(
                    node_id,
                    "negation",
                    clause,
                    "normalized_clause_preservation",
                    "semantic_strict",
                )
            )

        if OBLIGATION_MARKERS.search(clause):
            output.append(
                _span(
                    node_id,
                    "obligation",
                    clause,
                    "normalized_clause_preservation",
                    "semantic_strict",
                )
            )

        if CONDITION_MARKERS.search(clause):
            output.append(
                _span(
                    node_id,
                    "condition",
                    clause,
                    "normalized_clause_preservation",
                    "semantic_strict",
                )
            )

    return output


def extract_protected_spans(nodes: list[DocumentNode]) -> list[ProtectedSpan]:
    output: list[ProtectedSpan] = []
    seen: set[tuple[str, str, str]] = set()

    for node in nodes:
        text = node.text
        candidates: list[ProtectedSpan] = []

        candidates += [
            _span(
                node.id,
                "currency",
                m.group(),
                "numeric_unit_equivalence",
                "value_and_unit",
            )
            for m in CURRENCY_RE.finditer(text)
        ]
        candidates += [
            _span(
                node.id,
                "number",
                m.group(),
                "numeric_equivalence",
            )
            for m in NUMBER_RE.finditer(text)
        ]
        candidates += [
            _span(
                node.id,
                "percentage",
                m.group(),
                "numeric_unit_equivalence",
                "value_and_unit",
            )
            for m in PERCENT_RE.finditer(text)
        ]
        candidates += [
            _span(
                node.id,
                "date",
                m.group(),
                "date_equivalence",
            )
            for m in DATE_RE.finditer(text)
        ]
        candidates += [
            _span(
                node.id,
                "standard",
                m.group(),
                "exact_or_normalized_identifier",
                "identity",
            )
            for m in STANDARD_RE.finditer(text)
        ]
        candidates += [
            _span(
                node.id,
                "legal_reference",
                m.group(),
                "exact_or_normalized_identifier",
                "identity",
            )
            for m in LEGAL_REFERENCE_RE.finditer(text)
        ]
        candidates += [
            _span(
                node.id,
                "role",
                m.group(),
                "exact_or_normalized_identifier",
                "identity",
            )
            for m in ROLE_RE.finditer(text)
        ]
        candidates += [
            _span(
                node.id,
                "quotation",
                m.group(),
                "exact_or_normalized_identifier",
                "exact",
            )
            for m in QUOTE_RE.finditer(text)
        ]
        candidates += [
            _span(
                node.id,
                "qualifier",
                m.group(),
                "meaning_marker_preservation",
                "semantic_marker",
            )
            for m in QUALIFIER_RE.finditer(text)
        ]
        candidates += _extract_entities(node.id, text)
        candidates += _critical_clause_spans(node.id, text)

        for candidate in candidates:
            key = (candidate.node_id, candidate.type, candidate.value)
            if key in seen:
                continue
            seen.add(key)
            output.append(candidate)

    return output
