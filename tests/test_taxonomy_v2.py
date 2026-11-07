import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate import load, validate, TOPIC_IDS, AXIS_TYPES
from generate_worlds import generate

class TaxonomyV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs, cls.tasks = load()

    def test_forteen_levels_covered(self):
        self.assertEqual(set(range(1, 15)), {d['level'] for d in self.docs})

    def test_sixteen_topics_covered(self):
        self.assertEqual(16, len(TOPIC_IDS))
        self.assertEqual(TOPIC_IDS, {topic for d in self.docs for topic in d.get('topics', [])})

    def test_twelve_axes(self):
        self.assertEqual(12, len(AXIS_TYPES))

    def test_new_examples_split_per_level(self):
        for level in range(7, 15):
            splits = {d['split'] for d in self.docs if d['level'] == level}
            self.assertEqual({'train', 'validation', 'test'}, splits)

    def test_corpus_and_tasks_are_valid(self):
        self.assertEqual([], validate(self.docs, self.tasks))

    def test_invalid_topic_detected(self):
        docs = [dict(d) for d in self.docs]
        i = next(i for i, d in enumerate(docs) if 'topics' in d)
        docs[i]['topics'] = ['not_a_domain']
        self.assertTrue(any('topic' in e for e in validate(docs, self.tasks)))

    def test_out_of_range_level_detected(self):
        docs = [dict(d) for d in self.docs]
        docs[0]['level'] = 15
        self.assertTrue(any('level' in e for e in validate(docs, self.tasks)))

    def test_world_generator_reproducible(self):
        self.assertEqual(generate(seed=43, count_per_split=2), generate(seed=43, count_per_split=2))

    def test_world_generator_cross_split_group_isolation(self):
        docs, tasks = generate(seed=17, count_per_split=3, entities=18, steps=8, documents=5)
        self.assertEqual([], validate(docs, tasks))
        groups = {}
        for d in docs:
            if d['group_id'] in groups:
                self.assertEqual(groups[d['group_id']], d['split'])
            groups[d['group_id']] = d['split']
        self.assertEqual(9, len(groups))
        self.assertEqual(45, len(docs))

    def test_world_generator_varied_parameters(self):
        for entities, steps, documents in ((3, 1, 1), (10, 20, 5), (14, 3, 30)):
            with self.subTest(entities=entities, steps=steps, documents=documents):
                docs, tasks = generate(seed=29, count_per_split=1, entities=entities, steps=steps, documents=documents)
                self.assertEqual([], validate(docs, tasks))
                self.assertEqual(3 * documents, len(docs))
                self.assertEqual(3, len(tasks))

    def test_world_generator_no_answer_in_source_as_full_phrase(self):
        docs, tasks = generate(seed=61)
        for task in tasks:
            source = '\n'.join(d['text'] for d in docs if d['id'] in task['source_ids'])
            self.assertNotIn(task['expected_answers'][0], source)

    def test_world_generator_rejects_invalid_parameters(self):
        for kwargs in ({'entities':2}, {'steps':0}, {'documents':0}, {'novelty':'invalid'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                generate(**kwargs)

if __name__ == '__main__':
    unittest.main()
