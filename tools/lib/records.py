"""Parse registries, references, and Markdown sections."""

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Schema:
    """Required fields and choices for one record type."""

    letter: str
    required: str
    choices: tuple[tuple[str, str], ...] = ()
    optional: str = ""


# Keep this table in sync with agent/records.md.
SCHEMAS = (
    Schema("S", "название|тип|где|дата источника|дата обращения|надёжность|статус", (
        ("тип", "документ|таблица|сайт|интервью|изображение|аудио|видео|продукт|модель"),
        ("надёжность", "A|B|C"), ("статус", "действует|устарело|отозвано"))),
    Schema("E", "текст|вид|период|статус|задача", (
        ("вид", "факт|оценка|гипотеза|прогноз|синтетика"),
        ("статус", "действует|устарело|отозвано"),
        ("годность", "цены|функции|аудитория|нормы|структура")), optional="годность|годен до"),
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
    """A parsed record with its source text and file location."""

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
    """A document section including nested headings."""

    title: str
    line: int
    text: str
    raw: str


@dataclass(frozen=True)
class Project:
    """A parsed snapshot of project files."""

    records: tuple[Record, ...]
    documents: dict[Path, str]


def read(path: Path) -> str:
    """Read UTF-8 text while preserving line endings.

    Args:
        path: File path.

    Returns:
        Original text, including CRLF when present.
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
    """Mask comments and fenced code without shifting lines.

    Args:
        text: Source Markdown text.

    Returns:
        Text of the same length with hidden content replaced by spaces.
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
    """Parse single-line fields at the first colon.

    Args:
        text: Source Markdown text.

    Returns:
        Field values and duplicate field names.
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
    """Read references from link fields and square brackets.

    Args:
        text: Source Markdown text.

    Returns:
        Unique identifiers in first-appearance order.
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
    """Parse records up to the next heading of any level.

    Args:
        path: File path.
        text: Source Markdown text.

    Returns:
        Parsed records with line numbers.
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
    """Extract level-two sections including nested records.

    Args:
        text: Source Markdown text.

    Returns:
        Sections with visible and original text.
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
    """Read project Markdown, excluding inbox and rejecting external links.

    Args:
        project: Project directory or selected project name.

    Returns:
        A shared snapshot for find, impact, and check.
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
