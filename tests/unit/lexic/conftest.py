"""Shared helpers for unit tests under tests/unit/lexic/."""

from __future__ import annotations

from typing import Iterable

from lexic.compile import parse_grammar
from lexic.ir.base import IrSelf, IrSeq
from lexic.ir.canonical import canonicalize
from lexic.ir.flavour import IrFlavour
from lexic.ir.nodes import (
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot

# Canonical set of all grammar-AST IR types that every flavour must cover.
GRAMMAR_AST_TYPES: frozenset[type] = frozenset(
    {
        IrLiteral,
        IrCharClass,
        IrNot,
        IrAlphabet,
        IrRuleRef,
        IrQuantifier,
        IrItem,
        IrSequence,
        IrAlternation,
        IrRule,
        IrAst,
    }
)


def contains_ir_type(roots: Iterable[IrSelf], target: type) -> bool:
    """Whether ``target`` appears anywhere in the trees rooted at ``roots``.

    A plain identity-guarded DFS over ``.children()`` — used to assert a
    flavour's action/reduction tables carry no stray instance of a given IR
    node type (e.g. no leftover :class:`~lexic.ir.base.IrLambda` procedural
    escape hatch in a table meant to be pure algebra).
    """
    seen: set[int] = set()
    stack = list(roots)
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, target):
            return True
        if isinstance(node, IrSelf):
            stack.extend(node.children())
    return False


def wide_grammar() -> IrAst:
    """A flavour-neutral start rule wide enough to overflow width 88, plus
    its refs — the shared fixture for GBNF/ABNF doc-wrap tests (their
    flavour tables render the same IR differently)."""
    names = [f"alternative-name-number-{i}" for i in range(6)]
    root = IrRule(
        "wide-rule",
        IrAlternation(*(IrSequence(IrItem(IrRuleRef(name))) for name in names)),
    )
    refs = [
        IrRule(name, IrAlternation(IrSequence(IrItem(IrLiteral("x")))))
        for name in names
    ]
    return IrAst(IrSeq(root, *refs), "wide-rule")


def assert_wide_rule_wraps_and_round_trips(
    flavour: IrFlavour, trailing_marker: str, flat_text: str
) -> None:
    """Shared body for a flavour's wide-alternation doc-wrap contract:
    trailing-continuation wrap at indent 6, no line over width 88,
    round-trips through parse_grammar + canonicalize, and width=None
    reproduces the flat single-line form.

    :param flavour: The flavour singleton under test.
    :param trailing_marker: The broken arm separator's trailing mark
        (e.g. ``"|"`` for GBNF/EBNF, ``"/"`` for ABNF).
    :param flat_text: The expected width=None single-line rendering of
        :func:`wide_grammar`'s start rule (flavour-specific spelling).
    """
    ast = wide_grammar()
    wrapped = str(flavour.apply(ast))
    lines = wrapped.splitlines()
    continuation_lines = [ln for ln in lines if ln.startswith("      alternative")]
    assert continuation_lines, wrapped
    assert lines[0].rstrip().endswith(trailing_marker)
    assert all(len(line) <= 88 for line in lines)

    reparsed = parse_grammar(wrapped, flavour)
    assert canonicalize(reparsed) == canonicalize(ast)

    flat = str(flavour.apply(ast, width=None))
    root_line = flat.splitlines()[0]
    assert "\n" not in root_line
    assert root_line == flat_text
