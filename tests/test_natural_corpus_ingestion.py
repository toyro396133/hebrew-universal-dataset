import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ingest_corpus import (source_by_id, source_rows, stage, quality_rejection,
                           canonical, write_stage)
from audit_staging import audit

class NaturalCorpusIngestionTests(unittest.TestCase):
    def setUp(self):
        self.source = source_by_id("hebrew_wikipedia_sentences")
        self.fixture = ROOT / "tests" / "fixtures" / "wiki-rows.jsonl"

    def test_fixture_generates_staged_train_only(self):
        docs, stats = stage(self.source, source_rows(self.fixture), 25)
        self.assertEqual(7, len(docs))
        self.assertEqual(7, stats["accepted"])
        self.assertTrue(all(d["split"] == "train" and d["level"] == 0 for d in docs))
        self.assertTrue(all(d["source"]["license"] == "CC-BY-SA-3.0" for d in docs))
        self.assertTrue(all(d["provenance"]["article_id"] for d in docs))

    def test_staged_output_passes_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "stage"
            docs, stats = stage(self.source, source_rows(self.fixture), 25)
            write_stage(out, docs, stats, self.source, "fixture")
            result = audit(out)
            self.assertEqual("PASS_STAGING_ONLY", result["status"])
            self.assertFalse(result["publishable"])
            self.assertEqual(7, result["distinct_groups"])

    def test_staging_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "stage"
            docs, stats = stage(self.source, source_rows(self.fixture), 25)
            write_stage(out, docs, stats, self.source, "fixture")
            with self.assertRaises(ValueError):
                write_stage(out, docs, stats, self.source, "fixture")

    def test_not_approved_for_publication_source_rejected(self):
        config = source_by_id("fineweb2_hebrew")
        with self.assertRaises(ValueError):
            stage(config, [], 3)

    def test_unchanged_source_id_stability(self):
        a, _ = stage(self.source, source_rows(self.fixture), 25)
        b, _ = stage(self.source, source_rows(self.fixture), 25)
        self.assertEqual(a, b)

    def test_filters(self):
        self.assertIsNone(quality_rejection("הדוגמה כוללת קישור https://example.org ואין לשמור מידע שאינו נדרש."))
        self.assertIsNone(quality_rejection("משפט קצר"))
        self.assertIsNone(quality_rejection("A very long example with English words and only שתי מילים עבריות."))
        self.assertEqual("טקסט לדוגמה", canonical("  טקסט \n לדוגמה  "))

    def test_validation_benchmark_guard(self):
        sample = None
        for p in (ROOT / "corpus" / "samples").rglob("*.jsonl"):
            for line in p.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row["split"] == "test" and len(row["text"]) >= 30 and len(row["text"].split()) >= 5:
                    sample = row["text"]
                    break
            if sample:
                break
        self.assertIsNotNone(sample)
        malicious = [{"sentence_id":"wiki_999_1", "sentence":sample,"article_id":999}]
        docs, stats = stage(self.source, enumerate(malicious), 1)
        self.assertEqual([], docs)
        self.assertGreater(stats.get("reject_benchmark_overlap",0),0)

    def test_license_tampering_fails_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "stage"
            docs, stats = stage(self.source, source_rows(self.fixture), 25)
            write_stage(out, docs, stats, self.source, "fixture")
            meta = json.loads((out / "report.json").read_text(encoding="utf-8"))
            meta["license"] = "UNLICENSED"
            (out / "report.json").write_text(json.dumps(meta), encoding="utf-8")
            with self.assertRaises(ValueError):
                audit(out)

if __name__ == "__main__":
    unittest.main()
