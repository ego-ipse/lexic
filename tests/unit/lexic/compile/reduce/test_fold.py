"""Tests for lexic.compile.reduce.fold — the thin-fold reducer bridge.

Exactness against real grammars (json, GBNF's own self-grammar) lives in the
parity differential (``tests/integration/lexic/parity/test_reduce_directives.py``)
and the thread-safety pin (``tests/.../test_shared_artefact.py``); this file
targets ``ReduceFold``'s own channel-assembly branches through the public
``CompiledGrammar.reduce`` seam, on small hand-built and hand-compiled
grammars.
"""

from __future__ import annotations

import functools
from typing import Any

import pytest

from lexic.compile import compile_ast, compile_text
from lexic.compile.artifact import _reduce_entry, _sub_run
from lexic.compile.reduce.fold import Unit
from lexic.compile.reduction import derive_reduction
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import EBNF_FLAVOUR, GBNF_FLAVOUR
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import (
    DROP,
    KEEP_RAW,
    YIELD,
    IrAlternation,
    IrArg,
    IrArgs,
    IrAst,
    IrItem,
    IrJoin,
    IrLiteral,
    IrMap,
    IrRaise,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSeq,
    IrSequence,
    IrStr,
    IrTuple,
    Reducer,
)
from tests.integration.lexic.parity.fold_recorder_helpers import (
    CarriesFoldState,
    count_pool_entries,
)
from tests.paths import GROUND_TRUTH


def _chain_grammar() -> IrAst:
    """root -> mid -> leaf, an unmapped pass-through chain of two hops."""
    return IrAst(
        IrSeq(
            IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("mid"))))),
            IrRule("mid", IrAlternation(IrSequence(IrItem(IrRuleRef("leaf"))))),
            IrRule("leaf", IrAlternation(IrSequence(IrItem(IrLiteral("x"))))),
        ),
        "root",
    )


def test_reduce_applies_the_default_body_when_no_rule_is_mapped():
    """An unmapped rule falls through to the reducer's default (YIELD)."""
    reducer = Reducer(actions=IrMap(), default=YIELD)
    assert compile_ast(_chain_grammar()).reduce("x", reducer) == IrStr("x")


def test_a_mapped_leaf_body_is_reached_through_a_pass_through_chain():
    """``root`` and ``mid`` pass their one channel argument through
    (``IrArg(0)``); the mapped body on ``leaf`` two hops down still reaches
    the result — a YIELD body anywhere in the chain would have short-circuited
    to raw text instead."""
    reducer = Reducer(
        actions=IrMap(
            IrTuple(IrRuleRef("root"), IrArg(0)),
            IrTuple(IrRuleRef("mid"), IrArg(0)),
            IrTuple(IrRuleRef("leaf"), IrStr("mapped")),
        ),
        default=YIELD,
        literal=DROP,
    )
    assert compile_ast(_chain_grammar()).reduce("x", reducer) == IrStr("mapped")


def test_keep_raw_literal_policy_includes_literal_characters_in_the_channel():
    """``literal=KEEP_RAW`` puts inline literal characters on the channel."""
    grammar = IrAst(
        IrSeq(
            IrRule(
                "root",
                IrAlternation(
                    IrSequence(IrItem(IrLiteral("a")), IrItem(IrLiteral("b")))
                ),
            ),
        ),
        "root",
    )
    reducer = Reducer(
        actions=IrMap(IrTuple(IrRuleRef("root"), IrJoin(IrArgs()))),
        default=YIELD,
        literal=KEEP_RAW,
    )
    assert compile_ast(grammar).reduce("ab", reducer) == IrStr("ab")


def test_drop_literal_policy_excludes_literal_characters_from_the_channel():
    """``literal=DROP`` (the default) keeps inline literals off the channel."""
    grammar = IrAst(
        IrSeq(
            IrRule(
                "root",
                IrAlternation(
                    IrSequence(IrItem(IrLiteral("a")), IrItem(IrLiteral("b")))
                ),
            ),
        ),
        "root",
    )
    reducer = Reducer(
        actions=IrMap(IrTuple(IrRuleRef("root"), IrJoin(IrArgs()))),
        default=YIELD,
        literal=DROP,
    )
    assert str(compile_ast(grammar).reduce("ab", reducer)) == ""


def test_a_hoisted_optional_group_reduces_through_its_owning_arm():
    """An inline anonymous group hoisted by the codegen pipeline still folds
    correctly whether it matches or is skipped."""
    cg = compile_text('root ::= ("a" "b")? "c"\n', cache_key="fold-hoist-splice")
    reducer = Reducer(actions=IrMap(), default=YIELD)
    assert cg.reduce("abc", reducer) == IrStr("abc")
    assert cg.reduce("c", reducer) == IrStr("c")


def test_reduce_refuses_a_no_body_default_of_a_dispatch_miss_the_same_way_as_parse():
    """A DROP default with an unmapped rule yields no text at all rather than
    raising — DROP is a legal terminal policy, not an error."""
    reducer = Reducer(actions=IrMap(), default=DROP)
    result = compile_ast(_chain_grammar()).reduce("x", reducer)
    assert result == () or not str(result)


# ── Obligation B — a fold worker's sub-parse can never contend the fold pool


def test_sub_run_binds_its_sub_parse_at_cores_1():
    """A poisoned marked run's escape hatch (``_splice_run``, T2 in the
    design notes) re-enters the parser FROM INSIDE a fold. ``_sub_run``
    binds that sub-parse to ``cores=1`` via ``functools.partial`` — so a
    later "helpful" parallelisation of the sub-parse cannot silently
    deadlock a future partitioned fold's own worker pool. This is a pin, not
    new coverage: the binding already exists (``artifact.py``); a
    regression here must fail loudly rather than surface as a deadlock.

    The other half of this obligation — that ``split_model`` itself settles
    "too few workers" BEFORE ever taking a pool lease, so cores=1 alone is
    the second line of defence even if this binding were ever dropped — is
    pinned in ``tests/unit/lexic/parsing/parallel/test_orchestrate.py``.
    """
    cg = compile_ast(JSON_GRAMMAR, cache_key="fold-obligation-b-subrun")
    derivation = derive_reduction(JSON_GRAMMAR, JSON_REDUCER)
    spec = derivation.runs["char-run"]
    sub = _sub_run(cg, JSON_REDUCER, "char-run", spec)
    assert isinstance(sub.parse, functools.partial)
    assert sub.parse.keywords == {"cores": 1}


# ── the parallel fold (I22 step 4) ──────────────────────────────────────────


class _ScratchProbe(CarriesFoldState):
    """Exposes ``_memo``/``_roots``/``_frontier`` through PUBLIC methods, so
    a test can inspect the parallel fold's per-thread scratch without
    external protected access — the same shape as
    ``tests/integration/lexic/parity/test_fold_refusals.py``'s ``_Probe``.
    """

    def probe_memo(self) -> dict[tuple[int, str, str, tuple[str, bool] | None], IrSelf]:
        """The calling thread's worker-results memo, right now."""
        return self._memo

    def probe_roots(self) -> set[tuple[int, str]]:
        """The calling thread's unit-root set, right now."""
        return self._roots

    def probe_frontier(self, model: Any, rule: str, target: int) -> list[Unit]:
        """The partition ``_frontier`` derives for ``target`` units."""
        return self._frontier(model, rule, target)


def test_a_divisible_model_actually_partitions_at_cores_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Engagement, observed rather than inferred from a speedup: a model with
    enough independent subtrees takes a ``PoolLease`` when ``cores=2`` grants
    more than one worker — ``reduce()`` only ever enters one when it actually
    partitions, never on the sequential path.
    """
    entered = count_pool_entries(monkeypatch)
    cg = compile_ast(GBNF_FLAVOUR.grammar, cache_key="fold-engage-arithmetic")
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    cg.reduce(text, GBNF_FLAVOUR.reducer, cores=2)
    assert entered[0] >= 1, "the pool was never entered — did not partition"


def test_a_model_below_the_unit_floor_folds_in_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The floor that keeps every ``compile_text`` fast, pinned loudly: a
    self-grammar-sized fold — the size of the hand-written grammar snippets
    this test file and most of the suite compile — stays sequential even
    when ``cores`` would grant many workers, because it never reaches the
    ``2 * workers`` unit floor. The pool is never entered at all.
    """
    entered = count_pool_entries(monkeypatch)
    cg = compile_ast(GBNF_FLAVOUR.grammar, cache_key="fold-decline-self-grammar")
    cg.reduce('root ::= "a" "b"\n', GBNF_FLAVOUR.reducer, cores=8)
    assert entered[0] == 0, f"pool entered {entered[0]} times — should have declined"


_RAISING_RUN_GRAMMAR = (
    'root ::= item*\nitem ::= good | bad\ngood ::= [a-y]\nbad ::= "z"\n'
)
"""Many independent ``item`` units (enough to partition at ``cores=2``); one
arm (``bad``) is mapped to an unconditional refusal, so a document with a
single ``z`` among many other characters refuses from INSIDE a worker's
fold — the realistic shape a real refusal takes under this design (T2's
poisoned-run precedent is the same shape: a worker-side raise, not a
root-level one)."""


def _raising_run_reducer() -> Reducer:
    """``bad`` refuses; every other rule is mapped (never left ``YIELD``, for
    the same reason ``test_fold_refusals.py``'s poison fixture states: a
    ``YIELD`` ancestor would collapse the whole subtree to a span first)."""
    return Reducer(
        actions=IrMap(
            IrTuple(IrRuleRef("root"), IrJoin(IrArgs())),
            IrTuple(IrRuleRef("item"), IrArg(0)),
            IrTuple(IrRuleRef("good"), IrArg(0)),
            IrTuple(
                IrRuleRef("bad"),
                IrRaise(UnsupportedConstructError, "refusal BANG"),
            ),
        ),
        default=YIELD,
    )


def test_scratch_is_empty_on_the_calling_thread_after_a_successful_reduce():
    """``_memo``/``_roots`` are per-call scratch, not a cache — after
    ``reduce()`` returns successfully, both are empty on the thread that
    called it, so a second unrelated ``reduce()`` on the same fold instance
    never sees a prior call's units."""
    cg = compile_text(_RAISING_RUN_GRAMMAR, cache_key="fold-scratch-success")
    reducer = _raising_run_reducer()
    entry = _reduce_entry(cg, reducer)
    probe = _ScratchProbe.carrying(entry.fold)
    text = "a" * 40  # no "z" — every unit folds cleanly
    probe.reduce(entry.variant.parse(text, cores=1), cores=2)
    assert not probe.probe_memo()
    assert probe.probe_roots() == set()


def test_scratch_is_empty_on_the_calling_thread_after_a_refusal():
    """The refusal counterpart. ``WorkPool.map`` raises the earliest failing
    unit's own exception FROM INSIDE the ``with PoolLease(...)`` block —
    before the join ever assembles ``_memo`` — so this pins the stronger
    property the design actually needs: a failed partition never leaves
    ANY stale scratch behind, whether or not the join got far enough to
    populate one in the first place."""
    cg = compile_text(_RAISING_RUN_GRAMMAR, cache_key="fold-scratch-refusal")
    reducer = _raising_run_reducer()
    entry = _reduce_entry(cg, reducer)
    probe = _ScratchProbe.carrying(entry.fold)
    text = "a" * 40 + "z" + "a" * 5
    model = entry.variant.parse(text, cores=1)
    with pytest.raises(UnsupportedConstructError, match="refusal BANG"):
        probe.reduce(model, cores=2)
    assert not probe.probe_memo()
    assert probe.probe_roots() == set()


def test_the_frontier_is_monotone_nondecreasing_as_the_target_rises():
    """The step-3 bug, permanently pinned: a shape whose branches bottom out
    at DIFFERENT depths (``arithmetic.ebnf`` under its own EBNF self-grammar
    reducer, the exact witness that caught the original defect) must never
    yield FEWER units for a HIGHER target — a bottomed-out unit with no
    contributions of its own stays at its own depth instead of being
    descended past and deleted from the frontier."""
    text = (GROUND_TRUTH / "arithmetic.ebnf").read_text(encoding="utf-8")
    entry = _reduce_entry(
        compile_ast(EBNF_FLAVOUR.grammar, cache_key="fold-frontier-monotone"),
        EBNF_FLAVOUR.reducer,
    )
    probe = _ScratchProbe.carrying(entry.fold)
    model = entry.variant.parse(text, cores=1)
    rule = probe.rule(model)
    counts = [len(probe.probe_frontier(model, rule, target)) for target in (8, 64, 512)]
    assert counts == sorted(counts), f"frontier unit counts not monotone: {counts}"
    assert counts[0] < counts[-1], "targets never actually grew the partition"
