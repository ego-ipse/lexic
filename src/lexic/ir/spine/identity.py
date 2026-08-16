"""The identity walk — what a value's graph IS, under one child definition.

A loaded grammar, a reducer, a parsed document: each is a graph of ``IrSelf``
objects, and three facts about it no repr can carry. One object reached from
four places is ONE node with four arrivals, not four copies. Absence is a node
like any other. And some nodes carry a payload no text can name, which is a
fact about the value rather than a failure to print it.

**The child definition, stated once.** A node's children are the elements of
its own field tuple that are themselves nodes — the spine's central sentence
(*a record IS its field tuple*) read as a traversal. That is the only
definition this module walks, and the number it reports for sharing means
nothing except under it. Two consequences, both deliberate:

- it is WIDER than :meth:`~lexic.ir.spine.spine.IrSelf.children`, which honours
  ``_child_attrs`` and so omits a record's non-dispatched fields. Those fields
  hold real nodes, shared as often as any other, and an identity walk that
  dropped them would undercount;
- a map is a LEAF. :class:`~lexic.ir.action.mapping.IrMapping` carries a dict
  in a slot, not a tuple, so a dispatch table censuses as one node and the
  bodies filed in it are outside this walk's reach. A census over a flavour's
  reducer therefore reports the table, not the table's contents.

Counting sharing under one definition and reporting it under another is how a
walk manufactures a delta out of nothing; the whole point of naming the
definition is that the census can be checked against it.
"""

from __future__ import annotations

from typing import ClassVar, Self

from lexic.ir.spine.records import IrNamedTuple, IrSeq
from lexic.ir.spine.spine import IrLambda, IrSelf


def field_children(node: IrSelf) -> tuple[IrSelf, ...]:
    """This node's children — the node-valued elements of its field tuple.

    :param node: Any node.
    :returns: The children in field order; empty for a scalar, a map, or any
        other node whose payload is not a tuple.
    """
    parts = tuple(node) if isinstance(node, tuple) else ()
    return tuple(part for part in parts if isinstance(part, IrSelf))


def unspellable(node: IrSelf) -> bool:
    """Does this node carry something no name can spell back?

    :class:`~lexic.ir.spine.spine.IrLambda` is that node by construction — the
    spine holds it as the one node whose payload is a callable. A tuple node
    joins it when one of its own parts is a bare callable; a class is not one,
    because a class has a name and the notation spells names.

    :param node: Any node.
    :returns: ``True`` when the node's payload defeats repr-is-codegen.
    """
    if isinstance(node, IrLambda):
        return True
    parts = tuple(node) if isinstance(node, tuple) else ()
    return any(
        callable(part) and not isinstance(part, (IrSelf, type)) for part in parts
    )


class IrIdentity(IrNamedTuple[IrSelf, int, bool]):
    """One distinct node of a census — the node, and how the walk met it.

    :ivar node: The node itself, held so the census is readable without a
        second traversal to resolve an index back to a value.
    :ivar reached: How many times the walk arrived here — one per edge that
        points at this node, plus one for the root. ``1`` is an unshared node;
        anything higher is sharing, and sharing is the normal case.
    :ivar unspellable: ``True`` when this node is on the refusal boundary.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("node",)
    node: IrSelf
    reached: int
    unspellable: bool


class IrCensus(IrSeq[IrIdentity]):
    """Every DISTINCT node reachable from a root, in first-reach order.

    Distinct by identity, not by equality: on this spine equal values are
    routinely different occurrences, and two ``IrLiteral('a')`` objects are two
    nodes here even though they compare equal. ``len(census)`` is the unique
    count and ``sum(entry.reached for entry in census)`` the total arrivals.
    """

    def shared(self) -> Self:
        """The nodes the walk arrived at more than once.

        :returns: The sub-census of shared nodes, in first-reach order.
        """
        return type(self)(*(entry for entry in self if entry.reached > 1))

    def refusals(self) -> Self:
        """The refusal boundary — the nodes no notation can spell back.

        :returns: The sub-census of unspellable nodes, in first-reach order.
        """
        return type(self)(*(entry for entry in self if entry.unspellable))


def census(root: IrSelf) -> IrCensus:
    """Walk ``root`` and report every distinct node under it.

    Iterative, so a deep chain cannot exhaust the interpreter stack, and
    pre-order, so a parent always precedes the children it reaches.

    :param root: The value to walk — any node, of any type.
    :returns: The census, root first.
    """
    at: dict[int, int] = {}  # id → index; `order` holds every node, so no id reuse
    order: list[IrSelf] = []
    reached: list[int] = []
    stack: list[IrSelf] = [root]
    while stack:
        node = stack.pop()
        seen = at.get(id(node))
        if seen is not None:
            reached[seen] += 1
            continue
        at[id(node)] = len(order)
        order.append(node)
        reached.append(1)
        stack.extend(reversed(field_children(node)))
    entries = (
        IrIdentity(node, reached[i], unspellable(node)) for i, node in enumerate(order)
    )
    return IrCensus(*entries)
