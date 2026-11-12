"""Search records, trace dependencies, and summarize status."""

from collections import Counter, deque
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import re

from .records import ID_PATTERN, Project, Record, fields, read, references, sections
from .workspace import within


def find(data: Project, words: list[str], letter: str | None = None,
         kind: str | None = None, status: str | None = None) -> tuple[Record, ...]:
    """Filter records by number, type, status, and words.

    Args:
        data: Parsed project snapshot.
        words: Words that must all occur in the record.
        letter: Record type letter.
        kind: Evidence kind filter.
        status: Record status filter.

    Returns:
        Matching records in file and line order.
    """
    query = " ".join(words).strip()
    if not query and not any((letter, kind, status)):
        raise ValueError("Укажите номер, слова или отбор для find")
    exact = query if re.fullmatch(ID_PATTERN, query) else None
    result = []
    for record in data.records:
        if letter and record.id[0] != letter or kind and record.fields.get("вид") != kind:
            continue
        if status and record.fields.get("статус") != status:
            continue
        if exact and record.id != exact:
            continue
        if not exact and any(word.casefold() not in record.visible.casefold() for word in query.split()):
            continue
        result.append(record)
    return tuple(result)


def impact(data: Project, number: str, root: Path) -> tuple[str, ...]:
    """Trace dependent records and sections in breadth-first order.

    Args:
        data: Parsed project snapshot.
        number: Record identifier.
        root: Repository root.

    Returns:
        Dependency report lines for records and document sections.
    """
    ids = {record.id for record in data.records}
    if number not in ids:
        raise ValueError(f"Нет записи: {number}")
    nodes = [(r.id, f"{r.id} {r.path.relative_to(root).as_posix()}:{r.line}", r.refs) for r in data.records]
    for path, text in data.documents.items():
        if path.parent.name == "out":
            for section in sections(text):
                label = f"{path.relative_to(root).as_posix()}:{section.line} ## {section.title}"
                nodes.append((label, label, references(section.text)))
    queue, seen, lines = deque([(number, 0)]), {number}, [f"Зависимости {number}"]
    while queue:
        current, level = queue.popleft()
        for key, label, refs in nodes:
            if current in refs and key not in seen:
                seen.add(key)
                queue.append((key, level + 1))
                lines.append(f"Уровень {level + 1}: {label}")
    return tuple(lines if len(lines) > 1 else [*lines, "Зависимых записей и разделов нет"])


def _overdue(record: Record, today: str) -> str | None:
    letter, values = record.id[0], record.fields
    key = "срок" if letter == "K" else "срок проверки"
    expected = "открыто" if letter == "K" else "действует"
    deadline = values.get(key, "")
    if letter not in "KD" or values.get("статус") != expected:
        return None
    try:
        parsed = date.fromisoformat(deadline)
    except ValueError:
        return f"{record.id}: неверная дата «{key}», запустите check"
    return f"Просрочено {record.id}: {deadline}" if parsed.isoformat() < today else None


@dataclass(frozen=True)
class _Life:
    record: Record
    until: date | None
    sources: tuple[str, ...]


@dataclass(frozen=True)
class _Strength:
    lines: tuple[str, ...]
    expired: tuple[str, ...]


def _date(value: str) -> date | None:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _links(record: Record) -> tuple[str, ...]:
    letter = record.id[0]
    if letter == "O":
        keys = tuple(record.fields)
    elif letter == "E" and record.fields.get("вид") == "оценка":
        keys = ("основание",)
    else:
        keys = {"D": ("основания", "выбран вариант"), "C": ("опора",)}.get(letter, ())
    return references("\n".join(f"- {key}: {record.fields[key]}" for key in keys if key in record.fields))


def _supports(record: Record, index: dict[str, Record]) -> tuple[Record, ...]:
    queue, seen, found = deque(_links(record)), {record.id}, []
    while queue:
        ref = queue.popleft()
        if ref in seen or ref not in index or ref[0] not in "CEO":
            continue
        seen.add(ref)
        target = index[ref]
        found.append(target)
        queue.extend(_links(target))
    return tuple(sorted(found, key=lambda item: (item.id[0], int(item.id[1:]))))


def _source_ids(record: Record) -> tuple[str, ...]:
    return tuple(ref for ref in references(f"- источник: {record.fields.get('источник', '')}") if ref[0] == "S")


def _expiry(record: Record, index: dict[str, Record]) -> date | None:
    if "годен до" in record.fields:
        return _date(record.fields["годен до"])
    days = {"цены": 90, "функции": 180, "аудитория": 365, "структура": 730}.get(record.fields.get("годность", ""))
    if days is None:
        return None
    dates = []
    for ref in _source_ids(record):
        source = index.get(ref)
        if source is None:
            return None
        base = _date(source.fields.get("дата источника", "")) or _date(source.fields.get("дата обращения", ""))
        if base is None:
            return None
        dates.append(base)
    try:
        return min(dates) + timedelta(days=days) if dates else None
    except OverflowError:
        return None


def _stale_records(item: _Life, index: dict[str, Record]) -> tuple[Record, ...]:
    records = (item.record, *(index[ref] for ref in item.sources if ref in index))
    return tuple(record for record in records if record.fields.get("статус") in ("устарело", "отозвано"))


def _expired(item: _Life, today: date, index: dict[str, Record]) -> bool:
    return ((item.until is not None and item.until < today) or
            bool(_stale_records(item, index)))


def _life_label(item: _Life, index: dict[str, Record]) -> str:
    kind = item.record.fields.get("годность") or "годность не указана"
    deadline = item.until.isoformat() if item.until else "дата не определена"
    sources = ", ".join(item.sources) or "не указан"
    stale = ", ".join(f"{record.id} {record.fields['статус']}" for record in _stale_records(item, index))
    return f"{item.record.id}: {kind}, {deadline}, источник {sources}" + (f"; статус: {stale}" if stale else "")


def _bottleneck(record: Record, index: dict[str, Record]) -> str | None:
    evidence = [r for r in _supports(record, index) if r.id[0] == "E" and r.fields.get("вид") in ("факт", "оценка")]
    if len(evidence) == 1:
        return f"Узкое место {record.id}: один факт или оценка ({evidence[0].id})"
    facts = [r for r in evidence if r.fields.get("вид") == "факт"]
    sources = {ref for item in facts for ref in _source_ids(item)}
    if facts and all(_source_ids(item) for item in facts) and len(sources) == 1:
        return f"Узкое место {record.id}: все факты из {next(iter(sources))}"
    return None


def _forecasts(support: tuple[Record, ...], review: date | None) -> tuple[str, ...]:
    lines = []
    for record in support:
        if record.id[0] != "E" or record.fields.get("вид") != "прогноз":
            continue
        value = record.fields.get("срок прогноза", "")
        match = re.search(r"(?<![\w-])[0-9]{4}-[0-9]{2}-[0-9]{2}(?![\w-])", value)
        deadline = _date(match[0]) if match else None
        if deadline is None:
            lines.append(f"Срок прогноза не определён {record.id}: {value or 'не указан'}")
        elif review is not None and deadline < review:
            lines.append(f"Прогноз до проверки {record.id}: {deadline.isoformat()}")
    return tuple(lines)


def _freshness_notes(lives: tuple[_Life, ...]) -> tuple[str, ...]:
    missing = [item.record.id for item in lives if not item.record.fields.get("годность")]
    manual = [item.record.id for item in lives if item.record.fields.get("годность") == "нормы"
              and "годен до" not in item.record.fields]
    unknown = [item.record.id for item in lives if item.until is None and item.record.id not in manual
               and (item.record.fields.get("годность") or "годен до" in item.record.fields)]
    lines = [f"Без класса годности: {len(missing)} ({', '.join(missing[:10]) or 'нет'})"]
    if missing:
        lines.append("Без класса: годность не указана; срок известен только при наличии «годен до»")
    if manual:
        lines.append(f"Нормы, проверить вручную: {', '.join(manual)}")
    if unknown:
        lines.append(f"Срок годности не определён: {', '.join(unknown)}; запустите check и проверьте даты источников")
    return tuple(lines)


def _decision_strength(decision: Record, index: dict[str, Record], today: date) -> _Strength:
    support = _supports(decision, index)
    lives = tuple(_Life(r, _expiry(r, index), _source_ids(r)) for r in support if r.id[0] == "E")
    expired = tuple(item for item in lives if _expired(item, today, index))
    review = _date(decision.fields.get("срок проверки", ""))
    expiring = tuple(item for item in lives if item not in expired and item.until is not None
                     and review is not None and today <= item.until < review)
    narrow = tuple(line for r in support if r.id[0] == "C" if (line := _bottleneck(r, index)))
    counts = Counter(item.record.fields.get("вид") for item in lives)
    lines = [f"Решение {decision.id}, проверка: {decision.fields.get('срок проверки') or 'не указана'}",
             f"Опоры: фактов {counts['факт']}, оценок {counts['оценка']}, гипотез {counts['гипотеза']}, прогнозов {counts['прогноз']}",
             f"Устарели на {today.isoformat()}: {len(expired)}"]
    lines.extend(f"Устарело {_life_label(item, index)}" for item in expired)
    lines.append(f"Устареют до проверки: {len(expiring)}")
    lines.extend(f"Истекает {_life_label(item, index)}" for item in expiring)
    lines.extend(_freshness_notes(lives))
    lines.append(f"Узкие места: {len(narrow)}")
    lines.extend(narrow)
    if review is None:
        lines.append("Неверный срок проверки решения: запустите check")
    forecasts = _forecasts(support, review)
    lines.extend(forecasts or ("Прогнозов до проверки нет",))
    lines.append(f"Прочность {decision.id}: устарело {len(expired)}, истекает до проверки {len(expiring)}, узких мест {len(narrow)}")
    return _Strength(tuple(lines), tuple(item.record.id for item in expired))


def _strengths(data: Project, today: date, number: str | None = None) -> tuple[_Strength, ...]:
    index = {record.id: record for record in data.records}
    if number is not None:
        if not re.fullmatch(r"D[1-9][0-9]*", number):
            raise ValueError(f"Неверный номер решения: {number!r}; нужен D<номер>")
        if number not in index:
            raise ValueError(f"Нет решения: {number}")
        decisions = (index[number],)
    else:
        decisions = tuple(r for r in data.records if r.id[0] == "D" and r.fields.get("статус") == "действует")
    return tuple(_decision_strength(r, index, today) for r in sorted(decisions, key=lambda r: int(r.id[1:])))


def fragile(data: Project, number: str | None = None, today: str | None = None,
            strict: bool = False) -> tuple[tuple[str, ...], int]:
    """Report decision support freshness without changing files.

    Args:
        data: Parsed project snapshot.
        number: Optional decision identifier, including historical decisions.
        today: Reference date in YYYY-MM-DD format; defaults to the local date.
        strict: Return code 1 when any support has expired.

    Returns:
        Russian report lines and the command exit code.
    """
    reference = date.today() if today is None else _date(today)
    if reference is None:
        raise ValueError("Неверная дата --today: нужна дата ГГГГ-ММ-ДД")
    reports = _strengths(data, reference, number)
    lines = tuple(line for report in reports for line in report.lines)
    return lines or ("Действующих решений нет",), int(strict and any(report.expired for report in reports))


def status(project: Path, task: Path, data: Project) -> tuple[str, ...]:
    """Summarize state, open questions, and overdue commitments.

    Args:
        project: Project directory or selected project name.
        task: Task directory or selected task name.
        data: Parsed project snapshot.

    Returns:
        Status report lines.
    """
    state = fields(read(within(task, task / "STATE.md")))[0]
    lines = [f"Проект: {project.name}", f"Задача: {task.name}"]
    for key in ("этап", "статус", "следующий шаг", "ждём от человека"):
        lines.append(f"{key}: {state.get(key) or 'не указано'}")
    counts = Counter((r.id[0], r.fields.get("вид", ""), r.fields.get("статус", "без статуса")) for r in data.records)
    for (letter, kind, record_status), count in sorted(counts.items()):
        lines.append(f"Записи {letter}{' ' + kind if kind else ''}, {record_status}: {count}")
    for record in data.records:
        if record.id.startswith("Q") and record.fields.get("статус") == "открыт":
            lines.append(f"Открыт {record.id}: {record.fields.get('вопрос', '')}")
        message = _overdue(record, date.today().isoformat())
        if message:
            lines.append(message)
    expired = {ref for report in _strengths(data, date.today()) for ref in report.expired}
    lines.append(f"Устаревших опор: {len(expired)}, подробнее: fragile")
    return tuple(lines)


def inventory(root: Path) -> tuple[str, ...]:
    """List projects and tasks when no active task is selected.

    Args:
        root: Repository root.

    Returns:
        Project and task list lines.
    """
    lines = ["Активной задачи нет"]
    parent = within(root, root / "projects")
    for project in sorted(parent.iterdir()) if parent.exists() else ():
        within(root, project)
        if project.is_dir():
            tasks = within(root, project / "tasks")
            names = [p.name for p in sorted(tasks.iterdir()) if within(root, p).is_dir()] if tasks.exists() else []
            lines.append(f"Проект {project.name}: {', '.join(names) or 'задач нет'}")
    return tuple(lines)
