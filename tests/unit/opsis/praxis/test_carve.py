"""Carve contract — read_shape, read_spec, and the extraction itself."""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.compile.templating import KEEP
from lexic.exceptions import UnsupportedConstructError
from opsis.praxis.carve import Shape, carve, read_shape, read_spec

_TOY = r"""
# One formulation of a nested key=value map. Deliberately NOT the
# spelling lexic's own templating tests use: templating is defined over
# a shape, not over a grammar somebody privileged, so a second spelling
# of the same language is the honest fixture.
doc ::= gap group gap
group ::= "(" gap pairs gap ")"
pairs ::= pair tail*
tail ::= gap "," gap pair
pair ::= label gap "=" gap thing
label ::= [a-z]+
thing ::= digits | group
digits ::= [0-9]+
gap ::= [ \t\n]*
# @start doc
# @non-semantic gap
"""

_TOY_COMPILED = compile_text(_TOY)
_TOY_DOC = "(a=1, b=(c=22, d=(e=3)), f=4)"


def test_read_shape_parses_four_comma_separated_names() -> None:
    """A full shape names section, entry, key and value in order."""
    assert read_shape("a, b, c, d") == Shape("a", "b", "c", "d")


def test_read_shape_partial_is_not_stated() -> None:
    """Fewer than four names leaves the shape incomplete."""
    shape = read_shape("sect, entry")
    assert shape.stated is False


def test_read_spec_builds_nesting_from_dotted_lines() -> None:
    """A dotted path deepens the spec tree at every step."""
    spec = read_spec("f\nb.c\nb.d.e")
    assert set(spec.keys()) == {"f", "b"}
    assert spec["f"] is KEEP
    nested = spec["b"]
    assert set(nested.keys()) == {"c", "d"}
    assert nested["c"] is KEEP
    assert set(nested["d"].keys()) == {"e"}
    assert nested["d"]["e"] is KEEP


def test_read_spec_ignores_blanks_and_comments() -> None:
    """Blank lines and ``#`` comments contribute nothing to the spec."""
    spec = read_spec("\n# a whole comment line\nf  # trailing comment\n\n")
    assert set(spec.keys()) == {"f"}


def test_carve_with_an_incomplete_shape_raises() -> None:
    """Fewer than four rule names cannot address a mapping level at all."""
    with pytest.raises(UnsupportedConstructError, match="all four names"):
        carve(_TOY_COMPILED, Shape("sect"), "f", _TOY_DOC)


def test_carve_with_an_empty_spec_raises() -> None:
    """A spec naming no paths keeps nothing, which is refused rather than silent."""
    shape = Shape("group", "pair", "label", "thing")
    with pytest.raises(UnsupportedConstructError, match="nothing to keep"):
        carve(_TOY_COMPILED, shape, "", _TOY_DOC)


def test_carve_with_a_section_rule_not_in_the_grammar_names_it() -> None:
    """A shape naming a rule the grammar does not have says which one."""
    shape = Shape("nope", "pair", "label", "thing")
    with pytest.raises(UnsupportedConstructError, match="nope"):
        carve(_TOY_COMPILED, shape, "f", _TOY_DOC)


def test_carve_extracts_the_named_paths() -> None:
    """A working shape and spec extract exactly the paths asked for."""
    shape = Shape("group", "pair", "label", "thing")
    result = carve(_TOY_COMPILED, shape, "f\nb.c\nb.d.e", _TOY_DOC)
    values = dict(result.paths)
    assert values == {"f": "4", "b.c": "22", "b.d.e": "3"}
