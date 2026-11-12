"""Check registry ordering, quotation marks, and missing journal amounts."""

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from tools.lib.checks import check
from tools.lib.journal import cost
from tools.tests.fixtures import clean, prepare, record, write
from tools.tests.test_clock import HEADER


class RegistryRulesTests(unittest.TestCase):
    """Exercise the new gates through complete project checks."""

    def setUp(self) -> None:
        """Prepare an isolated project with Cyrillic paths."""
        self.temp = tempfile.TemporaryDirectory(prefix="реестры ", dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        prepare(self.root)
        self.task = clean(self.root)
        self.project = self.task.parents[1]

    def problems(self, code: str) -> list[tuple[str, str]]:
        """Return subjects and messages for one gate.

        Args:
            code: Validation gate code.

        Returns:
            Matching subjects and messages.
        """
        return [(i.subject, i.message) for i in check(self.root, self.project, self.task) if i.code == code]

    def test_registry_numeric_order_and_separate_letters(self) -> None:
        """Sort numerically per file and letter, allowing gaps and interleaving."""
        cases = (("sources.md", "S"), ("evidence.md", "E"), ("decisions.md", "D"),
                 ("decisions.md", "K"), ("tasks/01-test/questions.md", "Q"))
        for filename, letter in cases:
            path = self.project / filename
            original = path.read_bytes()
            for numbers, bad in (((1, 2, 10), ()), ((10, 1, 2), (1, 2)), ((2, 1, 3), (1,))):
                with self.subTest(filename=filename, letter=letter, numbers=numbers):
                    write(path, "# Реестр\nОписание.\n" + "".join(record(f"{letter}{n}") for n in numbers))
                    actual = [s for s, m in self.problems("V01") if m == "запись не по порядку"]
                    self.assertEqual(actual, [f"{letter}{n}" for n in bad])
            path.write_bytes(original)
        write(self.project / "decisions.md", record("D1") + record("K1") + record("D2") + record("K2"))
        self.assertFalse(any(m == "запись не по порядку" for _, m in self.problems("V01")))

    def test_registry_records_below_introduction(self) -> None:
        """Catch a displaced title or prose even when numbers increase."""
        path = self.project / "sources.md"
        for intro in ("# Источники\nОписание.\n", "Описание реестра.\n", "## Правила\nОписание.\n"):
            with self.subTest(intro=intro):
                write(path, record("S1") + intro + record("S2"))
                self.assertIn(("S1", "запись не по порядку"), self.problems("V01"))
                self.assertNotIn(("S2", "запись не по порядку"), self.problems("V01"))

    def test_hidden_records_and_prose_do_not_affect_order(self) -> None:
        """Ignore comments, both fence types, indented code, and CRLF."""
        hidden = ("<!--\n### S99\nОписание.\n-->\n", "```md\n### S99\n# Описание\n```\n",
                  "~~~~\n### S99\nОписание.\n~~~~\n", "    ### S99\n    Описание.\n")
        path = self.project / "sources.md"
        for fragment in hidden:
            with self.subTest(fragment=fragment):
                write(path, ("# Источники\nОписание.\n" + record("S1") + fragment + record("S2")).replace("\n", "\r\n"))
                self.assertFalse(any(m == "запись не по порядку" for _, m in self.problems("V01")))
        write(path, "# Источники\n<!-- только образец\n### S9\n-->\n")
        self.assertNotIn(("S9", "запись не по порядку"), self.problems("V01"))

    def test_task_question_order_is_local_and_outputs_are_exempt(self) -> None:
        """Check Q locally, leaving arbitrary output record order unchanged."""
        write(self.project / "tasks/02-other/questions.md", record("Q10") + record("Q11"))
        write(self.task / "out/situation.md", record("C9") + record("C2"))
        self.assertFalse(any(m == "запись не по порядку" for _, m in self.problems("V01")))

    def test_fact_quotation_pairs(self) -> None:
        """Accept matching outer quotes, whitespace and nested quotation marks."""
        path = self.project / "evidence.md"
        valid = ('«Цена»', '"Цена"', '  «Цена»  ', '«Тариф «Мой»»', '"Тариф «Мой»"')
        invalid = ("Цена", "«Цена", "Цена»", '«Цена"', '"Цена»', '"', "«»", '""', "« »")
        for quote in (*valid, *invalid):
            with self.subTest(quote=quote):
                write(path, record("E1", вид="факт", источник="S1", место="цены", цитата=quote))
                self.assertEqual(("E1", "цитата без кавычек") in self.problems("V03"), quote in invalid)
        for kind in ("оценка", "гипотеза", "прогноз", "синтетика"):
            write(path, record("E1", вид=kind, цитата="Цена"))
            self.assertFalse(self.problems("V03"))

    def test_quote_length_and_missing_quote(self) -> None:
        """Count words inside either quote pair, preserving missing-field errors."""
        path = self.project / "evidence.md"
        for left, right in (("«", "»"), ('"', '"')):
            for count in (25, 26):
                write(path, record("E1", вид="факт", источник="S1", место="цены",
                                   цитата=left + " ".join(["слово"] * count) + right))
                self.assertEqual(("E1", "цитата длиннее 25 слов") in self.problems("V03"), count > 25)
                self.assertNotIn(("E1", "цитата без кавычек"), self.problems("V03"))
        for extra in ({}, {"цитата": ""}):
            write(path, record("E1", вид="факт", **extra))
            self.assertIn(("E1", "нет поля «цитата»"), self.problems("V03"))


class MissingCostTests(unittest.TestCase):
    """Keep missing estimates separate for every metric and group."""

    def setUp(self) -> None:
        """Create an isolated journal path."""
        self.temp = tempfile.TemporaryDirectory(prefix="расходы ", dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.task = Path(self.temp.name).resolve()

    def report(self, amounts: tuple[tuple[str, str, str], ...], price: Decimal | None = None) -> tuple[str, ...]:
        """Build a journal and return its report.

        Args:
            amounts: Minutes, tokens, and rubles for each row.
            price: Optional rubles per thousand tokens.

        Returns:
            Cost report lines.
        """
        rows = [f"| {n} | 2026-11-12 | {n} | шаг | средство{n} | итог | {m} | {t} | {r} | | готово |\n"
                for n, (m, t, r) in enumerate(amounts, 1)]
        write(self.task / "journal.md", HEADER + "".join(rows))
        return cost(self.task, price)

    def test_empty_journal_and_all_missing(self) -> None:
        """An absent measurement never prints as zero, including empty journals."""
        for amounts in ((), (("", "", ""),), ((" ", "", ""), ("", "", ""))):
            for line in self.report(amounts):
                if "шагов:" in line:
                    for label in ("мин", "ток., тыс.", "₽"):
                        self.assertIn(f"{label}: не оценено", line)
                        self.assertNotIn(f"{label}: 0", line)
            if amounts:
                label = "1 строка" if len(amounts) == 1 else "2 строки"
                self.assertIn(f"не оценено ({label})", self.report(amounts)[1])

    def test_partial_totals_and_missing_counts_for_each_metric(self) -> None:
        """Sum only populated cells, retaining approximate totals and counts."""
        lines = self.report((("~65", "", "2"), ("", "1,5", ""), ("", "", "")))
        self.assertIn("мин: ~65; не оценено: 2 строки", lines[1])
        self.assertIn("ток., тыс.: 1.5; не оценено: 2 строки", lines[1])
        self.assertIn("₽: 2; не оценено: 2 строки", lines[1])
        for label in ("Этап 3", "Средство средство3"):
            line = next(line for line in lines if line.startswith(label + ":"))
            self.assertIn("мин: не оценено (1 строка)", line)
            self.assertIn("₽: не оценено (1 строка)", line)

    def test_explicit_zero_is_estimated(self) -> None:
        """Explicit zero and approximate zero remain measured values."""
        line = self.report((("0", "~0", "0"),))[1]
        self.assertIn("мин: 0; ток., тыс.: ~0; ₽: 0", line)
        self.assertNotIn("не оценено", line)

    def test_price_only_fills_rubles_when_tokens_are_present(self) -> None:
        """Preserve explicit cost, token estimates, zero price, and missing tokens."""
        amounts = (("", "~1,5", ""), ("", "2", "4"), ("", "", ""), ("", "0", ""))
        self.assertIn("₽: ~19; не оценено: 1 строк", self.report(amounts, Decimal(10))[1])
        self.assertIn("₽: ~4; не оценено: 1 строк", self.report(amounts, Decimal(0))[1])
        self.assertIn("₽: 4; не оценено: 3 строк", self.report(amounts)[1])

    def test_bad_number_and_missing_file_still_fail(self) -> None:
        """Unknown values cannot conceal corrupt numbers or a missing journal."""
        with self.assertRaises(FileNotFoundError):
            cost(self.task)
        for bad in ("~", "NaN", "текст", "-1"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.report((("", bad, ""),))
