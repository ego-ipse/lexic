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
would own ``ABNF_REDUCTIONS``; this module is the flavour-agnostic walker.
"""

from __future__ import annotations

from lexic.ir.base import IrSelf, IrTuple
from lexic.ir.mapping import IrMap
from lexic.ir.walk import IrDispatch
from lexic.parsing_2.forest import ParseTree


class Reducer(IrDispatch):
    """Bottom-up fold of a :class:`ParseTree` into IR, driven by ``reductions``.

    Each node's children are reduced first, then the body bound to the node's
    ``symbol`` is evaluated with those reduced children on the argument channel
    (``nc``) and the tree as ``n`` — so a body reads children with
    :class:`~lexic.ir.action.IrArgs` and rule-level payload with
    :class:`~lexic.ir.action.IrField`. ``self`` is the dispatcher, so a body that
    sub-dispatches (e.g. :class:`~lexic.ir.action.IrChild`) recurses through here.

    :ivar reductions: Rule ref → reduction body. A miss raises via the table.
    """

    reductions: IrMap = IrMap()

    def reduce(self, tree: ParseTree) -> IrSelf:
        """Reduce ``tree`` to its IR node.

        :param tree: The derivation to fold.
        :returns: The IR node the matched rule reduces to.
        :raises IrKeyError: If no reduction is registered for ``tree.symbol``.
        """
        reduced = IrTuple(
            *(
                self.reduce(child) if isinstance(child, ParseTree) else child
                for child in tree.kids
            )
        )
        body = self.reductions[tree.symbol]
        return body.eval(self, tree, reduced)
