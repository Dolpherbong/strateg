"""Проверки общего разбора записей и ссылок."""

from pathlib import Path
import tempfile
import unittest

from tools.tests.fixtures import record, write


class RecordsTests(unittest.TestCase):
    """Проверяет границы записей, маскирование и ссылки."""

    def test_comments_code_and_lines(self) -> None:
        """Образцы не становятся записями, номера строк сохраняются."""
        from tools.lib.records import parse_records
        text = ("<!--\n### E99\n-->\n```md\n### E98\n```\n~~~\n### E97\n~~~\n"
                "### E1 Название\n- ТЕКСТ : Цена: 450 [E2, C3]\n- источник: S1\n"
                "<!-- [E900] -->\n#### Конец\n- опора: E44\n### E2\n- текст: свой\n")
        records = parse_records(Path("evidence.md"), text)
        self.assertEqual([r.id for r in records], ["E1", "E2"])
        self.assertEqual(records[0].line, 10)
        self.assertEqual(records[0].fields["текст"], "Цена: 450 [E2, C3]")
        self.assertEqual(set(records[0].refs), {"E2", "C3", "S1"})
        self.assertNotIn("E44", records[0].text)

    def test_reference_syntax(self) -> None:
        """Ссылки отличаются от номеров в тексте и пометок."""
        from tools.lib.records import references
        text = ("- источник: свой\n- основание: E1, E2\n- текст: E77 [гипотеза] [C3, E4]\n"
                "- где: https://example.org/E88\n<!-- [E90] -->\n```\n[E91]\n```\n")
        self.assertEqual(set(references(text)), {"E1", "E2", "C3", "E4"})

    def test_sections_and_nested_headings(self) -> None:
        """Раздел включает записи, но заканчивается перед следующим разделом."""
        from tools.lib.records import sections
        result = sections("# Тест\n## Первый\n<!-- скрыто -->\n### C1\n- опора: E1\n"
                          "## Второй\n```\n## Ложный\n```\nТекст\n# Конец\nне входит")
        self.assertEqual([s.title for s in result], ["Первый", "Второй"])
        self.assertIn("### C1", result[0].text)
        self.assertNotIn("не входит", result[1].text)

    def test_project_scan_ignores_inbox(self) -> None:
        """Обход видит все задачи и рабочие файлы, но не исходные материалы."""
        from tools.lib.records import load_project
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            write(root / "evidence.md", record("E1", текст="русский"))
            write(root / "tasks/02-two/work/extra.md", record("E7", текст="ещё"))
            write(root / "inbox/document.md", record("E99", текст="данные"))
            self.assertEqual([r.id for r in load_project(root).records], ["E1", "E7"])
