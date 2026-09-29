from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable
from uuid import NAMESPACE_URL, uuid5

from app.contracts import DocumentNode, Suggestion


ARABIC = r"\u0600-\u06FF"
ARABIC_WORD_BOUNDARY_LEFT = rf"(?<![{ARABIC}])"
ARABIC_WORD_BOUNDARY_RIGHT = rf"(?![{ARABIC}])"
URL_RE = re.compile(r"https?://|www\.|\b[\w.+-]+@[\w.-]+\.\w+\b", re.I)
CODEISH_RE = re.compile(r"[{}<>_=]{2,}|\b(?:const|function|SELECT|INSERT|UPDATE)\b")
FULL_QUOTE_RE = re.compile(r"^\s*«.*»\s*[.!؟؛]?$", re.S)


Replacement = str | Callable[[re.Match[str]], str]


@dataclass(frozen=True)
class ReviewRule:
    id: str
    category: str
    title: str
    explanation: str
    pattern: re.Pattern[str]
    replacement: Replacement
    confidence: float
    apply_to_headings: bool = True
    max_matches: int = 2


def _stable_suggestion_id(
    node_id: str,
    rule_id: str,
    start: int,
    original: str,
) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"nadid-review|{node_id}|{rule_id}|{start}|{original}",
        )
    )


def _literal_pattern(value: str) -> re.Pattern[str]:
    return re.compile(
        ARABIC_WORD_BOUNDARY_LEFT
        + re.escape(value)
        + ARABIC_WORD_BOUNDARY_RIGHT
    )


def _literal_rule(
    rule_id: str,
    category: str,
    wrong: str,
    correct: str,
    title: str,
    explanation: str,
    confidence: float = 0.99,
    apply_to_headings: bool = True,
) -> ReviewRule:
    return ReviewRule(
        id=rule_id,
        category=category,
        title=title,
        explanation=explanation,
        pattern=_literal_pattern(wrong),
        replacement=correct,
        confidence=confidence,
        apply_to_headings=apply_to_headings,
    )


UNIT_AFTER_NUMBER = (
    r"(?:أشهر|اشهر|شهر|أيام|ايام|يوم|سنوات|سنة|"
    r"ساعات|ساعة|وحدات|وحدة|قطع|قطعة|صفحات|صفحة|"
    r"متر|كيلومتر|كجم|طن)"
)

LANGUAGE_RULES: tuple[ReviewRule, ...] = (
    ReviewRule(
        id="punctuation.number_unit_colon",
        category="language",
        title="علامة ترقيم زائدة بين العدد والوحدة",
        explanation="لا توضع النقطتان بين العدد ووحدة القياس أو المدة.",
        pattern=re.compile(
            rf"(?P<number>[0-9٠-٩۰-۹]+(?:[.,٫٬][0-9٠-٩۰-۹]+)?)"
            rf"\s*:\s*(?P<unit>{UNIT_AFTER_NUMBER})"
        ),
        replacement=lambda m: f"{m.group('number')} {m.group('unit')}",
        confidence=0.995,
        max_matches=4,
    ),
    ReviewRule(
        id="punctuation.space_before",
        category="language",
        title="مسافة قبل علامة ترقيم",
        explanation="لا توضع مسافة قبل علامة الترقيم.",
        pattern=re.compile(
            rf"\s+([،؛؟!,.]|:(?!\s*{UNIT_AFTER_NUMBER}))"
        ),
        replacement=lambda m: m.group(1),
        confidence=0.995,
        max_matches=4,
    ),
    ReviewRule(
        id="punctuation.missing_space_after_period",
        category="language",
        title="مسافة بعد علامة ترقيم",
        explanation="تُفصل النقطة عن الكلمة التالية بمسافة.",
        pattern=re.compile(
            r"(?<![0-9٠-٩۰-۹])\.(?=[\u0600-\u06FF])"
        ),
        replacement=". ",
        confidence=0.99,
        max_matches=4,
    ),
    ReviewRule(
        id="punctuation.missing_space_after",
        category="language",
        title="مسافة بعد علامة ترقيم",
        explanation="تُفصل علامة الترقيم عن الكلمة التالية بمسافة.",
        pattern=re.compile(
            rf"([،؛؟!]|:(?!{UNIT_AFTER_NUMBER}))(?=[\u0600-\u06FF])"
        ),
        replacement=lambda m: m.group(1) + " ",
        confidence=0.99,
        max_matches=4,
    ),
    ReviewRule(
        id="spacing.repeated",
        category="language",
        title="مسافات متكررة",
        explanation="تكفي مسافة واحدة بين الكلمات.",
        pattern=re.compile(r"(?<=\S)[ \t]{2,}(?=\S)"),
        replacement=" ",
        confidence=0.995,
        max_matches=4,
    ),
    ReviewRule(
        id="punctuation.repeated",
        category="language",
        title="علامة ترقيم مكررة",
        explanation="تكرار علامة الترقيم هنا غير لازم.",
        pattern=re.compile(r"([،؛:؟!])\1+"),
        replacement=lambda m: m.group(1),
        confidence=0.99,
        max_matches=3,
    ),
    _literal_rule(
        "orthography.binaan",
        "language",
        "بناءاً",
        "بناءً",
        "رسم إملائي",
        "الصواب «بناءً» دون ألف بعد الهمزة.",
    ),
    _literal_rule(
        "orthography.in_sha_allah",
        "language",
        "ان شاء الله",
        "إن شاء الله",
        "فصل كلمتين",
        "الصواب «إن شاء الله».",
        0.99,
    ),
    _literal_rule(
        "orthography.masouliya_ha",
        "language",
        "مسؤوليه",
        "مسؤولية",
        "تاء مربوطة",
        "الصواب في هذا الاسم «مسؤولية» بالتاء المربوطة.",
    ),
    _literal_rule(
        "orthography.hatha",
        "language",
        "هاذا",
        "هذا",
        "رسم إملائي",
        "الصواب «هذا».",
    ),
    _literal_rule(
        "orthography.lakin",
        "language",
        "لاكن",
        "لكن",
        "رسم إملائي",
        "الصواب «لكن».",
    ),
    _literal_rule(
        "orthography.allathi",
        "language",
        "اللذي",
        "الذي",
        "رسم إملائي",
        "الصواب «الذي».",
    ),
    _literal_rule(
        "orthography.allati",
        "language",
        "اللتي",
        "التي",
        "رسم إملائي",
        "الصواب «التي».",
    ),
    _literal_rule(
        "orthography.shay",
        "language",
        "شئ",
        "شيء",
        "رسم إملائي",
        "الصواب «شيء».",
        0.98,
    ),
    _literal_rule(
        "grammar.haythu_anna",
        "language",
        "حيث أن",
        "حيث إن",
        "كسر همزة «إن»",
        "تُكسر همزة «إن» بعد «حيث» في هذا الاستعمال.",
        0.97,
    ),
    _literal_rule(
        "orthography.liada",
        "language",
        "لذاك",
        "لذلك",
        "رسم إملائي",
        "الصواب في هذا السياق «لذلك».",
        0.95,
    ),
)


STYLE_RULES: tuple[ReviewRule, ...] = (
    ReviewRule(
        id="style.duplicate_word",
        category="style",
        title="تكرار كلمة",
        explanation="وردت الكلمة نفسها مرتين متتاليتين.",
        pattern=re.compile(r"\b([\u0600-\u06FF]{3,})[ \t]+\1\b"),
        replacement=lambda m: m.group(1),
        confidence=0.96,
        apply_to_headings=False,
        max_matches=3,
    ),
    ReviewRule(
        id="style.extra_preposition",
        category="style",
        title="حرف جر زائد",
        explanation="يمكن حذف «من» لتصبح العبارة أخف وأدق.",
        pattern=re.compile(r"تحسين\s+من\s+مستوى"),
        replacement="تحسين مستوى",
        confidence=0.98,
        apply_to_headings=False,
    ),
    ReviewRule(
        id="style.doing_work_review",
        category="style",
        title="تركيب مطوّل",
        explanation="يمكن اختصار التركيب من دون فقد المعنى.",
        pattern=re.compile(
            r"بالعمل\s+على\s+القيام\s+بمراجعة\s+الإجراءات"
        ),
        replacement="بمراجعة الإجراءات",
        confidence=0.96,
        apply_to_headings=False,
    ),
    ReviewRule(
        id="style.current_phase",
        category="style",
        title="حشو دلالي",
        explanation="كلمة «الحالية» زائدة بعد «هذه المرحلة».",
        pattern=re.compile(r"في\s+هذه\s+المرحلة\s+الحالية"),
        replacement="في هذه المرحلة",
        confidence=0.96,
        apply_to_headings=False,
    ),
    ReviewRule(
        id="style.current_time",
        category="style",
        title="عبارة مطوّلة",
        explanation="يمكن التعبير عنها باختصار أوضح.",
        pattern=re.compile(r"في\s+الوقت\s+الراهن"),
        replacement="حاليًا",
        confidence=0.93,
        apply_to_headings=False,
    ),
    ReviewRule(
        id="style.through_using",
        category="style",
        title="تركيب مطوّل",
        explanation="«باستخدام» أكثر مباشرة من «من خلال استخدام».",
        pattern=re.compile(r"من\s+خلال\s+استخدام"),
        replacement="باستخدام",
        confidence=0.95,
        apply_to_headings=False,
    ),
    ReviewRule(
        id="style.for_purpose_working",
        category="style",
        title="حشو أسلوبي",
        explanation="يمكن حذف «العمل على» من هذا التركيب.",
        pattern=re.compile(r"بهدف\s+العمل\s+على"),
        replacement="بهدف",
        confidence=0.93,
        apply_to_headings=False,
    ),
    ReviewRule(
        id="style.all_all",
        category="style",
        title="تكرار في المعنى",
        explanation="«كافة» و«جميع» تؤديان المعنى نفسه هنا.",
        pattern=re.compile(r"(?:كافة\s+جميع|جميع\s+كافة)"),
        replacement="جميع",
        confidence=0.98,
        apply_to_headings=False,
    ),
    ReviewRule(
        id="style.previously_before",
        category="style",
        title="تكرار في المعنى",
        explanation="يكفي أحد التعبيرين «مسبقًا» أو «من قبل».",
        pattern=re.compile(r"مسبق[ًاا]+\s+من\s+قبل"),
        replacement="مسبقًا",
        confidence=0.96,
        apply_to_headings=False,
    ),
    ReviewRule(
        id="style.general_duplicate",
        category="style",
        title="تكرار في المعنى",
        explanation="يكفي أحد التعبيرين الدالين على العموم.",
        pattern=re.compile(r"(?:بصورة\s+عامة\s+بشكل\s+عام|بشكل\s+عام\s+بصورة\s+عامة)"),
        replacement="بشكل عام",
        confidence=0.96,
        apply_to_headings=False,
    ),
    ReviewRule(
        id="style.regarding",
        category="style",
        title="صياغة أكثر مباشرة",
        explanation="يمكن استخدام «بشأن» لصياغة أكثر إيجازًا.",
        pattern=re.compile(r"فيما\s+يخص"),
        replacement="بشأن",
        confidence=0.9,
        apply_to_headings=False,
    ),
    ReviewRule(
        id="style.in_order_to",
        category="style",
        title="صياغة أكثر إيجازًا",
        explanation="يمكن اختصار «من أجل أن» إلى «لـ» بحسب السياق.",
        pattern=re.compile(r"من\s+أجل\s+أن\s+(?P<verb>[\u0600-\u06FF]{3,})"),
        replacement=lambda m: "ل" + m.group("verb"),
        confidence=0.9,
        apply_to_headings=False,
    ),
)


def _node_is_code_like(text: str) -> bool:
    if URL_RE.search(text) or CODEISH_RE.search(text):
        return True
    non_space = [char for char in text if not char.isspace()]
    if not non_space:
        return False
    ascii_symbols = sum(
        1
        for char in non_space
        if char in "{}[]<>/=\\|_"
    )
    return ascii_symbols / len(non_space) > 0.18


def _replacement(rule: ReviewRule, match: re.Match[str]) -> str:
    if callable(rule.replacement):
        return rule.replacement(match)
    return rule.replacement


def _apply_rule(
    node: DocumentNode,
    rule: ReviewRule,
) -> list[Suggestion]:
    if node.type == "heading" and not rule.apply_to_headings:
        return []

    suggestions: list[Suggestion] = []
    for index, match in enumerate(rule.pattern.finditer(node.text)):
        if rule.id == "spacing.repeated":
            if node.type == "table_cell":
                continue
            previous = node.text[match.start() - 1] if match.start() > 0 else ""
            following = node.text[match.end()] if match.end() < len(node.text) else ""
            if previous in "◆•▪◦●○■□–—-" or following in "◆•▪◦●○■□–—-":
                continue
            if node.text.count(":") >= 2:
                continue
        if index >= rule.max_matches:
            break

        original = match.group(0)
        replacement = _replacement(rule, match)
        if replacement == original:
            continue

        suggestions.append(
            Suggestion(
                id=_stable_suggestion_id(
                    node.id,
                    rule.id,
                    match.start(),
                    original,
                ),
                node_id=node.id,
                category=rule.category,
                title=rule.title,
                explanation=rule.explanation,
                original=original,
                replacement=replacement,
                confidence=rule.confidence,
            )
        )

    return suggestions


def review_arabic_node(node: DocumentNode) -> list[Suggestion]:
    text = node.text
    if not text.strip() or _node_is_code_like(text):
        return []

    suggestions: list[Suggestion] = []

    for rule in LANGUAGE_RULES:
        suggestions.extend(_apply_rule(node, rule))

    # Quoted material is protected by Meaning Lock and should not receive
    # discretionary style rewrites. High-confidence language corrections
    # above remain visible for the author to review.
    if not FULL_QUOTE_RE.match(text):
        for rule in STYLE_RULES:
            suggestions.extend(_apply_rule(node, rule))

    # Avoid duplicate edits for an identical source span/category.
    deduped: dict[tuple[str, str, str], Suggestion] = {}
    for suggestion in suggestions:
        key = (
            suggestion.category,
            suggestion.original,
            suggestion.replacement or "",
        )
        existing = deduped.get(key)
        if existing is None or suggestion.confidence > existing.confidence:
            deduped[key] = suggestion

    return sorted(
        deduped.values(),
        key=lambda item: (
            0 if item.category == "language" else 1,
            -item.confidence,
            item.id,
        ),
    )


def review_arabic_document(
    nodes: list[DocumentNode],
) -> list[Suggestion]:
    issues: list[Suggestion] = []
    for node in nodes:
        issues.extend(review_arabic_node(node))
    return issues
