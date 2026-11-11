"""Check smoke output locations without launching shells."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.tests import smoke


class SmokeTests(unittest.TestCase):
    """Keep smoke artifacts in unique directories under the selected base."""

    def test_default_uses_system_temporary_directory(self) -> None:
        """Use tempfile's default parent without a repository output path."""
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "run"
            destination.mkdir()
            with patch.object(smoke.tempfile, "mkdtemp", return_value=str(destination)) as create:
                with patch.object(smoke, "_initial"), patch.object(smoke, "_final"):
                    with patch("sys.argv", ["smoke", "--shell", "bash"]), redirect_stdout(io.StringIO()):
                        self.assertEqual(smoke.main(), 0)
            create.assert_called_once_with(prefix="t01-bash-", dir=None)
            self.assertTrue((destination / "output.txt").is_file())

    def test_explicit_output_preserves_existing_files(self) -> None:
        """Create unique runs under --out and preserve earlier output."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "вывод с пробелами"
            output.mkdir()
            previous = output / "output.txt"
            previous.write_text("сохранить", encoding="utf-8")
            with patch.object(smoke, "_initial"), patch.object(smoke, "_final"):
                for _ in range(2):
                    with patch("sys.argv", ["smoke", "--shell", "bash", "--out", str(output)]):
                        with redirect_stdout(io.StringIO()):
                            self.assertEqual(smoke.main(), 0)
            self.assertEqual(previous.read_text(encoding="utf-8"), "сохранить")
            self.assertEqual(len(list(output.glob("t01-bash-*/output.txt"))), 2)
