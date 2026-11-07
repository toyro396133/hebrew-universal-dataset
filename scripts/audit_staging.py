#!/usr/bin/env python3
"""Audit a staged external corpus without moving it into the public dataset."""
import argparse
import collections
import json
import re
from pathlib import Path
from ingest_corpus import (ROOT, canonical, fingerprint, ngrams, quality_rejection,
                           benchmark_signatures, passes_benchmark_guard, source_by_id)

def audit(path, reference_root=ROOT):
    path = Path(path)
    metadata = json.loads((path / "report.json").read_text(encoding="utf-8"))
    src = source_by_id(metadata["source_id"])
    if metadata.get("status") != "STAGED_ONLY_NOT_APPROVED_FOR_PUBLICATION":
        raise ValueError("Cannot audit stage with missing publication gate")
    if metadata.get("license") != src["license"]:
        raise ValueError("License mismatch")
    if metadata.get("source_id") != src["id"] or metadata.get("dataset_card") != src["card_url"]:
        raise ValueError("Source metadata mismatch")
    if not (path / "ATTRIBUTION.md").exists():
        raise ValueError("Attribution file missing")
    seen_ids, seen_fp = set(), set()
    groups, errors = {}, []
    exact, benchmark_grams = benchmark_signatures(reference_root)
    count = 0
    for line_no, line in enumerate((path / "documents.jsonl").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        d = json.loads(line)
        count += 1
        did, text = d.get("id"), d.get("text")
        if not isinstance(did, str) or did in seen_ids:
            errors.append(f"{line_no}: invalid or repeated ID")
        seen_ids.add(did)
        if d.get("level") != 0 or d.get("split") != "train":
            errors.append(f"{line_no}: invalid natural-text grading or split")
        if d.get("source", {}).get("license") != src["license"]:
            errors.append(f"{line_no}: source license mismatch")
        if d.get("source", {}).get("revision") != metadata["snapshot_revision"]:
            errors.append(f"{line_no}: mixed upstream revisions")
        p = d.get("provenance", {})
        if not isinstance(p, dict) or p.get("dataset") != src["dataset"] or not p.get("attribution"):
            errors.append(f"{line_no}: missing provenance")
        if not isinstance(p.get("original_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", p["original_sha256"]):
            errors.append(f"{line_no}: malformed original hash")
        if quality_rejection(text):
            errors.append(f"{line_no}: quality or privacy filter violation")
            continue
        signature = fingerprint(text)
        if signature in seen_fp:
            errors.append(f"{line_no}: exact duplicate")
        seen_fp.add(signature)
        if not passes_benchmark_guard(text, exact, benchmark_grams):
            errors.append(f"{line_no}: benchmark overlap")
        group = d.get("group_id")
        if not isinstance(group, str) or not group.startswith(src["id"] + "-article-"):
            errors.append(f"{line_no}: invalid source group")
        groups[group] = groups.get(group, 0) + 1
    if metadata.get("statistics",{}).get("accepted") != count:
        errors.append("Staging report count mismatch")
    if count == 0:
        errors.append("Empty staged corpus")
    result = {"status":"PASS_STAGING_ONLY" if not errors else "INVALID",
              "documents":count, "distinct_groups":len(groups),
              "license":src["license"], "source":src["id"],
              "errors":errors, "publishable":False}
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage_dir", type=Path)
    p.add_argument("--reference-root", type=Path, default=ROOT)
    args = p.parse_args()
    try:
        result = audit(args.stage_dir, args.reference_root)
    except (ValueError, KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
        p.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
