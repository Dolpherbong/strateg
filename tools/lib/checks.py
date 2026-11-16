"""Validate gates V01-V12 without semantic evaluation or file changes."""

from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re

from .records import ID_PATTERN, LINK_FIELDS, SCHEMAS, Project, Record, fields, load_project, read, references, sections, visible
from .workspace import active_names, name, within


@dataclass(frozen=True)
class Issue:
    """One gate validation issue."""

    code: str
    path: Path
    subject: str
    message: str


def _issue(code: str, record: Record, message: str) -> Issue:
    return Issue(code, record.path, record.id, message)


def _correct_place(project: Path, record: Record) -> bool:
    parts = record.path.relative_to(project).parts
    expected = {"S": "sources.md", "E": "evidence.md", "D": "decisions.md", "K": "decisions.md"}
    letter = record.id[0]
    if letter in expected:
        return parts == (expected[letter],)
    suffix = ("questions.md",) if letter == "Q" else ("out", "options.md" if letter == "O" else "situation.md")
    return len(parts) == len(suffix) + 2 and parts[0] == "tasks" and parts[2:] == suffix


def _registry_order(data: Project) -> list[Issue]:
    issues = []
    for path, text in data.documents.items():
        if path.name not in ("sources.md", "evidence.md", "decisions.md", "questions.md"):
            continue
        shown = visible(text).splitlines()
        introduction = max((i for i, line in enumerate(shown, 1) if line.strip()
                            and not re.match(rf"^###\s+{ID_PATTERN}(?:\s|$)", line)
                            and not re.match(r"^\s*-\s+[^:]+:", line)), default=0)
        previous: dict[str, int] = {}
        for record in (item for item in data.records if item.path == path):
            letter, number = record.id[0], int(record.id[1:])
            if number <= previous.get(letter, 0) or record.line < introduction:
                issues.append(_issue("V01", record, "запись не по порядку"))
            previous[letter] = max(previous.get(letter, 0), number)
    return issues


def _numbers(project: Path, data: Project) -> list[Issue]:
    issues, seen = _registry_order(data), set()
    ids = {record.id for record in data.records}
    for record in data.records:
        if record.id in seen:
            issues.append(_issue("V01", record, "повтор номера"))
        seen.add(record.id)
        if not _correct_place(project, record):
            issues.append(_issue("V01", record, "неверный файл для этого вида записи"))
    for path, text in data.documents.items():
        for ref in references(text):
            if ref not in ids:
                issues.append(Issue("V01", path, ref, "ссылка на запись, которой нет"))
        for line, text_line in enumerate(visible(text).splitlines(), 1):
            if re.match(r"^###\s+[SEQOCDK]\S*(?:\s|$)", text_line) and not re.match(rf"^###\s+{ID_PATTERN}(?:\s|$)", text_line):
                issues.append(Issue("V01", path, f"строка {line}", "битый номер записи"))
    return issues


def _valid_date(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _conditional_fields(record: Record) -> tuple[str, ...]:
    values, letter = record.fields, record.id[0]
    required = []
    if letter == "E" and values.get("статус") == "устарело":
        required.append("заменено")
    if letter == "E" and values.get("статус") == "отозвано":
        required.append("причина")
    if letter == "D" and values.get("статус") == "пересмотрено":
        required.append("заменено")
    if letter == "Q" and values.get("статус") == "закрыт":
        required.extend(("ответ", "уверенность"))
    if letter == "Q" and values.get("статус") == "пробел":
        required.append("чем грозит")
    return tuple(required)


def _field_checks(record: Record) -> list[Issue]:
    schema = next(item for item in SCHEMAS if item.letter == record.id[0])
    values, issues = record.fields, []
    for key in (*schema.required.split("|"), *_conditional_fields(record)):
        if not values.get(key):
            issues.append(_issue("V02", record, f"нет обязательного поля «{key}»"))
    for key, choices in schema.choices:
        if values.get(key) and values[key] not in choices.split("|"):
            issues.append(_issue("V02", record, f"недопустимое значение «{key}»: {values[key]}"))
    for key in ("дата", "дата обращения", "срок", "срок проверки", "годен до"):
        if key in values and not _valid_date(values[key]):
            issues.append(_issue("V02", record, f"неверная дата в поле «{key}»"))
    for key in record.duplicate_fields:
        issues.append(_issue("V02", record, f"повтор поля «{key}»"))
    issues.extend(_link_checks(record))
    return issues


def _link_checks(record: Record) -> list[Issue]:
    issues = []
    for key in LINK_FIELDS:
        value = record.fields.get(key, "")
        own = key == "источник" and record.fields.get("вид") == "прогноз" and value == "свой"
        if value and not own and not re.fullmatch(rf"{ID_PATTERN}(?:\s*,\s*{ID_PATTERN})*", value):
            issues.append(_issue("V02", record, f"в поле «{key}» нужны номера через запятую без скобок"))
    return issues


def _evidence(record: Record) -> list[Issue]:
    values, issues = record.fields, []
    kind = values.get("вид")
    required = {"факт": ("источник", "место", "цитата"), "оценка": ("основание", "расчёт"),
                "гипотеза": ("как проверить",), "прогноз": ("источник", "срок прогноза")}
    code = "V03" if kind == "факт" else "V04"
    for key in required.get(kind, ()):
        if not values.get(key):
            issues.append(_issue(code, record, f"нет поля «{key}»"))
    quote = values.get("цитата", "")
    quoted = len(quote) >= 3 and (quote[0], quote[-1]) in (("«", "»"), ('"', '"')) and bool(quote[1:-1].strip())
    if kind == "факт" and quote and not quoted:
        issues.append(_issue("V03", record, "цитата без кавычек"))
    if kind == "факт" and len((quote[1:-1] if quoted else quote).split()) > 25:
        issues.append(_issue("V03", record, "цитата длиннее 25 слов"))
    for key in ("источник", "основание"):
        if any(ref.startswith("C") for ref in references(f"- {key}: {values.get(key, '')}")):
            issues.append(_issue("V05", record, f"сведение опирается на вывод в поле «{key}»"))
    return issues


def _support(record: Record, index: dict[str, Record], key: str) -> tuple[Record, ...]:
    queue, seen, found = list(references(f"- {key}: {record.fields.get(key, '')}")), {record.id}, []
    while queue:
        ref = queue.pop(0)
        if ref in seen or ref not in index:
            continue
        seen.add(ref)
        target = index[ref]
        found.append(target)
        if ref.startswith("C"):
            queue.extend(references(f"- опора: {target.fields.get('опора', '')}"))
    return tuple(found)


def _synthetic(record: Record, index: dict[str, Record]) -> list[Issue]:
    issues, values = [], record.fields
    if record.id.startswith("E"):
        sources = _support(record, index, "источник")
        if values.get("вид") == "синтетика" and (not sources or any(s.id[0] != "S" or s.fields.get("тип") != "модель" for s in sources)):
            issues.append(_issue("V06", record, "у синтетики нужен источник типа «модель»"))
        if values.get("вид") == "факт" and any(s.fields.get("тип") == "модель" for s in sources):
            issues.append(_issue("V06", record, "у факта источник типа «модель»"))
    if record.id[0] in "CD":
        key = "опора" if record.id[0] == "C" else "основания"
        if any(item.fields.get("вид") == "синтетика" for item in _support(record, index, key)):
            issues.append(_issue("V06", record, f"синтетика в поле «{key}»"))
    return issues


def _conclusion(record: Record, index: dict[str, Record]) -> list[Issue]:
    issues, support = [], _support(record, index, "опора")
    if not references(f"- опора: {record.fields.get('опора', '')}"):
        issues.append(_issue("V08", record, "нет опоры"))
    if record.fields.get("уверенность") in ("высокая", "средняя"):
        if not any(r.id.startswith("E") and r.fields.get("вид") in ("факт", "оценка") for r in support):
            issues.append(_issue("V08", record, "высокая или средняя уверенность без факта или оценки в опоре"))
    return issues


def _out(path: Path, project: Path) -> bool:
    parts = path.relative_to(project).parts
    return len(parts) == 4 and parts[0] == "tasks" and parts[2] == "out"


def _final_names(root: Path) -> set[str]:
    """Names of the final documents: one per form in templates/out."""
    return {path.name for path in (root / "templates/out").glob("*.md")}


def _outdated(root: Path, project: Path, data: Project, index: dict[str, Record]) -> list[Issue]:
    """Flag active records and final documents that cite outdated or withdrawn records.

    Answered questions and dated reports in out/ (revisions, checks) are history and are skipped.
    """
    issues = []
    old = {key for key, item in index.items() if item.fields.get("статус") in ("устарело", "отозвано")}
    inactive = ("устарело", "отозвано", "пересмотрено", "отменено", "снят", "снято", "выполнено", "сорвано", "закрыт")
    for record in data.records:
        if record.fields.get("статус") not in inactive:
            for ref in record.refs:
                if ref in old:
                    issues.append(_issue("V07", record, f"ссылка на устаревшую или отозванную запись {ref}"))
    finals = _final_names(root)
    for path, text in data.documents.items():
        if _out(path, project) and path.name in finals:
            for ref in references(_outside_records(path, text, data.records)):
                if ref in old:
                    issues.append(Issue("V07", path, ref, "итоговый документ ссылается на устаревшую или отозванную запись"))
    return issues


def _listed_commitments(text: str) -> set[str]:
    """Read commitment numbers, including ranges such as K1–K6, from free text."""
    found = set()
    for first, last in re.findall(r"(?<![\w])K(\d+)\s*[–—-]\s*K?(\d+)(?![\w])", text):
        found.update(f"K{number}" for number in range(int(first), int(last) + 1))
    found.update(re.findall(r"(?<![\w])K\d+(?![\w])", text))
    return found


def _successor(decision: Record, index: dict[str, Record]) -> Record | None:
    """Follow «заменено» links from a revised decision to the active one, if any."""
    seen, current = set(), decision
    while current.fields.get("статус") == "пересмотрено" and current.id not in seen:
        seen.add(current.id)
        nxt = next(iter(references(f"- заменено: {current.fields.get('заменено', '')}")), None)
        if nxt is None or nxt not in index:
            return None
        current = index[nxt]
    return current if current.fields.get("статус") == "действует" else None


def _revised_commitments(data: Project, index: dict[str, Record]) -> list[Issue]:
    """Flag open commitments left on a revised decision and not carried to its successor."""
    issues = []
    for record in data.records:
        if not record.id.startswith("K") or record.fields.get("статус") != "открыто":
            continue
        for ref in references(f"- к решению: {record.fields.get('к решению', '')}"):
            decision = index.get(ref)
            if decision is None or decision.fields.get("статус") != "пересмотрено":
                continue
            successor = _successor(decision, index)
            if successor is None or record.id not in _listed_commitments(successor.fields.get("обязательства", "")):
                issues.append(_issue("V07", record, f"открытое обязательство осталось у пересмотренного решения {ref}: "
                                                    "перечисли его в поле «обязательства» решения, которое его заменило, "
                                                    "или сними"))
    return issues


def _outside_records(path: Path, text: str, records: tuple[Record, ...]) -> str:
    lines = text.splitlines(keepends=True)
    for record in records:
        if record.path == path:
            start = record.line - 1
            end = start + len(record.text.splitlines())
            lines[start:end] = ["\n"] * (end - start)
    return "".join(lines)


def _options(task: Path, data: Project, final: bool) -> list[Issue]:
    path = task / "out/options.md"
    options = [r for r in data.records if r.path == path and r.id.startswith("O")]
    if not options and not final:
        return []
    issues, counts = [], Counter(r.fields.get("роль") for r in options)
    if len(options) < 3:
        issues.append(Issue("V09", path, "", "вариантов меньше трёх"))
    for role in ("статус-кво", "закрыть"):
        if counts[role] != 1:
            issues.append(Issue("V09", path, "", f"нужен ровно один вариант роли «{role}»"))
    if not counts["активный"]:
        issues.append(Issue("V09", path, "", "нет активного варианта"))
    for record in options:
        for key in ("возражение", "что должно быть правдой"):
            if not record.fields.get(key):
                issues.append(_issue("V09", record, f"пустое поле «{key}»"))
    return issues


def _section_checks(path: Path, template: str, document: str) -> list[Issue]:
    issues = []
    actual = sections(document)
    by_title = {section.title: section for section in actual}
    expected = {section.title: section for section in sections(template)}
    for title in expected:
        if title not in by_title:
            issues.append(Issue("V10", path, title, "нет раздела из формы"))
    for section in actual:
        content = re.sub(r"(?m)^#{1,6}\s+.*$", "", section.text).strip()
        if not content:
            issues.append(Issue("V10", path, section.title, "раздел пуст"))
        exempt = section.title in expected and "<!-- без опоры -->" in expected[section.title].raw
        if not exempt and not references(section.text) and not re.search(r"\b(?:(?:гипотез|допущени)\w*|не\s+знаем)\b", section.text, re.I):
            issues.append(Issue("V11", path, section.title, "нет ссылки или пометки об отсутствии опоры"))
    return issues


def _documents(root: Path, task: Path, data: Project) -> list[Issue]:
    directory = within(root, root / "templates/out")
    templates = sorted(directory.glob("*.md"))
    if not templates:
        raise ValueError("Нет форм итоговых документов: templates/out")
    issues, checked = [], set()
    for template in templates:
        within(root, template)
        path = task / "out" / template.name
        checked.add(path)
        if path not in data.documents:
            issues.append(Issue("V10", path, "", "нет документа из формы"))
        else:
            issues.extend(_section_checks(path, read(template), data.documents[path]))
    for path in sorted((task / "out").glob("*.md")):
        if path not in checked:
            issues.extend(_section_checks(path, "", data.documents[path]))
    return issues


def _state(root: Path, task: Path) -> list[Issue]:
    issues = []
    for filename in ("STATE.md", "journal.md"):
        if not within(root, task / filename).is_file():
            issues.append(Issue("V12", task / filename, "", "нет файла"))
    state = task / "STATE.md"
    if state.is_file():
        values = fields(read(state))[0]
        for key in ("этап", "статус", "следующий шаг"):
            if not values.get(key):
                issues.append(Issue("V12", state, "", f"пустое поле «{key}»"))
    issues.extend(active_issues(root))
    return issues


def active_issues(root: Path) -> tuple[Issue, ...]:
    """Validate the ACTIVE.md pointer, including invalid names.

    Args:
        root: Repository root.

    Returns:
        V12 issues, or an empty tuple.
    """
    try:
        project_name, task_name = active_names(root)
        if not task_name:
            return ()
        if not project_name:
            raise ValueError("у задачи не указан проект")
        target = root / "projects" / name(project_name) / "tasks" / name(task_name, task=True)
        if within(root, target).is_dir():
            return ()
        message = "указана задача, которой нет"
    except ValueError as error:
        message = f"неверный указатель: {error}"
    return (Issue("V12", root / "projects/ACTIVE.md", "", message),)


def check(root: Path, project: Path, task: Path, final: bool = False) -> tuple[Issue, ...]:
    """Validate the project and selected task.

    Args:
        root: Repository root.
        project: Project directory.
        task: Selected task directory; it may not exist yet.
        final: Whether to run final document checks.

    Returns:
        V01-V12 issues in stable order.
    """
    data = load_project(project)
    index = {record.id: record for record in data.records}
    issues = _numbers(project, data)
    for record in data.records:
        issues.extend(_field_checks(record))
        issues.extend(_synthetic(record, index))
        if record.id.startswith("E"):
            issues.extend(_evidence(record))
        if record.id.startswith("C"):
            issues.extend(_conclusion(record, index))
    issues.extend(_outdated(root, project, data, index))
    issues.extend(_revised_commitments(data, index))
    issues.extend(_options(task, data, final))
    issues.extend(_state(root, task))
    if final:
        issues.extend(_documents(root, task, data))
    return tuple(sorted(issues, key=lambda issue: (issue.code, str(issue.path), issue.subject, issue.message)))
