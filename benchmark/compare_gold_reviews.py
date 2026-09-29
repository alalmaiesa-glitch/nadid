from __future__ import annotations

import argparse
import json
from pathlib import Path


def _kappa(a_labels, b_labels):
    if not a_labels:
        return 0.0

    agree = sum(a == b for a, b in zip(a_labels, b_labels))
    observed = agree / len(a_labels)

    a_correct = sum(label == "correct" for label in a_labels) / len(a_labels)
    b_correct = sum(label == "correct" for label in b_labels) / len(b_labels)
    expected = (
        a_correct * b_correct
        + (1 - a_correct) * (1 - b_correct)
    )

    if expected >= 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def _prediction_map(payload):
    output = {}
    for unit in payload.get("units", []):
        for prediction in unit.get("predictions", []):
            label = prediction.get("label")
            if label in {"correct", "wrong"}:
                output[prediction["suggestion_id"]] = label
    return output


def _missed_map(payload):
    output = {}
    for unit in payload.get("units", []):
        pairs = {
            (
                item.get("category", ""),
                " ".join(item.get("original", "").split()),
                " ".join(item.get("replacement", "").split()),
            )
            for item in unit.get("missed", [])
            if item.get("label", "missed") == "missed"
        }
        output[unit["unit_id"]] = pairs
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-a", required=True)
    parser.add_argument("--review-b", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    a = json.loads(Path(args.review_a).read_text(encoding="utf-8"))
    b = json.loads(Path(args.review_b).read_text(encoding="utf-8"))

    a_predictions = _prediction_map(a)
    b_predictions = _prediction_map(b)
    common = sorted(set(a_predictions) & set(b_predictions))

    a_labels = [a_predictions[key] for key in common]
    b_labels = [b_predictions[key] for key in common]
    disagreements = [
        key
        for key in common
        if a_predictions[key] != b_predictions[key]
    ]

    a_missed = _missed_map(a)
    b_missed = _missed_map(b)
    common_units = sorted(set(a_missed) & set(b_missed))

    missed_exact_agreement = 0
    for unit_id in common_units:
        if a_missed[unit_id] == b_missed[unit_id]:
            missed_exact_agreement += 1

    report = {
        "prediction_labels": {
            "common": len(common),
            "agreements": len(common) - len(disagreements),
            "agreement_rate": round(
                (len(common) - len(disagreements)) / len(common)
                if common
                else 0.0,
                4,
            ),
            "cohen_kappa": round(_kappa(a_labels, b_labels), 4),
            "disagreement_suggestion_ids": disagreements,
        },
        "missed_annotations": {
            "common_units": len(common_units),
            "exact_agreement_units": missed_exact_agreement,
            "exact_agreement_rate": round(
                missed_exact_agreement / len(common_units)
                if common_units
                else 0.0,
                4,
            ),
        },
    }

    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
