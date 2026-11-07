#!/usr/bin/env python3
"""Blind, stratified human review preparation and *exploratory* evaluation.

Requires manually completed, independent reviews. Automated fixtures never
constitute human evidence. Raw external source text remains on local disk.
"""
import argparse
import collections
import hashlib
import json
import math
import statistics
from pathlib import Path

RUBRIC = ("language_quality", "clarity", "context_independence", "training_usefulness")
STRATA = ("short", "code_mixed", "long", "no_terminal", "priority_other", "routine")
VERSION = "blind-review-1"

def jsonl(path):
    with Path(path).open(encoding="utf-8-sig") as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            yield value

def save_jsonl(path, rows):
    with Path(path).open("x", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

def stable_int(seed, text):
    return int(hashlib.sha256((str(seed) + ":" + text).encode()).hexdigest(), 16)

def stratum(doc):
    quality = doc.get("quality") or {}
    signals = quality.get("signals") or {}
    flags = set(quality.get("review_flags") or [])
    hints = set(quality.get("complexity_hints") or [])
    if "mixed_script_review" in flags or "technical_lexicon_or_symbols" in hints:
        return "code_mixed"
    if signals.get("words", 1000) < 5:
        return "short"
    if signals.get("words", 0) > 70:
        return "long"
    if "fragment_or_no_terminal_punctuation" in flags:
        return "no_terminal"
    if quality.get("triage") == "priority_review":
        return "priority_other"
    return "routine"

def sample(documents, count, seed=17):
    if type(count) is not int or count < 1:
        raise ValueError("count must be a positive integer")
    buckets = {k: [] for k in STRATA}
    seen = set()
    for doc in documents:
        did = doc.get("id")
        if not isinstance(did, str) or not did or did in seen:
            raise ValueError("Missing or duplicate document ID")
        seen.add(did)
        if not isinstance(doc.get("text"), str) or not doc["text"].strip():
            raise ValueError("Invalid document text")
        if doc.get("split") != "train" or doc.get("level") != 0:
            raise ValueError("Review must target staged, ungraded training documents")
        q = doc.get("quality")
        if not isinstance(q, dict) or q.get("human_verified") is not False or type(q.get("surface_score")) is not int:
            raise ValueError("Missing or misrepresented machine quality metadata")
        buckets[stratum(doc)].append(doc)
    for key in STRATA:
        buckets[key].sort(key=lambda d: stable_int(seed, d["id"]))
    result = []
    while len(result) < count and any(buckets.values()):
        for key in STRATA:
            if buckets[key] and len(result) < count:
                result.append((key, buckets[key].pop(0)))
    return result

def prepare(stage_dir, output_dir, count, seed):
    stage_dir, output_dir = Path(stage_dir), Path(output_dir)
    report = json.loads((stage_dir / "report.json").read_text(encoding="utf-8"))
    if report.get("status") != "STAGED_ONLY_NOT_APPROVED_FOR_PUBLICATION":
        raise ValueError("Stage is not explicitly staging-only")
    selected = sample(list(jsonl(stage_dir / "documents.jsonl")), count, seed)
    if not selected:
        raise ValueError("No review documents available")
    if output_dir.exists():
        raise ValueError("Refusing to overwrite review output")
    output_dir.mkdir(parents=True)
    packet = [{"id":d["id"], "text":d["text"]} for _, d in selected]
    manifest = {
        "version":VERSION, "status":"REVIEW_PENDING_NOT_CALIBRATED",
        "source_snapshot":report["snapshot_revision"], "sample_seed":seed,
        "requested":count, "selected":len(packet),
        "stratum_counts":dict(collections.Counter(k for k, _ in selected)),
        "rubric":list(RUBRIC), "score_is_uncalibrated":True, "publication_approved":False,
        "items":[{
            "id":d["id"], "stratum":key,
            "source_group":d["group_id"],
            "holdout": stable_int(seed, d["group_id"]) % 5 == 0,
            "surface_score":d["quality"]["surface_score"],
            "source_text_sha256":hashlib.sha256(d["text"].encode("utf-8")).hexdigest()
        } for key, d in selected]
    }
    save_jsonl(output_dir / "blind-review-packet.jsonl", packet)
    (output_dir / "internal-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "REVIEW-INSTRUCTIONS.md").write_text(
        "# Independent blind review\n\n"
        "Reviewers A and B independently read only blind-review-packet.jsonl and this rubric. "
        "Do not show them internal-manifest.json or source machine scores. "
        "Keep this folder local: third-party text is NOT approved for public upload.\n\n"
        "For each item, write JSONL: {\"id\":\"...\",\"reviewer_id\":\"A\","
        "\"ratings\":{\"language_quality\":4,\"clarity\":4,"
        "\"context_independence\":3,\"training_usefulness\":4}}.\n"
        "Ratings are integers 1–5 (1=very poor, 3=uncertain/partial, 5=very good). "
        "Rate language correctness, clarity, ability to interpret without external context, "
        "and potential usefulness to Hebrew language training separately. "
        "Do NOT infer factual correctness without external evidence. "
        "Do not coordinate or see each other's ratings. "
        "Reviewer B uses reviewer_id B. Every document must be evaluated.\n",
        encoding="utf-8"
    )
    return manifest

def read_ratings(path, expected, reviewer):
    rows = list(jsonl(path))
    mapping = {}
    for row in rows:
        did = row.get("id")
        if not isinstance(did, str) or did not in expected or did in mapping:
            raise ValueError(f"{reviewer}: unknown or duplicate sample ID")
        if row.get("reviewer_id") != reviewer:
            raise ValueError(f"{reviewer}: unexpected reviewer identity")
        scores = row.get("ratings")
        if not isinstance(scores, dict) or set(scores) != set(RUBRIC):
            raise ValueError(f"{reviewer}: missing or extra ratings")
        if not all(type(value) is int and 1 <= value <= 5 for value in scores.values()):
            raise ValueError(f"{reviewer}: each rating must be an integer from 1 to 5")
        mapping[did] = scores
    if set(mapping) != expected:
        raise ValueError(f"{reviewer}: incomplete reviews: {len(expected - set(mapping))} missing")
    return mapping

def pearson(xs, ys):
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    dx, dy = [x - mx for x in xs], [y - my for y in ys]
    denom = math.sqrt(sum(x*x for x in dx) * sum(y*y for y in dy))
    return round(sum(x*y for x, y in zip(dx, dy)) / denom, 4) if denom else None

def quadratic_kappa(xs, ys):
    """Cohen quadratic weighted kappa for ordinal categories 1..5."""
    if not xs or len(xs) != len(ys):
        return None
    n = len(xs)
    px = [xs.count(i)/n for i in range(1,6)]
    py = [ys.count(i)/n for i in range(1,6)]
    observed = sum(((x-y)/4)**2 for x,y in zip(xs,ys))/n
    expected = sum(((i-j)/4)**2*px[i-1]*py[j-1] for i in range(1,6) for j in range(1,6))
    return round(1-observed/expected,4) if expected else (1.0 if observed == 0 else None)

def evaluate(manifest_path, a_path, b_path):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or manifest.get("status") != "REVIEW_PENDING_NOT_CALIBRATED":
        raise ValueError("Invalid or already-calibrated review manifest")
    items = manifest["items"]
    ids = {x["id"] for x in items}
    if len(ids) != len(items) or not ids:
        raise ValueError("Review manifest contains duplicate or missing IDs")
    a = read_ratings(a_path, ids, "A")
    b = read_ratings(b_path, ids, "B")
    scores = [x["surface_score"] for x in items]
    metrics = {}
    for dim in RUBRIC:
        x = [a[i["id"]][dim] for i in items]
        y = [b[i["id"]][dim] for i in items]
        avg = [(u+v)/2 for u,v in zip(x,y)]
        metrics[dim] = {
            "agreement_exact":round(sum(u==v for u,v in zip(x,y))/len(x),4),
            "large_disagreements":sum(abs(u-v)>=2 for u,v in zip(x,y)),
            "quadratic_weighted_kappa":quadratic_kappa(x,y),
            "exploratory_pearson_to_surface_proxy":pearson(scores, avg)
        }
    return {
        "status":"ANNOTATED_NOT_CALIBRATED",
        "source":"external reviewer files; reviewer identities not independently verified",
        "samples_reviewed":len(items),
        "holdout_items":sum(bool(x["holdout"]) for x in items),
        "surface_score_min":min(scores), "surface_score_max":max(scores),
        "surface_score_unique":len(set(scores)),
        "metrics":metrics, "automatically_trained_calibration":False,
        "factuality_assessed":False, "publication_approved":False,
        "recommended_next_step":"independent adjudication of disagreements, held-out calibration and separate privacy/licensing checks"
    }

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    p1 = sub.add_parser("prepare")
    p1.add_argument("--stage-dir", type=Path, required=True)
    p1.add_argument("--output-dir", type=Path, required=True)
    p1.add_argument("--count", type=int, default=120)
    p1.add_argument("--seed", type=int, default=17)
    p2 = sub.add_parser("evaluate")
    p2.add_argument("--manifest", type=Path, required=True)
    p2.add_argument("--ratings-a", type=Path, required=True)
    p2.add_argument("--ratings-b", type=Path, required=True)
    p2.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    try:
        if a.command == "prepare":
            m = prepare(a.stage_dir, a.output_dir, a.count, a.seed)
            print(json.dumps({k:v for k,v in m.items() if k!="items"},ensure_ascii=False))
        else:
            report = evaluate(a.manifest, a.ratings_a, a.ratings_b)
            if a.output.exists():
                raise ValueError("Refusing to overwrite report")
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        p.error(str(exc))

if __name__ == "__main__":
    main()
