from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def save(path: Path, payload: dict):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def ask_prediction(prediction: dict) -> str:
    while True:
        print()
        print(f"[{prediction['category']}] {prediction['title']}")
        print(f"  الأصل: {prediction['original']}")
        print(f"  البديل: {prediction.get('replacement') or ''}")
        answer = input("Correct / Wrong [c/w]: ").strip().lower()
        if answer in {"c", "correct"}:
            return "correct"
        if answer in {"w", "wrong"}:
            return "wrong"


def ask_missed() -> list[dict]:
    missed = []
    while True:
        answer = input(
            "هل يوجد خطأ لم يكتشفه نَضِيد؟ [y/n]: "
        ).strip().lower()
        if answer in {"n", "no", ""}:
            break
        if answer not in {"y", "yes"}:
            continue

        category = input(
            "الفئة [language/style]: "
        ).strip().lower()
        if category not in {"language", "style"}:
            category = "language"

        original = input("النص الأصلي: ").strip()
        replacement = input("التصحيح: ").strip()
        note = input("ملاحظة اختيارية: ").strip()

        if original and replacement:
            missed.append(
                {
                    "label": "missed",
                    "category": category,
                    "original": original,
                    "replacement": replacement,
                    "note": note,
                }
            )

    return missed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", required=True)
    parser.add_argument("--reviewer", required=True)
    args = parser.parse_args()

    path = Path(args.gold)
    payload = json.loads(path.read_text(encoding="utf-8"))
    units = payload.get("units", [])

    for index, unit in enumerate(units, 1):
        if unit.get("review", {}).get("status") == "adjudicated":
            continue

        print("\n" + "=" * 72)
        print(
            f"{index}/{len(units)} · {unit['doc_id']} · "
            f"{unit['node_type']} · {unit['stratum']}"
        )
        print("-" * 72)
        print(unit["text"])
        print("-" * 72)

        for prediction in unit.get("predictions", []):
            prediction["label"] = ask_prediction(prediction)
            prediction["review_note"] = input(
                "ملاحظة على الحكم (اختياري): "
            ).strip()

        unit["missed"] = ask_missed()
        unit["review"] = {
            "status": "adjudicated",
            "reviewer": args.reviewer,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "note": input("ملاحظة عامة على العقدة (اختياري): ").strip(),
        }
        save(path, payload)
        print("تم الحفظ.")

    print("\nاكتمل التحكيم لجميع الوحدات.")


if __name__ == "__main__":
    main()
