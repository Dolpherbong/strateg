"""Проверка цитат в сохранённых снимках и арифметика одного сравнения.

Не проверяет истинность сайта, актуальность продажи или спрос.
Никаких сетевых запросов и значений экономики N.
"""
from pathlib import Path
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

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
for record_id, fields in records.items():
    if fields.get('статус') != 'действует':
        continue
    if 'цитата' not in fields:
        continue
    source = fields['источник']
    cache = (project / '.cache' / f'{source}.txt').read_text(encoding='utf-8')
    quote = fields['цитата'][1:-1]
    found = normalise(quote) in normalise(cache)
    checks.append({'record': record_id, 'source': source, 'match': found})

def price(record_id):
    return int(re.search(r'за (\d+) ₽', records[record_id]['текст'])[1])

travel = price('E9')
comparison = {
    'date': '2026-11-11',
    'scenario': 'Турция, 10 ГБ, 30 дней; только указанные цены пакетов',
    'esim_mts_payment_rub': travel,
    't2_standard_roaming_rub': price('E11'),
    'mts_personal_offer_rub': price('E18'),
    'difference_roaming_minus_esim_rub': {
        't2_standard': price('E11') - travel,
        'mts_personal': price('E18') - travel,
    },
    'limitations': [
        'Один официальный источник на цену; оплата не выполнялась.',
        'Разные поставщики: это ценовые ориентиры, не предложения N.',
        'МТС 646 ₽ — региональная страница и персональное SMS-предложение.',
        'Тарифные льготы и домашняя абонентская плата не включены.',
        'Качество связи, скорость и доступность покупки не измерены.',
        'Акция T2 с посуточным лимитом не эквивалентна 10 ГБ на 30 дней.',
    ],
}
result = {'quote_checks': checks, 'price_comparison': comparison}
output = Path(__file__).with_name('public-checks.json')
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
missing = [item['record'] for item in checks if not item['match']]
print(f'Цитат: {len(checks)}; совпало: {len(checks) - len(missing)}; не совпало: {missing}')
print(json.dumps(comparison, ensure_ascii=False, indent=2))
if missing:
    raise SystemExit(1)
