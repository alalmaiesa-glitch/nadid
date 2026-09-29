from __future__ import annotations

import re
import unicodedata


DIACRITICS_RE = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]"
)
TOKEN_RE = re.compile(r"[\u0600-\u06FFA-Za-z0-9]{2,}")

STOPWORDS = {
    "في", "من", "على", "إلى", "الى", "عن", "مع", "هو", "هي",
    "هذا", "هذه", "ذلك", "تلك", "الذي", "التي", "تم", "يتم",
    "كان", "كانت", "يكون", "تكون", "ضمن", "وفق", "بموجب", "كما",
    "وقد", "ثم", "كل", "عند", "لدى", "لها", "له", "بها", "به",
}

TOKEN_CANONICAL = {
    "الطاقة": "قدرة",
    "طاقة": "قدرة",
    "القدرة": "قدرة",
    "قدرة": "قدرة",
    "الانتاجية": "إنتاج",
    "الإنتاجية": "إنتاج",
    "انتاجية": "إنتاج",
    "إنتاجية": "إنتاج",
    "التشغيلية": "تشغيل",
    "تشغيلية": "تشغيل",
    "السنوية": "سنوي",
    "سنوية": "سنوي",
    "سنويا": "سنوي",
    "سنويًا": "سنوي",
    "سنوي": "سنوي",
    "تأخر": "تأخير",
    "التأخر": "تأخير",
    "تعثر": "تأخير",
    "التعثر": "تأخير",
    "تأخير": "تأخير",
    "التسليم": "موعد",
    "تسليم": "موعد",
    "الموعد": "موعد",
    "موعد": "موعد",
    "الجدول": "جدول",
    "الزمني": "زمني",
    "زمنية": "زمني",
    "المدة": "مدة",
    "مدة": "مدة",
    "اكمال": "إكمال",
    "إكمال": "إكمال",
    "التنفيذ": "تنفيذ",
    "تنفيذ": "تنفيذ",
    "لتنفيذ": "تنفيذ",
    "تنفذ": "تنفيذ",
    "ينفذ": "تنفيذ",
    "التكلفة": "تكلفة",
    "تكلفة": "تكلفة",
    "التكاليف": "تكلفة",
    "تكاليف": "تكلفة",
    "المبلغ": "مبلغ",
    "مبلغ": "مبلغ",
}

CONCEPT_PATTERNS = (
    (
        "production_capacity",
        re.compile(
            r"(?:الطاقة|طاقة|القدرة|قدرة).{0,35}"
            r"(?:الإنتاج|الانتاج|الإنتاجية|الانتاجية|التشغيل)"
            r"|(?:الإنتاج|الانتاج|الإنتاجية|الانتاجية|التشغيل).{0,35}"
            r"(?:الطاقة|طاقة|القدرة|قدرة)"
        ),
    ),
    (
        "execution_duration",
        re.compile(
            r"(?:مدة\s+التنفيذ|الجدول\s+الزمني|"
            r"إكمال\s+المشروع\s+خلال|اكمال\s+المشروع\s+خلال|"
            r"تنفيذ\s+المشروع\s+خلال)"
        ),
    ),
    (
        "schedule_delay",
        re.compile(
            r"(?:تأخر|تعثر|تأخير).{0,30}"
            r"(?:التسليم|الجدول\s+الزمني|الموعد)"
            r"|(?:التسليم|الجدول\s+الزمني|الموعد).{0,30}"
            r"(?:تأخر|تعثر|تأخير)"
        ),
    ),
)


def normalize_arabic(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    value = DIACRITICS_RE.sub("", value)
    value = value.replace("ـ", "")
    value = value.translate(
        str.maketrans(
            {
                "أ": "ا",
                "إ": "ا",
                "آ": "ا",
                "ٱ": "ا",
                "ى": "ي",
                "ؤ": "و",
                "ئ": "ي",
            }
        )
    )
    return " ".join(value.casefold().split())


def semantic_concepts(text: str) -> set[str]:
    normalized = normalize_arabic(text)
    concepts: set[str] = set()
    for name, pattern in CONCEPT_PATTERNS:
        if pattern.search(normalized):
            concepts.add(name)
    return concepts


def semantic_tokens(text: str) -> set[str]:
    normalized = normalize_arabic(text)
    tokens: set[str] = set()

    for token in TOKEN_RE.findall(normalized):
        if token in STOPWORDS:
            continue
        canonical = TOKEN_CANONICAL.get(token, token)
        if len(canonical) >= 2:
            tokens.add(canonical)

    tokens.update(f"concept:{name}" for name in semantic_concepts(text))
    return tokens


def semantic_similarity(left: str, right: str) -> float:
    left_tokens = semantic_tokens(left)
    right_tokens = semantic_tokens(right)

    if not left_tokens or not right_tokens:
        return 0.0

    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    jaccard = intersection / max(1, union)

    left_concepts = semantic_concepts(left)
    right_concepts = semantic_concepts(right)
    concept_bonus = 0.35 if left_concepts & right_concepts else 0.0

    left_norm = normalize_arabic(left)
    right_norm = normalize_arabic(right)
    phrase_bonus = (
        0.2
        if left_norm
        and right_norm
        and (left_norm in right_norm or right_norm in left_norm)
        else 0.0
    )

    return min(1.0, jaccard + concept_bonus + phrase_bonus)


def semantic_claim_key(text: str, fact_type: str) -> str:
    concepts = semantic_concepts(text)

    if "production_capacity" in concepts:
        return f"production_capacity|{fact_type}"

    if "execution_duration" in concepts:
        return f"execution_duration|{fact_type}"

    tokens = sorted(semantic_tokens(text))
    if not tokens:
        return fact_type

    # Stable, conservative signature. Keep enough lexical material to avoid
    # collapsing unrelated claims that merely share one generic word.
    return f"{' '.join(tokens[-8:])}|{fact_type}"
