"""Parse arguments and implement the shared command contract."""

import argparse
from collections import Counter
from pathlib import Path
import sys

from .checks import Issue, active_issues, check
from .journal import LogEntry, append, cost, number
from .records import SCHEMAS, load_project
from .reports import find, impact, inventory, status
from .workspace import active_names, create_project, create_task, select


class Parser(argparse.ArgumentParser):
    """Argument parser that raises concise errors without exiting."""

    def error(self, message: str) -> None:
        """Report invalid command arguments.

        Args:
            message: Argument parser diagnostic.
        """
        translations = (("the following arguments are required:", "не указаны обязательные параметры:"),
                        ("unrecognized arguments:", "неизвестные параметры:"),
                        ("invalid choice:", "недопустимое значение:"), ("choose from", "допустимые значения"),
                        ("expected one argument", "ожидается одно значение"),
                        ("invalid int value:", "ожидается целое число:"), ("argument ", "параметр "))
        for source, target in translations:
            message = message.replace(source, target)
        raise ValueError(f"Неверные параметры: {message}")

    def format_help(self) -> str:
        """Render help with Russian labels.

        Returns:
            Help text with Russian labels.
        """
        text = super().format_help()
        for source, target in (("usage:", "Использование:"), ("positional arguments:", "Позиционные параметры:"),
                               ("options:", "Параметры:"), ("show this help message and exit", "показать справку")):
            text = text.replace(source, target)
        return text


def _common() -> Parser:
    parser = Parser(add_help=False, allow_abbrev=False)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2], help="корень репозитория")
    parser.add_argument("--project", help="имя проекта")
    parser.add_argument("--task", help="имя задачи")
    return parser


def _log_parser(commands: argparse._SubParsersAction) -> None:
    parser = commands.add_parser("log", help="дописать шаг в журнал")
    parser.add_argument("action", help="действие")
    parser.add_argument("--stage", type=int, choices=range(1, 8), required=True, help="этап от 1 до 7")
    parser.add_argument("--tool", required=True, choices=("скрипт", "чтение", "быстрая модель", "сильная модель", "субагент", "классификатор"))
    parser.add_argument("--result", required=True, help="итог шага")
    for key in ("minutes", "tokens", "cost"):
        parser.add_argument(f"--{key}", type=number, help="неотрицательное число")
    parser.add_argument("--approx", action="store_true", help="числа являются оценкой")
    parser.add_argument("--key", default="", help="ключ защиты от повторения")
    parser.add_argument("--status", default="готово", choices=("готово", "сбой"))


def _parser(common: Parser) -> Parser:
    parser = Parser(description="Стратег: локальные действия и проверки", parents=[common], allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    new = commands.add_parser("new", help="создать проект или задачу").add_subparsers(dest="kind", required=True, parser_class=Parser)
    new.add_parser("project", help="создать проект").add_argument("project_name")
    task = new.add_parser("task", help="создать задачу")
    task.add_argument("project_name")
    task.add_argument("task_name")
    commands.add_parser("status", help="показать состояние")
    commands.add_parser("next", help="следующий номер").add_argument("letter", choices=tuple(s.letter for s in SCHEMAS))
    finder = commands.add_parser("find", help="найти записи")
    finder.add_argument("words", nargs="*")
    finder.add_argument("--type", dest="letter", choices=tuple(s.letter for s in SCHEMAS))
    finder.add_argument("--kind", help="вид сведения")
    finder.add_argument("--status", help="статус записи")
    commands.add_parser("impact", help="показать зависимости").add_argument("number")
    commands.add_parser("check", help="проверить ворота").add_argument("--final", action="store_true")
    _log_parser(commands)
    commands.add_parser("cost", help="подсчитать расходы").add_argument("--price", type=number)
    return parser


def _new(root: Path, args: argparse.Namespace) -> tuple[tuple[str, ...], int]:
    if args.kind == "project":
        path = create_project(root, args.project_name)
        return (f"Создан проект: {path.relative_to(root).as_posix()}",), 0
    path = create_task(root, args.project_name, args.task_name)
    return (f"Создана задача: {path.relative_to(root).as_posix()}",
            f"Активная задача: {args.project_name}/{args.task_name}"), 0


def _check_output(root: Path, issues: tuple[Issue, ...]) -> tuple[tuple[str, ...], int]:
    lines = []
    for issue in issues:
        location = issue.path.relative_to(root).as_posix()
        subject = f" {issue.subject}" if issue.subject else ""
        lines.append(f"{issue.code} {location}{subject}: {issue.message}")
    counts = Counter(issue.code for issue in issues)
    lines.append("Итог: " + "; ".join(f"V{n:02}={counts[f'V{n:02}']}" for n in range(1, 13)))
    lines.append(f"Нарушений: {len(issues)}")
    return tuple(lines), 1 if issues else 0


def _records(root: Path, project: Path, args: argparse.Namespace) -> tuple[tuple[str, ...], int]:
    data = load_project(project)
    if args.command == "next":
        maximum = max((int(r.id[1:]) for r in data.records if r.id[0] == args.letter), default=0)
        return (f"{args.letter}{maximum + 1}",), 0
    if args.command == "impact":
        return impact(data, args.number, root), 0
    selected = find(data, args.words, args.letter, args.kind, args.status)
    lines = []
    for record in selected:
        text = "\n".join(record.text.rstrip().splitlines())
        lines.extend((f"{record.path.relative_to(root).as_posix()}:{record.line}", text))
    return tuple(lines) if lines else ("Записи не найдены",), 0


def _task_command(root: Path, project: Path, task: Path, args: argparse.Namespace) -> tuple[tuple[str, ...], int]:
    if args.command == "check":
        return _check_output(root, check(root, project, task, args.final))
    if args.command == "status":
        return status(project, task, load_project(project)), 0
    if args.command == "cost":
        return cost(task, args.price), 0
    entry = LogEntry(args.action, args.stage, args.tool, args.result, args.minutes,
                     args.tokens, args.cost, args.approx, args.key, args.status)
    line, already = append(task, entry)
    return (("уже сделано", line) if already else ("Добавлена строка журнала", line)), 0


def _dispatch(args: argparse.Namespace) -> tuple[tuple[str, ...], int]:
    root = args.root.resolve()
    if not root.is_dir():
        raise ValueError(f"Нет корня репозитория: {root}")
    if args.command == "new":
        return _new(root, args)
    if args.command == "check" and args.project is None and args.task is None:
        pointer_issues = active_issues(root)
        if pointer_issues:
            return _check_output(root, pointer_issues)
    if args.command == "status" and args.project is None and args.task is None:
        if not all(active_names(root)):
            return inventory(root), 0
    project, task = select(root, args.project, args.task, required=args.command != "check")
    if args.command in ("next", "find", "impact"):
        return _records(root, project, args)
    if task is None:
        if args.command == "status":
            return inventory(root), 0
        raise ValueError("Нет активной задачи. Укажите --task.")
    return _task_command(root, project, task, args)


def main(argv: list[str] | None = None) -> int:
    """Run one command with exit code 0, 1, or 2.

    Args:
        argv: Arguments without the script name; defaults to sys.argv.

    Returns:
        Exit code according to the command contract.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        common = _common()
        global_args, remaining = common.parse_known_args(argv)
        args = _parser(common).parse_args(remaining, namespace=global_args)
        lines, code = _dispatch(args)
        for line in lines:
            print(line)
        return code
    except (ValueError, OSError, UnicodeError) as error:
        print(f"Ошибка запуска: {error}", file=sys.stderr)
        return 2
