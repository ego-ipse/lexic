"""Forest → IR reduction — the seam where a flavour's meaning attaches.

Recognition proves a derivation exists; reduction turns the derivation into the
target :class:`~lexic.ir.nodes.IrAst`. The "meta notation" a flavour supplies is
exactly a reduction table — an :class:`~lexic.ir.mapping.IrMap` from a rule's
:class:`~lexic.ir.nodes.IrRuleRef` to an action body that folds the rule's matched
children into an IR node:

- emit (today):  ``IrTypeMap[type, body]``      IR node  → text
- reduce (here): ``IrMap[IrRuleRef, body]``      parse tree → IR node

Symmetry by design — both are dispatch tables over the same action algebra. A
reduction body reads the matched children off the argument channel via
:class:`~lexic.ir.action.IrArgs`, so the same algebra (:class:`~lexic.ir.action.IrConcat`,
:class:`~lexic.ir.base.IrCallable`, …) that renders IR also builds it. ``abnf_2.py``
owns ``ABNF_REDUCTIONS``; this module is the flavour-agnostic walker.

:class:`Reducer` overrides ``eval`` (not a named ``reduce`` method): the entry is
the inherited :meth:`~lexic.ir.walk.IrDispatch.apply`, and recursion flows back
through ``eval``. Child resolution — reduce each child, but splice a
synthetic-rule sub-tree's own resolved children in place — lives in the
:data:`RESOLVE_CHILDREN` node, so the fold stays ``eval`` + dunders only.
"""

from __future__ import annotations

from typing import Sequence, cast

from lexic.ir.base import IrLeaf, IrSelf, IrTuple
from lexic.ir.mapping import IrMap
from lexic.ir.walk import IrDispatch
from lexic.parsing_2.forest import ParseTree
from lexic.parsing_2.normalize import SYNTHETIC_PREFIX


class ResolveChildren(IrLeaf[IrSelf, IrSelf]):
    """A parse node's reduced children, with synthetic sub-trees spliced away.

    Invoked via :data:`RESOLVE_CHILDREN` with ``d`` the driving
    :class:`Reducer`: a non-:class:`ParseTree` child (a terminal leaf) passes
    through; a synthetic-rule sub-tree (its name carries
    :data:`~lexic.parsing_2.normalize.SYNTHETIC_PREFIX`) contributes its own
    resolved children recursively, flattening a desugared repetition/group back
    to the conceptual child sequence; any other sub-tree is fully reduced via
    ``d``. Returns the resolved children as an :class:`~lexic.ir.base.IrTuple`.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Resolve ``n``'s children in source order.

        :param d: The driving :class:`Reducer`.
        :param n: The parse node whose children to resolve.
        :returns: The resolved children as an :class:`IrTuple`.
        """
        tree = cast(ParseTree, n)
        out: list[IrSelf] = []
        for child in tree.kids:
            if not isinstance(child, ParseTree):
                out.append(child)
            elif str(child.symbol).startswith(SYNTHETIC_PREFIX):
                out.extend(cast(Sequence[IrSelf], self.eval(d, child, ())))
            else:
                out.append(d.eval(d, child, ()))
        return IrTuple(*out)


RESOLVE_CHILDREN = ResolveChildren()
"""Shared child-resolution node — stateless, so one instance."""


class Reducer(IrDispatch):
    """Bottom-up fold of a :class:`ParseTree` into IR, driven by ``reductions``.

    Each node's children are resolved first (see :data:`RESOLVE_CHILDREN`), then
    the body bound to the node's ``symbol`` is evaluated with those resolved
    children on the argument channel (``nc``) and the tree as ``n`` — so a body
    reads children with :class:`~lexic.ir.action.IrArgs` and rule-level payload
    with :class:`~lexic.ir.action.IrField`. ``self`` is the dispatcher, so a body
    that sub-dispatches recurses through here.

    The entry is :meth:`~lexic.ir.walk.IrDispatch.apply` (``reducer.apply(tree)``).
    Dispatch is on ``tree.symbol`` (a *value*, :class:`~lexic.ir.nodes.IrRuleRef`)
    via the ``reductions`` :class:`IrMap` — correct because every node is a
    ``ParseTree``, which is why this overrides ``eval`` rather than reusing the
    type-keyed table.

    :ivar reductions: Rule ref → reduction body. A miss raises via the table.
    """

    reductions: IrMap = IrMap()

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Reduce ``n`` (a :class:`ParseTree`) to its IR node.

        :param d: The dispatcher (this reducer).
        :param n: The derivation to fold.
        :param nc: Unused at entry — children are resolved here.
        :returns: The IR node the matched rule reduces to.
        :raises IrKeyError: If no reduction is registered for the node's symbol.
        """
        tree = cast(ParseTree, n)
        reduced = cast(Sequence[IrSelf], RESOLVE_CHILDREN.eval(self, tree, ()))
        body = self.reductions[tree.symbol]
        return body.eval(self, tree, reduced)
