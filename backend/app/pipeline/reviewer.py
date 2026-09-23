from __future__ import annotations

import re
from uuid import uuid4

from app.contracts import DocumentNode, Suggestion


def _issue(
    node: DocumentNode,
    category: str,
    title: str,
    explanation: str,
    original: str,
    replacement: str | None,
    confidence: float,
) -> Suggestion:
    return Suggestion(
        id=str(uuid4()),
        node_id=node.id,
        category=category,
        title=title,
        explanation=explanation,
        original=original,
        replacement=replacement,
        confidence=confidence,
    )


def fast_review(nodes: list[DocumentNode]) -> list[Suggestion]:
    issues: list[Suggestion] = []

    for node in nodes:
        if node.type == "heading":
            continue

        text = node.text

        punctuation = re.search(r"\s+([،؛:؟!,.])", text)
        if punctuation:
            issues.append(
                _issue(
                    node,
                    "language",
                    "مسافة قبل علامة ترقيم",
                    "لا توضع مسافة قبل علامة الترقيم.",
                    punctuation.group(0),
                    punctuation.group(1),
                    0.99,
                )
            )

        if "تحسين من مستوى" in text:
            issues.append(
                _issue(
                    node,
                    "style",
                    "حرف جر زائد",
                    "يمكن حذف «من» لتصبح العبارة أخف وأدق.",
                    "تحسين من مستوى",
                    "تحسين مستوى",
                    0.97,
                )
            )

        if "بناءاً" in text:
            issues.append(
                _issue(
                    node,
                    "language",
                    "رسم إملائي",
                    "الصواب «بناءً» دون ألف بعد الهمزة.",
                    "بناءاً",
                    "بناءً",
                    0.99,
                )
            )

        if "ان شاء الله" in text:
            issues.append(
                _issue(
                    node,
                    "language",
                    "فصل كلمتين",
                    "الصواب «إن شاء الله».",
                    "ان شاء الله",
                    "إن شاء الله",
                    0.98,
                )
            )

        repeated = re.search(r"\b([\u0600-\u06FF]{3,})\s+\1\b", text)
        if repeated:
            issues.append(
                _issue(
                    node,
                    "style",
                    "تكرار كلمة",
                    "وردت الكلمة نفسها مرتين متتاليتين.",
                    repeated.group(0),
                    repeated.group(1),
                    0.94,
                )
            )

    return issues
