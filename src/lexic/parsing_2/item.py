"""Earley items — a dotted position in one alternation arm, as an IR node.

An :class:`EarleyItem` is the classical Earley triple ``(rule, dot, origin)``
specialised to the IR shape: the "rule" is one :class:`~lexic.ir.nodes.IrSequence`
arm, the dot is an index into that arm, and the origin is the input column where
the arm was predicted. It IS-AN :class:`~lexic.ir.base.IrNamedTuple`, so identity
(equality / hashing for Earley-set dedup) is native tuple identity over the four
fields — and the SPPF/derivation node is deliberately NOT a field, exactly as in
Lark's ``Item`` (its ``node`` is a mutable side attribute, excluded from ``==``).
"""

from __future__ import annotations

from typing import ClassVar

from lexic.ir.base import IrAtom, IrNamedTuple, IrNone, IrNoneType
from lexic.ir.nodes import IrItem, IrRuleRef, IrSequence


class EarleyItem(IrNamedTuple[IrRuleRef, IrSequence, int, int]):
    """A dotted arm: ``rule_name -> alpha . beta``, predicted at ``origin``.

    ``rule_name`` is an :class:`~lexic.ir.nodes.IrRuleRef` (not a bare
    :class:`~lexic.ir.base.IrStr`) so it compares equal to the ``IrRuleRef`` that
    other items hold after the dot — :class:`~lexic.ir.base.IrScalar`'s
    type-aware equality makes distinct leaf kinds never equal, so the engine
    standardises on one kind for rule identity.

    The four fields are scalar payload, not dispatched children
    (``_child_attrs = ()``) — an item is engine state, never walked as grammar.

    :ivar rule_name: The non-terminal this arm defines.
    :ivar arm: The single alternation arm (sequence of :class:`IrItem`).
    :ivar dot: Index into ``arm`` of the next symbol to match.
    :ivar origin: Input column where this arm was predicted.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    rule_name: IrRuleRef
    arm: IrSequence
    dot: int
    origin: int

    @property
    def is_complete(self) -> bool:
        """True when the dot is past the last symbol — the arm fully matched.

        :returns: Whether ``dot`` has reached the end of ``arm``.
        """
        return self.dot >= len(self.arm)

    def next_item(self) -> IrItem | IrNoneType:
        """The :class:`IrItem` at the dot, or :data:`IrNone` if complete.

        :returns: The item to match next, or the absence sentinel.
        """
        return IrNone if self.is_complete else self.arm[self.dot]

    def next_symbol(self) -> IrAtom | IrNoneType:
        """The atom the dispatch table keys on: the dotted item's atom, or
        :data:`IrNone` when complete (which routes to :class:`~lexic.parsing_2.ops.Complete`).

        Assumes the arm is Earley-normalised to ``(1, 1)`` quantifiers (see
        :mod:`lexic.parsing_2.normalize`); the quantifier is ignored here.

        :returns: The next atom, or :data:`IrNone`.
        """
        nxt = self.next_item()
        return IrNone if isinstance(nxt, IrNoneType) else nxt.atom

    def advance(self) -> EarleyItem:
        """A new item with the dot moved one symbol right (same identity otherwise).

        :returns: The advanced :class:`EarleyItem`.
        """
        return EarleyItem(self.rule_name, self.arm, self.dot + 1, self.origin)
