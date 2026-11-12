"""Compare example registries against a local Git revision without changing files."""

import argparse
from collections import Counter
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.lib.records import parse_records, read


def _original(root: Path, revision: str, path: Path) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root),
         "show", f"{revision}:{path.relative_to(root).as_posix()}"],
        check=True, capture_output=True,
    )
    return result.stdout.decode("utf-8-sig")


def _unquote(value: str) -> str:
    return value[1:-1] if len(value) >= 2 and (value[0], value[-1]) in (("«", "»"), ('"', '"')) else value


def _entries(path: Path, text: str) -> Counter:
    return Counter((item.id, tuple(sorted((key, _unquote(value) if key == "цитата" else value)
                                        for key, value in item.fields.items())), item.duplicate_fields)
                   for item in parse_records(path, text))


def _lines(text: str) -> Counter:
    result = []
    for line in text.splitlines(keepends=True):
        match = re.fullmatch(r"(- цитата: )([^\r\n]*)(\r?\n|$)", line)
        result.append(match[1] + _unquote(match[2]) + match[3] if match else line)
    return Counter(result)


def _compare(root: Path, revision: str, project: str, task: str) -> bool:
    names = ("sources.md", "evidence.md", "decisions.md", f"tasks/{task}/questions.md")
    before_count, after_count, quotes, moved, same = 0, 0, 0, False, True
    for name in names:
        path = root / "projects" / project / name
        before, after = _original(root, revision, path), read(path)
        old, new = parse_records(path, before), parse_records(path, after)
        before_count, after_count = before_count + len(old), after_count + len(new)
        old_quotes = Counter((item.id, item.fields.get("цитата")) for item in old)
        new_quotes = Counter((item.id, item.fields.get("цитата")) for item in new)
        quotes += sum((old_quotes - new_quotes).values())
        moved = moved or before != after
        same = same and _entries(path, before) == _entries(path, after) and _lines(before) == _lines(after)
    print(f"{project}: файлов {len(names)}, записей {before_count} -> {after_count}; "
          + ("множества записей, поля и строки сохранены" if same else "содержание изменилось"))
    print(f"Порядок изменён: {'да' if moved else 'нет'}; изменений кавычек: {quotes}")
    return same


def main() -> int:
    """Verify records, field values, and all original lines, allowing order and quotes.

    Returns:
        Zero for an equivalent snapshot, one when content changed.
    """
    parser = argparse.ArgumentParser(description="Сверить реестры с локальным снимком Git")
    parser.add_argument("--before", required=True, help="хеш исходного коммита")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.before):
        parser.error("нужен полный хеш коммита")
    root = Path(__file__).resolve().parents[2]
    valid = True
    for project, task in (("operator-n-travel", "01-travel-esim"), ("operator-n-ai-smb", "01-ai-subscription")):
        same = _compare(root, args.before, project, task)
        valid = valid and same
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
