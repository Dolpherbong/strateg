"""Извлечение и расчёт выбранных строк официальной таблицы; без прогноза спроса."""
from pathlib import Path
from decimal import Decimal
from html import unescape
import csv
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
work = Path(__file__).resolve().parent
project = work.parents[2]
text = (project / '.cache' / 'S12.txt').read_text(encoding='utf-8')
# Берём первую полную HTML-таблицу из индексированного текста официального PDF.
table = re.search(r'<table[^>]*>(.*?)</table>', text, re.S)[1]
rows = {}
for row in re.findall(r'<tr>(.*?)</tr>', table, re.S):
    cells = [unescape(re.sub(r'<[^>]+>', '', cell)).strip() for cell in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
    if len(cells) >= 2:
        rows[cells[0]] = cells[1]

records = {'Всего':'E29', 'Турция':'E30', 'Абхазия':'E31', 'Казахстан':'E32',
           'Объединенные Арабские Эмираты':'E33', 'Китай':'E34', 'Египет':'E35',
           'Грузия':'E36', 'Таиланд':'E37', 'Армения':'E38'}
values = {}
with (work / 'outbound-2025.csv').open('w', encoding='utf-8', newline='') as target:
    writer = csv.writer(target)
    writer.writerow(['destination','year','thousand_trips','evidence'])
    for destination, evidence in records.items():
        value = Decimal(re.sub(r'\s+', '', rows[destination]).replace(',', '.'))
        values[destination] = value
        writer.writerow([destination,2025,str(value),evidence])
    writer.writerow(['Беларусь',2025,'','E40'])

selected = ['Турция','Объединенные Арабские Эмираты','Египет','Таиланд']
subtotal = sum(values[key] for key in selected)
if not 0 <= subtotal <= values['Всего']:
    raise ValueError('Сумма выбранных направлений выходит за общий итог')
if len(selected) != len(set(selected)):
    raise ValueError('В выбранных направлениях есть дубли')
result = {
    'source':'S12, один статистический первоисточник',
    'year':2025,
    'unit':'тысяч поездок',
    'total':str(values['Всего']),
    'selected_four':selected,
    'selected_four_total':str(subtotal),
    'selected_four_share_percent':str((subtotal / values['Всего'] * 100).quantize(Decimal('0.1'))),
    'conditional_max_one_purchase_per_recorded_trip':str(values['Всего'] * 1000),
    'conditions':'Только охваченный статистикой поток 2025; одна первичная покупка на поездку; не число людей, не весь рынок, не прогноз N; пополнения не считаем.'
}
(work / 'scale-2025.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
