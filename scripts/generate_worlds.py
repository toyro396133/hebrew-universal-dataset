#!/usr/bin/env python3
"""Deterministic synthetic long-context worlds for stress tests, NOT general pretraining data."""
import argparse
import json
import random
from pathlib import Path

SPLITS = ('train', 'validation', 'test')
NOVELTIES = ('entities', 'combinations', 'world', 'rules')

def generate(seed=7, count_per_split=2, entities=12, steps=4, documents=3, novelty='world'):
    """Return (docs, QA tasks) partitioned by disjoint world identifiers."""
    if count_per_split < 1 or entities < 3 or not 1 <= steps <= 100 or not 1 <= documents <= 100:
        raise ValueError('Expected count>=1, entities>=3, 1<=steps<=100, 1<=documents<=100')
    if novelty not in NOVELTIES:
        raise ValueError('Unrecognized novelty setting')
    rng = random.Random(seed)
    all_docs, all_tasks = [], []
    for split in SPLITS:
        for index in range(count_per_split):
            uid = f'generated-{split}-{seed}-{index:05d}'
            mark = rng.choice(('כוכב', 'ברק', 'ענן', 'גל', 'מעגל', 'משולש'))
            box = f'הקופסה המסומנת {mark} {index + 1}'
            item = f'האסימון של עולם {uid}'
            places = [f'תחנה {uid}-{i}' for i in range(entities - 2)]
            order = list(range(len(places)))
            rng.shuffle(order)
            sentences = [
                f'בעולם {uid} {item} נמצא בתוך {box}.',
                f'כל עוד לא נאמר אחרת, האסימון נשאר בתוך הקופסה גם כשמעבירים אותה.',
            ]
            current = None
            for step in range(steps):
                # The same container moves; tracking the contained item requires joining events.
                current = places[order[step % len(order)]]
                sentences.append(f'באירוע {step + 1} הועברה {box} אל {current}.')
            for i in range(entities - 2):
                sentences.append(f'בעולם {uid} קיים גם פריט רקע {i + 1}, ששמו פריט-{uid}-{i + 1}.')
            # Ensure all requested documents contain original, nonempty material.
            while len(sentences) < documents:
                sentences.append(f'ברשומת רקע {len(sentences) + 1} של עולם {uid} לא דווח שינוי במיקום {box}.')
            chunks = []
            for part in range(documents):
                left = len(sentences) * part // documents
                right = len(sentences) * (part + 1) // documents
                chunks.append(sentences[left:right])
            group_id = f'world-{uid}'
            ids = []
            for j, chunk in enumerate(chunks, 1):
                did = f'{uid}-doc-{j:03d}'
                ids.append(did)
                all_docs.append({
                    'id': did,
                    'language': 'he',
                    'text': ' '.join(chunk),
                    'level': 6,
                    'categories': ['long-context', 'entity-tracking', 'synthetic-stress'],
                    'topics': ['synthetic_worlds'],
                    'axis_tags': {
                        'linguistic_structure': ['document'],
                        'relation_types': ['containment', 'location', 'temporal'],
                        'temporal_memory': ['sequence'],
                        'novelty': [{'entities':'novel_entities','combinations':'novel_combinations','world':'novel_world','rules':'new_rule'}[novelty]],
                        'training_objectives': ['question_answering']
                    },
                    'metrics': {'entities': entities, 'events': steps, 'reasoning_steps': steps, 'documents': documents},
                    'split': split,
                    'group_id': group_id,
                    'source': {'kind':'synthetic', 'license':'CC0-1.0', 'reference':f'generate_worlds.py-seed-{seed}'}
                })
            all_tasks.append({
                'id': f'task-{uid}',
                'source_ids': ids,
                'split': split,
                'kind': 'entity_tracking',
                'question': f'לפי כל המסמכים, היכן נמצא {item} בסוף רצף האירועים?',
                'expected_answers': [f'בתוך {box}, הנמצאת ב{current}.'],
                'difficulty': {'reasoning_steps': steps, 'documents': documents, 'entities': entities}
            })
    return all_docs, all_tasks

def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed', type=int, default=7)
    p.add_argument('--count-per-split', type=int, default=2)
    p.add_argument('--entities', type=int, default=12)
    p.add_argument('--steps', type=int, default=4)
    p.add_argument('--documents', type=int, default=3)
    p.add_argument('--generalization', choices=NOVELTIES, default='world')
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    try:
        docs, tasks = generate(a.seed, a.count_per_split, a.entities, a.steps, a.documents, a.generalization)
        write_jsonl(a.output_dir / 'corpus' / 'worlds.jsonl', docs)
        write_jsonl(a.output_dir / 'evaluation' / 'world-tasks.jsonl', tasks)
    except (ValueError, FileExistsError, OSError) as exc:
        p.error(str(exc))
    print(f'Generated {len(docs)} documents and {len(tasks)} tasks in {a.output_dir}; seed={a.seed}.')

if __name__ == '__main__':
    main()
