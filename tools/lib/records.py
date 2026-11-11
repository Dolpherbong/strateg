"""Единый разбор реестров, ссылок и разделов Markdown."""

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Schema:
    """Обязательные поля и перечисления одного вида записи."""

    letter: str
    required: str
    choices: tuple[tuple[str, str], ...] = ()


# Keep this table in sync with agent/records.md.
SCHEMAS = (
    Schema("S", "название|тип|где|дата источника|дата обращения|надёжность|статус", (
        ("тип", "документ|таблица|сайт|интервью|изображение|аудио|видео|продукт|модель"),
        ("надёжность", "A|B|C"), ("статус", "действует|устарело|отозвано"))),
    Schema("E", "текст|вид|период|статус|задача", (
        ("вид", "факт|оценка|гипотеза|прогноз|синтетика"),
        ("статус", "действует|устарело|отозвано"))),
    Schema("Q", "вопрос|зачем|что изменит ответ|где искать|статус", (
        ("статус", "открыт|закрыт|снят|пробел"), ("уверенность", "высокая|средняя|низкая"))),
    Schema("C", "текст|опора|уверенность|что может опровергнуть|статус", (
        ("уверенность", "высокая|средняя|низкая"), ("статус", "действует|устарело|отозвано"))),
    Schema("O", "роль|суть|что должно быть правдой|выгоды|цена и риски|возражение|ответ на возражение|чего не знаем|дешёвая проверка", (
        ("роль", "статус-кво|закрыть|активный"),)),
    Schema("D", "решение|дата|кто решил|выбран вариант|основания|отвергнуто|ответственный|показатель|срок проверки|условие пересмотра|статус", (
        ("статус", "действует|пересмотрено|отменено"),)),
    Schema("K", "что|кто|срок|к решению|статус", (("статус", "открыто|выполнено|сорвано|снято"),)),
)
LINK_FIELDS = ("источник", "основание", "опора", "выбран вариант", "основания", "к решению", "заменено")
ID_PATTERN = r"[SEQOCDK][1-9][0-9]*"


@dataclass(frozen=True)
class Record:
    """Запись с исходным текстом и положением в файле."""

    id: str
    path: Path
    line: int
    text: str
    visible: str
    fields: dict[str, str]
    duplicate_fields: tuple[str, ...]
    refs: tuple[str, ...]


@dataclass(frozen=True)
class Section:
    """Раздел документа вместе с вложенными заголовками."""

    title: str
    line: int
    text: str
    raw: str


@dataclass(frozen=True)
class Project:
    """Разобранный снимок файлов проекта."""

    records: tuple[Record, ...]
    documents: dict[Path, str]


def read(path: Path) -> str:
    """Читает UTF-8, сохраняя переводы строк.

    Args:
        path: Путь файла.

    Returns:
        Исходный текст, включая CRLF при наличии.
    """
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return stream.read()


def _blank(text: str) -> str:
    return "".join(char if char in "\r\n" else " " for char in text)


def _comments(line: str, inside: bool) -> tuple[str, bool]:
    result, cursor = "", 0
    while cursor < len(line):
        token = "-->" if inside else "<!--"
        position = line.find(token, cursor)
        end = len(line) if position < 0 else position + len(token)
        fragment = line[cursor:end]
        result += _blank(fragment) if inside else line[cursor:position] + _blank(token) if position >= 0 else fragment
        if position < 0:
            break
        inside, cursor = not inside, end
    return result, inside


def visible(text: str) -> str:
    """Маскирует комментарии и ограждённый код без сдвига строк.

    Args:
        text: Markdown.

    Returns:
        Текст той же длины с пробелами вместо скрытых данных.
    """
    lines, comment, fence = [], False, ""
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = ""
            lines.append(_blank(line))
        elif marker and not comment and not (marker[1][0] == "`" and "`" in marker[2]):
            fence = marker[1]
            lines.append(_blank(line))
        elif not comment and line.startswith(("    ", "\t")):
            lines.append(_blank(line))
        else:
            shown, comment = _comments(line, comment)
            lines.append(shown)
    return "".join(lines)


def fields(text: str) -> tuple[dict[str, str], tuple[str, ...]]:
    """Разбирает однострочные поля по первому двоеточию.

    Args:
        text: Текст с полями.

    Returns:
        Поля и список повторённых имён.
    """
    result, duplicates = {}, []
    for line in visible(text).splitlines():
        match = re.match(r"^\s*-\s+([^:]+):\s*(.*)$", line)
        if match:
            name, value = match[1].strip().casefold(), match[2].strip()
            if name in result:
                duplicates.append(name)
            result[name] = value
    return result, tuple(duplicates)


def references(text: str) -> tuple[str, ...]:
    """Читает ссылки из полей-ссылок и квадратных скобок.

    Args:
        text: Markdown с записями или свободным текстом.

    Returns:
        Номера в порядке первого появления, без повторов.
    """
    shown = visible(text)
    found = []
    for line in shown.splitlines():
        pair = re.match(r"^\s*-\s+([^:]+):\s*(.*)$", line)
        if pair and pair[1].strip().casefold() in LINK_FIELDS:
            found.extend(re.findall(rf"(?<![\w]){ID_PATTERN}(?![\w])", pair[2]))
        for match in re.finditer(rf"\[\s*({ID_PATTERN}(?:\s*,\s*{ID_PATTERN})*)\s*\]", line):
            found.extend(re.findall(ID_PATTERN, match[1]))
    return tuple(dict.fromkeys(found))


def parse_records(path: Path, text: str) -> tuple[Record, ...]:
    """Разбирает записи до следующего заголовка любого уровня.

    Args:
        path: Путь для диагностик.
        text: Исходный Markdown.

    Returns:
        Найденные записи с номерами строк.
    """
    raw_lines, shown_lines = text.splitlines(keepends=True), visible(text).splitlines(keepends=True)
    headings = [i for i, line in enumerate(shown_lines) if re.match(r"^ {0,3}#{1,6}\s+", line)]
    result = []
    for position, start in enumerate(headings):
        match = re.match(rf"^###\s+({ID_PATTERN})(?:\s|$)", shown_lines[start])
        if not match:
            continue
        end = headings[position + 1] if position + 1 < len(headings) else len(raw_lines)
        raw, shown = "".join(raw_lines[start:end]), "".join(shown_lines[start:end])
        values, duplicates = fields(shown)
        result.append(Record(match[1], path, start + 1, raw, shown, values, duplicates, references(shown)))
    return tuple(result)


def sections(text: str) -> tuple[Section, ...]:
    """Выделяет разделы уровня два, включая вложенные записи.

    Args:
        text: Markdown документа или формы.

    Returns:
        Разделы с видимым и исходным текстом.
    """
    raw, shown = text.splitlines(keepends=True), visible(text).splitlines(keepends=True)
    boundaries = [i for i, line in enumerate(shown) if re.match(r"^#{1,2}\s+", line)]
    result = []
    for position, start in enumerate(boundaries):
        if not shown[start].startswith("## "):
            continue
        end = boundaries[position + 1] if position + 1 < len(boundaries) else len(raw)
        title = shown[start][3:].strip().rstrip("#").strip()
        result.append(Section(title, start + 1, "".join(shown[start + 1:end]), "".join(raw[start + 1:end])))
    return tuple(result)


def load_project(project: Path) -> Project:
    """Читает Markdown во всём проекте, кроме inbox и внешних ссылок.

    Args:
        project: Корень проекта.

    Returns:
        Единый снимок для find, impact и check.
    """
    documents, records = {}, []
    for path in sorted(project.rglob("*.md")):
        relative = path.relative_to(project)
        if "inbox" in (part.casefold() for part in relative.parts):
            continue
        if not path.resolve().is_relative_to(project.resolve()):
            raise ValueError(f"Файл выходит за пределы проекта: {relative.as_posix()}")
        text = read(path)
        documents[path] = text
        records.extend(parse_records(path, text))
    return Project(tuple(records), documents)
