#!/usr/bin/env python3
"""Create a minimal, password-protected ZIP archive of the project."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

PROJECT_MARKER = "pyproject.toml"
DEFAULT_OUTPUT = Path("dist/activity-insights.zip")
PROJECT_FILES = (
    Path(".editorconfig"),
    Path(".github/workflows/ci.yml"),
    Path(".gitignore"),
    Path(".streamlit/config.toml"),
    Path("LICENSE"),
    Path("README.md"),
    Path("activity_processing.py"),
    Path("app.py"),
    Path("data_loading.py"),
    Path("pyproject.toml"),
    Path("reporting.py"),
    Path("scripts/clean.py"),
    Path("scripts/package.py"),
    Path("tests/test_activity_processing.py"),
    Path("tests/test_app.py"),
    Path("tests/test_clean.py"),
    Path("tests/test_data_loading.py"),
    Path("tests/test_package.py"),
    Path("tests/test_reporting.py"),
    Path("tests/test_theme.py"),
    Path("theme.py"),
)
SAMPLE_DATA_FILE = Path("data.csv")


def validate_project_root(root: Path) -> Path:
    root = root.resolve()
    if not root.is_dir() or not (root / PROJECT_MARKER).is_file():
        raise ValueError(f"Refusing to package {root}: {PROJECT_MARKER} was not found")
    return root


def collect_project_files(root: Path, *, include_sample_data: bool = False) -> list[Path]:
    root = validate_project_root(root)
    relative_paths = list(PROJECT_FILES)
    if include_sample_data:
        relative_paths.append(SAMPLE_DATA_FILE)

    missing = []
    for relative_path in relative_paths:
        source = root / relative_path
        if not source.is_file() or source.is_symlink():
            missing.append(str(relative_path))
    if missing:
        raise FileNotFoundError("Required regular files are missing: " + ", ".join(missing))
    return relative_paths


def verify_archive(archive: Path, expected_files: list[Path]) -> None:
    zipinfo = shutil.which("zipinfo")
    if zipinfo is None:
        raise RuntimeError("zipinfo is required to verify the encrypted archive")

    listing = subprocess.run(
        [zipinfo, "-1", str(archive)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    expected = [str(path) for path in expected_files]
    if listing != expected:
        raise RuntimeError("Archive contents do not match the project allowlist")

    details = subprocess.run(
        [zipinfo, "-v", str(archive)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    encrypted_entries = details.count("file security status:") - details.count(
        "file security status:                           not encrypted"
    )
    if encrypted_entries != len(expected_files):
        raise RuntimeError("Archive verification found one or more unencrypted entries")


def create_archive(
    root: Path,
    output: Path,
    *,
    include_sample_data: bool = False,
    force: bool = False,
) -> Path:
    root = validate_project_root(root)
    files = collect_project_files(root, include_sample_data=include_sample_data)
    output = output.expanduser()
    if not output.is_absolute():
        output = root / output
    output = output.resolve()
    source_paths = {(root / relative_path).resolve() for relative_path in files}
    if output in source_paths:
        raise ValueError(f"Archive output cannot replace a project source file: {output}")
    if output.exists() and not force:
        raise FileExistsError(f"{output} already exists; use --force to replace it")

    zip_executable = shutil.which("zip")
    if zip_executable is None:
        raise RuntimeError("The system 'zip' command is required")
    if not sys.stdin.isatty():
        raise RuntimeError("Run this script in an interactive terminal to enter the password safely")

    output.parent.mkdir(parents=True, exist_ok=True)

    temporary_archive = output.with_name(f".{output.stem}-{uuid.uuid4().hex}.zip")
    try:
        print("The ZIP utility will ask for the password twice.")
        print("Note: the system ZIP format uses traditional ZIP encryption, not AES.")
        subprocess.run(
            [zip_executable, "-e", str(temporary_archive), *map(str, files)],
            cwd=root,
            check=True,
        )
        verify_archive(temporary_archive, files)
        temporary_archive.replace(output)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"ZIP command failed with exit code {error.returncode}") from error
    finally:
        if temporary_archive.exists():
            temporary_archive.unlink()
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a minimal encrypted ZIP using an explicit project file allowlist."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Archive destination (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--include-sample-data",
        action="store_true",
        help="Include data.csv in the archive.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing archive after the new archive passes verification.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parent.parent
    try:
        archive = create_archive(
            project_root,
            args.output,
            include_sample_data=args.include_sample_data,
            force=args.force,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Packaging failed: {error}", file=sys.stderr)
        return 1

    print(f"Created encrypted archive: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
