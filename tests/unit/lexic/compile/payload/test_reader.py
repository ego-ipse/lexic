"""The reader is lexic-free — by its SOURCE, and by a fresh interpreter.

Stated precisely, because the obvious phrasing is false: the module as it sits in
the tree is *not* lexic-free to import. It lives under ``lexic.compile``, so
importing it by path runs the package root and then ``lexic.compile.__init__``,
which is the seam onto the engine. What is lexic-free is the reader's SOURCE, and
that is the form an artefact carries — a payload inlines it, which is also what
makes the artefact self-contained against a newer reader.
"""

from __future__ import annotations

import ast as pyast
import subprocess
import sys

import pytest

from lexic.compile.payload import project, reader
from tests.paths import PROJECT_ROOT

SOURCE = PROJECT_ROOT / "src" / "lexic" / "compile" / "payload" / "reader.py"


def test_the_reader_source_imports_no_lexic() -> None:
    """Read from its AST: not one import names the package it lives in."""
    tree = pyast.parse(SOURCE.read_text(encoding="utf-8"))
    modules = {
        alias.name
        for node in pyast.walk(tree)
        if isinstance(node, pyast.Import)
        for alias in node.names
    } | {
        node.module
        for node in pyast.walk(tree)
        if isinstance(node, pyast.ImportFrom) and node.module
    }
    assert not [m for m in modules if m.split(".")[0] == "lexic"], sorted(modules)


def test_an_inlined_reader_decodes_a_payload_with_zero_lexic_modules() -> None:
    """The cycle the property defends: inline the source, decode, in a child.

    In this process every lexic module is resident, so the question cannot be
    asked here at all — and importing the reader by path would answer it wrongly,
    because that runs the compile seam.
    """
    payload = project(({"a": [1, 2]}, "x", 3.5, None))
    script = (
        SOURCE.read_text(encoding="utf-8") + "\nimport sys\n"
        f"VALUE = decode({payload.types!r}, {payload.strs!r}, {payload.nodes!r},"
        f" {{}}, {payload.digest()!r})\n"
        "assert VALUE == ({'a': [1, 2]}, 'x', 3.5, None), VALUE\n"
        "print(len([m for m in sys.modules if m.startswith('lexic')]))\n"
    )
    got = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src")},
    )
    assert got.stdout.strip() == "0"


def test_child_slots_covers_every_kind() -> None:
    """The arity table and the decoder table are the same length, or a kind lies."""
    assert len(reader.CHILD_SLOTS) == len(reader.DECODE)


def test_an_empty_table_refuses_rather_than_indexing_off_the_end() -> None:
    """``built[-1]`` on nothing is an IndexError; the refusal says what happened."""
    with pytest.raises(ValueError, match="empty"):
        reader.decode(("<plain>",), (), (), {})
