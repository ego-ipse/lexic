"""Permanent size and documentation gates for the source tree."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SOURCE_ROOT = ROOT / "src"
BENCHMARK_ROOT = ROOT / "tools" / "benchmark"
MAINTAINED_ROOTS = (SOURCE_ROOT, BENCHMARK_ROOT)
MAX_SOURCE_LINES = 700
MAX_FOLDER_FILES = 6


def source_files() -> list[Path]:
    """Maintained source files, excluding interpreter cache artefacts."""
    return sorted(
        path
        for root in MAINTAINED_ROOTS
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )


def active_source_dirs() -> set[Path]:
    """Directories containing maintained files, up through their owned root."""
    active = set(MAINTAINED_ROOTS)
    for root in MAINTAINED_ROOTS:
        for path in source_files():
            if not path.is_relative_to(root):
                continue
            parent = path.parent
            while parent.is_relative_to(root):
                active.add(parent)
                if parent == root:
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


EFFORT_DIR = "zzz_current_work"
"""The gitignored working directory. Committed files must not point into it."""


def _tracked_python() -> list[Path]:
    """Committed Python under ``src/`` and ``tests/``, this gate excepted.

    A gate has to name what it forbids, so its own file matches the pattern it
    exists to catch. Excepting exactly one file — this one — is cheaper than
    assembling the needle at runtime to dodge a grep.
    """
    here = Path(__file__).resolve()
    roots = (ROOT / "src", ROOT / "tests")
    return sorted(
        path
        for root in roots
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path.resolve() != here
    )


def test_committed_code_does_not_cite_the_gitignored_effort_directory() -> None:
    """A citation into ``zzz_current_work`` is a dangling reference on clone.

    The directory is gitignored, so anyone who checks this repo out reads a
    pointer to a path that does not exist — and the pointer usually stands in
    for the explanation rather than beside it, so the reasoning is lost with
    it. Docstrings state the architecture in the present tense; where a
    decision needs its history, the wiki carries it.
    """
    citing = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in _tracked_python()
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        )
        if EFFORT_DIR in line
    ]
    assert not citing, (
        f"{len(citing)} committed lines cite {EFFORT_DIR}/, which is not in the "
        "repository. State the fact instead of pointing at the working note:\n  "
        + "\n  ".join(citing)
    )
