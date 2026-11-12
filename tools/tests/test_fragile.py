"""Verify evidence freshness and decision support reports."""

from datetime import date, timedelta
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from tools.lib.checks import check
from tools.lib.records import load_project
from tools.tests.fixtures import clean, prepare, record, write


class FragileTests(unittest.TestCase):
    """Check dates, graph traversal, reporting, and command exit codes."""

    def setUp(self) -> None:
        """Create an isolated project with Cyrillic characters in its path."""
        self.temp = tempfile.TemporaryDirectory(prefix="прочность проекта ", dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        prepare(self.root)
        self.task = clean(self.root)
        self.project = self.task.parents[1]
        self.replace("decisions.md", "2000-01-01", "2027-03-01")

    def replace(self, filename: str, old: str, new: str) -> None:
        """Replace fixture text in a project file.

        Args:
            filename: Path relative to the project.
            old: Text to replace.
            new: Replacement text.
        """
        path = self.project / filename
        write(path, path.read_text(encoding="utf-8").replace(old, new))

    def report(self, number: str | None = None, today: str = "2026-11-12",
               strict: bool = False) -> tuple[str, int]:
        """Build a deterministic report.

        Args:
            number: Optional decision identifier.
            today: Reference date.
            strict: Whether expired support causes code 1.

        Returns:
            Report text and exit code.
        """
        from tools.lib.reports import fragile
        lines, code = fragile(load_project(self.project), number, today, strict)
        return "\n".join(lines), code

    def run_cli(self, *args: str, code: int = 0) -> str:
        """Run the real entry point.

        Args:
            args: Command arguments.
            code: Expected exit code.

        Returns:
            Captured output.
        """
        script = Path(__file__).resolve().parents[1] / "strateg.py"
        result = subprocess.run([sys.executable, "-B", str(script), *args, "--root", str(self.root)],
                                capture_output=True, encoding="utf-8",
                                env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result.stdout + result.stderr

    def test_classes_and_dates(self) -> None:
        """Use exact day counts rather than calendar months."""
        for kind, days in (("цены", 90), ("функции", 180), ("аудитория", 365), ("структура", 730)):
            with self.subTest(kind=kind):
                write(self.project / "evidence.md", record("E1", вид="факт", источник="S1", годность=kind))
                deadline = (date(2026, 11, 11) + timedelta(days=days)).isoformat()
                text, code = self.report(today="2029-01-01", strict=True)
                self.assertIn(f"E1: {kind}, {deadline}, источник S1", text)
                self.assertIn("Прочность D1: устарело 1, истекает до проверки 0, узких мест 1", text)
                self.assertEqual(code, 1)

    def test_explicit_date_overrides_class_and_needs_no_source(self) -> None:
        """Honor an explicit date even for manual or unspecified classes."""
        for kind in ("цены", "нормы", ""):
            write(self.project / "evidence.md", record("E1", **{
                "вид": "факт", "годность": kind, "годен до": "2026-11-01"}))
            text, code = self.report(strict=True)
            self.assertIn("2026-11-01", text)
            self.assertIn("Прочность D1: устарело 1", text)
            self.assertEqual(code, 1)

    def test_source_date_precedes_access_date(self) -> None:
        """Prefer a complete publication date and fall back for partial dates."""
        self.replace("evidence.md", "- вид: факт", "- вид: факт\n- годность: цены")
        for source_date, expected in (("2026-01-01", "2026-04-01"), ("2026-01", "2027-02-09"),
                                      ("нет данных", "2027-02-09"), ("2026-02-30", "2027-02-09")):
            write(self.project / "sources.md", record("S1", **{
                "дата источника": source_date, "дата обращения": "2026-11-11"}))
            text, _ = self.report()
            self.assertIn(expected, text)

    def test_manual_missing_class_and_missing_source_date(self) -> None:
        """Report unknown freshness without inventing dates."""
        text, _ = self.report()
        self.assertIn("Без класса годности: 1 (E1)", text)
        self.assertIn("годность не указана", text)
        self.replace("evidence.md", "- вид: факт", "- вид: факт\n- годность: нормы")
        self.assertIn("Нормы, проверить вручную: E1", self.report()[0])
        self.replace("evidence.md", "годность: нормы", "годность: цены")
        write(self.project / "sources.md", record("S1"))
        self.assertIn("Срок годности не определён: E1", self.report()[0])

    def test_date_boundaries(self) -> None:
        """Keep the expiration day valid and exclude the review day."""
        for deadline, expired, expiring in (("2026-11-11", 1, 0), ("2026-11-12", 0, 1),
                                            ("2027-02-28", 0, 1), ("2027-03-01", 0, 0)):
            write(self.project / "evidence.md", record("E1", **{
                "вид": "факт", "источник": "S1", "годен до": deadline}))
            text, _ = self.report()
            self.assertIn(f"устарело {expired}, истекает до проверки {expiring}", text)

    def test_decision_conclusion_estimate_chain(self) -> None:
        """Count every reachable evidence item once, including estimate bases."""
        self.replace("tasks/01-test/out/situation.md", "опора: E1", "опора: E2")
        path = self.project / "evidence.md"
        write(path, path.read_text(encoding="utf-8") + record("E2", вид="оценка", основание="E1"))
        text, _ = self.report()
        self.assertIn("Опоры: фактов 1, оценок 1, гипотез 0, прогнозов 0", text)

    def test_option_links_only_in_fields(self) -> None:
        """Follow option fields and ignore prose and rejected alternatives."""
        self.replace("decisions.md", "основания: C1", "основания: нет данных")
        self.replace("decisions.md", "отвергнуто: остальные", "отвергнуто: [E99]")
        write(self.task / "out/options.md", "### O3\n- суть: [E1]\nТекст [E99]\n")
        write(self.project / "evidence.md", record("E1", вид="факт") + record("E99", вид="гипотеза"))
        text, _ = self.report()
        self.assertIn("Опоры: фактов 1, оценок 0, гипотез 0, прогнозов 0", text)

    def test_cycles_and_missing_references(self) -> None:
        """Terminate cycles in conclusions, options, and estimates."""
        write(self.task / "out/situation.md", record("C1", опора="C2, E2") + record("C2", опора="C1, E999"))
        write(self.task / "out/options.md", record("O3", суть="[O4]") + record("O4", суть="[O3, C1]"))
        write(self.project / "evidence.md", record("E1", вид="факт", источник="S1") +
              record("E2", вид="оценка", основание="E3") + record("E3", вид="оценка", основание="E2, E1"))
        self.assertIn("Опоры: фактов 1, оценок 2, гипотез 0, прогнозов 0", self.report()[0])

    def test_one_bottleneck(self) -> None:
        """List a conclusion reached through multiple paths only once."""
        text, _ = self.report()
        self.assertEqual(text.count("Узкое место C1:"), 1)
        self.assertIn("узких мест 1", text)

    def test_single_source_bottleneck(self) -> None:
        """Distinguish several facts from independent sources."""
        self.replace("tasks/01-test/out/situation.md", "опора: E1", "опора: E1, E2")
        path = self.project / "evidence.md"
        write(path, path.read_text(encoding="utf-8") + record("E2", вид="факт", источник="S1"))
        self.assertIn("все факты из S1", self.report()[0])
        self.replace("evidence.md", "### E2\n- вид: факт\n- источник: S1", "### E2\n- вид: факт\n- источник: S2")
        self.assertIn("узких мест 0", self.report()[0])

    def test_forecasts_before_review_including_free_text(self) -> None:
        """Extract an ISO date embedded in the demo forecast wording."""
        self.replace("decisions.md", "основания: C1", "основания: C1, E72, E73, E74")
        path = self.project / "evidence.md"
        extra = "".join(record(number, **{"вид": "прогноз", "срок прогноза": deadline}) for number, deadline in (
            ("E72", "с 2026-12-01, срок действия предложения неизвестен"),
            ("E73", "2027-03-01"), ("E74", "2027-03-02")))
        write(path, path.read_text(encoding="utf-8") + extra)
        text, _ = self.report()
        self.assertIn("Прогноз до проверки E72: 2026-12-01", text)
        self.assertNotIn("Прогноз до проверки E73", text)
        self.assertNotIn("Прогноз до проверки E74", text)

    def test_no_active_decisions_and_explicit_historical_decision(self) -> None:
        """Default to current decisions while accepting explicit historical IDs."""
        self.replace("decisions.md", "статус: действует", "статус: отменено")
        self.assertEqual(self.report(strict=True), ("Действующих решений нет", 0))
        self.assertIn("Прочность D1:", self.report("D1")[0])

    def test_cli_today_strict_and_read_only(self) -> None:
        """Change the reference day and fail strictly only for expired support."""
        self.replace("evidence.md", "- вид: факт", "- вид: факт\n- годен до: 2026-11-12")
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertIn("устарело 0", self.run_cli("fragile", "D1", "--today", "2026-11-12", "--strict"))
        self.assertIn("устарело 1", self.run_cli("fragile", "--today", "2026-11-13"))
        self.run_cli("fragile", "--today", "2026-11-13", "--strict", code=1)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_cli_bad_number_and_date(self) -> None:
        """Reject invalid IDs, missing decisions, and invalid calendar dates."""
        for number in ("E1", "D0", "D01", "D999", "d1", "", "D1x"):
            self.run_cli("fragile", number, code=2)
        for today in ("2026-2-01", "2026-02-30", "20261112", "", "2026-11-12x"):
            self.run_cli("fragile", "--today", today, code=2)

    def test_cli_project_without_active_task_and_empty_project(self) -> None:
        """Allow project-wide reporting without an active task."""
        write(self.root / "projects/ACTIVE.md", "- проект: нет\n- задача: нет\n")
        self.assertIn("Прочность D1:", self.run_cli("fragile", "--project", "demo"))
        write(self.project / "decisions.md", "")
        self.assertIn("Действующих решений нет", self.run_cli("fragile", "--project", "demo"))

    def test_missing_class_list_is_limited_to_ten(self) -> None:
        """Count all unclassified evidence but show only the first ten IDs."""
        ids = [f"E{i}" for i in range(1, 13)]
        write(self.project / "evidence.md", "".join(record(number, вид="факт") for number in ids))
        self.replace("decisions.md", "основания: C1", f"основания: {', '.join(ids)}")
        text, _ = self.report()
        self.assertIn(f"Без класса годности: 12 ({', '.join(ids[:10])})", text)

    def test_status_counts_unique_expired_evidence(self) -> None:
        """Count shared expired evidence once across active decisions."""
        self.replace("evidence.md", "- вид: факт", "- вид: факт\n- годен до: 2000-01-01")
        path = self.project / "decisions.md"
        write(path, path.read_text(encoding="utf-8") + record("D2", статус="действует", основания="E1"))
        self.assertIn("Устаревших опор: 1, подробнее: fragile", self.run_cli("status"))

    def test_stale_status_overrides_future_expiration(self) -> None:
        """Treat revoked evidence and outdated sources as expired support."""
        self.replace("evidence.md", "- вид: факт", "- вид: факт\n- годен до: 2027-02-01")
        for filename, status, expected in (("evidence.md", "отозвано", "E1 отозвано"),
                                            ("sources.md", "устарело", "S1 устарело")):
            with self.subTest(filename=filename):
                self.replace(filename, "статус: действует", f"статус: {status}")
                text, code = self.report(strict=True)
                self.assertEqual(code, 1)
                self.assertIn(f"статус: {expected}", text)
                self.assertIn("устарело 1, истекает до проверки 0", text)
                self.replace(filename, f"статус: {status}", "статус: действует")

    def test_multiple_sources_and_unknown_forecast_date(self) -> None:
        """Use the oldest source date and report unparseable forecasts."""
        write(self.project / "sources.md", record("S1", **{"дата источника": "2026-01-01"}) +
              record("S2", **{"дата источника": "2026-11-01"}))
        write(self.project / "evidence.md", record("E1", вид="факт", источник="S1, S2", годность="цены") +
              record("E2", **{"вид": "прогноз", "срок прогноза": "4 кв. 2027"}))
        self.replace("decisions.md", "основания: C1", "основания: C1, E2")
        text, _ = self.report()
        self.assertIn("E1: цены, 2026-04-01, источник S1, S2", text)
        self.assertIn("Срок прогноза не определён E2: 4 кв. 2027", text)

    def test_default_today_and_cross_task_support(self) -> None:
        """Use the local date and follow conclusions in another task."""
        from tools.lib.reports import fragile
        write(self.project / "tasks/02-other/out/situation.md", record("C2", опора="E1"))
        self.replace("tasks/01-test/out/situation.md", "опора: E1", "опора: C2")
        lines, code = fragile(load_project(self.project))
        self.assertIn(f"Устарели на {date.today().isoformat()}: 0", lines)
        self.assertEqual(code, 0)
        self.assertTrue(any("Опоры: фактов 1" in line for line in lines))

    def test_optional_schema_fields_and_v02_dates(self) -> None:
        """Keep old records valid and validate optional shelf-life fields."""
        self.assertNotIn("V02", {i.code for i in check(self.root, self.project, self.task)})
        path = self.project / "evidence.md"
        original = path.read_text(encoding="utf-8")
        for extra in ("- годность: другое\n", "- годен до: 2026-02-30\n", "- годен до: 2026-2-01\n"):
            write(path, original + extra)
            self.assertIn("V02", {i.code for i in check(self.root, self.project, self.task)})
        for kind in ("цены", "функции", "аудитория", "нормы", "структура"):
            write(path, original + f"- годность: {kind}\n- годен до: 2026-12-31\n")
            self.assertNotIn("V02", {i.code for i in check(self.root, self.project, self.task)})


if __name__ == "__main__":
    unittest.main()
