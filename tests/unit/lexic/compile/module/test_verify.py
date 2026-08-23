"""Tests for lexic.compile.module.verify — the L2 exporter/binding cross-check.

Deep tamper-matrix coverage lives in ``test_selfgrammar.py`` (verify_module
re-exported off ``lexic.compile``); this file exercises the module's own
narrow surface directly.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path, export_source, parse_module
from lexic.compile.module.verify import verify_module
from lexic.exceptions import UnsupportedConstructError
from tests.paths import GROUND_TRUTH

ARITHMETIC = GROUND_TRUTH / "arithmetic.gbnf"
LIST_GRAMMAR = GROUND_TRUTH / "list.gbnf"


@pytest.mark.parametrize("inline_tables", [False, True])
def test_verify_module_returns_the_parsed_model_for_a_real_export(inline_tables: bool):
    """A genuine export verifies clean and returns what parse_module returns,
    in both bind and inline-table modes."""
    compiled = compile_from_path(ARITHMETIC)
    source = export_source(compiled, inline_tables=inline_tables)
    assert verify_module(compiled, source) == parse_module(source)


def test_verify_module_refuses_a_grammar_mismatch():
    """A module's embedded GRAMMAR checked against an unrelated compiled
    grammar names the mismatch."""
    list_compiled = compile_from_path(LIST_GRAMMAR)
    arithmetic_source = export_source(compile_from_path(ARITHMETIC))
    with pytest.raises(UnsupportedConstructError, match="GRAMMAR"):
        verify_module(list_compiled, arithmetic_source)


def test_verify_module_refuses_a_class_count_mismatch():
    """Deleting a class from the source drops the class count below the
    binding view's, and the refusal names both counts."""
    compiled = compile_from_path(ARITHMETIC)
    source = export_source(compiled)
    lines = source.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith("class "))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("class "))
    tampered = "".join(lines[:start] + lines[end:])
    with pytest.raises(UnsupportedConstructError, match="classes"):
        verify_module(compiled, tampered)


def test_verify_module_refuses_a_renamed_base_class():
    """A class whose base no longer matches the binding's parent chain
    refuses naming the class."""
    compiled = compile_from_path(ARITHMETIC)
    source = export_source(compiled)
    tampered = source.replace("(GrammarModel):", "(object):", 1)
    with pytest.raises(UnsupportedConstructError):
        verify_module(compiled, tampered)
