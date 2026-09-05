import tempfile
import unittest
from pathlib import Path

from scripts.package import PROJECT_FILES, collect_project_files, create_archive


class PackageProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        for relative_path in (*PROJECT_FILES, Path("data.csv")):
            path = self.root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_uses_an_explicit_minimal_allowlist(self) -> None:
        (self.root / "secret.env").touch()

        files = collect_project_files(self.root)

        self.assertEqual(files, list(PROJECT_FILES))
        self.assertNotIn(Path("secret.env"), files)
        self.assertNotIn(Path("data.csv"), files)

    def test_sample_data_is_opt_in(self) -> None:
        files = collect_project_files(self.root, include_sample_data=True)

        self.assertEqual(files[-1], Path("data.csv"))

    def test_rejects_a_symlinked_project_file(self) -> None:
        app = self.root / "app.py"
        app.unlink()
        app.symlink_to(self.root / "theme.py")

        with self.assertRaises(FileNotFoundError):
            collect_project_files(self.root)

    def test_refuses_to_overwrite_an_allowlisted_source_file(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot replace a project source file"):
            create_archive(self.root, Path("app.py"), force=True)


if __name__ == "__main__":
    unittest.main()
