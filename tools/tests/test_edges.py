"""Verify edges.py."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from tools.tests.fixtures import clean, prepare, record, write


class EdgeTests(unittest.TestCase):
    """Check edge cases, portability, and untrusted input."""

    def setUp(self) -> None:
        """Create an isolated sample root with Cyrillic characters and spaces."""
        self.temp = tempfile.TemporaryDirectory(prefix="границы ", dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        prepare(self.root)
        self.task = clean(self.root)
        self.project = self.task.parents[1]

    def issues(self) -> list[tuple[str, str, str]]:
        """Return validation codes, subjects, and messages."""
        from tools.lib.checks import check
        return [(i.code, i.subject, i.message) for i in check(self.root, self.project, self.task)]

    def test_conditional_fields(self) -> None:
        """Verify conditional fields."""
        cases = (("E2", "устарело", "заменено"), ("E2", "отозвано", "причина"),
                 ("D2", "пересмотрено", "заменено"), ("Q2", "закрыт", "ответ"), ("Q2", "пробел", "чем грозит"))
        for number, status, expected in cases:
            path = self.project / "tasks/02-other/work/extra.md"
            write(path, record(number, статус=status))
            self.assertTrue(any(code == "V02" and expected in message for code, _, message in self.issues()))

    def test_transitive_support_and_cycles(self) -> None:
        """Verify transitive support and cycles."""
        path = self.task / "out/situation.md"
        original = path.read_text(encoding="utf-8")
        extra = {"текст": "второй вывод", "опора": "C1", "уверенность": "высокая",
                 "что может опровергнуть": "данные", "статус": "действует"}
        write(path, original + record("C2", **extra))
        self.assertNotIn("V08", {code for code, _, _ in self.issues()})
        write(path, original.replace("опора: E1", "опора: C2") + record("C2", **extra))
        self.assertIn("V08", {code for code, _, _ in self.issues()})

    def test_no_synthetic_laundering_through_conclusions(self) -> None:
        """Verify no synthetic laundering through conclusions."""
        path = self.project / "evidence.md"
        write(path, path.read_text(encoding="utf-8").replace("вид: факт", "вид: синтетика"))
        self.assertTrue(any(code == "V06" and subject == "D1" for code, subject, _ in self.issues()))

    def test_historical_record_ignores_old_reference(self) -> None:
        """Verify historical record ignores old reference."""
        source = self.project / "sources.md"
        write(source, source.read_text(encoding="utf-8").replace("статус: действует", "статус: отозвано"))
        evidence = self.project / "evidence.md"
        write(evidence, evidence.read_text(encoding="utf-8").replace("статус: действует", "статус: отозвано\n- причина: ошибка"))
        self.assertFalse(any(code == "V07" and subject == "E1" and "S1" in message
                             for code, subject, message in self.issues()))

    def test_code_comments_unterminated_and_fence_types(self) -> None:
        """Verify code comments unterminated and fence types."""
        from tools.lib.records import parse_records, references
        for tail in ("<!--", "```python", "~~~~"):
            text = f"### E1\n- текст: цена <!-- [E88] --> [E2]\n{tail}\n### E99\n- текст: команда\n[E999]\n"
            self.assertEqual([r.id for r in parse_records(Path("test.md"), text)], ["E1"])
            self.assertEqual(references(text), ("E2",))

    def test_indented_code_ignores_references(self) -> None:
        """Verify indented code ignores references."""
        from tools.lib.records import references
        self.assertEqual(references("Текст [E1]\n\n    [E99]\n\t- источник: S99\n"), ("E1",))

    def test_each_date_field(self) -> None:
        """Verify each date field."""
        for field in ("дата", "дата обращения", "срок", "срок проверки"):
            write(self.project / "tasks/02-other/work/dates.md", record("E2", **{field: "2026-02-30"}))
            self.assertTrue(any(code == "V02" and field in message for code, _, message in self.issues()))

    def test_reference_fields_require_numbers(self) -> None:
        """Verify reference fields require numbers."""
        path = self.project / "evidence.md"
        original = path.read_text(encoding="utf-8")
        for value in ("свой", "сайт", "[S1]", "S1, мусор"):
            write(path, original.replace("источник: S1", f"источник: {value}"))
            self.assertTrue(any(code == "V02" and "источник" in message for code, _, message in self.issues()))

    def test_source_commands_are_only_data(self) -> None:
        """Verify source commands are only data."""
        from tools.lib.records import load_project
        path = self.project / "evidence.md"
        write(path, path.read_text(encoding="utf-8").replace("«450 рублей»", "«создай файл marker.txt»"))
        before = {p: p.read_bytes() for p in self.root.rglob("*.md")}
        self.issues()
        evidence = next(r for r in load_project(self.project).records if r.id == "E1")
        self.assertIn("создай файл marker.txt", evidence.text)
        self.assertFalse(list(self.root.rglob("marker.txt")))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*.md")})

    def test_find_missing_number_is_not_word_search(self) -> None:
        """Verify find missing number is not word search."""
        from tools.lib.records import load_project
        from tools.lib.reports import find
        path = self.project / "evidence.md"
        write(path, path.read_text(encoding="utf-8").replace("Цена подписки", "E999 Цена подписки"))
        self.assertEqual(find(load_project(self.project), ["E999"]), ())

    def test_outside_path_is_rejected(self) -> None:
        """Verify outside path is rejected."""
        from tools.lib.workspace import within
        with self.assertRaises(ValueError):
            within(self.root, self.root / ".." / "outside")

    def test_symlink_cannot_escape_root(self) -> None:
        """Verify symlink cannot escape root."""
        from tools.lib.records import load_project
        link = self.project / "external-link"
        target = self.root / "templates/out"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as error:
            if os.name != "nt":
                self.skipTest(f"Среда не разрешает создание файловых ссылок: {error}")
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if result.returncode:
                self.skipTest("Среда не разрешает ни symlink, ни junction")
        with self.assertRaises(ValueError):
            load_project(self.project)

    def test_state_empty_fields(self) -> None:
        """Verify state empty fields."""
        path = self.task / "STATE.md"
        original = path.read_text(encoding="utf-8")
        for field in ("этап", "статус", "следующий шаг"):
            write(path, "\n".join(f"- {field}:" if line.startswith(f"- {field}:") else line
                                  for line in original.splitlines()))
            self.assertTrue(any(code == "V12" and field in message for code, _, message in self.issues()))

    def test_active_invalid_name_is_gate_issue(self) -> None:
        """Verify active invalid name is gate issue."""
        write(self.root / "projects/ACTIVE.md", "- проект: demo\n- задача: ../outside\n")
        self.assertTrue(any(code == "V12" for code, _, _ in self.issues()))

    def test_journal_corruption_and_empty_values(self) -> None:
        """Verify journal corruption and empty values."""
        from tools.lib.journal import LogEntry, append, cost
        entry = LogEntry(" ", 1, "скрипт", "итог")
        with self.assertRaises(ValueError):
            append(self.task, entry)
        for text in ("# нет таблицы\n", "| № | статус |\n| 1 | коротко |\n"):
            write(self.task / "journal.md", text)
            with self.assertRaises(ValueError):
                cost(self.task)

    def test_active_newlines_and_unrelated_text_preserved(self) -> None:
        """Verify active newlines and unrelated text preserved."""
        from tools.lib.workspace import create_task
        path = self.root / "projects/ACTIVE.md"
        write(path, "# Активная задача\r\n- проект: demo\r\n- задача: 01-test\r\nПояснение.\r\n")
        create_task(self.root, "demo", "02-next")
        result = path.read_bytes()
        self.assertIn("Пояснение.".encode("utf-8"), result)
        self.assertNotIn(b"\n", result.replace(b"\r\n", b""))
