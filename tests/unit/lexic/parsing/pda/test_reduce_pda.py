"""Tests for lexic.parsing.pda.reduce_pda — the b1 reduce-completion twin of the
model fold.

``ReduceComp``/``ReduceRun``/``_ReduceCompile`` are exercised against a small,
fully self-contained hand-authored meta-grammar + matching custom
:class:`~lexic.parsing.earley.reduce.Reducer` — never the real GBNF/ABNF
self-grammars (those drive the end-to-end ``compile_reduce_pda`` gates in
``test_clones.py``/``test_runtime.py``/``test_compile.py``). This keeps the
module's own branch logic (DROP/KEEP/unknown-rule/custom-noise-policy;
YIELD-body detection; ``literal_keep`` derivation) pinned independent of any
particular flavour's grammar text.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrLambda, IrNone, IrSeq, IrTuple
from lexic.ir.mapping import IR_DEFAULT, IrMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce import (
    DROP,
    KEEP_RAW,
    KEEP_REDUCED,
    YIELD,
    Reducer,
    _plan_for,
)
from lexic.parsing.earley.tables import compile_tables
from lexic.parsing.pda.charsets import CharSet
from lexic.parsing.pda.clones import CloneKey
from lexic.parsing.pda.flatten import (
    _BUILD_REDUCE,
    _BUILD_TRANSPARENT,
    _R_DROP,
    _R_KEEP,
    _R_SPLICE,
    _FlatClone,
)
from lexic.parsing.pda.reduce_pda import (
    ReduceComp,
    ReduceRun,
    _reduce_rewrite,
    _ReduceCompile,
)

# ── fixture grammar + reducer ────────────────────────────────────────────
#
#   root  ::= noise leaf wrap weird     (KEEP, custom body — no YIELD mention)
#   noise ::= " "                       (semantic=False -> DROP noise)
#   leaf  ::= "a"                       (KEEP, no explicit reduction -> YIELD)
#   wrap  ::= "b"                       (KEEP, explicit body mentioning YIELD)
#   weird ::= "c"                       (a custom, non-DROP/KEEP noise policy)

_NO_YIELD_BODY = IrLambda(lambda d, n, nc: IrNone)
"""An opaque callable reduction body — _mentions_yield cannot inspect it, so
it counts as not mentioning YIELD (root's span_needed stays False)."""

_GRAMMAR = IrAst(
    IrSeq(
        IrRule(
            "root",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("noise")),
                    IrItem(IrRuleRef("leaf")),
                    IrItem(IrRuleRef("wrap")),
                    IrItem(IrRuleRef("weird")),
                )
            ),
        ),
        IrRule(
            "noise", IrAlternation(IrSequence(IrItem(IrLiteral(" ")))), semantic=False
        ),
        IrRule("leaf", IrAlternation(IrSequence(IrItem(IrLiteral("a"))))),
        IrRule("wrap", IrAlternation(IrSequence(IrItem(IrLiteral("b"))))),
        IrRule("weird", IrAlternation(IrSequence(IrItem(IrLiteral("c"))))),
    ),
    "root",
)

_NOISE = IrMap(
    IrTuple(IrRuleRef("noise"), DROP),
    IrTuple(IrRuleRef("weird"), KEEP_RAW),  # a non-DROP/KEEP_REDUCED policy
    IrTuple(IR_DEFAULT, KEEP_REDUCED),
)

_REDUCTIONS = IrMap(
    IrTuple(IrRuleRef("root"), _NO_YIELD_BODY),
    IrTuple(IrRuleRef("wrap"), IrTuple(YIELD)),  # mentions YIELD, isn't YIELD itself
    IrTuple(IR_DEFAULT, YIELD),
)

_REDUCER = Reducer(reductions=_REDUCTIONS, noise=_NOISE, literal=DROP)


def _compile_for(reducer: Reducer = _REDUCER) -> _ReduceCompile:
    """Build a :class:`_ReduceCompile` over the fixture grammar's tables."""
    tables = compile_tables(normalize(_GRAMMAR))
    plan = _plan_for(reducer, tables)
    name_to_rid = {name: rid for rid, name in enumerate(tables.decode.rule_names)}
    return _ReduceCompile(reducer, plan, name_to_rid)


# ── ReduceComp shape ─────────────────────────────────────────────────────


def test_reducecomp_carries_exactly_the_five_documented_fields():
    """ReduceComp is a plain NamedTuple over kind/body/is_yield/span_needed/can_drop."""
    comp = ReduceComp(_R_KEEP, "body-marker", True, False, True)
    assert comp.kind == _R_KEEP
    assert comp.body == "body-marker"
    assert comp.is_yield is True
    assert comp.span_needed is False
    assert comp.can_drop is True
    assert comp == (_R_KEEP, "body-marker", True, False, True)


# ── _ReduceCompile.comp_for ───────────────────────────────────────────────


def test_comp_for_drop_noise_rule_is_the_bare_drop_shape():
    """A DROP-noise rule (``noise``) bakes _R_DROP with no body and every
    flag False — the runtime contributes nothing for it."""
    comp = _compile_for().comp_for("noise")
    assert comp == ReduceComp(_R_DROP, None, False, False, False)


def test_comp_for_default_yield_rule_is_yield_and_span_needed():
    """A KEEP rule with no explicit reduction (``leaf``) resolves to the
    IR_DEFAULT body — the YIELD singleton itself, so both is_yield and
    span_needed (mentions) are True; it references no other rule, so
    can_drop is False."""
    comp = _compile_for().comp_for("leaf")
    assert comp.kind == _R_KEEP
    assert comp.body is YIELD
    assert comp.is_yield is True
    assert comp.span_needed is True
    assert comp.can_drop is False


def test_comp_for_explicit_body_mentioning_yield_is_span_needed_not_is_yield():
    """``wrap``'s explicit body (IrTuple(YIELD)) is not YIELD itself, so
    is_yield is False, but the scan finds YIELD nested inside it, so
    span_needed is True."""
    comp = _compile_for().comp_for("wrap")
    assert comp.kind == _R_KEEP
    assert comp.body is not YIELD
    assert comp.is_yield is False
    assert comp.span_needed is True
    assert comp.can_drop is False


def test_comp_for_opaque_body_is_neither_yield_nor_span_needed():
    """``root``'s explicit body is an opaque IrLambda — _mentions_yield cannot
    inspect it, so span_needed is False even though the grammar's default
    would otherwise be YIELD. root refs the DROP-noise ``noise`` rule
    directly, so can_drop is True."""
    comp = _compile_for().comp_for("root")
    assert comp.kind == _R_KEEP
    assert comp.is_yield is False
    assert comp.span_needed is False
    assert comp.can_drop is True


def test_comp_for_unknown_rule_name_raises():
    """A rule name absent from the instance tables raises — the
    whole-grammar opt-out signal Task-6's seam reads."""
    with pytest.raises(UnsupportedConstructError, match="not in instance tables"):
        _compile_for().comp_for("does-not-exist")


def test_comp_for_custom_noise_policy_raises():
    """A rule (``weird``) whose noise policy is neither DROP nor KEEP_REDUCED
    (here KEEP_RAW) is a custom policy the reduce runtime cannot reconstruct."""
    with pytest.raises(UnsupportedConstructError, match="custom noise policy"):
        _compile_for().comp_for("weird")


# ── ReduceRun ─────────────────────────────────────────────────────────────


def _run_for(reducer: Reducer) -> ReduceRun:
    """Bundle a :class:`ReduceRun` for ``reducer`` over the fixture tables."""
    tables = compile_tables(normalize(_GRAMMAR))
    plan = _plan_for(reducer, tables)
    name_to_rid = {name: rid for rid, name in enumerate(tables.decode.rule_names)}
    return ReduceRun(reducer, plan, tables, name_to_rid)


def test_reducerun_bundles_its_constructor_arguments_verbatim():
    """ReduceRun stores reducer/plan/tables/name_to_rid unchanged."""
    tables = compile_tables(normalize(_GRAMMAR))
    plan = _plan_for(_REDUCER, tables)
    name_to_rid = {name: rid for rid, name in enumerate(tables.decode.rule_names)}
    run = ReduceRun(_REDUCER, plan, tables, name_to_rid)
    assert run.reducer is _REDUCER
    assert run.plan is plan
    assert run.tables is tables
    assert run.name_to_rid is name_to_rid


def test_reducerun_literal_keep_true_when_the_terminal_policy_is_keep_raw():
    """literal_keep derives True exactly when the reducer's terminal-leaf
    policy is KEEP_RAW."""
    keep_reducer = Reducer(reductions=_REDUCTIONS, noise=_NOISE, literal=KEEP_RAW)
    run = _run_for(keep_reducer)
    assert run.literal_keep is True


def test_reducerun_literal_keep_false_when_the_terminal_policy_is_drop():
    """literal_keep derives False when the reducer's terminal-leaf policy is
    DROP (the fixture's own reducer, and every shipping flavour's)."""
    run = _run_for(_REDUCER)
    assert run.literal_keep is False


# ── _reduce_rewrite / _bake_reduce (unit-level) ─────────────────────────
# Ported from test_clones.py when the functions moved here (option-(a)
# rebuild, 2026-07-11).


def _bare_flat_clone() -> _FlatClone:
    """An empty _FlatClone shell — the pre-bake state _flatten_program leaves
    every clone in before its first pass fills mode/selectors/default."""
    clone = _FlatClone.__new__(_FlatClone)
    clone.selectors = ()
    clone.kwin_selectors = None
    clone.default = None
    clone.mode = _BUILD_TRANSPARENT  # placeholder, overwritten by _bake_reduce
    return clone


def test_reduce_rewrite_bakes_a_keep_completion_onto_its_own_clone():
    """A clone whose key has a KEEP completion bakes body/is_yield/span/can_drop
    verbatim off the ReduceComp — the exact _bake_reduce contract."""
    key = CloneKey("root", CharSet.from_chars(""))
    shell = _bare_flat_clone()
    comp = ReduceComp(_R_KEEP, "sentinel-body", True, False, True)
    _reduce_rewrite({key: shell}, {key: comp})
    assert shell.mode == _BUILD_REDUCE
    assert shell.reduce_kind == _R_KEEP
    assert shell.reduce_body == "sentinel-body"
    assert shell.reduce_is_yield is True
    assert shell.reduce_span is False
    assert shell.reduce_can_drop is True
    assert shell.needs_ends is True
    assert shell.fold is None
    assert shell.fast is None


def test_reduce_rewrite_bakes_a_drop_completion_onto_its_own_clone():
    """A DROP-noise rule's clone bakes _R_DROP with no body."""
    key = CloneKey("n", CharSet.from_chars(""))
    shell = _bare_flat_clone()
    comp = ReduceComp(_R_DROP, None, False, False, False)
    _reduce_rewrite({key: shell}, {key: comp})
    assert shell.reduce_kind == _R_DROP
    assert shell.reduce_body is None


def test_reduce_rewrite_defaults_a_clone_with_no_completion_to_splice():
    """An inline group's shell never appears in ``completions`` (only named
    rules do — groups are reached via a _OP_GRP payload, never a clone key
    of their own) — _reduce_rewrite defaults it to SPLICE, flattening its
    ordered children straight into the caller.
    """
    key = CloneKey("grp", CharSet.from_chars(""))
    shell = _bare_flat_clone()
    _reduce_rewrite({key: shell}, {})
    assert shell.reduce_kind == _R_SPLICE
    assert shell.reduce_body is None
