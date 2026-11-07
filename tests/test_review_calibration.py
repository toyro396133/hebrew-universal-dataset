"""Offline tests only: ratings below are simulated fixtures, NOT human judgments."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ingest_corpus import source_by_id, source_rows, stage, write_stage
from review_calibration import (
    RUBRIC, prepare, evaluate, sample, pearson, quadratic_kappa, stratum,
    read_ratings, save_jsonl
)

class ReviewCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.source = source_by_id("hebrew_wikipedia_sentences")
        self.fixture = ROOT / "tests" / "fixtures" / "wiki-rows.jsonl"

    def staged(self, temporary):
        docs, stats = stage(self.source, source_rows(self.fixture), 100)
        out = Path(temporary) / "stage"
        write_stage(out, docs, stats, self.source, "offline-fixture")
        return out

    def fake_ratings(self, out, manifest, offset=0):
        packet = list(self.read_packet(out))
        a, b = [], []
        for i, item in enumerate(packet):
            ratings_a = {name: (i % 5) + 1 for name in RUBRIC}
            ratings_b = {name: min(5, v + (i+offset) % 2) for name, v in ratings_a.items()}
            a.append({"id":item["id"], "reviewer_id":"A", "ratings":ratings_a})
            b.append({"id":item["id"], "reviewer_id":"B", "ratings":ratings_b})
        pa, pb = out / "ratings-a.jsonl", out / "ratings-b.jsonl"
        save_jsonl(pa,a)
        save_jsonl(pb,b)
        return pa,pb

    def read_packet(self, out):
        return (json.loads(x) for x in (out / "blind-review-packet.jsonl").read_text(encoding="utf-8").splitlines() if x.strip())

    def test_prepare_blind_and_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = self.staged(tmp)
            a=Path(tmp)/"review-a"
            b=Path(tmp)/"review-b"
            ma=prepare(staged,a,5,17)
            mb=prepare(staged,b,5,17)
            self.assertEqual(ma,mb)
            self.assertEqual(5,ma["selected"])
            self.assertEqual("REVIEW_PENDING_NOT_CALIBRATED",ma["status"])
            packet=list(self.read_packet(a))
            self.assertEqual(5,len(packet))
            self.assertTrue(all(set(x)=={"id","text"} for x in packet))
            self.assertNotIn("surface_score", (a/"blind-review-packet.jsonl").read_text(encoding="utf-8"))
            self.assertNotIn("text", ma["items"][0])
            self.assertFalse(ma["publication_approved"])

    def test_sample_stratum_and_group_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=self.staged(tmp)
            docs=[json.loads(x) for x in (st/"documents.jsonl").read_text(encoding="utf-8").splitlines()]
            selected=sample(docs,6,seed=29)
            self.assertEqual(6,len(selected))
            self.assertIn("short", [bucket for bucket,_ in selected])
            self.assertIn("routine", [bucket for bucket,_ in selected])
            self.assertTrue(all(bucket==stratum(d) for bucket,d in selected))

    def test_real_review_not_claimed_by_synthetic_test_ratings(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=self.staged(tmp)
            out=Path(tmp)/"review"
            m=prepare(st,out,7,17)
            pa,pb=self.fake_ratings(out,m)
            result=evaluate(out/"internal-manifest.json",pa,pb)
            self.assertEqual(7,result["samples_reviewed"])
            self.assertEqual("ANNOTATED_NOT_CALIBRATED",result["status"])
            self.assertFalse(result["automatically_trained_calibration"])
            self.assertFalse(result["factuality_assessed"])
            self.assertFalse(result["publication_approved"])
            self.assertIn("identities not independently verified", result["source"])

    def test_reviewer_completeness_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=self.staged(tmp)
            out=Path(tmp)/"review"
            m=prepare(st,out,4,17)
            pa,pb=self.fake_ratings(out,m)
            b=[json.loads(x) for x in pb.read_text(encoding="utf-8").splitlines()][:-1]
            pb.unlink()
            save_jsonl(pb,b)
            with self.assertRaisesRegex(ValueError,"incomplete"):
                evaluate(out/"internal-manifest.json",pa,pb)

    def test_reviewer_id_must_be_different(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=self.staged(tmp)
            out=Path(tmp)/"review"
            m=prepare(st,out,4,17)
            pa,pb=self.fake_ratings(out,m)
            pb.unlink()
            rows=[json.loads(x) for x in pa.read_text(encoding="utf-8").splitlines()]
            save_jsonl(pb,rows)
            with self.assertRaisesRegex(ValueError,"reviewer identity"):
                evaluate(out/"internal-manifest.json",pa,pb)

    def test_duplicate_and_invalid_rating_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=self.staged(tmp)
            out=Path(tmp)/"review"
            m=prepare(st,out,3,17)
            pa,pb=self.fake_ratings(out,m)
            rows=[json.loads(x) for x in pa.read_text(encoding="utf-8").splitlines()]
            rows.append(rows[0])
            pa.unlink()
            save_jsonl(pa,rows)
            with self.assertRaisesRegex(ValueError,"duplicate"):
                evaluate(out/"internal-manifest.json",pa,pb)
            rows=rows[:-1]
            rows[0]["ratings"]["clarity"]=4.5
            pa.unlink()
            save_jsonl(pa,rows)
            with self.assertRaisesRegex(ValueError,"integer"):
                evaluate(out/"internal-manifest.json",pa,pb)

    def test_scores_without_variation_report_no_correlation(self):
        self.assertIsNone(pearson([99,99,99],[2,3,5]))
        self.assertIsNone(pearson([10,30],[1,3]))
        self.assertEqual(1.0,pearson([1,2,3],[1,2,3]))
        self.assertEqual(1.0,quadratic_kappa([1,2,3,4,5],[1,2,3,4,5]))
        self.assertIsNone(quadratic_kappa([],[]))

    def test_no_overwrite_or_missing_stage_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=self.staged(tmp)
            out=Path(tmp)/"review"
            prepare(st,out,4,17)
            with self.assertRaisesRegex(ValueError,"overwrite"):
                prepare(st,out,4,17)
            with self.assertRaises(ValueError):
                prepare(Path(tmp)/"missing",Path(tmp)/"another",4,17)

    def test_holdout_group_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=self.staged(tmp)
            out=Path(tmp)/"review"
            m=prepare(st,out,100,43)
            partition={}
            for row in m["items"]:
                group=row["source_group"]
                if group in partition:
                    self.assertEqual(partition[group], row["holdout"])
                partition[group]=row["holdout"]

if __name__ == "__main__":
    unittest.main()
