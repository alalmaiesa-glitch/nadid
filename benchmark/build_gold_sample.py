from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from app.pipeline.parser import parse_docx
from app.pipeline.reviewer import fast_review


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _word_count(text: str) -> int:
    return len([token for token in text.split() if token])


def _eligible(node) -> bool:
    return (
        node.type in {"paragraph", "table_cell", "heading"}
        and len(node.text.strip()) >= 8
        and _word_count(node.text) >= 2
    )


def _group_key(item: dict) -> str:
    return f"{item['doc_id']}|{item['node_type']}"


def _sample_grouped(items, wanted, rng):
    groups = defaultdict(list)
    for item in items:
        groups[_group_key(item)].append(item)

    group_population = {
        key: len(rows)
        for key, rows in groups.items()
    }
    group_sample = Counter()
    selected = []
    keys = sorted(groups)

    while len(selected) < min(wanted, len(items)):
        progressed = False
        for key in keys:
            pool = groups[key]
            if not pool:
                continue
            index = rng.randrange(len(pool))
            row = pool.pop(index)
            row = {
                **row,
                "_sample_group": key,
            }
            selected.append(row)
            group_sample[key] += 1
            progressed = True
            if len(selected) >= min(wanted, len(items)):
                break
        if not progressed:
            break

    return selected, group_population, dict(group_sample)


def build_sample(manifest, predicted_nodes, clean_nodes, seed):
    rng = random.Random(seed)
    predicted = []
    clean = []
    document_stats = []

    for doc_index, item in enumerate(manifest.get("documents", []), 1):
        path = Path(item["path"])
        doc_id = item.get("id") or f"D{doc_index:02d}"
        nodes = parse_docx(path.read_bytes())
        suggestions = fast_review(nodes)
        by_node = defaultdict(list)
        for suggestion in suggestions:
            by_node[suggestion.node_id].append(suggestion)

        eligible_nodes = [node for node in nodes if _eligible(node)]
        predicted_population = 0
        clean_population = 0

        for node in eligible_nodes:
            row = {
                "doc_id": doc_id,
                "node_id": node.id,
                "node_type": node.type,
                "sequence_no": node.sequence_no,
                "text": node.text,
                "text_sha256": _digest(node.text),
                "word_count": _word_count(node.text),
            }
            node_suggestions = by_node.get(node.id, [])
            if node_suggestions:
                predicted_population += 1
                row["predictions"] = [
                    {
                        "suggestion_id": suggestion.id,
                        "category": suggestion.category,
                        "title": suggestion.title,
                        "original": suggestion.original,
                        "replacement": suggestion.replacement,
                        "confidence": suggestion.confidence,
                        "label": None,
                        "review_note": "",
                    }
                    for suggestion in node_suggestions
                ]
                predicted.append(row)
            else:
                clean_population += 1
                row["predictions"] = []
                clean.append(row)

        document_stats.append(
            {
                "doc_id": doc_id,
                "eligible_nodes": len(eligible_nodes),
                "predicted_nodes": predicted_population,
                "clean_nodes": clean_population,
                "suggestions": len(suggestions),
            }
        )

    predicted_sample, predicted_group_population, predicted_group_sample = (
        _sample_grouped(
            predicted,
            min(predicted_nodes, len(predicted)),
            rng,
        )
    )
    clean_sample, clean_group_population, clean_group_sample = _sample_grouped(
        clean,
        min(clean_nodes, len(clean)),
        rng,
    )

    populations = {
        "predicted": len(predicted),
        "clean": len(clean),
    }
    sample_sizes = {
        "predicted": len(predicted_sample),
        "clean": len(clean_sample),
    }
    group_populations = {
        "predicted": predicted_group_population,
        "clean": clean_group_population,
    }
    group_samples = {
        "predicted": predicted_group_sample,
        "clean": clean_group_sample,
    }

    units = []
    for stratum, rows in (
        ("predicted", predicted_sample),
        ("clean", clean_sample),
    ):
        for row in rows:
            sample_group = row.pop("_sample_group")
            group_population = group_populations[stratum][sample_group]
            group_sample_size = group_samples[stratum][sample_group]
            inclusion_probability = (
                group_sample_size / group_population
                if group_population
                else 0.0
            )
            weight = (
                group_population / group_sample_size
                if group_sample_size
                else 0.0
            )

            units.append(
                {
                    "unit_id": _digest(
                        f"{row['doc_id']}|{row['node_id']}|{seed}"
                    )[:20],
                    **row,
                    "stratum": stratum,
                    "sample_group": sample_group,
                    "group_population_size": group_population,
                    "group_sample_size": group_sample_size,
                    "inclusion_probability": round(
                        inclusion_probability,
                        8,
                    ),
                    "weight": round(weight, 8),
                    "missed": [],
                    "review": {
                        "status": "pending",
                        "reviewer": "",
                        "reviewed_at": "",
                        "note": "",
                    },
                }
            )

    rng.shuffle(units)

    return {
        "schema_version": 1,
        "purpose": "human_gold_set",
        "label_policy": {
            "prediction_labels": ["correct", "wrong"],
            "missed_label": "missed",
        },
        "sampling": {
            "seed": seed,
            "predicted_nodes_requested": predicted_nodes,
            "clean_nodes_requested": clean_nodes,
            "predicted_population": populations["predicted"],
            "clean_population": populations["clean"],
            "predicted_sample": sample_sizes["predicted"],
            "clean_sample": sample_sizes["clean"],
            "sampled_predictions": sum(
                len(row["predictions"])
                for row in predicted_sample
            ),
            "weighting": (
                "inverse inclusion probability by doc_id and node_type "
                "within predicted/clean strata"
            ),
        },
        "documents": document_stats,
        "units": units,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--predicted-nodes", type=int, default=120)
    parser.add_argument("--clean-nodes", type=int, default=120)
    parser.add_argument("--seed", type=int, default=20260929)
    args = parser.parse_args()

    manifest = json.loads(
        Path(args.manifest).read_text(encoding="utf-8")
    )
    sample = build_sample(
        manifest,
        predicted_nodes=args.predicted_nodes,
        clean_nodes=args.clean_nodes,
        seed=args.seed,
    )
    Path(args.output).write_text(
        json.dumps(sample, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        "Gold candidate sample: "
        f"{sample['sampling']['predicted_sample']} predicted nodes + "
        f"{sample['sampling']['clean_sample']} clean nodes, "
        f"{sample['sampling']['sampled_predictions']} predictions"
    )


if __name__ == "__main__":
    main()
