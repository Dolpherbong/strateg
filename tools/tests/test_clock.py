"""Check that cost reports elapsed wall time from journal timestamps."""

from pathlib import Path
import tempfile
import unittest

from tools.lib.journal import cost

HEADER = (
    "# Журнал задачи\n\n"
    "| № | когда | этап | действие | средство | итог | мин | ток., тыс. | ₽ | ключ | статус |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|\n"
)


def _journal(rows: str) -> Path:
    """Create a temporary task directory with the given journal rows."""
    task = Path(tempfile.mkdtemp())
    (task / "journal.md").write_text(HEADER + rows, encoding="utf-8")
    return task


class ClockTests(unittest.TestCase):
    """Wall time comes from the clock column, not from model estimates."""

    def test_elapsed_minutes_from_first_to_last_timestamp(self) -> None:
        """Skip date-only rows and count minutes across midnight."""
        task = _journal(
            "| 1 | 2026-11-11 | 1 | создана задача | скрипт | папка | 0 | 0 | 0 | new-task | готово |\n"
            "| 2 | 2026-11-11 23:50 | 1 | постановка | сильная модель | бриф | ~40 |  |  | e1 | готово |\n"
            "| 3 | 2026-11-12 00:20 | 2 | опись | чтение | реестр | ~30 |  |  | e2 | готово |\n"
        )
        lines = cost(task)
        self.assertIn("По часам: с 2026-11-11 23:50 по 2026-11-12 00:20, 30 мин", lines)

    def test_not_enough_timestamps(self) -> None:
        """Say so when fewer than two rows carry a time of day."""
        task = _journal("| 1 | 2026-11-11 | 1 | создана задача | скрипт | папка | 0 | 0 | 0 | new-task | готово |\n")
        self.assertIn("По часам: меньше двух отметок времени", cost(task))


if __name__ == "__main__":
    unittest.main()
