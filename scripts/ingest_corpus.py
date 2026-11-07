#!/usr/bin/env python3
"""Stage a reproducible, provenance-preserving Hebrew corpus sample.

Runs on an offline JSONL fixture or a bounded public HF Dataset Viewer slice.
Never publishes imported text or assigns fabricated difficulty ratings.
Python 3.10+, standard library only.
"""
import argparse
import collections
import hashlib
import json
import math
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "sources" / "registry.json"
HEBREW = re.compile(r"[\u0590-\u05ff]")
LATIN = re.compile(r"[A-Za-z]")
EMAIL = re.compile(r"(?<!\S)[^\s@]+@[^\s@]+\.[A-Za-z]{2,}")
URL = re.compile(r"https?://|www\.", flags=re.I)
PHONE = re.compile(r"(?<!\d)(?:\+972|0[2-9])[-\s]?(?:\d[-\s]?){7,9}(?!\d)")
TOKEN = re.compile(r"\S+")

def source_by_id(name, registry_path=REGISTRY):
    data = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    matches = [r for r in data["sources"] if r["id"] == name]
    if len(matches) != 1:
        raise ValueError("Unknown corpus source")
    return matches[0]

def canonical(text):
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()

def ngrams(text, n=5):
    words = canonical(text).split()
    return frozenset(tuple(words[i:i+n]) for i in range(max(0, len(words)-n+1)))

def fingerprint(text):
    return hashlib.sha256(canonical(text).encode("utf-8")).hexdigest()

def hebrew_ratio(text):
    he = len(HEBREW.findall(text))
    latin = len(LATIN.findall(text))
    return he / max(1, he + latin)

def quality_rejection(text):
    if not isinstance(text, str) or not text.strip():
        return "empty"
    if len(text) < 30 or len(text) > 1200:
        return "length"
    words = TOKEN.findall(text)
    if not 5 <= len(words) <= 70:
        return "words"
    if hebrew_ratio(text) < 0.75:
        return "language"
    if EMAIL.search(text) or PHONE.search(text) or URL.search(text):
        return "privacy_or_url"
    if re.search(r"(.)\1{8,}", text):
        return "noise"
    return None

def benchmark_signatures(root):
    """Protect exact and high-overlap benchmarks across splits."""
    path = Path(root) / "corpus"
    corpus = []
    if path.exists():
        for file in sorted(path.rglob("*.jsonl")):
            for line in file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("split") in ("validation", "test"):
                        corpus.append(row["text"])
    return {fingerprint(x) for x in corpus}, [ngrams(x) for x in corpus if len(ngrams(x)) >= 2]

def passes_benchmark_guard(text, fingerprints, benchmark_ngrams):
    if fingerprint(text) in fingerprints:
        return False
    pattern = ngrams(text)
    if len(pattern) >= 2:
        for ref in benchmark_ngrams:
            # Containment catches copied benchmark snippets in longer material.
            if len(pattern & ref) / min(len(pattern), len(ref)) >= 0.85:
                return False
    return True

def source_rows(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        for index, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                row = record.get("row", record)
                if not isinstance(row, dict):
                    raise ValueError("Row must be a JSON object")
                yield index - 1, row
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{path}:{index}: {exc}") from exc

def json_request(base, params=None, timeout=25):
    if params:
        base += "?" + urlencode(params)
    # All network requests are to fixed, known public hosts, never user-supplied URLs.
    req = Request(base, headers={"User-Agent": "HebrewUniversalDataset/0.1 (research pilot)"})
    with urlopen(req, timeout=timeout) as response:
        body = response.read(5_000_001)
        if len(body) > 5_000_000:
            raise ValueError("Response size limit exceeded")
        return json.loads(body)

def hf_snapshot(dataset):
    data = json_request("https://huggingface.co/api/datasets/" + dataset)
    sha = data.get("sha")
    if not isinstance(sha, str) or len(sha) < 20:
        raise ValueError("Dataset revision SHA unavailable; refusing unstable download")
    return sha

def hf_rows(config, scan_limit, seed, offset=0, strategy="spread"):
    """Bounded HF viewer API; <=100 rows per call, stable seeded page choices."""
    import random
    dataset = config["dataset"]
    max_rows = config["total_rows_reference"]
    if not isinstance(max_rows, int) or max_rows <= 0:
        raise ValueError("No verified total_rows_reference for this source")
    rng = random.Random(seed)
    pages = math.ceil(scan_limit / 100)
    seen_offsets = set()
    for i in range(pages):
        if strategy == "spread":
            page_start = rng.randrange((max_rows + 99)//100) * 100
        else:
            page_start = offset + i * 100
        if page_start in seen_offsets:
            continue
        seen_offsets.add(page_start)
        length = min(100, scan_limit - i*100, max_rows - page_start)
        if length <= 0:
            break
        data = json_request("https://datasets-server.huggingface.co/rows", {
            "dataset":dataset, "config":config["config"],
            "split":config["upstream_split"], "offset":page_start, "length":length
        })
        if not isinstance(data.get("rows"), list):
            raise ValueError("Unexpected HF viewer response")
        for record in data["rows"]:
            if not isinstance(record, dict) or not isinstance(record.get("row"), dict):
                continue
            yield record.get("row_idx", page_start), record["row"]

def stage(config, rows, limit, root=ROOT, snapshot="fixture"):
    """Pure streaming stage: fixed source, unique documents, no grading/inferred topics."""
    if config.get("status") != "approved_for_staging_only":
        raise ValueError("Source is not approved for the staging pipeline")
    if not 1 <= limit <= 10000:
        raise ValueError("limit must be in 1..10000")
    exact_eval, grams_eval = benchmark_signatures(root)
    accepted, stats = [], collections.Counter()
    exact_seen, seen_ids, grams_seen = set(), set(), []
    shingle_index = collections.defaultdict(set)
    for idx, row in rows:
        stats["scanned"] += 1
        text = row.get(config["text_field"])
        problem = quality_rejection(text)
        if problem:
            stats["reject_" + problem] += 1
            continue
        text_nfc = unicodedata.normalize("NFC", text).strip()
        fp = fingerprint(text_nfc)
        if fp in exact_seen:
            stats["reject_duplicate"] += 1
            continue
        if not passes_benchmark_guard(text_nfc, exact_eval, grams_eval):
            stats["reject_benchmark_overlap"] += 1
            continue
        # Near-duplicate guard within the batch, not a claim of global deduplication.
        grams = ngrams(text_nfc)
        candidate_ids = set()
        if len(grams) >= 2:
            for shingle in grams:
                candidate_ids.update(shingle_index[shingle])
        if any(len(grams & grams_seen[k]) / len(grams | grams_seen[k]) >= 0.90 for k in candidate_ids):
            stats["reject_near_duplicate"] += 1
            continue
        source_id = row.get(config.get("record_id_field", ""), idx)
        group = row.get(config.get("group_field", ""), source_id)
        if not isinstance(source_id, (int, str)) or not isinstance(group, (int, str)):
            stats["reject_bad_id"] += 1
            continue
        dedup_id = hashlib.sha256((config["id"] + ":" + str(source_id)).encode()).hexdigest()[:20]
        record_id = "he-natural-" + dedup_id
        if record_id in seen_ids:
            stats["reject_duplicate_id"] += 1
            continue
        seen_ids.add(record_id)
        exact_seen.add(fp)
        if grams:
            pos = len(grams_seen)
            grams_seen.append(grams)
            for shingle in grams:
                shingle_index[shingle].add(pos)
        provenance = {
            "dataset": config["dataset"], "snapshot_revision": snapshot,
            "source_row_id": str(source_id), "row_index": idx,
            "article_id": row.get("article_id"),
            "article_title": row.get("article_title"),
            "sentence_position": row.get("sentence_position"),
            "original_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "attribution": config["publisher"],
            "dataset_card": config["card_url"]
        }
        if str(group).isdecimal() and config.get("source_url_template"):
            provenance["article_url"] = config["source_url_template"].format(article_id=group)
        accepted.append({
            "id":record_id, "language":"he", "text":text_nfc,
            "level":0, "categories":["natural-text", "ungraded"],
            "split":"train", "group_id":config["id"] + "-article-" + str(group),
            "source":{"kind":"external","license":config["license"],
                      "reference":config["card_url"], "revision":snapshot},
            "provenance":provenance
        })
        stats["accepted"] += 1
        if len(accepted) >= limit:
            break
    stats["acceptance_rate"] = round(stats["accepted"] / max(1, stats["scanned"]), 4)
    return accepted, dict(stats)

def write_stage(path, documents, stats, config, snapshot):
    directory = Path(path)
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Output directory must be absent or empty (no accidental overwrite)")
    directory.mkdir(parents=True, exist_ok=True)
    metadata = {
        "source_id":config["id"], "license":config["license"],
        "attribution":config["publisher"], "dataset_card":config["card_url"],
        "snapshot_revision":snapshot, "publication_review_required":True,
        "status":"STAGED_ONLY_NOT_APPROVED_FOR_PUBLICATION",
        "data_split":"train_only", "statistics":stats
    }
    with (directory / "documents.jsonl").open("w", encoding="utf-8") as f:
        for doc in documents:
            f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
    (directory / "report.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",encoding="utf-8")
    (directory / "ATTRIBUTION.md").write_text(
        "# Source attribution and redistribution gate\n\n"
        f"Dataset: {config['dataset']}\n\nAuthors: {config['publisher']}\n\n"
        f"License: {config['license']} — {config['license_url']}\n\n"
        f"Source: {config['card_url']}\n\nRevision: {snapshot}\n\n"
        "Original per-row article links and hashes are preserved in documents.jsonl.\n"
        "No publication is authorized by this staging operation. Human review of source terms, privacy and attribution is required.\n",
        encoding="utf-8"
    )

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", default="hebrew_wikipedia_sentences")
    mx = p.add_mutually_exclusive_group(required=True)
    mx.add_argument("--fixture", type=Path, help="Offline JSONL with source columns")
    mx.add_argument("--fetch", action="store_true", help="Fetch bounded live HF Dataset Viewer rows")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--scan-limit", type=int, default=1000)
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--start-offset", type=int, default=0)
    p.add_argument("--strategy", choices=["spread","start"], default="spread")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--reference-root", type=Path, default=ROOT)
    args = p.parse_args(argv)
    try:
        cfg = source_by_id(args.source)
        if cfg.get("status") != "approved_for_staging_only":
            raise ValueError("This source is catalog-only; review required before any fetch")
        if not 1 <= args.scan_limit <= 50000:
            raise ValueError("scan-limit must be in 1..50000")
        if args.fetch:
            snapshot = hf_snapshot(cfg["dataset"])
            rows = hf_rows(cfg, args.scan_limit, args.seed, args.start_offset, args.strategy)
        else:
            snapshot = "offline-fixture"
            rows = source_rows(args.fixture)
        docs, stats = stage(cfg, rows, args.limit, args.reference_root, snapshot)
        if args.fetch and snapshot != hf_snapshot(cfg["dataset"]):
            raise ValueError("Dataset changed during import; rejecting unstable sample")
        write_stage(args.output_dir, docs, stats, cfg, snapshot)
    except (OSError, ValueError, KeyError) as exc:
        p.error(str(exc))
    print(json.dumps({"count":len(docs), "status":"STAGED_ONLY", "statistics":stats, "output":str(args.output_dir)}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
