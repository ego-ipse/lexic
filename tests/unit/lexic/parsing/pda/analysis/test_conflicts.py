"""Tests for lexic.parsing.pda.analysis.conflicts — the ordered-attempt licence.

``attempt_spec`` derives the arm-try order (nullable arms last, deterministic)
for BOTH a rule body (``_classify``'s call) and an inline group
(``attempt_group``'s call) — one pure function of the arm list. ``attempt_group``
is the group-only entry: it declines a rule-body site (that licence belongs to
``_classify``, which sees the whole note ledger) and files the licence under
the group's node identity, counting its notes covered.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.ir import IrAlternation, IrCharClass, IrChr, IrLiteral, IrRange, IrSequence
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.conflicts import (
    attempt_group,
    attempt_spec,
    greedy_exact,
)
from lexic.parsing.pda.analysis.cursors import Notes, Site
from lexic.parsing.pda.analysis.taxonomy import AttemptSpec
from lexic.parsing.pda.core.charsets import CharSet
from tests.unit.lexic.parsing.ir_fixtures import analysis_of as _analysis
from tests.unit.lexic.parsing.ir_fixtures import item_of as _item
from tests.unit.lexic.parsing.ir_fixtures import rule_of as _rule
from tests.unit.lexic.parsing.pda.analysis.test_analysis import (
    arm_items,
    stop_set_notes,
)

_LOWER = IrCharClass(IrRange(IrChr(97), IrChr(122)))


def test_attempt_spec_orders_nullable_arms_last_and_is_deterministic():
    """Authored order for non-nullable arms; a nullable arm (here an empty
    one) moves to the end regardless of where it was authored — and the same
    arm list produces the identical order on a second call."""
    root = _rule(
        "root",
        IrSequence(_item(IrLiteral("a"))),
        IrSequence(),
        IrSequence(_item(IrLiteral("c"))),
    )
    analysis = _analysis(root, start="root")
    arms = [arm_items(arm) for arm in root.body]
    first = attempt_spec(analysis, arms)
    second = attempt_spec(analysis, arms)
    assert first == second == AttemptSpec((0, 2, 1))


def test_attempt_spec_keeps_all_nullable_arms_in_authored_order():
    """Nullable-last does not reorder WITHIN either bucket."""
    root = _rule(
        "root",
        IrSequence(),
        IrSequence(_item(IrLiteral("a"))),
        IrSequence(),
    )
    analysis = _analysis(root, start="root")
    arms = [arm_items(arm) for arm in root.body]
    assert attempt_spec(analysis, arms).order == (1, 0, 2)


def _throwaway_analysis():
    """A minimal analysis unrelated to any node under test — ``attempt_group``
    only needs it for ``seq_nullable`` (irrelevant to ref-free arms here) and
    a fresh :class:`Taxonomy` store; building it from an unrelated rule keeps
    its OWN eager walk from ever touching the node identities below."""
    return _analysis(_rule("x", IrSequence(_item(IrLiteral("x")))), start="x")


def test_attempt_group_files_the_licence_and_counts_notes_covered():
    """A group whose overlap survives to ``attempt_group`` gets a licence
    filed under its node id, in nullable-last order, and every overlap note
    it raised is counted covered — the channel that keeps the enclosing rule
    attemptable instead of islanded."""
    grp = IrAlternation(
        IrSequence(_item(_LOWER, lo=1, hi=None)),
        IrSequence(),
        IrSequence(_item(_LOWER, lo=1, hi=None)),
    )
    analysis = _throwaway_analysis()
    notes = Notes()
    follow = CharSet.from_chars("!")
    site = Site("root[0]grp", id(grp), follow)

    attempt_group(analysis, [arm_items(arm) for arm in grp], site, notes, count=1)

    assert notes.covered == 1
    windows, peek, attempt = analysis.taxonomy.grp_arm_gates[id(grp)]
    assert (windows, peek) == (None, None)
    assert attempt is not None
    order, stored_follow = attempt
    assert order.order == (0, 2, 1)
    assert stored_follow == follow


def test_attempt_group_declines_a_rule_body_site():
    """A rule-body site (``site.at`` is a name, not a node id) is excluded —
    that licence is ``_classify``'s, decided against the whole note ledger
    once every arm in the body has been walked."""
    analysis = _throwaway_analysis()
    notes = Notes()
    site = Site("root", "root", CharSet.from_chars("!"))

    attempt_group(analysis, [[_item(IrLiteral("a"))]], site, notes, count=1)

    assert notes.covered == 0
    assert not analysis.taxonomy.grp_arm_gates


# ── the longest take ───────────────────────────────────────────────────────


def test_a_text_only_run_that_reaches_its_follow_is_taken_longest() -> None:
    """``x ::= "b" [ab]*`` before ``"a" y``: the same visible exit, but ``x``
    is text, so its greedy match is its island's longest completion. It
    compiles to that match, and the runtime asks the island only where the
    span holds an ``a``."""
    source = 's ::= x "a" y\nx ::= "b" [ab]*\ny ::= [ab]*\n'
    demoted, conflicts = stop_set_notes(source, "x")
    assert demoted == ["x[1]: loop stop-set taken longest"]
    assert not conflicts
    compiled = compile_text(source, cache_key="longest-x")
    analysis = GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))
    assert "x" in analysis.taxonomy.longest


def test_a_one_item_text_run_that_reaches_its_follow_islands() -> None:
    """``x ::= [ab]*``: text too, but one item wide, and the runtime checks a
    span only on the matcher's multi-item path, so it stays an island."""
    demoted, conflicts = stop_set_notes(
        's ::= x "a" y\nx ::= [ab]*\ny ::= [ab]*\n', "x"
    )
    assert conflicts == ["x[0]: loop stop-set reaches FOLLOW"]
    assert not demoted


def _greedy_exact(body: str) -> bool:
    """:func:`greedy_exact` of rule ``x`` in ``s ::= x ";"`` with ``body``."""
    compiled = compile_text(f's ::= x ";"\nx ::= {body}\n', cache_key=f"ge-{body}")
    analysis = GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))
    return greedy_exact(analysis, analysis.rules["x"])


def test_a_prefix_then_a_run_is_greedy_exact():
    """A fixed prefix, then the run: nothing earlier can starve it."""
    assert _greedy_exact('"v" [a-z]*')


def test_a_loop_absorbed_by_the_final_run_is_greedy_exact():
    """``"#"+`` before a run that holds ``#``: whatever the loop leaves, the
    run takes, so the greedy end is the longest."""
    assert _greedy_exact('"\\\\" "#"+ [#a-z]*')


def test_a_loop_that_starves_what_follows_is_not():
    """``[ab]*`` before ``"b"``: the loop eats the ``b`` the literal needs."""
    assert not _greedy_exact('"v" [ab]* "b"')


def test_arms_that_start_alike_are_not():
    """The first character must pick the arm."""
    assert not _greedy_exact('"v" [a-z]* | "v" [0-9]*')


def test_a_one_item_arm_is_not():
    """The span is checked on the multi-item path only."""
    assert not _greedy_exact("[a-z]*")
