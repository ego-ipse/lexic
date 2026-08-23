"""The shared module writer — the line budget, and the two-file atomicity.

Every ``.py`` lexic emits goes out through here, and the ``.pyc`` beside it
outranks its source unconditionally. So the properties worth pinning are the
ones a crash or a second process could break, not the happy path.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from lexic.compile.output.writer import WIDTH, literal, write_module
from lexic.exceptions import UnsupportedConstructError


def _read_back(tmp_path, rendered: str, stem: str = "lit") -> str:
    """Put a rendered assignment in a module and read ``X`` back from an import.

    Through the file and a fresh interpreter rather than ``eval``: the claim is
    about what Python makes of the text that lands on disk.

    :param tmp_path: The directory to write into.
    :param rendered: A rendered ``X = ...`` assignment.
    :param stem: The module name.
    :returns: ``repr(X)`` as the fresh interpreter sees it.
    """
    write_module(tmp_path / f"{stem}.py", rendered + "\n")
    got = subprocess.run(
        [sys.executable, "-c", f"import {stem}; print(repr({stem}.X))"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return got.stdout.strip()


def test_a_long_string_element_stays_within_the_line_budget(tmp_path) -> None:
    """Adjacent string literals concatenate, which is how a long string wraps."""
    value = ("a" * 400,)
    rendered = literal("X = ", value)
    assert max(len(line) for line in rendered.splitlines()) <= WIDTH
    assert _read_back(tmp_path, rendered) == repr(value)


@pytest.mark.parametrize("length", range(80, 96))
def test_an_element_just_under_the_budget_does_not_overrun(length: int) -> None:
    """The decision to chunk is made against the budget the chunks are cut to.

    Measured against the raw width instead, an element that just fits is still
    one nest in and still carries a comma, and the line lands up to five over.
    """
    rendered = literal("X = ", ("a" * length,))
    assert max(len(line) for line in rendered.splitlines()) <= WIDTH


def test_a_long_int_is_rendered_within_the_line_budget(tmp_path) -> None:
    """An int literal cannot be split, and ``NODES`` holds arbitrary widths."""
    value = (10**300, -(10**200))
    rendered = literal("X = ", value)
    assert max(len(line) for line in rendered.splitlines()) <= WIDTH
    assert _read_back(tmp_path, rendered) == repr(value)


def test_a_non_finite_float_has_no_literal_spelling() -> None:
    """``nan`` and ``inf`` repr as bare NAMES — valid Python, NameError at import."""
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(UnsupportedConstructError, match="no literal spelling"):
            literal("X = ", (value,))


def test_a_stale_pyc_never_outranks_a_module_written_after_it(tmp_path) -> None:
    """The read must agree with the source, in a FRESH interpreter.

    ``UNCHECKED_HASH`` makes the ``.pyc`` win outright, so any moment the two
    disagree is a moment the module reads as a wrong value.
    """
    target = tmp_path / "mod.py"
    write_module(target, "VALUE = 1\n")
    write_module(target, "VALUE = 2\n")
    got = subprocess.run(
        [sys.executable, "-c", "import mod; print(mod.VALUE)"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert got.stdout.strip() == "2"


def test_the_staged_name_is_not_derived_from_the_target(tmp_path) -> None:
    """Two exports into one directory must not share a scratch path.

    A staged name derived only from the target is one name for every process
    writing that file, and each one's cleanup deletes the other's mid-write.
    """
    target = tmp_path / "mod.py"
    decoy = tmp_path / "mod.py.staged"
    decoy.write_text("# a file that merely looks like scratch\n", encoding="utf-8")
    write_module(target, "VALUE = 1\n")
    assert decoy.read_text(encoding="utf-8").startswith("# a file")
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"


def test_nothing_lands_when_the_source_is_not_python(tmp_path) -> None:
    """A previous module and its ``.pyc`` are a matched pair; keep them matched."""
    target = tmp_path / "mod.py"
    write_module(target, "VALUE = 1\n")
    with pytest.raises(UnsupportedConstructError):
        write_module(target, "VALUE = (\n")
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
