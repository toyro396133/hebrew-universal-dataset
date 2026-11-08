import json
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate import load, validate
from export import build_export

class OriginalExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        docs, tasks = load()
        cls.docs = [d for d in docs if d['id'].startswith('hud26-')]
        cls.tasks = [t for t in tasks if t['id'].startswith('hud26-')]

    def test_counts_and_levels(self):
        self.assertEqual(560, len(self.docs))
        self.assertEqual(560, len(self.tasks))
        for level in range(1, 15):
            self.assertEqual(40, sum(d['level']==level for d in self.docs))

    def test_world_and_family_isolation(self):
        groups, families = {}, {}
        for d in self.docs:
            groups.setdefault(d['group_id'], set()).add(d['split'])
            families.setdefault(d['categories'][1], set()).add(d['split'])
        self.assertEqual(40, len(groups))
        self.assertTrue(all(len(s)==1 for s in groups.values()))
        self.assertTrue(all(len(s)==1 for s in families.values()))

    def test_valid_references(self):
        self.assertEqual([], validate(self.docs, self.tasks))

    def test_default_messages_exclude_held_out_answers(self):
        rows = list(build_export(self.docs, self.tasks, 'messages', 'all'))
        self.assertEqual(336, len(rows))
        self.assertTrue(all(r['split']=='train' for r in rows))

    def test_grounded_answers(self):
        truth = json.loads((ROOT/'evaluation/original-expansion/world-states.json').read_text(encoding='utf-8'))
        for t in self.tasks:
            w = t['id'].split('-')[2]
            self.assertEqual(truth[w]['split'],t['split'])
            if t['id'].endswith('-l06'):
                self.assertEqual(truth[w]['latest']+'.',t['expected_answers'][0])
            if t['id'].endswith('-l07'):
                self.assertEqual(truth[w]['evidence']['later']+'.',t['expected_answers'][0])
            if t['id'].endswith('-l09'):
                self.assertEqual(truth[w]['rule']['exception']+'.',t['expected_answers'][0])
            if t['id'].endswith('-l11'):
                self.assertEqual(truth[w]['plan']['prerequisite']+'.',t['expected_answers'][0])
if __name__ == '__main__':
    unittest.main()
