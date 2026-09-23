from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


DIGIT_TRANSLATION = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)

DIGITS = r"0-9٠-٩۰-۹"
NUMBER_PATTERN = (
    rf"(?:[{DIGITS}]{{1,3}}(?:[,٬][{DIGITS}]{{3}})+"
    rf"(?:[.٫][{DIGITS}]+)?|[{DIGITS}]+(?:[.٫][{DIGITS}]+)?)"
)
NUMBER_RE = re.compile(NUMBER_PATTERN)


def normalize_numeric_text(value: str) -> str:
    return (
        value.translate(DIGIT_TRANSLATION)
        .replace("٬", ",")
        .replace("٫", ".")
        .replace("٪", "%")
    )


def canonical_decimal(value: str) -> str | None:
    normalized = normalize_numeric_text(value)
    match = re.search(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?", normalized)
    if not match:
        return None

    raw = match.group(0).replace(",", "")

    try:
        decimal = Decimal(raw)
    except InvalidOperation:
        return None

    if decimal == decimal.to_integral():
        return str(decimal.quantize(Decimal("1")))

    return format(decimal.normalize(), "f")


def numeric_values(text: str) -> set[str]:
    values: set[str] = set()

    for match in NUMBER_RE.finditer(text):
        canonical = canonical_decimal(match.group(0))
        if canonical is not None:
            values.add(canonical)

    return values


def preserves_numeric_value(protected_value: str, candidate_text: str) -> bool:
    canonical = canonical_decimal(protected_value)
    if canonical is None:
        return protected_value in candidate_text

    return canonical in numeric_values(candidate_text)
