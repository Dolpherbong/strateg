"""Verify cli.py."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.tests.fixtures import clean, prepare, record, write


class CliTests(unittest.TestCase):
    """Check exit codes, output, and file changes for CLI commands."""

    def setUp(self) -> None:
        """Create an isolated sample root with Cyrillic characters and spaces."""
        self.temp = tempfile.TemporaryDirectory(prefix="учебный проект ", dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.script = Path(__file__).resolve().parents[1] / "strateg.py"
        prepare(self.root)

    def run_cli(self, *args: str, code: int = 0) -> str:
        """Run a command and capture output without a subprocess."""
        result = subprocess.run([sys.executable, str(self.script), *args, "--root", str(self.root)],
                                capture_output=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result.stdout + result.stderr

    def test_creation_and_duplicate_protection(self) -> None:
        """Verify creation and duplicate protection."""
        active = self.root / "projects/ACTIVE.md"
        original = active.read_bytes()
        self.run_cli("new", "project", "demo")
        self.assertEqual(active.read_bytes(), original)
        self.run_cli("new", "project", "demo", code=2)
        self.run_cli("new", "task", "demo", "01-test")
        task = self.root / "projects/demo/tasks/01-test"
        self.assertTrue((task / "work").is_dir())
        self.assertEqual(list((task / "out").iterdir()), [])
        self.assertNotIn("{{", (task / "STATE.md").read_text(encoding="utf-8"))
        self.assertIn("- задача: 01-test", active.read_text(encoding="utf-8"))
        before = active.read_bytes()
        self.run_cli("new", "task", "demo", "01-test", code=2)
        self.assertEqual(active.read_bytes(), before)
        self.run_cli("check")

    def test_invalid_names_and_missing_project(self) -> None:
        """Verify invalid names and missing project."""
        for name in ("", "../escape", "Demo", "demo/name", "демо", "demo name", "con", "a."):
            self.run_cli("new", "project", name, code=2)
        self.run_cli("new", "task", "missing", "01-test", code=2)
        self.run_cli("new", "project", "demo")
        for name in ("test", "1-test", "01-", "01-../escape"):
            self.run_cli("new", "task", "demo", name, code=2)

    def test_missing_templates_no_partial_creation(self) -> None:
        """Verify missing templates no partial creation."""
        (self.root / "templates/project/evidence.md").write_bytes(b"\xff")
        self.run_cli("new", "project", "demo", code=2)
        self.assertFalse((self.root / "projects/demo").exists())

    def test_status_without_task(self) -> None:
        """Verify status without task."""
        self.assertIn("нет", self.run_cli("status").lower())
        self.run_cli("new", "project", "demo")
        self.assertIn("demo", self.run_cli("status"))
        self.run_cli("next", "E", code=2)

    def test_status_counts_and_overdue(self) -> None:
        """Verify status counts and overdue."""
        clean(self.root)
        text = self.run_cli("status")
        for token in ("demo", "01-test", "следующий шаг", "факт", "Q1", "K1", "D1"):
            self.assertIn(token, text)

    def test_next_across_all_tasks_and_statuses(self) -> None:
        """Verify next across all tasks and statuses."""
        task = clean(self.root)
        write(task.parents[1] / "tasks/02-other/work/old.md", record("E19", статус="устарело"))
        self.assertEqual(self.run_cli("next", "E").strip(), "E20")
        self.run_cli("next", "Z", code=2)

    def test_find_full_record_words_and_filters(self) -> None:
        """Verify find full record words and filters."""
        task = clean(self.root)
        text = self.run_cli("find", "E1")
        for token in ("evidence.md:1", "### E1", "450 рублей"):
            self.assertIn(token, text)
        self.assertIn("E1", self.run_cli("find", "ПОДПИСКИ", "цена", "--type", "E", "--kind", "факт"))
        self.assertIn("Q1", self.run_cli("find", "--type", "Q", "--status", "открыт"))
        self.assertIn("не найдены", self.run_cli("find", "нетсовпадений"))
        self.assertIn("не найдены", self.run_cli("find", "E1", "--kind", "гипотеза"))
        self.run_cli("find", code=2)
        self.run_cli("find", "", code=2)
        write(task.parents[1] / "tasks/02-other/questions.md", record("Q8", вопрос="Цена подписки"))
        self.assertIn("Q8", self.run_cli("find", "цена", "подписки"))

    def test_impact_breadth_first_and_cycle(self) -> None:
        """Verify impact breadth first and cycle."""
        task = clean(self.root)
        text = self.run_cli("impact", "E1")
        for token in ("Уровень 1", "Уровень 2", "C1", "O3", "D1", "summary.md", "K1"):
            self.assertIn(token, text)
        path = task / "out/situation.md"
        write(path, path.read_text(encoding="utf-8").replace("опора: E1", "опора: E1, C2") +
              record("C2", опора="C1"))
        self.run_cli("impact", "E1")
        self.run_cli("impact", "E999", code=2)

    def test_check_exit_codes(self) -> None:
        """Verify check exit codes."""
        task = clean(self.root)
        self.assertIn("Нарушений: 0", self.run_cli("check", "--final"))
        from tools.tests.fixtures import break_rule
        for number in range(1, 13):
            break_rule(task, f"V{number:02}")
        text = self.run_cli("check", "--final", code=1)
        for number in range(1, 13):
            self.assertIn(f"V{number:02}", text)

    def test_check_missing_active_target(self) -> None:
        """Verify check missing active target."""
        clean(self.root)
        write(self.root / "projects/ACTIVE.md", "- проект: demo\n- задача: 99-gone\n")
        self.assertIn("V12", self.run_cli("check", code=1))
        self.run_cli("status", code=2)

    def test_log_append_dedup_and_preserve_state_newlines(self) -> None:
        """Verify log append dedup and preserve state newlines."""
        task = clean(self.root)
        journal = task / "journal.md"
        journal.write_bytes(journal.read_bytes().replace(b"\n", b"\r\n"))
        before = journal.read_bytes()
        state = (task / "STATE.md").read_bytes()
        args = ("log", "проверка|цены\nстрока", "--stage", "2", "--tool", "скрипт",
                "--result", "есть|цена", "--minutes", "2.5", "--tokens", "1", "--cost", "3",
                "--approx", "--key", "price")
        text = self.run_cli(*args)
        self.assertIn("~2.5", text)
        self.assertIn("есть/цена", text)
        self.assertTrue(journal.read_bytes().startswith(before))
        self.assertNotIn(b"\n", journal.read_bytes().replace(b"\r\n", b""))
        saved = journal.read_bytes()
        self.assertIn("уже сделано", self.run_cli(*args))
        self.assertEqual(journal.read_bytes(), saved)
        self.assertEqual((task / "STATE.md").read_bytes(), state)

    def test_failed_key_retry_and_journal_numbers(self) -> None:
        """Verify failed key retry and journal numbers."""
        task = clean(self.root)
        path = task / "journal.md"
        write(path, path.read_text(encoding="utf-8").replace("| 1 |", "| 9 |"))
        args = ("log", "поиск", "--stage", "3", "--tool", "чтение", "--result", "нет", "--key", "retry")
        self.assertIn("| 10 |", self.run_cli(*args, "--status", "сбой"))
        self.assertIn("| 11 |", self.run_cli(*args))
        self.assertIn("Сбоев: 1", self.run_cli("cost"))

    def test_cost_totals_groups_estimates_and_price(self) -> None:
        """Verify cost totals groups estimates and price."""
        clean(self.root)
        base = ("log", "шаг", "--stage", "3", "--tool", "быстрая модель", "--result", "готово")
        self.run_cli(*base, "--minutes", "2", "--tokens", "1.5", "--approx")
        self.run_cli(*base, "--tokens", "2", "--cost", "4")
        text = self.run_cli("cost", "--price", "10")
        for token in ("Всего", "Этап 3", "быстрая модель", "~19", "~3.5", "Шагов: 3"):
            self.assertIn(token, text)
        self.assertIn("₽: 4; не оценено: 1 строк", self.run_cli("cost"))

    def test_bad_parameters_and_missing_files(self) -> None:
        """Verify bad parameters and missing files."""
        self.run_cli(code=2)
        self.run_cli("unknown", code=2)
        self.run_cli("find", "E1", "--project", "../outside", code=2)
        clean(self.root)
        base = ("log", "шаг", "--stage", "2", "--tool", "скрипт", "--result", "готово")
        for option, value in (("--minutes", "-1"), ("--tokens", "nan"), ("--cost", "inf")):
            self.run_cli(*base, option, value, code=2)
        self.run_cli("cost", "--price", "-2", code=2)
        journal = self.root / "projects/demo/tasks/01-test/journal.md"
        journal.unlink()
        self.run_cli(*base, code=2)
        self.run_cli("cost", code=2)

    def test_global_options_before_and_after_command(self) -> None:
        """Verify global options before and after command."""
        clean(self.root)
        self.run_cli("--project", "demo", "--task", "01-test", "status")
        self.run_cli("status", "--project", "demo", "--task", "01-test")

    def test_explicit_selection_does_not_need_active(self) -> None:
        """Verify explicit selection does not need active."""
        clean(self.root)
        write(self.root / "projects/ACTIVE.md", "- проект: нет\n- задача: нет\n")
        self.assertIn("E1", self.run_cli("find", "E1", "--project", "demo"))

    def test_utf8_error_is_short(self) -> None:
        """Verify utf8 error is short."""
        clean(self.root)
        (self.root / "projects/demo/evidence.md").write_bytes(b"\xff")
        self.run_cli("find", "E1", code=2)


if __name__ == "__main__":
    unittest.main()
