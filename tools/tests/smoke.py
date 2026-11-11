"""Повторяемый прогон всех команд в PowerShell или Git Bash на копии."""

import argparse
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

from .fixtures import broken, populate, prepare, write


def _quote_ps(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _shell(shell: str, arguments: list[str]) -> list[str]:
    if shell == "powershell":
        executable = shutil.which("powershell")
        if executable is None:
            raise ValueError("PowerShell не найден")
        command = "& " + " ".join(_quote_ps(value) for value in arguments)
        script = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); " + command + "; exit $LASTEXITCODE"
        return [executable, "-NoProfile", "-NonInteractive", "-Command", script]
    executable = shutil.which("bash")
    if executable is None:
        raise ValueError("Git Bash не найден")
    return [executable, "--noprofile", "--norc", "-c", shlex.join(arguments)]


def _run(root: Path, shell: str, log: Path, arguments: list[str], expected: int = 0) -> None:
    command = [sys.executable.replace("\\", "/"), *arguments]
    result = subprocess.run(_shell(shell, command), cwd=root, capture_output=True,
                            encoding="utf-8", timeout=240)
    display = shlex.join(["python", *arguments])
    text = f"$ {display}\n{result.stdout}{result.stderr}Код: {result.returncode}\n\n"
    with log.open("a", encoding="utf-8", newline="") as stream:
        stream.write(text)
    if result.returncode != expected:
        raise AssertionError(f"{display}: ожидался код {expected}\n{text}")


def _initial(root: Path, shell: str, log: Path) -> None:
    _run(root, shell, log, ["-m", "unittest", "discover", "-s", "tools/tests", "-t", "."])
    for command in (["--help"], ["status"], ["new", "project", "demo"],
                    ["new", "task", "demo", "01-test"], ["check"]):
        _run(root, shell, log, ["tools/strateg.py", *command])
    populate(root, root / "projects/demo/tasks/01-test")
    for command in (["status"], ["next", "E"], ["find", "E1"],
                    ["find", "ЦЕНА", "подписки", "--type", "E", "--kind", "факт"],
                    ["find", "--type", "Q", "--status", "открыт"], ["impact", "E1"]):
        _run(root, shell, log, ["tools/strateg.py", *command])


def _final(root: Path, shell: str, log: Path) -> None:
    step = ["tools/strateg.py", "log", "проверка | цены", "--stage", "3", "--tool", "скрипт",
            "--result", "найдена учебная цена", "--minutes", "2.5", "--tokens", "1", "--approx", "--key", "price"]
    _run(root, shell, log, step)
    _run(root, shell, log, step)
    _run(root, shell, log, ["tools/strateg.py", "cost", "--price", "10"])
    _run(root, shell, log, ["tools/strateg.py", "check", "--final"])
    _run(root, shell, log, ["tools/strateg.py", "new", "project", "demo"], 2)
    _run(root, shell, log, ["tools/strateg.py", "new", "task", "demo", "01-test"], 2)
    invalid = root / "учебный проект с нарушениями"
    prepare(invalid)
    broken(invalid)
    _run(root, shell, log, ["tools/strateg.py", "check", "--final", "--root", str(invalid)], 1)


def main() -> int:
    """Создаёт копию в dev/runs и сохраняет настоящий вывод оболочки.

    Returns:
        Ноль после успешного прогона всех команд.
    """
    parser = argparse.ArgumentParser(description="Все команды в выбранной оболочке на учебной копии")
    parser.add_argument("--shell", choices=("powershell", "bash"), required=True)
    args = parser.parse_args()
    workspace = Path(__file__).resolve().parents[3]
    runs = workspace / "dev/runs"
    runs.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=f"t01-{args.shell}-", dir=runs)) / "учебный корень"
    root.mkdir()
    prepare(root)
    shutil.copytree(Path(__file__).resolve().parents[1], root / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    log = root.parent / "output.txt"
    write(log, f"Оболочка: {args.shell}\nPython: {sys.version.split()[0]}\nКорень: {root}\n\n")
    _initial(root, args.shell, log)
    _final(root, args.shell, log)
    print(f"Проверены все команды; оболочка: {args.shell}")
    print(f"Вывод: {log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
