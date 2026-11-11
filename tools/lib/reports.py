"""Search records, trace dependencies, and summarize status."""

from collections import Counter, deque
from datetime import date
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
