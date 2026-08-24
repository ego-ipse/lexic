"""Tests for ``lexic.parsing.parallel.plan.cuts`` — where a document is cut.

The plan says which spellings bound a unit; this says which of their
occurrences a given document is actually cut at. The floor is absolute in both
directions, and an OPENING mark belongs to the piece after it rather than the
piece before — the one arithmetic difference between a proposal and a proof.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.parallel.orchestrate import _safe_plans, _split_plans
from lexic.parsing.parallel.plan.cuts import (
    after_mark,
    cut_offsets,
    cut_spans,
    scan_marks,
    scan_windows,
    sole_mark,
)
from lexic.parsing.parallel.policy import MIN_CHUNK
from lexic.parsing.parallel.pool import WorkPool
from tests.unit.lexic.parsing.parallel.speculation_fixtures import (
    ANNOUNCED,
    announced_doc,
)

LINES = 'root ::= line+\nline ::= [a-z0-9]* nl\nnl ::= "\\n"\n'


def _plan(source: str, key: str):
    compiled = compile_text(source, cache_key=key)
    grammar = compiled.codegen_grammar
    safe = _safe_plans(
        _split_plans(grammar), compiled.split_analysis or compiled.grammar
    )
    assert safe, "the fixture must certify a plan"
    return safe[0]


# ── sole_mark ─────────────────────────────────────────────────────────────


def test_a_one_spelling_plan_names_its_mark_and_a_set_declines() -> None:
    """The proofs stated over a single mark have no reading over a set, and
    say so by declining rather than picking one of its members."""
    plan = _plan(LINES, "cuts-lines")
    assert sole_mark(plan) == "\n"
    assert sole_mark(plan._replace(mark=frozenset({"\n", ";"}))) == ""


# ── closing vs opening arithmetic ─────────────────────────────────────────


def test_a_closing_mark_belongs_to_the_piece_before_it() -> None:
    """A terminated unit OWNS its terminator, so the piece keeps it and the
    next one starts past it."""
    plan = _plan(LINES, "cuts-lines")
    text = "one\ntwo\n"
    assert after_mark(plan, text, 3) == 4


def test_an_opening_mark_belongs_to_the_piece_after_it() -> None:
    """A proposal marks where the NEXT unit begins, so the piece before it
    ends there and the mark itself is the next piece's first character."""
    plan = _plan(ANNOUNCED, "cuts-announced")
    assert plan.opening
    text = announced_doc(4)
    at = text.index("#", 1)
    assert after_mark(plan, text, at) == at


def test_opening_spans_hand_the_mark_forward_and_lose_nothing() -> None:
    """The spans a proposal produces tile the document exactly: no character
    is dropped at a cut and none is counted twice."""
    plan = _plan(ANNOUNCED, "cuts-announced")
    text = announced_doc(60)
    cuts = [text.index("#", 1), text.rindex("#")]
    spans, leads = cut_spans(plan, text, cuts)
    assert not any(leads)
    assert "".join(text[lo:hi] for lo, hi in spans) == text


# ── the floor, in both directions ─────────────────────────────────────────


def test_every_chosen_cut_clears_the_floor_on_both_sides() -> None:
    """The 2 KiB floor is absolute, and a proposal is not exempt from it."""
    plan = _plan(ANNOUNCED, "cuts-announced")
    text = announced_doc(300)
    assert len(text) > 4 * MIN_CHUNK
    with WorkPool(8) as pool:
        cuts = cut_offsets(plan, text, 8, pool)
    assert cuts
    bounds = [0, *cuts, len(text)]
    assert all(hi - lo >= MIN_CHUNK for lo, hi in zip(bounds, bounds[1:])), (
        "a cut left a piece under the floor"
    )


def test_a_proposal_is_never_cut_at_offset_zero() -> None:
    """A cut at the document's first character leaves an empty first piece,
    which is not a document.

    The candidate SCAN reports it — a unit does begin there — and the cut
    selection drops it. Keeping the scan honest is what lets a re-selection
    reach every real candidate; the floor is what refuses this one."""
    plan = _plan(ANNOUNCED, "cuts-announced")
    text = announced_doc(300)
    assert text[0] == "#", "the fixture must open ON a proposal character"
    with WorkPool(8) as pool:
        windows = scan_windows(plan.scanner, text, 8, pool)
        assert 0 in scan_marks(plan, text, 8, pool, windows)
        assert 0 not in cut_offsets(plan, text, 8, pool, windows)


def test_every_candidate_stands_on_a_mark_of_the_plan() -> None:
    """Candidate generation is grammar-derived, never a byte offset: each one
    is an occurrence of a spelling the plan named."""
    plan = _plan(ANNOUNCED, "cuts-announced")
    text = announced_doc(300)
    with WorkPool(8) as pool:
        marks = scan_marks(plan, text, 8, pool)
    assert marks
    assert all(text[at] in plan.mark for at in marks)
