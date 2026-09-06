"""Island valid-prefix regression — window truncation must fail SOFT.

The island sub-parse runs a doubling character window (256 …) whose growth
heuristic is "grow while the best completion touches the window edge". A
language with the *valid-prefix property* (bare identifiers) defeats it: when
the window cuts a token, the truncated text can complete as a VALID island
parse strictly inside the window — no edge touch, no growth — and the spliced
sub-model is wrong. The first thing to notice is the fold (an unknown-symbol
``LexicError``), which must reroute to ``PdaFail`` so the Earley completion
(whole input, same fold) becomes the authority — on the splice path
(``island_value``) and on the island-interior delegate path
(``finish_delegate`` declining).

The fixture is a mini comma-list grammar whose ``list ::= value rest* comma?``
shape is ungateable (the ``rest`` loop and the optional trailing comma share
FIRST = ','), so ``list`` islands — asserted below so the fixture can never
silently stop exercising the island path. The name fold resolves against a
whitelist, exactly like the notation's symbol table: a truncated identifier
is a *valid parse* whose fold refuses.
"""

from __future__ import annotations

from lexic.compile.notation.parse import load_ir
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.gbnf import GBNF_GRAMMAR
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.products import parse_model
from tests.integration.lexic.parity.island_fixtures import (
    BINDING,
    GRAMMAR,
    NAME_A,
    NAME_B,
    NOTATION_VARIANT_BINDING,
    NOTATION_VARIANT_GRAMMAR,
    WINDOW_CUT_CALL,
)


def test_the_fixture_list_rule_actually_islands():
    """``list`` must stay an island — the fixture's licence. Its
    left-recursive arm pins that against any future gate sharpening
    (structured separators now gate the plain trailing-comma shape)."""
    analysis = GrammarAnalysis(lift_optional_nullables(GRAMMAR))
    assert "list" in analysis.islands


def test_window_cut_identifier_fails_soft_to_the_completion():
    """An identifier straddling the 256 window parses correctly end-to-end."""
    text = f"{NAME_A}, {NAME_B}"
    assert parse_model(GRAMMAR, text, BINDING) == ["A", "B"]


def test_window_cut_with_trailing_comma_and_noise():
    """Same crossing with the variant's motivating syntax (trailing comma)."""
    text = f"  {NAME_A} ,\n {NAME_B} , "
    assert parse_model(GRAMMAR, text, BINDING) == ["A", "B"]


def test_a_genuine_unknown_name_still_errors():
    """A real fold error reproduces on the Earley completion — never muted."""
    try:
        parse_model(GRAMMAR, "zzz", BINDING)
    except UnsupportedConstructError as exc:
        assert "zzz" in str(exc) or "parse" in str(exc)
    else:
        raise AssertionError("unknown name must surface an error")


def test_notation_variant_window_cut_call_parses_correctly():
    """The splice-path truncation reroutes; the product returns the truth."""
    got = parse_model(
        NOTATION_VARIANT_GRAMMAR, WINDOW_CUT_CALL, NOTATION_VARIANT_BINDING
    )
    assert got == load_ir(WINDOW_CUT_CALL)


def test_notation_variant_full_self_grammar_repr_round_trips():
    """A whole self-grammar repr (many window crossings) round-trips."""
    got = parse_model(
        NOTATION_VARIANT_GRAMMAR,
        repr(GBNF_GRAMMAR),
        NOTATION_VARIANT_BINDING,
    )
    assert got == GBNF_GRAMMAR
