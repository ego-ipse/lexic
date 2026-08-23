"""Tests for lexic.compile.reduce.fold — the thin-fold reducer bridge.

Exactness against real grammars (json, GBNF's own self-grammar) lives in the
parity differential (``tests/integration/lexic/parity/test_reduce_directives.py``)
and the thread-safety pin (``tests/.../test_shared_artefact.py``); this file
targets ``ReduceFold``'s own channel-assembly branches through the public
``CompiledGrammar.reduce`` seam, on small hand-built and hand-compiled
grammars.
"""

from __future__ import annotations

from lexic.compile import compile_ast, compile_text
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
