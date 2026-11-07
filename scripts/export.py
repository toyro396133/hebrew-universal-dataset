#!/usr/bin/env python3
"""Model-neutral exports: text, Unicode characters, UTF-8 bytes and messages."""
from pathlib import Path
import argparse
import json
from validate import load, validate

def build_export(docs, tasks, fmt, split, allow_evaluation_targets=False):
    docs = [d for d in docs if split == 'all' or d['split'] == split]
    sources = {d['id']: d for d in docs}
    if fmt == 'messages':
        for t in tasks:
            if t['split'] != 'train' and not allow_evaluation_targets: continue
            if split != 'all' and t['split'] != split: continue
            if not all(s in sources for s in t['source_ids']): continue
            context = '\n'.join(sources[s]['text'] for s in t['source_ids'])
            history = t.get('history', [])
            if history:
                messages = [{'role':'user','content':f'קטע:\n{context}\n\nשאלה: {history[0]["content"]}'}]
                messages.extend(history[1:])
                messages.append({'role':'user','content':t['question']})
            else:
                messages = [{'role':'user','content':f'קטע:\n{context}\n\nשאלה: {t["question"]}'}]
            messages.append({'role':'assistant','content':t['expected_answers'][0]})
            yield {'id':t['id'],'split':t['split'],'messages':messages}
        return
    for d in docs:
        row = {'id':d['id'],'split':d['split'],'group_id':d['group_id']}
        if fmt == 'text': row['text'] = d['text']
        elif fmt == 'chars': row['characters'] = list(d['text'])
        elif fmt == 'bytes': row['utf8_bytes'] = list(d['text'].encode('utf-8'))
        else: raise ValueError(fmt)
        yield row

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--format', required=True, choices=['text','chars','bytes','messages'])
    p.add_argument('--split', default='train', choices=['train','validation','test','all'])
    p.add_argument('--allow-evaluation-targets', action='store_true')
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    docs, tasks = load(args.root)
    errors = validate(docs, tasks)
    if errors: p.error('Invalid dataset; run scripts/validate.py: ' + errors[0])
    if args.format == 'messages' and args.split in ('validation', 'test') and not args.allow_evaluation_targets:
        p.error('Refusing to export evaluation answers without --allow-evaluation-targets.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8', newline='\n') as out:
        rows = list(build_export(docs, tasks, args.format, args.split, args.allow_evaluation_targets))
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(f'Exported {len(rows)} records to {args.output}')

if __name__ == '__main__':
    main()
