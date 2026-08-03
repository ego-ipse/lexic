"""The views registry — product type → window body, raising default.

One open :class:`~lexic.ir.IrTypeMap` from product types to layout
docs. A product with no view is a REFUSAL the page draws — never
silence, never a blank window. The registry is itself a dispatch
table, so the doctrine is self-inspecting: it opens like any other.

Rule names carry ``data-rule`` — the deixis attribute convention: one
document-level listener glows every occurrence of a hovered rule name
across every window at every depth.
"""

from __future__ import annotations

from typing import Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import get_flavour
from lexic.ir import IrAction, IrAst, IrCat, IrDoc, IrLeaf, IrRule, IrSelf, IrTypeMap
from lexic.model import GrammarModel

from opsis.opsis.canvas import el

__all__ = ["VIEWS", "refusal", "view_body"]


class GrammarView(IrLeaf[IrSelf, IrSelf]):
    """A grammar's window body: its rules, each row deixis-wired."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        ast = IrAst.ensure(n, "views: the grammar view")
        rows = [_rule_row(rule) for rule in ast.rules]
        return el("div", {"class": "vbody"}, *rows)


def _rule_row(rule: IrRule) -> IrDoc:
    """One rule: its name (deixis-wired) and its emitted form."""
    emitted = str(get_flavour("gbnf").apply(rule, None))
    return el(
        "div",
        {"class": "rrow"},
        el("span", {"class": "rname", "data-rule": str(rule.name)}, str(rule.name)),
        el("pre", {"class": "rsrc"}, emitted),
    )


class ModelView(IrLeaf[IrSelf, IrSelf]):
    """An instance's window body: its class, its rule, its text."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        model = GrammarModel.ensure(n, "views: the model view")
        rule = str(model.__grammar__.name)
        return el(
            "div",
            {"class": "vbody"},
            el(
                "div",
                {"class": "rrow"},
                el("span", {"class": "rname", "data-rule": rule}, type(model).__name__),
            ),
            el("pre", {"class": "rsrc"}, model.to_text()),
        )


VIEWS: IrTypeMap = IrTypeMap(
    IrAction(IrAst, GrammarView()),
    IrAction(GrammarModel, ModelView()),
)
"""The registry — open, concrete-first via MRO, raising default."""


def refusal(message: str) -> IrDoc:
    """A drawn refusal — the real message, in the register's err voice."""
    return el("div", {"class": "refusal"}, message)


def view_body(product: IrSelf) -> IrDoc:
    """The window body for a product — its view, or the drawn refusal.

    The raising default is the coverage doctrine's runtime form: the
    raise is caught HERE, at the drawing boundary, and drawn with its
    real message — a coverage gap is a visible defect, not silence.
    """
    try:
        return IrDoc.ensure(VIEWS.eval(VIEWS, product, ()), "views: a view body")
    except UnsupportedConstructError as exc:
        return refusal(f"{type(exc).__name__}: {exc}")
