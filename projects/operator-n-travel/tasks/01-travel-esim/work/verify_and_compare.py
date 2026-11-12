"""Арифметика CSV; сверка цитат отдельно и только с --verify-quotes.

Не проверяет истинность сайта, актуальность продажи или спрос.
Никаких сетевых запросов и значений экономики N.
"""
from pathlib import Path
import argparse
from calc_prices import calculate
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--verify-quotes', action='store_true', help='Отдельно сверить цитаты с .cache; не требуется для расчёта')
args = parser.parse_args()
calculate()
print('Цены пересчитаны из prices.csv; кэш для арифметики не используется')
if not args.verify_quotes:
    raise SystemExit(0)

project = Path(__file__).resolve().parents[3]
evidence = (project / 'evidence.md').read_text(encoding='utf-8')
# Служебные образцы не являются записями.
evidence = re.sub(r'<!--[\s\S]*?-->', '', evidence)
records = {}
for match in re.finditer(r'^### (E\d+)\b[^\n]*\n([\s\S]*?)(?=^#{1,3} |\Z)', evidence, re.M):
    fields = dict(re.findall(r'^- ([^:\n]+): (.*)$', match[2], re.M))
    records[match[1]] = fields

def normalise(value):
    value = re.sub(r'^L\d+: ?', '', value, flags=re.M)
    return re.sub(r'\s+', ' ', value).strip()

checks = []
source_paths = {}
sources_text = (project / 'sources.md').read_text(encoding='utf-8')
for match in re.finditer(r'^### (S\d+)\b[^\n]*\n([\s\S]*?)(?=^#{1,3} |\Z)', sources_text, re.M):
    fields = dict(re.findall(r'^- ([^:\n]+): (.*)$', match[2], re.M))
    location = fields.get('где', '')
    if location.startswith('inbox/'):
        source_paths[match[1]] = project / location
for record_id, fields in records.items():
    if fields.get('статус') != 'действует':
        continue
    if 'цитата' not in fields:
        continue
    source = fields['источник']
    snapshot = project / '.cache' / f'{source}.txt'
    if not snapshot.exists():
        snapshot = source_paths.get(source, snapshot)
    if not snapshot.exists():
        checks.append({'record': record_id, 'source': source, 'match': None, 'status': 'источник недоступен'})
        continue
    cache = snapshot.read_text(encoding='utf-8')
    quote = fields['цитата'][1:-1]
    found = normalise(quote) in normalise(cache)
    checks.append({'record': record_id, 'source': source, 'match': found, 'path': str(snapshot.relative_to(project))})

result = {'quote_checks': checks}
output = Path(__file__).with_name('quote-checks.json')
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
mismatched = [item['record'] for item in checks if item['match'] is False]
unavailable = [item['record'] for item in checks if item['match'] is None]
matched = len(checks) - len(mismatched) - len(unavailable)
print(f'Цитат: {len(checks)}; совпало: {matched}; не совпало: {mismatched}; источник недоступен: {unavailable}')
if mismatched or unavailable:
    raise SystemExit(1)
