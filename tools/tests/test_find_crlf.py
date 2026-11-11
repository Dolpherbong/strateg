"""Check that find prints records from CRLF files without blank lines between fields."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]


class FindCrlfTests(unittest.TestCase):
    """Records written by Windows tools keep one line per field in find output."""

    def test_find_output_has_no_doubled_line_breaks(self) -> None:
        """A CRLF evidence file prints each field on its own line."""
        root = Path(tempfile.mkdtemp()) / "корень с пробелом"
        shutil.copytree(REPO / "templates", root / "templates")
        shutil.copytree(REPO / "tools", root / "tools", ignore=shutil.ignore_patterns("tests", "__pycache__"))
        (root / "projects").mkdir()
        (root / "projects" / "ACTIVE.md").write_text("# Активная задача\n\n- проект: нет\n- задача: нет\n", encoding="utf-8")
        script = [sys.executable, str(root / "tools" / "strateg.py")]
        subprocess.run([*script, "new", "project", "demo"], check=True, capture_output=True)
        evidence = root / "projects" / "demo" / "evidence.md"
        record = "### E1\r\n- текст: Цена 450 рублей\r\n- вид: гипотеза\r\n- как проверить: опрос\r\n"
        with evidence.open("a", encoding="utf-8", newline="") as stream:
            stream.write("\r\n" + record)
        result = subprocess.run([*script, "find", "E1", "--project", "demo"], capture_output=True)
        text = result.stdout.decode("utf-8").replace("\r\n", "\n")
        self.assertIn("### E1\n- текст: Цена 450 рублей\n- вид: гипотеза", text)


if __name__ == "__main__":
    unittest.main()
