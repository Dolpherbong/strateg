"""Add freshness metadata to the 33 D2 supports; preserve original bytes otherwise."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[5]
PATH = ROOT / 'projects/operator-n-travel/evidence.md'
GROUPS = {
    'функции': [1, 2, 3, 5, 7, 15, 42, 43, 44, 45, 46, 48, 49, 50, 65],
    'цены': [9, 18, 72, 73, 74],
    'аудитория': [16, 17, 20, 21, 24, 25, 30],
    'структура': [67, 68, 69, 70, 71, 75],
}
CLASSES = {f'E{n}': kind for kind, numbers in GROUPS.items() for n in numbers}
EXTRA = {
    'E20': [
        '- годен до: 2026-08-31',
        '- заметка годности: Аудиторская верхняя граница, не точная дата опроса: последний возможный день летнего поля 2025-08-31 плюс 365 дней. Поведенческие данные уже старше срока; сохраняются как исторический фон, не подтверждают текущий спрос.',
    ],
    'E73': [
        '- годен до: 2027-02-09',
        '- заметка годности: Срок условного расчёта ограничен сроками ценовых входов [E9, E72]: источники от 2026-11-11 плюс 90 дней. Изменение входов требует пересчёта раньше; исполнение прогноза не подтверждено.',
    ],
}
EXTRA['E21'] = EXTRA['E20']
raw = PATH.read_bytes()
text = raw.decode('utf-8')
seen = set()

def update(match):
    number = match[1]
    if number not in CLASSES:
        return match[0]
    seen.add(number)
    end = text.find('### ', match.end())
    block = text[match.end():end if end != -1 else len(text)]
    line = f'- годность: {CLASSES[number]}'
    if line in block:
        return match[0]
    if '- годность:' in block:
        raise ValueError(f'Existing different class: {number}')
    newline = match[3]
    return match[0] + newline.join([line, *EXTRA.get(number, [])]) + newline

result = re.sub(r'(?m)^### (E[1-9][0-9]*)([^\r\n]*)(\r?\n)', update, text)
assert seen == set(CLASSES), (seen, set(CLASSES))
if result != text:
    PATH.write_bytes(result.encode('utf-8'))
print(f'Freshness metadata: {len(seen)} records; changed: {result != text}')
