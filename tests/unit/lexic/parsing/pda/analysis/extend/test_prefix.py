"""Tests for lexic.parsing.pda.analysis.extend.prefix — whether a loop's complete
units can spell into what follows the loop."""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.ir import IrRuleRef
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.extend.prefix import COPIES, After, spelled, spells_into
from lexic.parsing.pda.core.charsets import CharSet


def _analysis(source: str) -> GrammarAnalysis:
    compiled = compile_text(source, cache_key=f"spell-{hash(source)}")
    return GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))


def _spells(unit: str, follower: str) -> bool:
    """Whether rule ``u`` spells into rule ``f``'s body, nothing past it."""
    analysis = _analysis(f"root ::= u f\nu ::= {unit}\nf ::= {follower}\n")
    return spells_into(
        analysis, IrRuleRef("u"), list(analysis.rules["f"].body[0]), None
    )


@pytest.mark.parametrize(
    ("unit", "follower", "expected"),
    [
        ('"ab"', '"abc"', True),
        ('"ab"', '"ab"', True),
        ('"ab"', '"ac"', False),
        ('"abc"', '"ab"', False),
        ('"#" [a-z]*', '"#" [a-z]* "\\n"', True),
        ('"#" [a-z]+', '"#" "\\n"', False),
        ('" " | "#" [a-z]*', '";" [a-z]*', False),
        ('"x" | "#" [a-z]* "\\n" " "', '"#" [a-z]* "\\n"', False),
        ("[a-z]*", '"x"', True),
        ('"a" ("b" | "c")', '"a" "c" "d"', True),
    ],
    ids=[
        "proper-prefix",
        "whole",
        "apart",
        "unit-longer",
        "comment-then-newline",
        "comment-needs-a-letter",
        "leads-apart",
        "every-shared-unit-longer",
        "empty-unit",
        "group-arm",
    ],
)
def test_a_complete_unit_at_the_cursor(
    unit: str, follower: str, expected: bool
) -> None:
    """A unit that is the whole of, or a proper prefix of, a follower string
    spells into it."""
    assert _spells(unit, follower) is expected


@pytest.mark.parametrize(
    ("unit", "follower", "expected"),
    [
        ("[ ]+", '" " "\\n"', True),
        ('"#" "#"?', '"#" "x"', True),
        ('"a" | "a" "b"', '"b" "c"', True),
        ('"a" | "a" "x"', '"b" "c"', False),
        ('("#" [a-z]* "\\n")+', '"#" [a-z]*', False),
    ],
    ids=[
        "run",
        "bounded",
        "only-past-a-shorter-unit",
        "past-apart",
        "longer-needs-newline",
    ],
)
def test_a_unit_running_past_a_shorter_one(
    unit: str, follower: str, expected: bool
) -> None:
    """Past a complete shorter unit, a longer one reads a nonempty prefix of
    a follower string — EXTEND's exact, local form. ``"a" | "a" "b"`` before
    ``"b" "c"`` is seen only this way: no unit begins ``bc``."""
    assert _spells(unit, follower) is expected


def test_recursion_and_wide_bounds_read_as_supersets() -> None:
    """A reference recurring on its path reads as ``Σ*``, and a bound past
    :data:`COPIES` as its star, so both answer yes too often, never too
    rarely."""
    assert _spells('"(" u ")" | "x"', '"((y)"') is True
    assert _spells('"(" u ")" | "x"', '"y"') is False
    assert _spells(f'"a"{{{COPIES + 1}}}', '"a"') is True
    assert _spells(f'"a"{{{COPIES}}}', '"a"') is False


def test_what_follows_a_follower_that_runs_out() -> None:
    """Past an inline group's end, one character of its FOLLOW and then
    anything; past a rule body's end, what follows the rule at its sites."""
    analysis = _analysis(
        'root ::= x "!" | "(" x "?" ")"\nx ::= "#" [a-z]* ";"\n'
        'u ::= "#" [a-z]* ";" "!"\nv ::= "#" [a-z]* ";" "-"\n'
    )
    items, unit = list(analysis.rules["x"].body[0]), IrRuleRef("u")
    assert (
        spells_into(analysis, unit, items, After(None, CharSet.from_chars("!"))) is True
    )
    assert (
        spells_into(analysis, unit, items, After(None, CharSet.from_chars("?")))
        is False
    )
    assert spells_into(analysis, unit, items, None) is False
    assert spells_into(analysis, unit, items, After("x", analysis.follow["x"])) is True
    assert (
        spells_into(analysis, IrRuleRef("v"), items, After("x", analysis.follow["x"]))
        is False
    )


def test_a_unit_side_is_built_once_and_a_lead_less_follower_builds_nothing() -> None:
    """Two followers share one unit side, each answered as if alone; a
    follower that starts with none of the unit's leads grows nothing."""
    analysis = _analysis(
        'root ::= u f g\nu ::= "#" [a-z]* | " "\nf ::= "#" "x" "\\n"\ng ::= ";"\n'
    )
    unit = IrRuleRef("u")
    side = spelled(analysis, unit)
    assert spelled(analysis, unit) is side
    assert spells_into(analysis, unit, list(analysis.rules["f"].body[0]), None) is True
    size = len(side.nfa.moves)
    assert spells_into(analysis, unit, list(analysis.rules["g"].body[0]), None) is False
    assert len(side.nfa.moves) == size
