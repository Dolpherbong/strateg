"""Move introductions before records and sort IDs without changing any original line."""
from collections import Counter
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PROJECT = ROOT / 'projects/operator-n-travel'
sys.path.insert(0, str(ROOT))
from tools.lib.records import parse_records, read, visible

FILES = ['sources.md', 'evidence.md', 'decisions.md', 'tasks/01-travel-esim/questions.md']
report = []
for name in FILES:
    path = PROJECT / name
    before = read(path)
    records = parse_records(path, before)
    raw_lines = before.splitlines(keepends=True)
    shown_lines = visible(before).splitlines(keepends=True)
    owners = {}
    buffers = {r.id: [] for r in records}
    for record in records:
        start = record.line - 1
        for line in range(start, start + len(record.text.splitlines(keepends=True))):
            owners[line] = record.id
    introduction = []
    for line, raw in enumerate(raw_lines):
        owner = owners.get(line)
        shown = shown_lines[line]
        if owner and (re.match(r'^###\s+[SEQOCDK][1-9][0-9]*(?:\s|$)', shown)
                      or re.match(r'^\s*-\s+[^:]+:', shown) or not raw.strip()):
            buffers[owner].append(raw)
        else:
            introduction.append(raw)
    ordered = sorted(buffers, key=lambda number: (number[0], int(number[1:])))
    after = ''.join(introduction) + ''.join(''.join(buffers[number]) for number in ordered)
    old_entries = Counter((r.id, tuple(sorted(r.fields.items())), r.duplicate_fields) for r in records)
    new_records = parse_records(path, after)
    new_entries = Counter((r.id, tuple(sorted(r.fields.items())), r.duplicate_fields) for r in new_records)
    assert old_entries == new_entries, f'Records or fields changed: {name}'
    assert Counter(raw_lines) == Counter(after.splitlines(keepends=True)), f'Lines changed: {name}'
    backup = HERE / 'archive' / (path.name + '.before-order-2026-11-12.txt')
    if not backup.exists():
        backup.write_bytes(path.read_bytes())
    if after != before:
        path.write_bytes(after.encode('utf-8'))
    report.append({'file': name, 'records': len(records), 'changed': before != after,
                   'fields_preserved': True, 'all_original_lines_preserved': True,
                   'backup': backup.relative_to(ROOT).as_posix()})
(HERE / 'registry-order-verification.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
for item in report:
    print(f"{item['file']}: {item['records']} records, changed={item['changed']}; fields and all lines preserved")
