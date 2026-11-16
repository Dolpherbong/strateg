"""Verify checks.py."""

from pathlib import Path
import tempfile
import unittest

from tools.tests.fixtures import break_rule, broken, clean, prepare, record, write


class ChecksTests(unittest.TestCase):
    """Check all validation gates and empty templates."""

    def setUp(self) -> None:
        """Create an isolated sample root with Cyrillic characters and spaces."""
        self.temp = tempfile.TemporaryDirectory(prefix="учебный проект ", dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        prepare(self.root)

    def codes(self, task: Path, final: bool = False) -> set[str]:
        """Return the set of validation issue codes."""
        from tools.lib.checks import check
        return {issue.code for issue in check(self.root, task.parents[1], task, final)}

    def test_clean_final(self) -> None:
        """Verify clean final."""
        self.assertEqual(self.codes(clean(self.root), True), set())

    def test_new_task_passes(self) -> None:
        """Verify new task passes."""
        from tools.lib.workspace import create_project, create_task
        create_project(self.root, "demo")
        task = create_task(self.root, "demo", "01-test")
        self.assertEqual(self.codes(task), set())
        self.assertTrue({"V09", "V10"} <= self.codes(task, True))

    def test_each_rule_independently(self) -> None:
        """Verify each rule independently."""
        task = clean(self.root)
        original = {p: p.read_bytes() for p in self.root.rglob("*.md")}
        for number in range(1, 13):
            code = f"V{number:02}"
            for path, content in original.items():
                path.write_bytes(content)
            with self.subTest(code=code):
                break_rule(task, code)
                self.assertIn(code, self.codes(task, True))

    def test_all_twelve_together(self) -> None:
        """Verify all twelve together."""
        self.assertEqual(self.codes(broken(self.root), True), {f"V{n:02}" for n in range(1, 13)})

    def test_v01_duplicate_missing_and_wrong_location(self) -> None:
        """Verify v01 duplicate missing and wrong location."""
        task = clean(self.root)
        write(task / "work/wrong.md", record("E1", текст="[E999]"))
        from tools.lib.checks import check
        issues = [f"{i.subject} {i.message}" for i in check(self.root, task.parents[1], task, False) if i.code == "V01"]
        for word in ("повтор", "E999", "файл"):
            self.assertTrue(any(word in message for message in issues), issues)

    def test_v02_fields_enums_dates_and_broken_record(self) -> None:
        """Verify v02 fields enums dates and broken record."""
        task = clean(self.root)
        path = task.parents[1] / "sources.md"
        valid = path.read_text(encoding="utf-8")
        for old, new in (("- название: Учебный сайт", "- название:"), ("- тип: сайт", "- тип: другое"),
                         ("2026-11-11", "2026-2-01"), ("2026-11-11", "2026-02-30"),
                         ("- тип: сайт", "- тип: сайт\n- тип: сайт")):
            with self.subTest(new=new):
                write(path, valid.replace(old, new))
                self.assertIn("V02", self.codes(task))

    def test_v01_broken_record_number(self) -> None:
        """Report malformed record numbers as V01, without V02."""
        from tools.lib.checks import check
        task = clean(self.root)
        path = task.parents[1] / "sources.md"
        write(path, path.read_text(encoding="utf-8").replace("### S1", "### Sbroken"))
        issues = check(self.root, task.parents[1], task)
        malformed = [issue for issue in issues if issue.message == "битый номер записи"]
        self.assertEqual([issue.code for issue in malformed], ["V01"])
        self.assertNotIn("V02", {issue.code for issue in issues})

    def test_v07_record_references_are_not_document_references(self) -> None:
        """Check C and O references once, retaining separate prose references."""
        from tools.lib.checks import check
        task = clean(self.root)
        evidence = task.parents[1] / "evidence.md"
        write(evidence, evidence.read_text(encoding="utf-8").replace(
            "статус: действует", "статус: устарело\n- заменено: E2") + record("E2"))
        for filename, number in (("situation.md", "C1"), ("options.md", "O1")):
            path = task / "out" / filename
            for status in ("действует", "отозвано"):
                for prose in ("", "## Итог\nСсылка [E1].\n"):
                    with self.subTest(number=number, status=status, prose=bool(prose)):
                        write(path, record(number, текст="[E1]", статус=status) + prose)
                        issues = [i for i in check(self.root, task.parents[1], task)
                                  if i.code == "V07" and i.path == path]
                        subjects = ([number] if status == "действует" else []) + (["E1"] if prose else [])
                        self.assertCountEqual([i.subject for i in issues], subjects)

    def test_v03_missing_fields_and_quote_boundary(self) -> None:
        """Verify v03 missing fields and quote boundary."""
        task = clean(self.root)
        path = task.parents[1] / "evidence.md"
        original = path.read_text(encoding="utf-8")
        for field in ("источник", "место", "цитата"):
            write(path, "\n".join(l for l in original.splitlines() if not l.startswith(f"- {field}:")))
            self.assertIn("V03", self.codes(task))
        for count in (25, 26):
            write(path, original.replace("«450 рублей»", "«" + " ".join(["слово"] * count) + "»"))
            self.assertEqual("V03" in self.codes(task), count > 25)

    def test_v04_all_kinds(self) -> None:
        """Verify v04 all kinds."""
        task = clean(self.root)
        path = task.parents[1] / "evidence.md"
        original = path.read_text(encoding="utf-8")
        for kind, extra in (("оценка", {}), ("оценка", {"основание": "E1"}),
                            ("оценка", {"расчёт": "2*2"}), ("гипотеза", {}), ("прогноз", {})):
            fields = {"текст": "учебное", "вид": kind, "период": "2026", "статус": "действует",
                      "задача": "01-test", **extra}
            write(path, original + record("E2", **fields))
            self.assertIn("V04", self.codes(task))
        write(path, original + record("E2", **{"текст": "прогноз", "вид": "прогноз", "источник": "свой",
              "срок прогноза": "4 кв. 2027", "период": "2027", "статус": "действует", "задача": "01-test"}))
        self.assertNotIn("V04", self.codes(task))

    def test_v05_both_fields(self) -> None:
        """Verify v05 both fields."""
        task = clean(self.root)
        path = task.parents[1] / "evidence.md"
        original = path.read_text(encoding="utf-8")
        for field in ("источник", "основание"):
            write(path, original + record("E2", **{field: "C1"}))
            self.assertIn("V05", self.codes(task))

    def test_v06_synthetic_support_and_model_source(self) -> None:
        """Verify v06 synthetic support and model source."""
        task = clean(self.root)
        path = task.parents[1] / "evidence.md"
        write(path, path.read_text(encoding="utf-8").replace("вид: факт", "вид: синтетика"))
        self.assertIn("V06", self.codes(task))
        source = task.parents[1] / "sources.md"
        write(source, source.read_text(encoding="utf-8").replace("тип: сайт", "тип: модель"))
        from tools.lib.checks import check
        messages = [i.message for i in check(self.root, task.parents[1], task, False) if i.code == "V06"]
        self.assertTrue(any("C1" in i or "синтетик" in i for i in messages))
        decision = task.parents[1] / "decisions.md"
        write(decision, decision.read_text(encoding="utf-8").replace("основания: C1", "основания: E1"))
        self.assertIn("V06", self.codes(task))

    def test_v07_current_and_historical(self) -> None:
        """Verify v07 current and historical."""
        task = clean(self.root)
        break_rule(task, "V07")
        self.assertIn("V07", self.codes(task))
        path = task.parents[1] / "evidence.md"
        write(path, path.read_text(encoding="utf-8").replace("статус: действует", "статус: отозвано\n- причина: ошибка"))
        self.assertIn("V07", self.codes(task))

    def test_v07_commitment_of_revised_decision(self) -> None:
        """Verify an open commitment of a revised decision must move to the successor or close."""
        task = clean(self.root)
        path = task.parents[1] / "decisions.md"
        revised = path.read_text(encoding="utf-8").replace(
            "- статус: действует", "- статус: пересмотрено\n- заменено: D2", 1)
        successor = record("D2", **{
            "решение": "проверить подписку дешевле", "дата": "2026-11-12",
            "кто решил": "руководитель продукта", "выбран вариант": "O3", "основания": "C1",
            "отвергнуто": "остальные", "ответственный": "аналитик", "показатель": "спрос",
            "срок проверки": "2000-01-01", "условие пересмотра": "спроса нет", "статус": "действует",
            "предыдущее решение": "[D1]"})
        write(path, revised + successor)
        self.assertIn("V07", self.codes(task))
        carried = successor.replace("- статус: действует\n", "- статус: действует\n- обязательства: K1–K3 продолжаются под D2\n")
        write(path, revised + carried)
        self.assertNotIn("V07", self.codes(task))
        unrelated = record("D3", **{
            "решение": "другое направление", "дата": "2026-11-13",
            "кто решил": "руководитель продукта", "выбран вариант": "O3", "основания": "C1",
            "отвергнуто": "остальные", "ответственный": "аналитик", "показатель": "спрос",
            "срок проверки": "2000-01-01", "условие пересмотра": "спроса нет", "статус": "действует",
            "обязательства": "K1 продолжается под D3"})
        write(path, revised + successor + unrelated)
        self.assertIn("V07", self.codes(task))
        write(path, revised.replace("- статус: открыто", "- статус: снято") + successor)
        self.assertNotIn("V07", self.codes(task))

    def test_v08_confidence_support(self) -> None:
        """Verify v08 confidence support."""
        task = clean(self.root)
        path = task.parents[1] / "evidence.md"
        write(path, path.read_text(encoding="utf-8").replace("вид: факт", "вид: гипотеза") + "- как проверить: цена\n")
        self.assertIn("V08", self.codes(task))
        conclusion = task / "out/situation.md"
        write(conclusion, conclusion.read_text(encoding="utf-8").replace("уверенность: средняя", "уверенность: низкая"))
        self.assertNotIn("V08", self.codes(task))

    def test_v09_counts_roles_and_empty_fields(self) -> None:
        """Verify v09 counts roles and empty fields."""
        task = clean(self.root)
        path = task / "out/options.md"
        original = path.read_text(encoding="utf-8")
        for text in (original.split("### O3")[0], original.replace("роль: закрыть", "роль: активный"),
                     original.replace("- что должно быть правдой: цена [E1]", "- что должно быть правдой:"),
                     original.replace("роль: активный", "роль: закрыть")):
            write(path, text)
            self.assertIn("V09", self.codes(task))

    def test_v10_missing_empty_sections_and_documents(self) -> None:
        """Verify v10 missing empty sections and documents."""
        task = clean(self.root)
        write(self.root / "templates/out/extra.md", "# Ещё\n## Новый раздел\n")
        self.assertIn("V10", self.codes(task, True))
        write(task / "out/extra.md", "# Ещё\n## Новый раздел\n<!-- пусто -->\n```\nне текст\n```\n")
        self.assertIn("V10", self.codes(task, True))
        self.assertNotIn("V10", self.codes(task))

    def test_v11_only_template_can_exempt(self) -> None:
        """Verify v11 only template can exempt."""
        task = clean(self.root)
        write(self.root / "templates/out/extra.md", "## Основание\n## Свободно\n<!-- без опоры -->\n")
        path = task / "out/extra.md"
        write(path, "## Основание\n<!-- без опоры -->\nТекст.\n## Свободно\nТекст.\n")
        self.assertIn("V11", self.codes(task, True))
        for marker in ("гипотеза", "Допущение", "Допущения:", "гипотезы", "ГИПОТЕЗАМИ",
                       "допущению", "не знаем", "НЕ   ЗНАЕМ", "[E1]"):
            write(path, f"## Основание\n{marker}\n## Свободно\nТекст.\n")
            self.assertNotIn("V11", self.codes(task, True))

    def test_v12_missing_state_journal_and_active_target(self) -> None:
        """Verify v12 missing state journal and active target."""
        task = clean(self.root)
        for name in ("STATE.md", "journal.md"):
            path = task / name
            original = path.read_bytes()
            path.unlink()
            self.assertIn("V12", self.codes(task))
            path.write_bytes(original)
        write(self.root / "projects/ACTIVE.md", "- проект: demo\n- задача: 99-missing\n")
        self.assertIn("V12", self.codes(task))
