from __future__ import annotations

from dataclasses import dataclass

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
        exists_after = protected.value in candidate

        if protected.validator_key in {
            "numeric_equivalence",
            "date_equivalence",
            "exact_or_normalized_identifier",
            "negation_preservation",
        }:
            passed = (not existed_before) or exists_after
        else:
            passed = True

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
