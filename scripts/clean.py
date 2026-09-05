#!/usr/bin/env python3
"""Remove generated project artifacts without touching source or environments."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
from pathlib import Path

PROJECT_MARKER = "pyproject.toml"
PROTECTED_TOP_LEVEL = {".git", ".idea", ".venv", "venv"}
GENERATED_TOP_LEVEL = {"build", "dist", "htmlcov", "output", "tmp"}
CACHE_DIRECTORIES = {"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
GENERATED_FILE_SUFFIXES = {".pyc", ".pyo"}


def validate_project_root(root: Path) -> Path:
    root = root.resolve()
    if not root.is_dir() or not (root / PROJECT_MARKER).is_file():
        raise ValueError(f"Refusing to clean {root}: {PROJECT_MARKER} was not found")
    return root


def discover_targets(root: Path) -> list[Path]:
    """Return generated paths while pruning protected directories."""
    root = validate_project_root(root)
    targets: set[Path] = set()

    for name in GENERATED_TOP_LEVEL:
        candidate = root / name
        if candidate.exists() or candidate.is_symlink():
            targets.add(candidate)

    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories[:] = [name for name in directories if name not in PROTECTED_TOP_LEVEL]
        if current_path == root:
            directories[:] = [name for name in directories if name not in GENERATED_TOP_LEVEL]

        for name in directories:
            candidate = current_path / name
            if name in CACHE_DIRECTORIES or name.endswith(".egg-info"):
                targets.add(candidate)
                directories.remove(name)

        for name in files:
            candidate = current_path / name
            if name == ".coverage" or name.startswith(".coverage."):
                targets.add(candidate)
            elif candidate.suffix in GENERATED_FILE_SUFFIXES:
                targets.add(candidate)

    return sorted(targets, key=lambda path: (len(path.parts), str(path)), reverse=True)


def _make_writable_and_retry(function, path: str, _error_info) -> None:
    os.chmod(path, os.stat(path, follow_symlinks=False).st_mode | stat.S_IWUSR)
    function(path)


def remove_target(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path, onerror=_make_writable_and_retry)


def clean_project(root: Path, *, dry_run: bool = False) -> list[Path]:
    targets = discover_targets(root)
    if not dry_run:
        failures = []
        for target in targets:
            try:
                remove_target(target)
            except OSError as error:
                failures.append(f"{target}: {error}")
        if failures:
            raise RuntimeError("Could not remove:\n" + "\n".join(failures))
    return targets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove generated files while preserving source code and virtual environments."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting anything.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parent.parent
    try:
        targets = clean_project(project_root, dry_run=args.dry_run)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Clean failed: {error}", file=sys.stderr)
        return 1

    action = "Would remove" if args.dry_run else "Removed"
    if targets:
        for target in targets:
            print(f"{action}: {target.relative_to(project_root)}")
    else:
        print("Project is already clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
