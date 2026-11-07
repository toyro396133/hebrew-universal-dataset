import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from validate import load, validate
from export import build_export

class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.docs, self.tasks = load()

    def test_data_valid(self):
        self.assertEqual([], validate(self.docs, self.tasks))

    def test_all_six_levels_present(self):
        self.assertEqual(set(range(1, 7)), {d['level'] for d in self.docs})

    def test_splits_present(self):
        self.assertEqual({'train','validation','test'}, {d['split'] for d in self.docs})

    def test_leakage_detected(self):
        records = [dict(d) for d in self.docs]
        records[-1]['split'] = 'train'
        self.assertTrue(any('appears in several splits' in e for e in validate(records, self.tasks)))

    def test_missing_document_reference_detected(self):
        ts = [dict(t) for t in self.tasks]
        ts[-1]['source_ids'] = ['does-not-exist']
        self.assertTrue(any('unknown source ID' in e for e in validate(self.docs, ts)))

    def test_default_messages_never_export_test_answers(self):
        rows = list(build_export(self.docs, self.tasks, 'messages', 'all'))
        self.assertTrue(rows)
        self.assertTrue(all(row['split'] == 'train' for row in rows))

    def test_character_byte_equivalence(self):
        chars = list(build_export(self.docs, self.tasks, 'chars', 'train'))
        binary = list(build_export(self.docs, self.tasks, 'bytes', 'train'))
        self.assertEqual(''.join(chars[0]['characters']), bytes(binary[0]['utf8_bytes']).decode('utf-8'))

    def test_conversation_chain_export(self):
        rows = list(build_export(self.docs, self.tasks, 'messages', 'train'))
        followup = [row for row in rows if row['id'] == 'task-l03-train-02']
        self.assertEqual(1, len(followup))
        self.assertEqual(['user','assistant','user','assistant'], [m['role'] for m in followup[0]['messages']])

    def test_invalid_history_detected(self):
        ts = [dict(t) for t in self.tasks]
        ts[0]['history'] = [{'role':'assistant', 'content':'unexpected'}]
        self.assertTrue(any('history' in e for e in validate(self.docs, ts)))

    def test_long_context_has_three_documents(self):
        long_docs = [d for d in self.docs if d['level'] == 6]
        for split in ('train','validation','test'):
            self.assertEqual(3, len([d for d in long_docs if d['split'] == split]))

if __name__ == '__main__':
    unittest.main()
