"""Focused regression gates for the new explainable, non-binary quality policy."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from quality_scoring import hard_rejection, score_text
from ingest_corpus import source_by_id, stage, source_rows, write_stage
from audit_staging import audit

class QualityScoringTests(unittest.TestCase):
    def setUp(self):
        self.source = source_by_id("hebrew_wikipedia_sentences")
        self.fixture = ROOT / "tests" / "fixtures" / "wiki-rows.jsonl"

    def test_short_hebrew_sentence_preserved(self):
        text = "המים קפאו."
        self.assertIsNone(hard_rejection(text))
        result = score_text(text)
        self.assertIn("short_text", result["review_flags"])
        self.assertIsNone(result["semantic_quality"])
        self.assertIsNone(result["factuality"])
        self.assertFalse(result["human_verified"])
        self.assertGreaterEqual(result["surface_score"], 60)

    def test_mixed_technical_hebrew_is_not_rejected(self):
        text = "המהנדס בדק את קובץ JSON בעזרת Python והשווה את נתוני ה API."
        self.assertIsNone(hard_rejection(text))
        result = score_text(text)
        self.assertIn("technical_lexicon_or_symbols", result["complexity_hints"])
        self.assertIn("hebrew_letter_ratio", result["signals"])

    def test_mixed_script_review_instead_of_drop(self):
        text = "This API uses JSON and Python, והמפתח בודק אם זה עובד."
        self.assertIsNone(hard_rejection(text))
        result = score_text(text)
        self.assertEqual("priority_review", result["triage"])
        self.assertIn("mixed_script_review", result["review_flags"])

    def test_url_marked_for_review_not_dropped(self):
        text = "הקובץ נמצא בכתובת https://example.org והקישור נוסף לתיעוד כדי להסביר את השינוי."
        self.assertIsNone(hard_rejection(text))
        self.assertIn("url_review", score_text(text)["review_flags"])

    def test_contact_details_still_blocked(self):
        self.assertEqual("contact_data", hard_rejection("אנא כתבו ל support@example.org בנוגע לשינוי בתיעוד."))
        self.assertEqual("contact_data", hard_rejection("אפשר להתקשר למוקד בטלפון 050-1234567 כדי לקבל מידע נוסף."))

    def test_unreadable_content_blocked(self):
        self.assertEqual("empty", hard_rejection("  "))
        self.assertEqual("no_hebrew", hard_rejection("Only English words are included here."))
        self.assertEqual("control_character", hard_rejection("שלום\x00 עולם"))
        self.assertEqual("noise", hard_rejection("אאאאאאאאא שלום"))

    def test_scores_are_reproducible(self):
        x = "אם השרת אינו זמין, המערכת תציג הודעה ותשמור את הפעולה בתור."
        self.assertEqual(score_text(x), score_text(x))
        self.assertTrue(0 <= score_text(x)["surface_score"] <= 100)
        self.assertIn("possible_logical_connector", score_text(x)["complexity_hints"])

    def test_fixture_short_and_url_pass_without_auto_approval(self):
        docs, stats = stage(self.source, source_rows(self.fixture), 25)
        self.assertEqual(7, len(docs))
        self.assertTrue(all(d["quality"]["human_verified"] is False for d in docs))
        self.assertTrue(all(d["quality"]["triage"] in ("priority_review", "routine_review") for d in docs))
        self.assertIn("scorer_version", stats)
        short = [d for d in docs if d["text"] == "זו דוגמה."]
        self.assertEqual(1,len(short))
        self.assertIn("short_text", short[0]["quality"]["review_flags"])
        urls = [d for d in docs if "https://" in d["text"]]
        self.assertEqual(1,len(urls))
        self.assertEqual("priority_review", urls[0]["quality"]["triage"])

    def test_stage_report_preserves_flags_and_rubric(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, stats = stage(self.source, source_rows(self.fixture), 25)
            target = Path(tmp) / "stage"
            write_stage(target, docs, stats, self.source, "fixture")
            report = json.loads((target / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(7, report["statistics"]["accepted"])
            self.assertGreater(report["statistics"]["triage_priority_review"], 0)
            self.assertEqual("PASS_STAGING_ONLY", audit(target)["status"])
            self.assertFalse(audit(target)["publishable"])

    def test_tampered_score_detected_by_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, stats = stage(self.source, source_rows(self.fixture), 25)
            target = Path(tmp) / "stage"
            write_stage(target, docs, stats, self.source, "fixture")
            path = target / "documents.jsonl"
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            rows[0]["quality"]["surface_score"] = 0
            path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            result = audit(target)
            self.assertEqual("INVALID", result["status"])
            self.assertTrue(any("quality score" in e for e in result["errors"]))

    def test_near_duplicates_are_preserved_for_review(self):
        common = "במהלך הניסוי נבדקו חמישה מכשירים במעבדה המרכזית ונמצא שכולם פועלים באופן תקין בשעות הבוקר"
        rows = [
            (1, {"sentence": common + " ולאחר מכן נמסרו לתחנת האריזה בתחילת השבוע.", "sentence_id":"a","article_id":1001}),
            (2, {"sentence": common + " ולאחר מכן נמסרו לתחנת האריזה בסוף השבוע.", "sentence_id":"b","article_id":1002})
        ]
        docs, stats = stage(self.source, rows, 10)
        self.assertEqual(2,len(docs))
        self.assertGreaterEqual(stats.get("flag_near_duplicate",0), 1)
        self.assertEqual("priority_review", docs[-1]["quality"]["triage"])
        self.assertIn("near_duplicate", docs[-1]["quality"]["review_flags"])

    def test_identical_text_still_deduplicated(self):
        txt = "הספר הונח על המדף, והאחראי רשם את מיקומו החדש ביומן העבודה."
        rows = [
            (1, {"sentence":txt,"sentence_id":"first","article_id":1}),
            (2, {"sentence":txt,"sentence_id":"second","article_id":2})
        ]
        docs,stats = stage(self.source,rows,10)
        self.assertEqual(1,len(docs))
        self.assertEqual(1,stats["reject_duplicate"])

if __name__ == "__main__":
    unittest.main()
