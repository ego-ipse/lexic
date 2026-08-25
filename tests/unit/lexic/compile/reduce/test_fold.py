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

from lexic.compile import compile_ast, compile_text
from lexic.compile.artifact import _sub_run
from lexic.compile.reduction import derive_reduction
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
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
    IrStr,
    IrTuple,
    Reducer,
)


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
