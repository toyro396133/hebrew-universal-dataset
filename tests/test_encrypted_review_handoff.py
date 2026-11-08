"""Fixture-only encryption tests; never check in real external packet text."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from encrypted_review_handoff import encrypt, decrypt, check_packet
from review_calibration import prepare
from ingest_corpus import stage, source_by_id, source_rows, write_stage

PASS = "This is a LOCAL-ONLY strong test passphrase, not a production secret."

class EncryptedHandoffTests(unittest.TestCase):
    def prepare_fixture(self, root):
        config=source_by_id("hebrew_wikipedia_sentences")
        docs, stats=stage(config, source_rows(ROOT/"tests/fixtures/wiki-rows.jsonl"), 7, snapshot="offline-fixture")
        staging=Path(root)/"stage"
        write_stage(staging, docs, stats, config, "offline-fixture")
        review=Path(root)/"review"
        m=prepare(staging,review,5,17)
        self.assertEqual(5,m["selected"])
        return review

    def test_round_trip_blind_packet_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            r=self.prepare_fixture(temp)
            archive=Path(temp)/"sealed.hureview"
            result=encrypt(r,archive,PASS)
            self.assertEqual("ENCRYPTED_ONLY",result["status"])
            data=archive.read_bytes()
            packet=(r/"blind-review-packet.jsonl").read_bytes()
            self.assertNotIn(packet[:60],data)
            self.assertNotIn(b"surface_score",data)
            decrypted=Path(temp)/"decrypted"
            outcome=decrypt(archive,decrypted,PASS)
            self.assertEqual(5,outcome["item_count"])
            self.assertEqual(packet,(decrypted/"blind-review-packet.jsonl").read_bytes())
            self.assertEqual((r/"internal-manifest.json").read_bytes(),
                             (decrypted/"internal-manifest.json").read_bytes())

    def test_wrong_passphrase_fails_without_writing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            r=self.prepare_fixture(temp)
            archive=Path(temp)/"sealed.hureview"
            encrypt(r,archive,PASS)
            out=Path(temp)/"out"
            with self.assertRaisesRegex(ValueError,"passphrase|altered"):
                decrypt(archive,out,PASS + " incorrect")
            self.assertFalse(out.exists())

    def test_authenticated_integrity_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            r=self.prepare_fixture(temp)
            archive=Path(temp)/"sealed.hureview"
            encrypt(r,archive,PASS)
            payload=bytearray(archive.read_bytes())
            payload[-20] ^= 0x12
            archive.write_bytes(payload)
            out=Path(temp)/"out"
            with self.assertRaisesRegex(ValueError,"altered"):
                decrypt(archive,out,PASS)
            self.assertFalse(out.exists())

    def test_no_overwrite_on_decryption(self):
        with tempfile.TemporaryDirectory() as temp:
            r=self.prepare_fixture(temp)
            archive=Path(temp)/"sealed.hureview"
            encrypt(r,archive,PASS)
            with self.assertRaisesRegex(ValueError,"exists"):
                decrypt(archive,r,PASS)

    def test_rejects_short_secret(self):
        with tempfile.TemporaryDirectory() as temp:
            r=self.prepare_fixture(temp)
            with self.assertRaisesRegex(ValueError,"20"):
                encrypt(r,Path(temp)/"out.hureview","weak")

    def test_missing_packet_fails_before_creating_cipher(self):
        with tempfile.TemporaryDirectory() as temp:
            r=self.prepare_fixture(temp)
            (r/"blind-review-packet.jsonl").unlink()
            archive=Path(temp)/"sealed.hureview"
            with self.assertRaises(FileNotFoundError):
                encrypt(r,archive,PASS)
            self.assertFalse(archive.exists())

    def test_rejects_modified_packet(self):
        with tempfile.TemporaryDirectory() as temp:
            r=self.prepare_fixture(temp)
            path=r/"blind-review-packet.jsonl"
            lines=[json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
            lines[0]["text"]+=" נוסף"
            path.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in lines),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"hash"):
                encrypt(r,Path(temp)/"sealed.hureview",PASS)

if __name__ == "__main__":
    unittest.main()
