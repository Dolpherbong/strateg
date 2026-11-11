"""Проверки ворот V01-V12 на учебных проектах."""

from pathlib import Path
import tempfile
import unittest

from tools.tests.fixtures import break_rule, broken, clean, prepare, record, write


class ChecksTests(unittest.TestCase):
    """Проверяет каждый вид нарушения и пустые формы."""

    def setUp(self) -> None:
        """Создаёт изолированный корень с кириллицей и пробелами."""
        self.temp = tempfile.TemporaryDirectory(prefix="учебный проект ", dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        prepare(self.root)

    def codes(self, task: Path, final: bool = False) -> set[str]:
        """Возвращает коды найденных нарушений."""
        from tools.lib.checks import check
        return {issue.code for issue in check(self.root, task.parents[1], task, final)}

    def test_clean_final(self) -> None:
        """Полный проект проходит финальные ворота."""
        self.assertEqual(self.codes(clean(self.root), True), set())

    def test_new_task_passes(self) -> None:
        """Незаполненные формы новой задачи проходят обычные ворота."""
        from tools.lib.workspace import create_project, create_task
        create_project(self.root, "demo")
        task = create_task(self.root, "demo", "01-test")
        self.assertEqual(self.codes(task), set())
        self.assertTrue({"V09", "V10"} <= self.codes(task, True))

    def test_each_rule_independently(self) -> None:
        """Каждое из двенадцати нарушений обнаруживается отдельно."""
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
        """Учебный проект показывает все двенадцать проверок за раз."""
        self.assertEqual(self.codes(broken(self.root), True), {f"V{n:02}" for n in range(1, 13)})

    def test_v01_duplicate_missing_and_wrong_location(self) -> None:
        """Повторы, потерянные ссылки и неверные файлы видны во всём проекте."""
        task = clean(self.root)
        write(task / "work/wrong.md", record("E1", текст="[E999]"))
        from tools.lib.checks import check
        issues = [f"{i.subject} {i.message}" for i in check(self.root, task.parents[1], task, False) if i.code == "V01"]
        for word in ("повтор", "E999", "файл"):
            self.assertTrue(any(word in message for message in issues), issues)

    def test_v02_fields_enums_dates_and_broken_record(self) -> None:
        """Пустое поле, неверные значения, даты и битый заголовок не теряются."""
        task = clean(self.root)
        path = task.parents[1] / "sources.md"
        valid = path.read_text(encoding="utf-8")
        for old, new in (("- название: Учебный сайт", "- название:"), ("- тип: сайт", "- тип: другое"),
                         ("2026-11-11", "2026-2-01"), ("2026-11-11", "2026-02-30"),
                         ("### S1", "### Sbroken"), ("- тип: сайт", "- тип: сайт\n- тип: сайт")):
            with self.subTest(new=new):
                write(path, valid.replace(old, new))
                self.assertIn("V02", self.codes(task))

    def test_v03_missing_fields_and_quote_boundary(self) -> None:
        """Каждое поле факта обязательно, граница цитаты ровно 25 слов."""
        task = clean(self.root)
        path = task.parents[1] / "evidence.md"
        original = path.read_text(encoding="utf-8")
        for field in ("источник", "место", "цитата"):
            write(path, "\n".join(l for l in original.splitlines() if not l.startswith(f"- {field}:")))
            self.assertIn("V03", self.codes(task))
        for count in (25, 26):
            write(path, original.replace("450 рублей\n", " ".join(["слово"] * count) + "\n"))
            self.assertEqual("V03" in self.codes(task), count > 25)

    def test_v04_all_kinds(self) -> None:
        """Оценке нужны основание и расчёт, гипотезе проверка, прогнозу источник и срок."""
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
        """Вывод запрещён и в источнике, и в основании сведения."""
        task = clean(self.root)
        path = task.parents[1] / "evidence.md"
        original = path.read_text(encoding="utf-8")
        for field in ("источник", "основание"):
            write(path, original + record("E2", **{field: "C1"}))
            self.assertIn("V05", self.codes(task))

    def test_v06_synthetic_support_and_model_source(self) -> None:
        """Синтетика не доказывает вывод или решение и требует модельный источник."""
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
        """Исторические записи не требуют актуальной опоры, действующие требуют."""
        task = clean(self.root)
        break_rule(task, "V07")
        self.assertIn("V07", self.codes(task))
        path = task.parents[1] / "evidence.md"
        write(path, path.read_text(encoding="utf-8").replace("статус: действует", "статус: отозвано\n- причина: ошибка"))
        self.assertIn("V07", self.codes(task))

    def test_v08_confidence_support(self) -> None:
        """Высокой и средней уверенности недостаточно одной гипотезы."""
        task = clean(self.root)
        path = task.parents[1] / "evidence.md"
        write(path, path.read_text(encoding="utf-8").replace("вид: факт", "вид: гипотеза") + "- как проверить: цена\n")
        self.assertIn("V08", self.codes(task))
        conclusion = task / "out/situation.md"
        write(conclusion, conclusion.read_text(encoding="utf-8").replace("уверенность: средняя", "уверенность: низкая"))
        self.assertNotIn("V08", self.codes(task))

    def test_v09_counts_roles_and_empty_fields(self) -> None:
        """Проверяет число, обязательные роли и два содержательных поля варианта."""
        task = clean(self.root)
        path = task / "out/options.md"
        original = path.read_text(encoding="utf-8")
        for text in (original.split("### O3")[0], original.replace("роль: закрыть", "роль: активный"),
                     original.replace("- что должно быть правдой: цена [E1]", "- что должно быть правдой:"),
                     original.replace("роль: активный", "роль: закрыть")):
            write(path, text)
            self.assertIn("V09", self.codes(task))

    def test_v10_missing_empty_sections_and_documents(self) -> None:
        """Список документов и разделов берётся из форм, комментарии и код не заполняют раздел."""
        task = clean(self.root)
        write(self.root / "templates/out/extra.md", "# Ещё\n## Новый раздел\n")
        self.assertIn("V10", self.codes(task, True))
        write(task / "out/extra.md", "# Ещё\n## Новый раздел\n<!-- пусто -->\n```\nне текст\n```\n")
        self.assertIn("V10", self.codes(task, True))
        self.assertNotIn("V10", self.codes(task))

    def test_v11_only_template_can_exempt(self) -> None:
        """Метка в документе не снимает опору, пометки и метка формы снимают."""
        task = clean(self.root)
        write(self.root / "templates/out/extra.md", "## Основание\n## Свободно\n<!-- без опоры -->\n")
        path = task / "out/extra.md"
        write(path, "## Основание\n<!-- без опоры -->\nТекст.\n## Свободно\nТекст.\n")
        self.assertIn("V11", self.codes(task, True))
        for marker in ("гипотеза", "Допущение", "не знаем", "[E1]"):
            write(path, f"## Основание\n{marker}\n## Свободно\nТекст.\n")
            self.assertNotIn("V11", self.codes(task, True))

    def test_v12_missing_state_journal_and_active_target(self) -> None:
        """Отсутствующие файлы и неверный указатель становятся нарушениями."""
        task = clean(self.root)
        for name in ("STATE.md", "journal.md"):
            path = task / name
            original = path.read_bytes()
            path.unlink()
            self.assertIn("V12", self.codes(task))
            path.write_bytes(original)
        write(self.root / "projects/ACTIVE.md", "- проект: demo\n- задача: 99-missing\n")
        self.assertIn("V12", self.codes(task))
