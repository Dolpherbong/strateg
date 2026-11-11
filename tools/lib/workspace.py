"""Создание задач и безопасный выбор путей."""

from datetime import date
from pathlib import Path
import re

from .records import fields, read


def name(value: str, task: bool = False) -> str:
    """Проверяет переносимое имя каталога.

    Args:
        value: Имя проекта или задачи.
        task: Требовать префикс NN-.

    Returns:
        Проверенное имя.
    """
    pattern = r"[0-9]{2}-[a-z0-9]+(?:-[a-z0-9]+)*" if task else r"[a-z0-9]+(?:-[a-z0-9]+)*"
    reserved = ("con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10)))
    if not re.fullmatch(pattern, value) or value in reserved:
        raise ValueError(f"Неверное имя {'задачи' if task else 'проекта'}: {value!r}")
    return value


def within(root: Path, path: Path) -> Path:
    """Проверяет, что путь после раскрытия ссылок остаётся внутри корня.

    Args:
        root: Разрешённый корень.
        path: Проверяемый путь.

    Returns:
        Исходный проверенный путь.
    """
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Путь выходит за пределы корня: {path.name}")
    return path


def _plan(root: Path, kind: str, values: dict[str, str]) -> tuple[list[Path], list[tuple[Path, str]]]:
    template = within(root, root / "templates" / kind)
    if not template.is_dir():
        raise ValueError(f"Нет папки форм: templates/{kind}")
    directories, files = [], []
    for source in sorted(template.rglob("*")):
        within(root, source)
        relative = source.relative_to(template)
        if source.is_dir():
            directories.append(relative)
        else:
            text = read(source)
            for key, value in values.items():
                text = text.replace("{{" + key + "}}", value)
            files.append((relative, text))
    if not files:
        raise ValueError(f"Пустая папка форм: templates/{kind}")
    return directories, files


def _create(target: Path, plan: tuple[list[Path], list[tuple[Path, str]]]) -> None:
    directories, files = plan
    target.mkdir(parents=True, exist_ok=False)
    for directory in directories:
        (target / directory).mkdir(parents=True, exist_ok=True)
    for relative, text in files:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8", newline="") as stream:
            stream.write(text)


def create_project(root: Path, project: str) -> Path:
    """Создаёт новый проект из форм без изменения ACTIVE.md.

    Args:
        root: Корень репозитория.
        project: Имя проекта.

    Returns:
        Путь созданного проекта.
    """
    target = within(root, root / "projects" / name(project))
    if target.exists():
        raise ValueError(f"Проект уже есть: {project}")
    plan = _plan(root, "project", {"project": project, "date": date.today().isoformat()})
    _create(target, plan)
    return target


def _active_text(path: Path, project: str, task: str) -> str:
    text = read(path) if path.exists() else "# Активная задача\n\n"
    newline = "\r\n" if "\r\n" in text else "\n"
    for key, value in (("проект", project), ("задача", task), ("обновлено", date.today().isoformat())):
        pattern = rf"(?m)^- {key}:[^\r\n]*"
        line = f"- {key}: {value}"
        if re.search(pattern, text):
            text = re.sub(pattern, lambda match: line, text)
        else:
            text += ("" if text.endswith(("\n", "\r")) else newline) + line + newline
    return text


def create_task(root: Path, project: str, task: str) -> Path:
    """Создаёт задачу из форм и делает её активной.

    Args:
        root: Корень репозитория.
        project: Имя существующего проекта.
        task: Имя новой задачи NN-имя.

    Returns:
        Путь созданной задачи.
    """
    parent = within(root, root / "projects" / name(project))
    if not parent.is_dir():
        raise ValueError(f"Нет проекта: {project}")
    target = within(root, parent / "tasks" / name(task, task=True))
    if target.exists():
        raise ValueError(f"Задача уже есть: {task}")
    active = within(root, root / "projects/ACTIVE.md")
    active_text = _active_text(active, project, task)
    plan = _plan(root, "task", {"project": project, "task": task, "date": date.today().isoformat()})
    _create(target, plan)
    for directory in ("work", "out"):
        (target / directory).mkdir(exist_ok=True)
    with active.open("w", encoding="utf-8", newline="") as stream:
        stream.write(active_text)
    return target


def active_names(root: Path) -> tuple[str | None, str | None]:
    """Читает указатель активной задачи.

    Args:
        root: Корень репозитория.

    Returns:
        Имена проекта и задачи или None.
    """
    path = within(root, root / "projects/ACTIVE.md")
    values = fields(read(path))[0] if path.exists() else {}
    project, task = values.get("проект"), values.get("задача")
    return (None if project in (None, "", "нет") else project,
            None if task in (None, "", "нет") else task)


def select(root: Path, project: str | None, task: str | None, required: bool = True) -> tuple[Path, Path | None]:
    """Выбирает проект и задачу из параметров или ACTIVE.md.

    Args:
        root: Корень репозитория.
        project: Явное имя проекта.
        task: Явное имя задачи.
        required: Проверять наличие каталога задачи.

    Returns:
        Пути проекта и выбранной задачи.
    """
    active_project, active_task = active_names(root)
    selected_project = project if project is not None else active_project
    if selected_project is None:
        raise ValueError("Нет активного проекта. Укажите --project.")
    parent = within(root, root / "projects" / name(selected_project))
    if not parent.is_dir() and required:
        raise ValueError(f"Нет проекта: {selected_project}")
    selected_task = task if task is not None else active_task if selected_project == active_project else None
    target = within(root, parent / "tasks" / name(selected_task, task=True)) if selected_task is not None else None
    if required and target is not None and not target.is_dir():
        raise ValueError(f"Нет задачи: {selected_task}")
    return parent, target
