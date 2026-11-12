"""Расчёт из зафиксированной CSV-выборки S12; без кэша и прогноза спроса."""
from pathlib import Path
from decimal import Decimal
import csv
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
work = Path(__file__).resolve().parent
records = {'Всего':'E29', 'Турция':'E30', 'Абхазия':'E31', 'Казахстан':'E32',
           'Объединенные Арабские Эмираты':'E33', 'Китай':'E34', 'Египет':'E35',
           'Грузия':'E36', 'Таиланд':'E37', 'Армения':'E38'}
values = {}
with (work / 'outbound-2025.csv').open(encoding='utf-8-sig', newline='') as stream:
    rows = list(csv.DictReader(stream))
if len({row['destination'] for row in rows}) != len(rows):
    raise ValueError('Дубли направлений')
if {row['destination'] for row in rows} != set(records) | {'Беларусь'}:
    raise ValueError('Неверный набор направлений')
for row in rows:
    if row['year'] != '2025':
        raise ValueError('Смешаны периоды')
    destination = row['destination']
    if destination == 'Беларусь':
        if row['thousand_trips'] != '' or row['evidence'] != 'E40':
            raise ValueError('Прочерк Беларуси должен оставаться пропуском')
        continue
    if row['evidence'] != records[destination]:
        raise ValueError('Неверное основание строки')
    value = Decimal(row['thousand_trips'])
    if not value.is_finite() or value < 0:
        raise ValueError('Недопустимое число поездок')
    values[destination] = value
if values['Всего'] <= 0 or any(value > values['Всего'] for value in values.values()):
    raise ValueError('Неверный общий итог или часть больше итога')

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
