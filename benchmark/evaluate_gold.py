from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def _ratio(a: float, b: float) -> float:
    return a / b if b else 0.0


def _f1(precision: float, recall: float) -> float:
    return (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )


def _wilson(successes: int, total: int, z: float = 1.96):
    if total <= 0:
        return [0.0, 0.0]
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            (p * (1 - p) + z * z / (4 * total)) / total
        )
        / denominator
    )
    return [
        round(max(0.0, center - margin), 4),
        round(min(1.0, center + margin), 4),
    ]


def evaluate(payload, require_complete=False):
    raw_tp = raw_fp = raw_fn = 0
    weighted_tp = weighted_fp = weighted_fn = 0.0
    pending_units = 0
    pending_predictions = 0
    by_category = defaultdict(
        lambda: {
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "weighted_tp": 0.0,
            "weighted_fp": 0.0,
            "weighted_fn": 0.0,
        }
    )

    for unit in payload.get("units", []):
        weight = float(unit.get("weight", 1.0))
        if unit.get("review", {}).get("status") != "adjudicated":
            pending_units += 1

        for prediction in unit.get("predictions", []):
            label = prediction.get("label")
            category = prediction.get("category", "unknown")
            if label == "correct":
                raw_tp += 1
                weighted_tp += weight
                by_category[category]["tp"] += 1
                by_category[category]["weighted_tp"] += weight
            elif label == "wrong":
                raw_fp += 1
                weighted_fp += weight
                by_category[category]["fp"] += 1
                by_category[category]["weighted_fp"] += weight
            else:
                pending_predictions += 1

        for missed in unit.get("missed", []):
            if missed.get("label", "missed") != "missed":
                continue
            category = missed.get("category", "unknown")
            raw_fn += 1
            weighted_fn += weight
            by_category[category]["fn"] += 1
            by_category[category]["weighted_fn"] += weight

    raw_precision = _ratio(raw_tp, raw_tp + raw_fp)
    raw_recall = _ratio(raw_tp, raw_tp + raw_fn)
    weighted_precision = _ratio(
        weighted_tp,
        weighted_tp + weighted_fp,
    )
    weighted_recall = _ratio(
        weighted_tp,
        weighted_tp + weighted_fn,
    )

    categories = {}
    for category, stats in sorted(by_category.items()):
        p = _ratio(
            stats["weighted_tp"],
            stats["weighted_tp"] + stats["weighted_fp"],
        )
        r = _ratio(
            stats["weighted_tp"],
            stats["weighted_tp"] + stats["weighted_fn"],
        )
        categories[category] = {
            **stats,
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(_f1(p, r), 4),
        }

    result = {
        "schema_version": 1,
        "status": (
            "complete"
            if pending_units == 0 and pending_predictions == 0
            else "incomplete"
        ),
        "raw": {
            "tp": raw_tp,
            "fp": raw_fp,
            "fn": raw_fn,
            "precision": round(raw_precision, 4),
            "recall": round(raw_recall, 4),
            "f1": round(_f1(raw_precision, raw_recall), 4),
            "precision_95ci": _wilson(
                raw_tp,
                raw_tp + raw_fp,
            ),
            "recall_95ci": _wilson(
                raw_tp,
                raw_tp + raw_fn,
            ),
        },
        "weighted_estimate": {
            "tp": round(weighted_tp, 3),
            "fp": round(weighted_fp, 3),
            "fn": round(weighted_fn, 3),
            "precision": round(weighted_precision, 4),
            "recall": round(weighted_recall, 4),
            "f1": round(
                _f1(weighted_precision, weighted_recall),
                4,
            ),
        },
        "categories": categories,
        "review_progress": {
            "total_units": len(payload.get("units", [])),
            "pending_units": pending_units,
            "pending_predictions": pending_predictions,
        },
    }

    if require_complete and result["status"] != "complete":
        raise SystemExit(
            "Gold set is not fully human-adjudicated: "
            f"{pending_units} units and "
            f"{pending_predictions} predictions remain pending."
        )

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    payload = json.loads(
        Path(args.gold).read_text(encoding="utf-8")
    )
    result = evaluate(
        payload,
        require_complete=args.require_complete,
    )
    Path(args.report).write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    weighted = result["weighted_estimate"]
    print(
        "Gold metrics: "
        f"precision={weighted['precision']:.1%}, "
        f"recall={weighted['recall']:.1%}, "
        f"F1={weighted['f1']:.1%}, "
        f"status={result['status']}"
    )


if __name__ == "__main__":
    main()
