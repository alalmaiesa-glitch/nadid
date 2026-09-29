from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.arabic_numbers import canonical_decimal, normalize_numeric_text, preserves_numeric_value
from app.contracts import ProtectedSpan
from app.pipeline.protection import (
    CONDITION_MARKERS,
    EPISTEMIC_MARKERS,
    LOGIC_MARKERS,
    NEGATION_MARKERS,
    OBLIGATION_MARKERS,
    QUALIFIER_RE,
    RELATION_MARKERS,
)


DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
NON_WORD_RE = re.compile(r"[^0-9A-Za-z\u0600-\u06FF]+")
CURRENCY_UNITS = {
    "sar": ("ريال", "ر.س", "sar"),
    "usd": ("دولار", "usd"),
    "eur": ("يورو", "eur"),
}


@dataclass
class ValidationCheck:
    protected_id: str
    value: str
    status: str


@dataclass
class PatchValidationResult:
    status: str
    candidate: str
    reason: str | None
    checks: list[ValidationCheck]


def _normalize_identity(text: str) -> str:
    value = unicodedata.normalize("NFKC", text)
    value = normalize_numeric_text(value)
    value = DIACRITICS_RE.sub("", value)
    value = value.replace("ـ", "")
    value = value.translate(
        str.maketrans(
            {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"}
        )
    )
    return NON_WORD_RE.sub("", value.casefold())


def _normalized_present(value: str, candidate: str) -> bool:
    wanted = _normalize_identity(value)
    return bool(wanted) and wanted in _normalize_identity(candidate)


def _currency_unit(value: str) -> str | None:
    normalized = normalize_numeric_text(value).casefold()
    for key, aliases in CURRENCY_UNITS.items():
        if any(alias.casefold() in normalized for alias in aliases):
            return key
    return None


def _has_currency_unit(candidate: str, unit: str) -> bool:
    normalized = normalize_numeric_text(candidate).casefold()
    return any(
        alias.casefold() in normalized
        for alias in CURRENCY_UNITS.get(unit, ())
    )


def _preserves_numeric_unit(
    protected: ProtectedSpan,
    candidate: str,
) -> bool:
    if canonical_decimal(protected.value) is None:
        return False
    if not preserves_numeric_value(protected.value, candidate):
        return False
    if protected.type == "percentage":
        return "%" in normalize_numeric_text(candidate)
    if protected.type == "currency":
        unit = _currency_unit(protected.value)
        return bool(unit) and _has_currency_unit(candidate, unit)
    return True


def _semantic_marker_signature(text: str) -> tuple[tuple[str, ...], ...]:
    patterns = (
        NEGATION_MARKERS,
        OBLIGATION_MARKERS,
        CONDITION_MARKERS,
        QUALIFIER_RE,
        EPISTEMIC_MARKERS,
        RELATION_MARKERS,
        LOGIC_MARKERS,
    )
    return tuple(
        tuple(
            sorted(
                _normalize_identity(match.group())
                for match in pattern.finditer(text)
            )
        )
        for pattern in patterns
    )


def _check_span(
    protected: ProtectedSpan,
    block_text: str,
    candidate: str,
) -> bool:
    existed_before = (
        protected.value in block_text
        or _normalized_present(protected.value, block_text)
    )
    if not existed_before:
        return True

    if protected.validator_key == "numeric_equivalence":
        return preserves_numeric_value(protected.value, candidate)
    if protected.validator_key == "numeric_unit_equivalence":
        return _preserves_numeric_unit(protected, candidate)
    if protected.validator_key == "date_equivalence":
        return _normalized_present(protected.value, candidate)
    if protected.validator_key in {
        "exact_or_normalized_identifier",
        "meaning_marker_preservation",
        "normalized_clause_preservation",
        "negation_preservation",
    }:
        return _normalized_present(protected.value, candidate)
    return protected.value in candidate


def validate_patch(
    block_text: str,
    original: str,
    replacement: str,
    protected_spans: list[ProtectedSpan],
) -> PatchValidationResult:
    if original not in block_text:
        return PatchValidationResult(
            status="BLOCK",
            candidate=block_text,
            reason="SOURCE_CHANGED",
            checks=[],
        )

    candidate = block_text.replace(original, replacement, 1)
    checks: list[ValidationCheck] = []

    marker_signature_preserved = (
        _semantic_marker_signature(block_text)
        == _semantic_marker_signature(candidate)
    )
    checks.append(
        ValidationCheck(
            protected_id="semantic-marker-signature",
            value="semantic_markers",
            status="PASS" if marker_signature_preserved else "BLOCK",
        )
    )

    for protected in protected_spans:
        passed = _check_span(protected, block_text, candidate)
        checks.append(
            ValidationCheck(
                protected_id=protected.id,
                value=protected.value,
                status="PASS" if passed else "BLOCK",
            )
        )

    blocked = any(check.status == "BLOCK" for check in checks)

    return PatchValidationResult(
        status="BLOCK" if blocked else "PASS",
        candidate=block_text if blocked else candidate,
        reason="PROTECTED_MEANING_CHANGED" if blocked else None,
        checks=checks,
    )
