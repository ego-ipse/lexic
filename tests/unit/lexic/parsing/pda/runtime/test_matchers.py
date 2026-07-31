"""Tests for lexic.parsing.pda.runtime.matchers — the recognition leaf.

Terminal matching as free functions over the input text: arm selection, a
literal's or char class's whole quantifier loop, a whole all-terminal arm, and
one ``value_str`` iteration. Every ``FlatArm`` / ``FlatClone`` here comes from a
real compiled PDA — the module's inputs are the compiler's outputs, so no fake
one is constructed.
"""

from __future__ import annotations

import pytest

from lexic.compile import canonical_grammar, compile_text
from lexic.compile.pipeline.passes import build_codegen_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.compiler.clones import compile_pda
from lexic.parsing.pda.compiler.flatten import (
    OP_CC,
    OP_LIT,
    OP_VSTR,
    all_clones,
)
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.kernel.reduce_runtime import pda_model
from lexic.parsing.pda.runtime.matchers import (
    match_arm,
    match_cc,
    match_lit,
    select_arm,
    vstr_once,
)


def pda_for(text: str):
    """The compiled PDA tables for a GBNF source, through the public seams."""
    canonical = canonical_grammar(text, GBNF_FLAVOUR)
    lifted = lift_optional_nullables(build_codegen_grammar(canonical))
    compiled = compile_text(text, flavour="gbnf")
    return compile_pda(lifted, normalize(lifted), compiled.fold.config), compiled


def arms_of(clone):
    """Every arm a clone can select — its FIRST-gated ones plus its default."""
    arms = [selector[2] for selector in clone.selectors]
    if clone.default is not None:
        arms.append(clone.default)
    return arms


def first_item(tables, kind: int):
    """The first ``(arm, index)`` in the program whose item carries ``kind``.

    :raises AssertionError: When the grammar compiled no such item — the test
        would otherwise pass vacuously on a shape that stopped existing.
    """
    for clone in all_clones([tables.program.start]):
        for arm in arms_of(clone):
            for i in range(arm.n):
                if arm.kinds[i] == kind:
                    return arm, i
    raise AssertionError(f"no item of kind {kind} in the compiled program")


def start_arm(tables):
    """The start clone's only arm — the single-arm grammars below."""
    arms = arms_of(tables.program.start)
    assert len(arms) == 1
    return arms[0]


# ── quantified terminals ───────────────────────────────────────────────────


def test_match_cc_consumes_the_maximal_run() -> None:
    """A ``[0-9]+`` item's whole quantifier loop runs in one call."""
    tables, _ = pda_for('root ::= [0-9]+ "!"\n')
    found = first_item(tables, OP_CC)
    assert found is not None
    arm, i = found
    assert match_cc("1234!", arm, i, 0) == 4


def test_match_cc_stops_at_the_first_non_member() -> None:
    """The run ends where membership ends, not at end of input."""
    tables, _ = pda_for('root ::= [0-9]+ "!"\n')
    arm, i = first_item(tables, OP_CC)
    assert match_cc("12ab", arm, i, 0) == 2


def test_match_cc_raises_when_the_mandatory_run_is_unmet() -> None:
    """A ``+`` item with no matching first char refuses by name."""
    tables, _ = pda_for('root ::= [0-9]+ "!"\n')
    arm, i = first_item(tables, OP_CC)
    with pytest.raises(PdaFail, match="char class miss"):
        match_cc("abc", arm, i, 0)


def test_match_lit_consumes_repeated_literals() -> None:
    """A repeated literal item advances by its length per iteration."""
    tables, _ = pda_for('root ::= "ab"+ "!"\n')
    found = first_item(tables, OP_LIT)
    assert found is not None
    arm, i = found
    assert match_lit("ababab!", arm, i, 0) == 6


def test_match_lit_raises_on_a_mandatory_mismatch() -> None:
    """A ``+`` literal that does not start at the cursor refuses by name."""
    tables, _ = pda_for('root ::= "ab"+ "!"\n')
    arm, i = first_item(tables, OP_LIT)
    with pytest.raises(PdaFail, match="expected"):
        match_lit("xy", arm, i, 0)


def test_match_lit_starts_from_the_given_position() -> None:
    """``pos`` is where matching begins — the caller owns the cursor."""
    tables, _ = pda_for('root ::= "ab"+ "!"\n')
    arm, i = first_item(tables, OP_LIT)
    assert match_lit("zzabab!", arm, i, 2) == 6


# ── whole-arm matching ─────────────────────────────────────────────────────


def test_match_arm_runs_every_item_and_returns_the_end() -> None:
    """``match_arm`` matches all of an all-terminal arm, returning one span end."""
    tables, _ = pda_for('root ::= "0x" [0-9a-f]+\n')
    assert match_arm("0xffa1", start_arm(tables), 0) == 6


def test_match_arm_refuses_a_mid_arm_mismatch() -> None:
    """A later item's mismatch fails the whole arm."""
    tables, _ = pda_for('root ::= "0x" [0-9a-f]+\n')
    with pytest.raises(PdaFail):
        match_arm("0xzz", start_arm(tables), 0)


# ── arm selection ──────────────────────────────────────────────────────────


def test_select_arm_picks_the_arm_whose_first_admits_the_char() -> None:
    """Two arms with disjoint FIRST sets select by the lookahead char."""
    tables, _ = pda_for('root ::= a | b\na ::= "x"\nb ::= "y"\n')
    start = tables.program.start
    assert select_arm(start, "x", 0) is not select_arm(start, "y", 0)


def test_select_arm_refuses_when_no_arm_matches_and_no_default() -> None:
    """No viable arm and no default raises by name, carrying the position."""
    tables, _ = pda_for('root ::= "x"\n')
    start = tables.program.start
    assert start.default is None  # else the refusal below could not fire
    with pytest.raises(PdaFail, match="no arm at 3"):
        select_arm(start, "q", 3)


# ── one value_str iteration ────────────────────────────────────────────────


def test_vstr_once_appends_one_built_model_to_the_sink() -> None:
    """A single-item ``value_str`` arm builds exactly one model per iteration."""
    tables, _ = pda_for('root ::= digit+ "!"\ndigit ::= [0-9]\n')
    arm, i = first_item(tables, OP_VSTR)
    clone = arm.payloads[i]
    sink: list = []
    assert vstr_once("7", {}, clone, sink, 0) == 1
    assert [model.to_text() for model in sink] == ["7"]


def test_vstr_once_interns_an_identical_span_into_one_model() -> None:
    """Two iterations over the same span share one model through the memo."""
    tables, _ = pda_for('root ::= digit+ "!"\ndigit ::= [0-9]\n')
    arm, i = first_item(tables, OP_VSTR)
    clone = arm.payloads[i]
    intern: dict = {}
    sink: list = []
    vstr_once("77", intern, clone, sink, 0)
    vstr_once("77", intern, clone, sink, 1)
    assert sink[0] is sink[1]


def test_vstr_multi_item_arm_takes_the_cold_span_path():
    """A ``value_str`` rule whose sole arm has MORE than one terminal item
    (``"0x" [0-9a-f]+`` — a literal then a char class) routes through
    ``match_arm``, not ``vstr_once``'s single-item fast path. No ground-truth
    grammar has a multi-item value_str arm, so this is the only exercise of
    that cold path — built raw (no fold-fallback engine escape) to prove the
    PDA itself handles it, not a silent Earley completion."""
    text = 'root ::= "0x" [0-9a-f]+\n'
    tables, compiled = pda_for(text)
    model = pda_model(tables, "0xffa1", compiled.fold)
    assert model.to_text() == "0xffa1"
