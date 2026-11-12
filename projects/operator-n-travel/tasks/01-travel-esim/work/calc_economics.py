"""Учебная модель из CSV. Все входы гипотезы, не экономика или прогноз N."""
import csv
import json
import sys
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

WORK = Path(__file__).resolve().parent
PARAMETERS = ('q', 'r', 'w', 'v', 'c', 'l', 'F')
SCENARIOS = ('cautious', 'base', 'bold')


def metrics(values):
    q, r, w, v, c, lost, fixed = (values[key] for key in PARAMETERS)
    unit = r - w - v - c * lost
    contribution = q * unit
    return {
        'unit_incremental_rub': float(unit),
        'incremental_contribution_rub': float(contribution),
        'net_after_fixed_rub': float(contribution - fixed),
        'break_even_packages': int((fixed / unit).to_integral_value(rounding=ROUND_CEILING)) if unit > 0 else None,
    }


def calculate(work=WORK):
    with (work / 'economics-inputs.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    by_key = {row['parameter']: row for row in rows}
    if len(rows) != len(by_key) or set(by_key) != set(PARAMETERS):
        raise ValueError('Дубли или неверный набор параметров')
    for row in rows:
        if row['kind'] != 'гипотеза' or not row['evidence'] or not row['how_to_check']:
            raise ValueError('Каждый вход должен быть проверяемой гипотезой')
        if any(not Decimal(row[s]).is_finite() or Decimal(row[s]) < 0 for s in SCENARIOS):
            raise ValueError('Пропуск, бесконечное или отрицательное значение')
    values = {s: {key: Decimal(by_key[key][s]) for key in PARAMETERS} for s in SCENARIOS}
    for s in SCENARIOS:
        if not 0 <= values[s]['c'] <= 1 or values[s]['q'] <= 0 or values[s]['q'] % 1:
            raise ValueError('Доля вне [0,1] или число пакетов не положительное целое')
    base = values['base']
    baseline = metrics(base)['net_after_fixed_rub']
    sensitivity = []
    for key in PARAMETERS:
        cases = []
        for factor in (Decimal('0.8'), Decimal('1.2')):
            changed = dict(base)
            changed[key] *= factor
            if key == 'c' and not 0 <= changed[key] <= 1:
                raise ValueError('Чувствительность выводит долю за [0,1]')
            net = metrics(changed)['net_after_fixed_rub']
            cases.append({'factor': str(factor), 'value': float(changed[key]), 'net_rub': net, 'change_from_base_rub': net - baseline})
        sensitivity.append({'parameter': key, 'cases': cases, 'max_abs_change_rub': max(abs(case['change_from_base_rub']) for case in cases)})
    sensitivity.sort(key=lambda row: row['max_abs_change_rub'], reverse=True)
    result = {
        'kind': 'оценка при учебных гипотезах; не прогноз и не измерение N',
        'horizon': 'условные 12 месяцев, единый для q и F',
        'formula': 'q * (r - w - v - c*l) - F',
        'inputs': rows,
        'scenarios': {s: metrics(values[s]) for s in SCENARIOS},
        'sensitivity_method': 'один вход ±20% относительно базового, остальные неизменны',
        'sensitivity': sensitivity,
        'base_max_c_for_nonnegative_net': float((base['r'] - base['w'] - base['v'] - base['F'] / base['q']) / base['l']) if base['l'] else None,
        'limitations': [
            'Сценариям не назначены вероятности; это сочетания допущений.',
            'r — доход N после налогов и возвратов, не обязательно розничная цена.',
            '590 ₽ — цена планового пакета, не потерянный вклад l.',
            'F — учебные постоянные затраты; не утверждённый лимит проверки.',
            'При агентской модели r — комиссия, w=0 если закупку несёт партнёр.',
            'Измеренная разность всех услуг теста и контроля уже включает замещение: c*l второй раз не вычитать.',
            'Не масштабировать на весь поток поездок; закрытые числа N не запрашивались.',
        ],
    }
    (work / 'economics-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    labels = {'cautious': 'Осторожный', 'base': 'Базовый', 'bold': 'Смелый'}
    def rub(value):
        return f'{value:,.0f}'.replace(',', ' ')
    report = [
        '# Учебные сценарии дополнительного вклада',
        '',
        '2026-11-12. Все входы — произвольные учебные гипотезы. Это условная оценка, не прогноз N, не доказательство спроса и не допуск к пилоту. [E76, E77, E78, E79, E80, E81, E82, E83]',
        '',
        '## Метод',
        '',
        '`u = r-w-v-c*l`; дополнительный вклад до постоянных затрат `q*u`; результат после них `q*u-F`. Горизонт — условные 12 месяцев. r — доход N после налогов и возвратов; w — закупка N; v — остальные переменные расходы; c*l — потерянный вклад роуминга. Полное определение входов и проверки — в [паспорте](economics-passport.md) и [CSV](economics-inputs.csv). [E76, E77, E78, E79, E80, E81, E82]',
        '',
        '## Входы: гипотезы',
        '',
        '| Параметр | Единица | Осторожный | Базовый | Смелый | Опора |',
        '|---|---|---:|---:|---:|---|',
    ]
    for row in rows:
        report.append(f"| {row['parameter']} | {row['unit']} | {row['cautious']} | {row['base']} | {row['bold']} | [{row['evidence']}] гипотеза |")
    report += [
        '', '## Результаты', '',
        '| Сценарий | u, ₽/пакет | Вклад до F, ₽ | После F, ₽ | Пакетов для безубыточности |',
        '|---|---:|---:|---:|---|',
    ]
    for s, item in result['scenarios'].items():
        threshold = str(item['break_even_packages']) if item['break_even_packages'] is not None else 'Нет: u≤0'
        report.append(f"| {labels[s]} | {rub(item['unit_incremental_rub'])} | {rub(item['incremental_contribution_rub'])} | {rub(item['net_after_fixed_rub'])} | {threshold} |")
    report += [
        '', 'Диапазон после F: −420 000…2 160 000 ₽. Это диапазон трёх сочетаний гипотез, не доверительный интервал. Положительный базовый результат не подтверждает выгодность N. [E83]',
        '', '## Чувствительность', '',
        'Один вход уменьшается/увеличивается на 20% от базы; остальные неизменны. Сравнивается результат после F, базовое значение 210 000 ₽. Рейтинг справедлив только для этой базы и шага. [E84]', '',
        '| Вход | Результат при −20%, ₽ | При +20%, ₽ | Максимальное изменение от базы, ₽ |',
        '|---|---:|---:|---:|',
    ]
    for row in sensitivity:
        report.append(f"| {row['parameter']} | {rub(row['cases'][0]['net_rub'])} | {rub(row['cases'][1]['net_rub'])} | {rub(row['max_abs_change_rub'])} |")
    report += [
        '', 'В этом упражнении сильнее всего влияет r, затем w. При базовых прочих входах нулевой результат достигается при c=63,333…%; для положительного результата доля должна быть ниже точного порога. Базовый объём безубыточности — 1600 пакетов. [E83, E84]',
        '', '## Границы применения', '',
        '590 ₽ — плановая розничная цена, её нельзя считать l. F=240000 ₽ — учебный вход, отдельно от лимита первой проверки 300000 ₽. При агентской модели r означает комиссию, w=0 если закупку несёт партнёр. [E72, E77, E78, E81, E82, D2]',
        '', 'Разность вклада всех поездочных услуг в тесте и контроле уже включает замещение: повторно вычитать c*l нельзя. Будущий поток ограничивается тем же отбором и каналом; статистика поездок не даёт объём N. [E63, E66]',
        '', 'Вероятности сценариев не назначены. Порог качества и статистическая неопределённость этой арифметикой не проверяются. Q5 и Q9 остаются открытыми по существу; обязательное полное сравнение K7 не выполнено этими числами. [E83, Q5, Q9, K7]',
        '', '## Воспроизведение', '',
        '`python projects/operator-n-travel/tasks/01-travel-esim/work/run_calculations.py --check`',
        '', 'Только стандартная библиотека Python и CSV; два изолированных прогона без страниц, кэша и реестров сравнивают JSON и эту записку побайтно. [E83, E84]',
        '',
    ]
    (work / 'economics.md').write_text('\n'.join(report), encoding='utf-8')
    return result


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    result = calculate()
    for name, value in result['scenarios'].items():
        print(f"{name}: вклад {value['incremental_contribution_rub']:.0f} ₽; после F {value['net_after_fixed_rub']:.0f} ₽")
    print('Самый чувствительный вход при ±20%: ' + result['sensitivity'][0]['parameter'])
