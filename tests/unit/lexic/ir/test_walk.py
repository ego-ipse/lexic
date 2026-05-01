# tests/unit/lexic/ir/test_walk.py
"""IrVisitor and IrTransformer — Python-ast-style traversal for IR AST."""

from __future__ import annotations

from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.walk import IrTransformer, IrVisitor


def _seq(*items):
    return IrSequence(tuple(items))


def _alt(*arms):
    return IrAlternation(tuple(arms))


def _it(atom, q=None):
    return IrItem(atom, q if q else Quantifier())


# ── IrVisitor ────────────────────────────────────────────────────────


def test_visitor_dispatches_by_type():
    """Test that the visitor dispatches to the correct visit method based on node type."""
    seen = []

    class V(IrVisitor):
        """Visit IrLiteral and IrRuleRef nodes and record their values."""

        def visit_IrLiteral(self, node):
            """Visit an IrLiteral and record its value."""
            seen.append(("lit", node.value))

        def visit_IrRuleRef(self, node):
            """Visit an IrRuleRef and record its name."""
            seen.append(("ref", node.name))

    v = V()
    v.visit(IrLiteral("a"))
    v.visit(IrRuleRef("r"))
    assert seen == [("lit", "a"), ("ref", "r")]


def test_visitor_generic_visit_walks_children():
    """Test that the generic visit implementation walks into child nodes."""
    counts = {"literals": 0, "refs": 0}

    class V(IrVisitor):
        """Count literals and rule references in the IR tree."""

        def visit_IrLiteral(self, node):
            counts["literals"] += 1

        def visit_IrRuleRef(self, node):
            counts["refs"] += 1

    body = _alt(
        _seq(_it(IrLiteral("a")), _it(IrRuleRef("x"))),
        _seq(_it(IrLiteral("b"))),
    )
    rule = IrRule("r", body)
    V().visit(rule)
    assert counts == {"literals": 2, "refs": 1}


def test_visitor_walks_groups():
    """Test that the visitor can walk into IrGroup nodes."""
    counts = {"chars": 0}

    class V(IrVisitor):
        """Count IrCharClass nodes, even when nested inside groups."""

        def visit_IrCharClass(self, node):
            """Visit an IrCharClass and count it."""
            counts["chars"] += 1

    seq = _seq(
        _it(IrGroup(_alt(_seq(_it(IrCharClass("a-z")), _it(IrCharClass("0-9")))))),
    )
    V().visit(seq)
    assert counts["chars"] == 2


# ── IrTransformer ────────────────────────────────────────────────────


def test_transformer_returns_node_unchanged_by_default():
    """Test that the default transformer implementation returns the node unchanged."""
    lit = IrLiteral("a")
    out = IrTransformer().visit(lit)
    assert out == lit


def test_transformer_can_rewrite_a_leaf():
    """Test that the transformer can rewrite a leaf node like IrLiteral."""

    class T(IrTransformer):
        """Rewrite an IrLiteral to uppercase."""

        def visit_IrLiteral(self, node):
            """Rewrite an IrLiteral to uppercase."""
            return IrLiteral(node.value.upper())

    body = _alt(_seq(_it(IrLiteral("a")), _it(IrLiteral("b"))))
    rule = IrRule("r", body)
    out = T().visit(rule)
    assert isinstance(out, IrRule)
    arm = out.body.arms[0]
    assert arm.items[0].atom == IrLiteral("A")
    assert arm.items[1].atom == IrLiteral("B")


def test_transformer_preserves_quantifier_when_rewriting_atom():
    """Test that when the transformer rewrites an atom, it preserves the quantifier from the parent IrItem."""

    class T(IrTransformer):
        """Rewrite an IrLiteral but preserve the quantifier from the parent IrItem."""

        def visit_IrLiteral(self, node):
            """Rewrite an IrLiteral but preserve the quantifier from the parent IrItem."""
            return IrLiteral(node.value + "!")

    body = _alt(_seq(_it(IrLiteral("x"), Quantifier(0, None))))
    rule = IrRule("r", body)
    out = T().visit(rule)
    assert isinstance(out, IrRule)
    item = out.body.arms[0].items[0]
    assert item.atom == IrLiteral("x!")
    assert item.quantifier == Quantifier(0, None)


def test_transformer_replacing_group_with_ruleref():
    """Helper-rule hoisting use case: replace IrGroup with IrRuleRef."""

    class T(IrTransformer):
        """Visit an IrGroup and replace it with an IrRuleRef to a hoisted rule."""

        def visit_IrGroup(self, node):
            """Hoist the group into a separate rule and return a reference to it."""
            return IrRuleRef("hoisted")

    body = _alt(
        _seq(_it(IrGroup(_alt(_seq(_it(IrLiteral("a"))))), Quantifier(1, None)))
    )
    rule = IrRule("r", body)
    out = T().visit(rule)
    assert isinstance(out, IrRule)
    item = out.body.arms[0].items[0]
    assert item.atom == IrRuleRef("hoisted")
    assert item.quantifier == Quantifier(1, None)


def test_transformer_walks_ast_top_level():
    """Test that the transformer can visit the top-level IrAst node and rewrite it."""

    class T(IrTransformer):
        """Visit the IrAst and rewrite the start rule name."""

        def visit_IrLiteral(self, node):
            """Rewrite an IrLiteral by appending a dot."""
            return IrLiteral(node.value + ".")

    ast = IrAst(
        rules=(
            IrRule("a", _alt(_seq(_it(IrLiteral("x"))))),
            IrRule("b", _alt(_seq(_it(IrLiteral("y"))))),
        ),
        start="a",
    )
    out = T().visit(ast)
    assert isinstance(out, IrAst)
    assert out.rules[0].body.arms[0].items[0].atom == IrLiteral("x.")
    assert out.rules[1].body.arms[0].items[0].atom == IrLiteral("y.")
    assert out.start == "a"
