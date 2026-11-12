"""Только арифметика CSV: снимки цен не подтверждают продажу или маржу."""
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

WORK = Path(__file__).resolve().parent


def calculate(work=WORK):
    with (work / 'prices.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    offers = {row['offer']: row for row in rows}
    required = {'esim_mts_payment', 't2_standard', 'mts_personal', 'n_planned'}
    if len(offers) != len(rows) or set(offers) != required:
        raise ValueError('Неверный набор предложений или дубли')
    for row in rows:
        if (row['country'], row['gb'], row['days'], row['as_of']) != ('Турция', '10', '30', '2026-11-11'):
            raise ValueError('Несопоставимая география, объём, срок или дата снимка')
        if not row['evidence'] or not row['source'] or Decimal(row['price_rub']) <= 0:
            raise ValueError('Нет основания или цена неположительная')
    if offers['n_planned']['kind'] != 'прогноз' or offers['n_planned']['valid_from'] != '2026-12-01':
        raise ValueError('Будущий тариф должен оставаться планом')
    if any(offers[key]['kind'] != 'факт' for key in required - {'n_planned'}):
        raise ValueError('Снимки цен должны быть помечены фактами')
    prices = {key: Decimal(row['price_rub']) for key, row in offers.items()}
    esim = prices['esim_mts_payment']
    historic = {
        'date': '2026-11-11',
        'scenario': 'Турция, 10 ГБ, 30 дней; только указанные цены пакетов',
        'inputs': rows,
        'esim_mts_payment_rub': float(esim),
        't2_standard_roaming_rub': float(prices['t2_standard']),
        'mts_personal_offer_rub': float(prices['mts_personal']),
        'difference_roaming_minus_esim_rub': {
            't2_standard': float(prices['t2_standard'] - esim),
            'mts_personal': float(prices['mts_personal'] - esim),
        },
        'limitations': [
            'Исторические снимки, один источник на цену; покупка не выполнялась.',
            'Разные поставщики; не экономия клиента N и не сравнение качества.',
            'МТС 646 ₽ — региональная страница и персональное предложение.',
            'Домашняя плата и льготы не включены; цена партнёра N неизвестна.',
        ],
    }
    delta = esim - prices['n_planned']
    planned = {
        'inputs': [offers['esim_mts_payment'], offers['n_planned']],
        'esim_snapshot_rub': float(esim),
        'N_planned_rub': float(prices['n_planned']),
        'difference_rub': float(delta),
        'N_lower_percent_of_esim_price': float((delta / esim * 100).quantize(Decimal('0.1'))),
        'condition': 'Запуск N с 2026-12-01 и неизменность цены eSIM; не сравнение качества или маржи',
    }
    outputs = {
        'public-checks.json': {'price_comparison': historic, 'quote_verification': 'Не запускалась; отдельный режим verify_and_compare.py --verify-quotes'},
        'roaming-plan-comparison.json': planned,
    }
    for name, value in outputs.items():
        (work / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return outputs


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    calculate()
    print('prices.csv → public-checks.json, roaming-plan-comparison.json')
