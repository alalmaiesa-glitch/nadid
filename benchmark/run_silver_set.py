from __future__ import annotations

import argparse, hashlib, json, re
from collections import Counter, defaultdict
from pathlib import Path

from app.pipeline.chunker import build_chunks
from app.pipeline.memory import build_document_memory
from app.pipeline.parser import parse_docx
from app.pipeline.patch_validator import validate_patch
from app.pipeline.protection import extract_protected_spans
from app.pipeline.reviewer import fast_review
from app.pipeline.semantic_review import semantic_review

PROBES = (
    ("punctuation.space_before", re.compile(r"\s+[،؛؟!,.]")),
    ("punctuation.missing_space_after", re.compile(r"[،؛؟!](?=[\u0600-\u06FF])")),
    ("punctuation.missing_space_after_colon", re.compile(r":(?=[\u0600-\u06FF])")),
    ("punctuation.missing_space_after_period", re.compile(r"(?<![0-9٠-٩۰-۹])\.(?=[\u0600-\u06FF])")),
    ("punctuation.repeated", re.compile(r"([،؛:؟!])\1+")),
)

def sha(text): return hashlib.sha256(text.encode("utf-8")).hexdigest()
def norm(text): return " ".join(text.split())

def covered(suggestion, evidence):
    a, b = norm(suggestion.original), norm(evidence)
    return bool(a and b) and (a == b or a in b or b in a)

def priority(kind, category, blocked=False):
    if blocked: return 100
    if kind == "wrong": return 95 if category == "language" else 85
    if kind == "missed": return 90 if category == "language" else 75
    if kind == "uncertain": return 88 if category == "consistency" else 78
    return 0

def probe_misses(nodes, suggestions_by_node):
    output = []
    for node in nodes:
        suggestions = suggestions_by_node.get(node.id, [])
        for probe_id, pattern in PROBES:
            # Consume one engine suggestion per probe hit so repeated identical
            # errors remain count-aware and future rule caps are detectable.
            remaining = list(suggestions)
            for match in pattern.finditer(node.text):
                if probe_id == "punctuation.missing_space_after_period":
                    start, end = match.span()
                    if start >= 2 and end + 1 < len(node.text) and node.text[start-2] == "(" and node.text[end+1] == ")":
                        continue
                covered_index = next((
                    index
                    for index, suggestion in enumerate(remaining)
                    if covered(suggestion, match.group(0))
                ), None)
                if covered_index is not None:
                    remaining.pop(covered_index)
                    continue
                output.append({
                    "kind": "missed", "category": "language",
                    "probe_id": probe_id, "node_id": node.id,
                    "node_type": node.type, "sequence_no": node.sequence_no,
                    "text_sha256": sha(node.text),
                    "evidence_sha256": sha(match.group(0)),
                    "priority": 90,
                    "reason": "independent_probe_not_covered_by_engine",
                })
    return output

def classify(node, suggestion, protected):
    replacement = suggestion.replacement or ""
    check = validate_patch(node.text, suggestion.original, replacement, protected)
    blocked = check.status == "BLOCK"
    if blocked:
        kind, reason = "uncertain", check.reason or "meaning_lock_block"
    elif suggestion.category == "style" or suggestion.confidence < 0.99:
        kind, reason = "uncertain", "contextual_or_below_threshold"
    elif suggestion.original not in node.text:
        kind, reason = "wrong", "source_fragment_not_present"
    elif replacement == suggestion.original:
        kind, reason = "wrong", "no_op_replacement"
    else:
        kind, reason = "correct", "high_confidence_language_and_meaning_lock_pass"
    return {
        "kind": kind, "category": suggestion.category,
        "suggestion_id": suggestion.id, "node_id": node.id,
        "node_type": node.type, "sequence_no": node.sequence_no,
        "text_sha256": sha(node.text), "confidence": suggestion.confidence,
        "priority": priority(kind, suggestion.category, blocked),
        "reason": reason, "meaning_lock": check.status,
    }

def analyze(path, doc_id):
    nodes = parse_docx(path.read_bytes())
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    suggestions = fast_review(nodes)
    memory = build_document_memory(nodes, chunks, protected)
    semantic = semantic_review(nodes, memory)

    node_by_id = {n.id: n for n in nodes}
    pmap, smap = defaultdict(list), defaultdict(list)
    for item in protected: pmap[item.node_id].append(item)
    for item in suggestions: smap[item.node_id].append(item)

    findings = [classify(node_by_id[s.node_id], s, pmap.get(s.node_id, [])) for s in suggestions]
    findings += probe_misses(nodes, smap)
    findings += [{
        "kind": "uncertain", "category": "consistency",
        "semantic_issue_id": issue.id, "issue_type": issue.issue_type,
        "node_id": issue.node_id, "confidence": issue.confidence,
        "priority": 88,
        "reason": "semantic_issue_requires_independent_adjudication",
    } for issue in semantic]

    counts = Counter(x["kind"] for x in findings)
    categories = Counter(x["category"] for x in findings)
    high = [x for x in findings if x["kind"] != "correct" and x["priority"] >= 80]
    return {
        "id": doc_id, "nodes": len(nodes), "suggestions": len(suggestions),
        "protected": len(protected), "semantic_issues": len(semantic),
        "silver_counts": dict(sorted(counts.items())),
        "category_counts": dict(sorted(categories.items())),
        "findings": findings, "high_priority": high,
    }

def load_manifest(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    for i, item in enumerate(payload.get("documents", []), 1):
        raw = Path(item["path"])
        yield item.get("id") or f"D{i:02d}", raw if raw.is_absolute() else path.parent / raw

def build_report(manifest):
    documents, errors = [], []
    for doc_id, path in load_manifest(manifest):
        try: documents.append(analyze(path, doc_id))
        except Exception as exc:
            errors.append({"doc_id": doc_id, "error": type(exc).__name__, "detail": str(exc)})
    totals, cats, high = Counter(), Counter(), []
    for doc in documents:
        totals.update(doc["silver_counts"]); cats.update(doc["category_counts"])
        high += [{"doc_id": doc["id"], **x} for x in doc["high_priority"]]
    correct, wrong = totals["correct"], totals["wrong"]
    missed, uncertain = totals["missed"], totals["uncertain"]
    precision = correct / (correct + wrong) if correct + wrong else 0
    recall = correct / (correct + missed) if correct + missed else 0
    return {
        "schema_version": 1,
        "purpose": "silver_set_automated_quality_triage",
        "warning": "Automated Silver metrics are diagnostic proxies, not Human Gold accuracy.",
        "documents": documents, "errors": errors,
        "summary": {
            "documents": len(documents), "errors": len(errors),
            "engine_suggestions": sum(d["suggestions"] for d in documents),
            "correct": correct, "wrong": wrong, "missed": missed,
            "uncertain": uncertain, "high_priority": len(high),
            "silver_proxy_precision": round(precision, 4),
            "silver_proxy_recall": round(recall, 4),
            "category_findings": dict(sorted(cats.items())),
        },
        "high_priority": sorted(high, key=lambda x: (-x["priority"], x["doc_id"], x.get("sequence_no", 0))),
    }

def public_report(report):
    return {
        "schema_version": 1, "purpose": report["purpose"], "warning": report["warning"],
        "summary": report["summary"],
        "documents": [{
            "id": d["id"], "nodes": d["nodes"], "suggestions": d["suggestions"],
            "protected": d["protected"], "semantic_issues": d["semantic_issues"],
            "silver_counts": d["silver_counts"], "category_counts": d["category_counts"],
            "high_priority": len(d["high_priority"]),
        } for d in report["documents"]],
        "errors": report["errors"],
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--private-report", required=True)
    parser.add_argument("--public-report", required=True)
    args = parser.parse_args()
    report = build_report(Path(args.manifest))
    Path(args.private_report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.public_report).write_text(json.dumps(public_report(report), ensure_ascii=False, indent=2), encoding="utf-8")
    s = report["summary"]
    print(f"Silver Set: {s['documents']} docs, correct={s['correct']}, wrong={s['wrong']}, missed={s['missed']}, uncertain={s['uncertain']}, high_priority={s['high_priority']}")
    if report["errors"]: raise SystemExit(1)

if __name__ == "__main__":
    main()
