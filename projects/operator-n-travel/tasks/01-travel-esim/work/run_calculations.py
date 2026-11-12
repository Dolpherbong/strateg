"""Воспроизвести расчёты; --check сравнивает два прогона в изоляции без кэша."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

WORK = Path(__file__).resolve().parent
SCRIPTS = ('scale_2025.py', 'calc_prices.py', 'calc_economics.py')
INPUTS = ('outbound-2025.csv', 'prices.csv', 'economics-inputs.csv')
OUTPUTS = ('scale-2025.json', 'public-checks.json', 'roaming-plan-comparison.json', 'economics-results.json', 'economics.md')


def run(work):
    for script in SCRIPTS:
        completed = subprocess.run([sys.executable, str(work / script)], cwd=work, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode:
            raise RuntimeError(completed.stderr.decode('utf-8', errors='replace'))
    return {name: (work / name).read_bytes() for name in OUTPUTS}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    original = run(WORK)
    if args.check:
        with tempfile.TemporaryDirectory(prefix='strateg-csv-') as directory:
            isolated = Path(directory)
            for name in SCRIPTS + INPUTS:
                shutil.copy2(WORK / name, isolated / name)
            # Ни реестры, ни .cache, ни исходные страницы в копию не попадают.
            first = run(isolated)
            second = run(isolated)
            if original != first or first != second:
                raise AssertionError('Расчёты не воспроизводятся побайтно')
        from calc_economics import metrics
        base = dict(q=Decimal(3000), r=Decimal(700), w=Decimal(350), v=Decimal(80), c=Decimal('0.4'), l=Decimal(300), F=Decimal(240000))
        result = metrics(base)
        if result['unit_incremental_rub'] != 150 or result['net_after_fixed_rub'] != 210000:
            raise AssertionError('Ошибка базовой арифметики')
        at_break_even = dict(base, q=Decimal(result['break_even_packages']))
        if metrics(at_break_even)['net_after_fixed_rub'] < 0 or metrics(dict(at_break_even, q=at_break_even['q'] - 1))['net_after_fixed_rub'] >= 0:
            raise AssertionError('Неверное округление безубыточности')
        if metrics(dict(base, c=Decimal(0)))['net_after_fixed_rub'] - result['net_after_fixed_rub'] != float(base['q'] * base['c'] * base['l']):
            raise AssertionError('Замещение вычтено неверно')
        negative = metrics(dict(base, r=Decimal(0)))
        if negative['break_even_packages'] is not None:
            raise AssertionError('Отрицательный вклад нельзя исправить объёмом')
        data = json.loads(original['scale-2025.json'])
        prices = json.loads(original['roaming-plan-comparison.json'])
        if Decimal(data['selected_four_total']) != Decimal('11966.1') or prices['difference_rub'] != 128:
            raise AssertionError('Изменились ранее сверенные результаты')
        print('Два прогона без кэша и реестров совпали побайтно; арифметика, замещение и безубыточность проверены.')
    print('Готово: ' + ', '.join(OUTPUTS))


if __name__ == '__main__':
    main()
