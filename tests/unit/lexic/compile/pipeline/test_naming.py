"""Tests for lexic.compile.pipeline.naming — class and field spelling.

``compute_binding`` (compile/pipeline/binding.py) is the consumer of TIER2/
``_HINT``/``has_ruleref`` and is where their choices get exercised end to end
against real grammars; this file targets naming.py's own pure functions.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.compile.pipeline.naming import (
    CHARCLASS_NAMES,
    RESERVED_FIELD_NAMES,
    class_name_for,
    has_ruleref,
)
from lexic.ir import IrAlternation, IrLiteral, IrRuleRef, IrSequence


@pytest.mark.parametrize(
    "rule_name,expected",
    [
        ("root", "Root"),
        ("jp-char", "JpChar"),
        ("snake_case_name", "SnakeCaseName"),
        ("a", "A"),
    ],
)
def test_class_name_for_pascal_cases_hyphen_and_underscore_words(rule_name, expected):
    """A rule name's hyphen/underscore words each capitalise into PascalCase."""
    assert class_name_for(rule_name) == expected


def test_class_name_for_suffixes_a_python_keyword():
    """A rule named after a keyword (``true`` → ``True``) gets a trailing
    underscore so it stays a legal class name."""
    assert class_name_for("true") == "True_"


def test_class_name_for_suffixes_a_reserved_header_name():
    """A rule whose Pascal form collides with the exporter's own header
    bindings (e.g. ``ir-rule`` → ``IrRule``) also gets suffixed."""
    assert class_name_for("ir-rule") == "IrRule_"


def test_has_ruleref_true_when_a_ruleref_is_anywhere_in_the_subtree():
    """A subtree containing an IrRuleRef anywhere reports True."""
    body = IrAlternation(IrSequence(IrLiteral("a"), IrRuleRef("other")))
    assert has_ruleref(body) is True


def test_has_ruleref_false_for_a_ruleref_free_subtree():
    """A subtree with no IrRuleRef at all reports False."""
    body = IrAlternation(IrSequence(IrLiteral("a"), IrLiteral("b")))
    assert has_ruleref(body) is False


def test_charclass_names_cover_the_documented_library_entries():
    """The library maps the documented bracketed patterns to their names."""
    assert CHARCLASS_NAMES["[0-9]"] == "digit"
    assert CHARCLASS_NAMES["[A-Za-z]"] == "letter"


def test_reserved_field_names_includes_python_keywords_and_model_methods():
    """The reserved set covers keywords and the GrammarModel/IrSelf protocol."""
    assert "class" in RESERVED_FIELD_NAMES  # a Python keyword
    assert "to_text" in RESERVED_FIELD_NAMES  # a GrammarModel method
    assert "bind" in RESERVED_FIELD_NAMES  # the inherited spine protocol


def test_a_charclass_library_name_reaches_the_generated_field_name():
    """End-to-end sanity: a digit-class field in a real grammar is named from
    the library, not a positional fallback."""
    cg = compile_text(
        'root ::= [0-9] other\nother ::= "y"\n', cache_key="naming-digit-field"
    )
    assert cg.classes["Root"]._fields == ("digit", "other")
