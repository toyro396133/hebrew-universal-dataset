#!/usr/bin/env python3
"""Validate Hebrew corpus and tasks using only the standard library."""
from pathlib import Path
import argparse
import json
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
SPLITS = {'train', 'validation', 'test'}
KINDS = {'fact', 'relation', 'qa', 'followup', 'deduction', 'abstraction', 'entity_tracking'}
REQUIRED_DOC = {'id', 'language', 'text', 'level', 'categories', 'split', 'group_id', 'source'}
REQUIRED_TASK = {'id', 'source_ids', 'split', 'kind', 'question', 'expected_answers'}

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
        if type(doc['level']) is not int or not 1 <= doc['level'] <= 6: errors.append(f'{tag}: level must be 1..6')
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
        source = doc['source']
        if not isinstance(source, dict) or not all(isinstance(source.get(x), str) and source.get(x) for x in ('kind', 'license', 'reference')):
            errors.append(f'{tag}: missing source kind/license/reference')
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
