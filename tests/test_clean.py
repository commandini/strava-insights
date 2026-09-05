import tempfile
import unittest
from pathlib import Path

from scripts.clean import clean_project


class CleanProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        (self.root / "pyproject.toml").touch()
        (self.root / "app.py").write_text("# keep\n")

        for directory in (
            "build",
            "output",
            "package.egg-info",
            "src/__pycache__",
            ".venv/__pycache__",
        ):
            path = self.root / directory
            path.mkdir(parents=True)
            (path / "artifact").touch()
        (self.root / ".coverage").touch()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_dry_run_does_not_remove_discovered_targets(self) -> None:
        targets = clean_project(self.root, dry_run=True)

        self.assertIn(self.root / "build", targets)
        self.assertIn(self.root / "src/__pycache__", targets)
        self.assertTrue((self.root / "build").exists())

    def test_removes_artifacts_and_preserves_protected_content(self) -> None:
        clean_project(self.root)

        self.assertFalse((self.root / "build").exists())
        self.assertFalse((self.root / "output").exists())
        self.assertFalse((self.root / "package.egg-info").exists())
        self.assertFalse((self.root / "src/__pycache__").exists())
        self.assertFalse((self.root / ".coverage").exists())
        self.assertTrue((self.root / ".venv/__pycache__").exists())
        self.assertTrue((self.root / "app.py").exists())

    def test_refuses_to_clean_a_directory_without_project_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                clean_project(Path(directory))


if __name__ == "__main__":
    unittest.main()
