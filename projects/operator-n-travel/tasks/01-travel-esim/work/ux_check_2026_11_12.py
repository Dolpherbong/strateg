"""Проверка целостности восьми PNG и адресации наблюдений; не заменяет визуальную сверку."""
import csv
import hashlib
from pathlib import Path
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
work = Path(__file__).resolve().parent
project = work.parents[2]
with (work / 'ux-screens-manifest.csv').open(encoding='utf-8', newline='') as stream:
    manifest = {row['source']: row for row in csv.DictReader(stream)}
assert len(manifest) == 8
for row in manifest.values():
    assert hashlib.sha256((project / row['file']).read_bytes()).hexdigest() == row['sha256'], row['file']
text = (project / 'evidence.md').read_text(encoding='utf-8')
count = 0
for number in range(87, 116):
    body = re.search(rf'^### E{number}\n(.*?)(?=^#|\Z)', text, re.M | re.S)[1]
    source = re.search(r'^- источник: (S\d+)\s*$', body, re.M)[1]
    row = manifest[source]
    location = re.search(r'^- место: (.*)$', body, re.M)[1]
    assert location.startswith(row['file'] + ','), f'E{number}: файл'
    x1, x2, y1, y2 = map(int, re.search(r'x(\d+)–(\d+), y(\d+)–(\d+)', location).groups())
    assert 0 <= x1 < x2 <= int(row['width_px']) and 0 <= y1 < y2 <= int(row['height_px']), f'E{number}: координаты'
    quote = re.search(r'^- цитата: «(.*)»$', body, re.M)[1]
    assert 0 < len(quote.split()) <= 25, f'E{number}: цитата'
    count += 1
for number in range(116, 121):
    body = re.search(rf'^### E{number}\n(.*?)(?=^#|\Z)', text, re.M | re.S)[1]
    assert '- вид: гипотеза' in body and '- как проверить:' in body
summary = (work.parent / 'out/summary.md').read_text(encoding='utf-8')
assert 350 <= len(summary.split()) <= 500
assert '???' not in summary
for path in [work / 'ux-travel-esim-screens-2026-11-12.md', work.parent / 'out/revision-UX-2026-11-12.md']:
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
        if not target.startswith(('http:', 'https:', '#')):
            assert (path.parent / target.split('#')[0]).exists(), target
print(f'8 SHA-256 неизменны; {count} наблюдений с корректными файлами/областями; 5 гипотез с проверкой; сводка {len(summary.split())} слов; локальные ссылки существуют.')
