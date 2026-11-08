import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate import load, validate
from export import build_export

class CuratedExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        all_docs, all_tasks = load()
        cls.docs = [x for x in all_docs if x['id'].startswith('cur26-')]
        cls.tasks = [x for x in all_tasks if x['id'].startswith('cur26-')]

    def test_curated_counts_and_level_coverage(self):
        self.assertEqual(140, len(self.docs))
        self.assertEqual(80, len(self.tasks))
        self.assertEqual({i:10 for i in range(1,15)}, {i:sum(x['level']==i for x in self.docs) for i in range(1,15)})

    def test_world_disjoint_splits(self):
        group_splits = {}
        for d in self.docs:
            group_splits.setdefault(d['group_id'],set()).add(d['split'])
        self.assertEqual(10,len(group_splits))
        self.assertTrue(all(len(v)==1 for v in group_splits.values()))
        self.assertEqual({'train':84,'validation':28,'test':28},{s:sum(d['split']==s for d in self.docs) for s in ('train','validation','test')})

    def test_curated_reference_integrity(self):
        self.assertEqual([], validate(self.docs,self.tasks))

    def test_uniqueness_and_unicode(self):
        self.assertEqual(140,len(set(d['text'] for d in self.docs)))
        self.assertTrue(all(d['text']==__import__('unicodedata').normalize('NFC',d['text']) for d in self.docs))

    def test_eval_targets_not_in_train_export(self):
        messages=list(build_export(self.docs,self.tasks,'messages','all'))
        self.assertEqual(48,len(messages))
        self.assertTrue(all(x['split']=='train' for x in messages))

if __name__=='__main__':
    unittest.main()
