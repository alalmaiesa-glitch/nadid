from __future__ import annotations

import re
from collections import defaultdict
from uuid import NAMESPACE_URL, uuid5

from app.contracts import DocumentMemory, DocumentNode, SemanticIssue
from app.pipeline.semantic_utils import (
    normalize_arabic,
    semantic_similarity,
    semantic_tokens,
)


STATUS_RE = re.compile(
    r"^(?P<subject>[\u0600-\u06FF\s]{2,80}?)\s+"
    r"(?P<neg>غير|ليس|ليست)?\s*"
    r"(?P<status>"
    r"معتمد(?:ه|ة)?|مكتمل(?:ه|ة)?|فعال(?:ه|ة)?|"
    r"ساري(?:ه|ة)?|متاح(?:ه|ة)?|ملزم(?:ه|ة)?|"
    r"جاهز(?:ه|ة)?"
    r")\b"
)

POSITIVE_DECISION_RE = re.compile(
    r"\b(?:تم\s+اعتماد|اعتمد|تمت\s+الموافقه\s+علي|"
    r"وافق\s+علي)\s+(?P<object>[^،؛.!؟\n]{2,180})"
)
NEGATIVE_DECISION_RE = re.compile(
    r"\b(?:تم\s+الغاء|الغي|تم\s+رفض|رفض)\s+"
    r"(?P<object>[^،؛.!؟\n]{2,180})"
)

STATUS_ROOTS = {
    "معتمد": "approved",
    "معتمده": "approved",
    "مكتمل": "complete",
    "مكتمله": "complete",
    "فعال": "active",
    "فعاله": "active",
    "ساري": "valid",
    "ساريه": "valid",
    "متاح": "available",
    "متاحه": "available",
    "ملزم": "binding",
    "ملزمه": "binding",
    "جاهز": "ready",
    "جاهزه": "ready",
}


def _stable_id(issue_type: str, parts: list[str]) -> str:
    payload = "|".join(normalize_arabic(part) for part in parts)
    return str(
        uuid5(
            NAMESPACE_URL,
            f"nadid-semantic-review|{issue_type}|{payload}",
        )
    )


def _issue(
    issue_type: str,
    node_id: str,
    title: str,
    explanation: str,
    original: str,
    evidence_node_ids: list[str],
    evidence_values: list[str],
    confidence: float,
) -> SemanticIssue:
    return SemanticIssue(
        id=_stable_id(
            issue_type,
            [node_id, original, *evidence_node_ids, *evidence_values],
        ),
        node_id=node_id,
        issue_type=issue_type,
        title=title,
        explanation=explanation,
        original=original,
        evidence_node_ids=list(dict.fromkeys(evidence_node_ids)),
        evidence_values=list(dict.fromkeys(evidence_values)),
        confidence=confidence,
    )


def _definition_issues(memory: DocumentMemory) -> list[SemanticIssue]:
    groups: dict[str, list] = defaultdict(list)
    for item in memory.knowledge_items:
        if item.kind == "definition":
            groups[normalize_arabic(item.key)].append(item)

    output: list[SemanticIssue] = []
    for _, items in groups.items():
        if len(items) < 2:
            continue

        for index, left in enumerate(items):
            for right in items[index + 1:]:
                if semantic_similarity(left.value, right.value) >= 0.72:
                    continue

                output.append(
                    _issue(
                        "definition_conflict",
                        right.node_ids[0],
                        "اختلاف في تعريف مصطلح",
                        (
                            f"ورد المصطلح «{right.key}» بتعريفين "
                            "مختلفين في المستند ويحتاج ذلك إلى تحقق."
                        ),
                        right.value,
                        left.node_ids + right.node_ids,
                        [left.value, right.value],
                        0.96,
                    )
                )
                break

    return output


def _abbreviation_issues(memory: DocumentMemory) -> list[SemanticIssue]:
    groups: dict[str, list] = defaultdict(list)
    for item in memory.knowledge_items:
        if item.kind == "abbreviation":
            groups[normalize_arabic(item.key)].append(item)

    output: list[SemanticIssue] = []
    for _, items in groups.items():
        if len(items) < 2:
            continue

        for index, left in enumerate(items):
            for right in items[index + 1:]:
                if semantic_similarity(left.value, right.value) >= 0.75:
                    continue

                output.append(
                    _issue(
                        "abbreviation_conflict",
                        right.node_ids[0],
                        "اختصار مرتبط بأكثر من معنى",
                        (
                            f"الاختصار «{right.key}» مرتبط بأسماء "
                            "مختلفة داخل المستند."
                        ),
                        right.key,
                        left.node_ids + right.node_ids,
                        [left.value, right.value],
                        0.97,
                    )
                )
                break

    return output


def _status_claims(nodes: list[DocumentNode]) -> list[dict]:
    claims: list[dict] = []

    for node in nodes:
        if node.type == "heading":
            continue

        normalized = normalize_arabic(node.text)
        match = STATUS_RE.search(normalized)
        if not match:
            continue

        subject = " ".join(match.group("subject").split())
        status = match.group("status")
        root = STATUS_ROOTS.get(status)
        if not root:
            continue

        negated = bool(match.group("neg"))
        subject_tokens = sorted(semantic_tokens(subject))
        if not subject_tokens:
            continue

        claims.append(
            {
                "node_id": node.id,
                "subject": subject,
                "subject_key": " ".join(subject_tokens[-8:]),
                "status": root,
                "negated": negated,
                "text": node.text,
            }
        )

    return claims


def _polarity_issues(nodes: list[DocumentNode]) -> list[SemanticIssue]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for claim in _status_claims(nodes):
        groups[(claim["subject_key"], claim["status"])].append(claim)

    output: list[SemanticIssue] = []
    for claims in groups.values():
        positives = [claim for claim in claims if not claim["negated"]]
        negatives = [claim for claim in claims if claim["negated"]]

        if not positives or not negatives:
            continue

        positive = positives[0]
        negative = negatives[0]
        output.append(
            _issue(
                "polarity_conflict",
                negative["node_id"],
                "تعارض في حالة مذكورة",
                (
                    "وردت الحالة نفسها بصيغتين متعارضتين "
                    "إحداهما مثبتة والأخرى منفية."
                ),
                negative["text"],
                [positive["node_id"], negative["node_id"]],
                [positive["text"], negative["text"]],
                0.98,
            )
        )

    return output


def _decision_claims(nodes: list[DocumentNode]) -> list[dict]:
    claims: list[dict] = []

    for node in nodes:
        if node.type == "heading":
            continue

        normalized = normalize_arabic(node.text)

        for polarity, pattern in (
            ("positive", POSITIVE_DECISION_RE),
            ("negative", NEGATIVE_DECISION_RE),
        ):
            for match in pattern.finditer(normalized):
                obj = " ".join(match.group("object").split())
                if not obj:
                    continue
                claims.append(
                    {
                        "node_id": node.id,
                        "polarity": polarity,
                        "object": obj,
                        "text": node.text,
                    }
                )

    return claims


def _decision_issues(nodes: list[DocumentNode]) -> list[SemanticIssue]:
    claims = _decision_claims(nodes)
    positive = [item for item in claims if item["polarity"] == "positive"]
    negative = [item for item in claims if item["polarity"] == "negative"]
    output: list[SemanticIssue] = []
    seen: set[tuple[str, str]] = set()

    for approved in positive:
        for cancelled in negative:
            similarity = semantic_similarity(
                approved["object"],
                cancelled["object"],
            )
            left = normalize_arabic(approved["object"])
            right = normalize_arabic(cancelled["object"])
            if (
                similarity < 0.6
                and left not in right
                and right not in left
            ):
                continue

            key = tuple(
                sorted([approved["node_id"], cancelled["node_id"]])
            )
            if key in seen:
                continue
            seen.add(key)

            output.append(
                _issue(
                    "decision_conflict",
                    cancelled["node_id"],
                    "قراران متعارضان حول الموضوع نفسه",
                    (
                        "وجد نَضِيد قرار اعتماد وقرار إلغاء أو رفض "
                        "يبدوان متعلقين بالموضوع نفسه."
                    ),
                    cancelled["text"],
                    [approved["node_id"], cancelled["node_id"]],
                    [approved["text"], cancelled["text"]],
                    min(0.98, 0.88 + similarity * 0.1),
                )
            )

    return output


def semantic_review(
    nodes: list[DocumentNode],
    memory: DocumentMemory,
) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    issues.extend(_definition_issues(memory))
    issues.extend(_abbreviation_issues(memory))
    issues.extend(_polarity_issues(nodes))
    issues.extend(_decision_issues(nodes))

    deduped: dict[str, SemanticIssue] = {}
    for issue in issues:
        deduped.setdefault(issue.id, issue)

    result = list(deduped.values())
    result.sort(
        key=lambda issue: (
            -issue.confidence,
            issue.issue_type,
            issue.node_id,
        )
    )
    return result
