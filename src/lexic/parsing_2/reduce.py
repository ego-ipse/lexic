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
from lexic.parsing_2.normalize import is_synthetic_name


class Reducer(IrDispatch):
    """Bottom-up fold of a :class:`ParseTree` into IR, driven by ``reductions``.

    Each node's children are reduced first, then the body bound to the node's
    ``symbol`` is evaluated with those reduced children on the argument channel
    (``nc``) and the tree as ``n`` — so a body reads children with
    :class:`~lexic.ir.action.IrArgs` and rule-level payload with
    :class:`~lexic.ir.action.IrField`. ``self`` is the dispatcher, so a body that
    sub-dispatches (e.g. :class:`~lexic.ir.action.IrChild`) recurses through here.

    Synthetic rules minted by normalisation (quantifier/group desugaring, see
    :func:`~lexic.parsing_2.normalize.is_synthetic_name`) carry no reduction:
    their reduced children are spliced into the parent in place, so the table
    only needs entries for the conceptual (pre-desugar) grammar.

    :ivar reductions: Rule ref → reduction body. A miss raises via the table.
    """

    reductions: IrMap = IrMap()

    def reduce(self, tree: ParseTree) -> IrSelf:
        """Reduce ``tree`` to its IR node.

        :param tree: The derivation to fold.
        :returns: The IR node the matched rule reduces to.
        :raises IrKeyError: If no reduction is registered for ``tree.symbol``.
        """
        reduced = IrTuple(*self._reduced_children(tree))
        body = self.reductions[tree.symbol]
        return body.eval(self, tree, reduced)

    def _reduced_children(self, tree: ParseTree) -> list[IrSelf]:
        """The reduced children of ``tree``, with synthetic nodes spliced away.

        A child that is a synthetic-rule sub-tree contributes its own reduced
        children (recursively), so a desugared repetition/group is flattened back
        to the conceptual child sequence the reduction table expects.

        :param tree: The node whose children to reduce.
        :returns: The reduced children in source order.
        """
        out: list[IrSelf] = []
        for child in tree.kids:
            if not isinstance(child, ParseTree):
                out.append(child)
            elif is_synthetic_name(str(child.symbol)):
                out.extend(self._reduced_children(child))
            else:
                out.append(self.reduce(child))
        return out
