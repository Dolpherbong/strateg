"""Опись переданных PNG и регистрация источников. Исходные снимки только читаются."""
from pathlib import Path
import csv
import hashlib
import struct
import sys

sys.stdout.reconfigure(encoding='utf-8')
work = Path(__file__).resolve().parent
project = work.parents[2]
task = work.parent
files = [
    ('S21', 'beeline-01-glavnyj-ekran.png', 'https://moskva.beeline.ru/travel-esim/'),
    ('S22', 'beeline-02-napravleniya.png', 'https://moskva.beeline.ru/travel-esim/'),
    ('S23', 'beeline-03-obeshchaniya.png', 'https://moskva.beeline.ru/travel-esim/'),
    ('S24', 'beeline-04-podklyuchenie.png', 'https://moskva.beeline.ru/travel-esim/'),
    ('S25', 'mts-01-vybor-strany.png', 'https://payment.mts.ru/esim'),
    ('S26', 'mts-02-turciya-zakaz.png', 'https://payment.mts.ru/esim/turkey'),
    ('S27', 'mts-03-turciya-pakety.png', 'https://payment.mts.ru/esim/turkey'),
    ('S28', 'mts-04-rouming-sravnenie.png', 'https://payment.mts.ru/esim/turkey'),
]
manifest = []
for source, filename, url in files:
    path = project / 'inbox/screens' / filename
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'Не PNG: {filename}')
    width, height = struct.unpack('>II', data[16:24])
    manifest.append([source, 'inbox/screens/' + filename, width, height, len(data), hashlib.sha256(data).hexdigest(), url, '2026-11-12'])
with (work / 'ux-screens-manifest.csv').open('w', encoding='utf-8', newline='') as stream:
    writer = csv.writer(stream)
    writer.writerow(['source', 'file', 'width_px', 'height_px', 'bytes', 'sha256', 'url_from_user', 'capture_date_from_user'])
    writer.writerows(manifest)

request = 'Принимаю редакцию, решение D2 не меняется. Ещё одно: я положил в inbox/screens восемь снимков открытых страниц покупки Travel eSIM, снятых 12.11.2026 без входа и без оплаты: билайн (https://moskva.beeline.ru/travel-esim/, файлы beeline-01...04) и МТС Оплата (https://payment.mts.ru/esim и https://payment.mts.ru/esim/turkey, файлы mts-01...04). Это фрагменты полных страниц, вырезанные по высоте. Разбери их навыком ux: наблюдения с файлом и областью экрана, обещания дословно, сравнение одинаковых шагов, гипотезы последствий с проверкой. Скажи, что из увиденного меняет в продукте или сообщении для N, а что нет. Раньше у нас был только текст инструкции без экранов.'
request_path = project / 'inbox/ux-request-2026-11-12.txt'
if request_path.exists() and request_path.read_text(encoding='utf-8') != request + '\n':
    raise ValueError('Исходное сообщение уже существует с другим текстом')
if not request_path.exists():
    request_path.write_text(request + '\n', encoding='utf-8')

sources = '''### S20
- название: Приёмка редакции и передача восьми фрагментов открытых страниц Travel eSIM
- тип: документ
- где: inbox/ux-request-2026-11-12.txt
- дата источника: 2026-11-12
- дата обращения: 2026-11-12
- надёжность: B
- статус: действует
- заметка: Прямое сообщение руководителя, первичный источник приёмки. Дата съёмки, адреса, отсутствие входа и оплаты — со слов передавшего материалы; самостоятельно не проверены.

'''
for source, filename, url in files:
    sources += f'''### {source}
- название: Фрагмент открытой страницы Travel eSIM — {filename}
- тип: изображение
- где: inbox/screens/{filename}
- дата источника: 2026-11-12
- дата обращения: 2026-11-12
- надёжность: B
- статус: действует
- заметка: Предоставлен человеком; заявленный адрес {url}, дата съёмки и режим без входа/оплаты по S20. Обрезанный фрагмент полной страницы, не отдельный шаг и не обязательно первый экран устройства. Надёжен для видимого текста и расположения; маркетинговые обещания заинтересованной стороны не проверены. Снимки одного сайта не независимые подтверждения исполнения. Размер и SHA-256 в tasks/01-travel-esim/work/ux-screens-manifest.csv.

'''
path = project / 'sources.md'
text = path.read_text(encoding='utf-8')
if '\n### S20\n' in text:
    raise SystemExit('Источники уже зарегистрированы; повторная запись запрещена')
text = text.replace('# Источники\n', '# Источники\n\n' + sources, 1)
if '### S28' not in text:
    raise ValueError('Не найден заголовок реестра источников')
path.write_text(text, encoding='utf-8')
records = '''### E85
- текст: Руководитель принял редакцию сводки и учебного приложения от 2026-11-12 и прямо сохранил D2; новое решение не требуется.
- вид: факт
- источник: S20
- место: inbox/ux-request-2026-11-12.txt, первое предложение
- цитата: «Принимаю редакцию, решение D2 не меняется.»
- период: сообщение 2026-11-12
- статус: действует
- задача: 01-travel-esim

### E86
- текст: По сообщению передавшего материалы, восемь PNG сняты 12.11.2026 с открытых страниц без входа и оплаты и являются фрагментами полных страниц. Это описание происхождения, не независимо проверенная запись действий браузера.
- вид: факт
- источник: S20
- место: inbox/ux-request-2026-11-12.txt, описание снимков
- цитата: «Это фрагменты полных страниц, вырезанные по высоте.»
- период: сообщение и заявленная съёмка 2026-11-12
- статус: действует
- задача: 01-travel-esim

'''
path = project / 'evidence.md'
text = path.read_text(encoding='utf-8')
if '\n### E85\n' in text:
    raise ValueError('E85 уже существует')
path.write_text(text.replace('# Сведения\n', '# Сведения\n\n' + records, 1), encoding='utf-8')
print('S20–S28, E85–E86; восемь исходных PNG только прочитаны, размеры и хеши зафиксированы.')
for row in manifest:
    print(f'{row[0]} {row[1]} {row[2]}x{row[3]}')
