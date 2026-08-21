"""Permanent size and documentation gates for the source tree."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SOURCE_ROOT = ROOT / "src"
MAX_SOURCE_LINES = 700
MAX_FOLDER_FILES = 6


def source_files() -> list[Path]:
    """Regular source-tree files, excluding interpreter cache artefacts."""
    return sorted(
        path
        for path in SOURCE_ROOT.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )


def active_source_dirs() -> set[Path]:
    """Directories containing a source file below them, up through ``src``."""
    active = {SOURCE_ROOT}
    for path in source_files():
        parent = path.parent
        while parent.is_relative_to(SOURCE_ROOT):
            active.add(parent)
            if parent == SOURCE_ROOT:
                break
            parent = parent.parent
    return active


def test_python_source_files_do_not_exceed_700_lines() -> None:
    """The 1h maintainability ceiling applies to every Python source file."""
    oversized = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in source_files()
        if path.suffix == ".py"
        and len(path.read_text(encoding="utf-8").splitlines()) > MAX_SOURCE_LINES
    }
    assert not oversized, f"source files exceed {MAX_SOURCE_LINES} lines: {oversized}"


def test_source_folders_have_at_most_six_files() -> None:
    """Count README and data files; exempt only the package marker."""
    crowded: dict[str, list[str]] = {}
    for directory in active_source_dirs():
        files = sorted(
            path.name
            for path in directory.iterdir()
            if path.is_file()
            and path.name != "__init__.py"
            and path.suffix not in {".pyc", ".pyo"}
        )
        if len(files) > MAX_FOLDER_FILES:
            crowded[str(directory.relative_to(ROOT))] = files
    assert not crowded, f"source folders exceed {MAX_FOLDER_FILES} files: {crowded}"


def test_every_active_source_folder_has_a_readme() -> None:
    """Each maintained source directory explains its responsibility boundary."""
    missing = sorted(
        str(directory.relative_to(ROOT))
        for directory in active_source_dirs()
        if not (directory / "README.md").is_file()
    )
    assert not missing, f"source folders missing README.md: {missing}"
