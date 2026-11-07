#!/usr/bin/env python3
"""Validate Hebrew corpus and tasks using only the standard library."""
from pathlib import Path
import argparse
import json
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
SPLITS = {'train', 'validation', 'test'}
KINDS = {'fact', 'relation', 'qa', 'followup', 'deduction', 'abstraction', 'entity_tracking', 'planning', 'revision', 'self_check'}
REQUIRED_DOC = {'id', 'language', 'text', 'level', 'categories', 'split', 'group_id', 'source'}
REQUIRED_TASK = {'id', 'source_ids', 'split', 'kind', 'question', 'expected_answers'}

def _taxonomy(filename, key):
    path = ROOT / 'taxonomy' / filename
    data = json.loads(path.read_text(encoding='utf-8'))
    return data[key]

TOPIC_IDS = {t['id'] for t in _taxonomy('topics.json', 'topics')}
_AXES = _taxonomy('axes.json', 'axes')
AXIS_TYPES = {a['id']: a['type'] for a in _AXES}
AXIS_VALUES = {a['id']: set(a.get('values', [])) for a in _AXES}

def read_jsonl(path):
    for n, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f'{path}:{n}: invalid JSON: {exc}') from exc

def load(root=ROOT):
    paths = sorted((root / 'corpus').rglob('*.jsonl'))
    if not paths:
        raise ValueError('No corpus JSONL files found')
    docs = [row for p in paths for row in read_jsonl(p)]
    tasks = [row for p in sorted((root / 'evaluation').rglob('*.jsonl')) for row in read_jsonl(p)]
    return docs, tasks

def validate(docs, tasks):
    errors, seen, fingerprints, group_split = [], {}, {}, {}
    for i, doc in enumerate(docs, 1):
        tag = f'document #{i}'
        if not isinstance(doc, dict):
            errors.append(f'{tag}: not an object')
            continue
        missing = REQUIRED_DOC - doc.keys()
        if missing:
            errors.append(f'{tag}: missing {sorted(missing)}')
            continue
        did = doc['id']
        tag = f'document {did}'
        if not isinstance(did, str) or not did:
            errors.append(f'{tag}: invalid id')
            continue
        if did in seen: errors.append(f'{tag}: duplicate ID')
        seen[did] = doc
        if doc['language'] != 'he': errors.append(f'{tag}: language must be he')
        if type(doc['level']) is not int or not 0 <= doc['level'] <= 14: errors.append(f'{tag}: level must be 0..14 (0 = ungraded natural text)')
        if doc['split'] not in SPLITS: errors.append(f'{tag}: invalid split')
        cats = doc['categories']
        if not isinstance(cats, list) or not cats or not all(isinstance(x, str) and x for x in cats) or len(set(cats)) != len(cats):
            errors.append(f'{tag}: invalid categories')
        if not isinstance(doc['text'], str) or not doc['text'].strip():
            errors.append(f'{tag}: empty text')
        else:
            value = doc['text']
            if unicodedata.normalize('NFC', value) != value: errors.append(f'{tag}: text is not Unicode NFC')
            fingerprint = ' '.join(value.split())
            if fingerprint in fingerprints: errors.append(f'{tag}: duplicate text of {fingerprints[fingerprint]}')
            fingerprints[fingerprint] = did
        # Optional v2 annotations; v1 documents remain valid without these keys.
        if 'topics' in doc:
            labels = doc['topics']
            if not isinstance(labels, list) or not labels or not all(isinstance(x, str) for x in labels) or len(set(labels)) != len(labels) or not set(labels) <= TOPIC_IDS:
                errors.append(f'{tag}: unknown, duplicate or invalid topic labels')
        if 'axis_tags' in doc:
            labels = doc['axis_tags']
            if not isinstance(labels, dict):
                errors.append(f'{tag}: axis_tags must be an object')
            else:
                for axis, values in labels.items():
                    if axis not in AXIS_TYPES:
                        errors.append(f'{tag}: unknown axis {axis}')
                        continue
                    typ = AXIS_TYPES[axis]
                    if typ == 'integer':
                        if type(values) is not int or values < 0:
                            errors.append(f'{tag}: axis {axis} needs a nonnegative integer')
                    elif typ == 'counts':
                        if not isinstance(values, dict) or not set(values) <= AXIS_VALUES[axis] or not all(type(x) is int and x >= 0 for x in values.values()):
                            errors.append(f'{tag}: axis {axis} needs a map of nonnegative counts')
                    elif not isinstance(values, list) or not values or not all(isinstance(x, str) for x in values) or len(set(values)) != len(values) or not set(values) <= AXIS_VALUES[axis]:
                        errors.append(f'{tag}: invalid tags for axis {axis}')
        if 'metrics' in doc:
            metrics = doc['metrics']
            if not isinstance(metrics, dict) or not set(metrics) <= {'reasoning_steps', 'documents', 'entities', 'events'} or not all(type(x) is int and x >= (1 if k in ('documents', 'entities') else 0) for k, x in metrics.items()):
                errors.append(f'{tag}: invalid numeric complexity metrics')
        source = doc['source']
        if not isinstance(source, dict) or not all(isinstance(source.get(x), str) and source.get(x) for x in ('kind', 'license', 'reference')):
            errors.append(f'{tag}: missing source kind/license/reference')
        if doc['level'] == 0 and doc['source'].get('kind') != 'external':
            errors.append(f'{tag}: ungraded level 0 is reserved for natural external text')
        if doc['source'].get('kind') == 'external':
            p = doc.get('provenance')
            if not isinstance(p, dict) or any(not p.get(k) for k in ('dataset','snapshot_revision','source_row_id','attribution','dataset_card')) or not isinstance(p.get('original_sha256'),str) or len(p['original_sha256']) != 64:
                errors.append(f'{tag}: external text is missing full provenance')
            if doc['split'] != 'train':
                errors.append(f'{tag}: external unreviewed documents must remain in train only')
        group = doc['group_id']
        if not isinstance(group, str) or not group: errors.append(f'{tag}: invalid group_id')
        elif group in group_split and group_split[group] != doc['split']:
            errors.append(f'{tag}: group {group} appears in several splits')
        else: group_split[group] = doc['split']
    task_ids = set()
    for i, task in enumerate(tasks, 1):
        tag = f'task #{i}'
        if not isinstance(task, dict):
            errors.append(f'{tag}: not an object')
            continue
        missing = REQUIRED_TASK - task.keys()
        if missing:
            errors.append(f'{tag}: missing {sorted(missing)}')
            continue
        tid = task['id']
        tag = f'task {tid}'
        if not isinstance(tid, str) or not tid:
            errors.append(f'{tag}: invalid id')
            continue
        if tid in task_ids: errors.append(f'{tag}: duplicate task ID')
        task_ids.add(tid)
        if task['split'] not in SPLITS: errors.append(f'{tag}: invalid split')
        if task['kind'] not in KINDS: errors.append(f'{tag}: invalid task kind')
        if not isinstance(task['question'], str) or not task['question'].strip(): errors.append(f'{tag}: empty question')
        answers = task['expected_answers']
        if not isinstance(answers, list) or not answers or not all(isinstance(x, str) and x.strip() for x in answers):
            errors.append(f'{tag}: missing expected answers')
        if 'difficulty' in task:
            difficulty = task['difficulty']
            if not isinstance(difficulty, dict) or not set(difficulty) <= {'reasoning_steps', 'documents', 'entities'} or not all(type(x) is int and x >= (0 if k == 'reasoning_steps' else 1) for k, x in difficulty.items()):
                errors.append(f'{tag}: invalid task difficulty')
        history = task.get('history', [])
        if not isinstance(history, list) or len(history) % 2:
            errors.append(f'{tag}: history must have alternating user/assistant pairs')
        elif any(not isinstance(turn, dict) or turn.get('role') != ('user' if j % 2 == 0 else 'assistant') or not isinstance(turn.get('content'), str) or not turn['content'].strip() for j, turn in enumerate(history)):
            errors.append(f'{tag}: invalid history turns')
        ids = task['source_ids']
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
            errors.append(f'{tag}: invalid source IDs')
            continue
        for did in ids:
            if did not in seen: errors.append(f'{tag}: unknown source ID {did}')
            elif seen[did]['split'] != task['split']: errors.append(f'{tag}: split mismatch for {did}')
    return errors

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        docs, tasks = load(args.root)
        errors = validate(docs, tasks)
    except (OSError, ValueError) as exc:
        print(f'INVALID: {exc}', file=sys.stderr)
        return 1
    if errors:
        print('\n'.join('ERROR: ' + x for x in errors), file=sys.stderr)
        return 1
    print(f'VALID: {len(docs)} corpus documents, {len(tasks)} tasks; splits and source groups consistent.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
