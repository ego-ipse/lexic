"""Tests for lexic.compile.module.attach — runtime binding for twin-module classes."""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.compile.module.attach import attach_module
from lexic.exceptions import UnsupportedConstructError
from lexic.model import GrammarModel

BIND_TEXT = 'root ::= "a" mid "b"\nmid ::= "x" | "y"\n'
ALT_TEXT = 'root ::= a | b\na ::= "x"\nb ::= "y"\n'


class HandMid(GrammarModel):
    """A hand-built twin of the compiled ``mid`` class (a value_str rule)."""

    value: str


class HandRoot(GrammarModel):
    """A hand-built twin of the compiled ``root`` class (a sequence rule)."""

    mid: HandMid


def test_bind_module_attaches_grammar_and_binds_matching_the_runtime_classes():
    """A hand-authored namespace binds exactly like the runtime compile's own
    classes: same ``__grammar__`` and ``__binds__``."""
    cg = compile_text(BIND_TEXT, cache_key="bind-happy")

    attach_module(cg.grammar, {"Root": HandRoot, "Mid": HandMid})

    assert HandRoot.__grammar__ == cg.classes["Root"].__grammar__
    assert HandMid.__grammar__ == cg.classes["Mid"].__grammar__
    assert HandRoot.__binds__ == cg.classes["Root"].__binds__
    assert HandRoot(mid=HandMid(value="x")).to_text() == "axb"


def test_bind_module_raises_when_a_class_is_missing():
    """A namespace missing a rule's class names both the rule and the class."""
    cg = compile_text(BIND_TEXT, cache_key="bind-missing")
    with pytest.raises(UnsupportedConstructError, match="mid.*Mid"):
        attach_module(cg.grammar, {"Root": HandRoot})


def test_bind_module_raises_when_the_entry_is_not_a_grammar_model():
    """A namespace entry that exists but is not a GrammarModel subclass is
    rejected the same way as a missing entry."""
    cg = compile_text(BIND_TEXT, cache_key="bind-not-a-model")
    with pytest.raises(UnsupportedConstructError, match="Mid"):
        attach_module(cg.grammar, {"Root": HandRoot, "Mid": object})


def test_bind_module_raises_on_a_field_shape_mismatch():
    """A class whose declared fields do not match its rule's binding names
    both the declared and the expected fields."""

    class _WrongFieldMid(GrammarModel):
        wrong_field: str

    cg = compile_text(BIND_TEXT, cache_key="bind-mismatch")
    with pytest.raises(
        UnsupportedConstructError, match=r"\('wrong_field',\).*\('value',\)"
    ):
        attach_module(cg.grammar, {"Root": HandRoot, "Mid": _WrongFieldMid})


def test_bind_module_expects_no_fields_for_an_alternation_rule():
    """An alternation-kind rule binds no fields at all — a class declaring any
    is rejected."""
    cg = compile_text(ALT_TEXT, cache_key="bind-alternation")

    class _A(GrammarModel):
        value: str

    class _B(GrammarModel):
        value: str

    class _ExtraFieldRoot(GrammarModel):
        stray: str

    with pytest.raises(UnsupportedConstructError, match=r"\(\)"):
        attach_module(cg.grammar, {"Root": _ExtraFieldRoot, "A": _A, "B": _B})
