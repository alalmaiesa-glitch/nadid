from __future__ import annotations

from dataclasses import dataclass

from app.arabic_numbers import preserves_numeric_value
from app.contracts import ProtectedSpan


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

    for protected in protected_spans:
        existed_before = protected.value in block_text

        if protected.validator_key in {
            "numeric_equivalence",
            "date_equivalence",
        }:
            passed = (
                not existed_before
                or preserves_numeric_value(protected.value, candidate)
            )
        elif protected.validator_key == "exact_or_normalized_identifier":
            passed = (
                not existed_before
                or protected.value.casefold() in candidate.casefold()
            )
        elif protected.validator_key == "negation_preservation":
            passed = not existed_before or protected.value in candidate
        else:
            passed = not existed_before or protected.value in candidate

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
        reason="PROTECTED_FACT_CHANGED" if blocked else None,
        checks=checks,
    )
