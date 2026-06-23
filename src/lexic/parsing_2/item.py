"""Earley items — a dotted position in one alternation arm, as an IR node.

An :class:`EarleyItem` is the classical Earley triple ``(rule, dot, origin)``
specialised to the IR shape: the "rule" is one :class:`~lexic.ir.nodes.IrSequence`
arm, the dot is an index into that arm, and the origin is the input column where
the arm was predicted. It IS-AN :class:`~lexic.ir.base.IrNamedTuple`, so identity
(equality / hashing for Earley-set dedup) is native tuple identity over the four
fields — and the SPPF/derivation node is deliberately NOT a field, exactly as in
Lark's ``Item`` (its ``node`` is a mutable side attribute, excluded from ``==``).

The item is **pure data**: it carries no methods of its own. The few derived
values it once exposed (the symbol after the dot, the advanced item) are computed
inline in the operation ``eval`` bodies that need them (see
:mod:`lexic.parsing_2.ops` and :mod:`lexic.parsing_2.engine`), keeping the record
to ``eval`` + dunders only.
"""

from __future__ import annotations

from typing import ClassVar, Self

from lexic.ir.base import IrNamedTuple
from lexic.ir.nodes import IrRuleRef, IrSequence


class EarleyItem(IrNamedTuple[IrRuleRef, IrSequence, int, int]):
    """A dotted arm: ``rule_name -> alpha . beta``, predicted at ``origin``.

    ``rule_name`` is an :class:`~lexic.ir.nodes.IrRuleRef` (not a bare
    :class:`~lexic.ir.base.IrStr`) so it compares equal to the ``IrRuleRef`` that
    other items hold after the dot — :class:`~lexic.ir.base.IrScalar`'s
    type-aware equality makes distinct leaf kinds never equal, so the engine
    standardises on one kind for rule identity.

    The four fields are scalar payload, not dispatched children
    (``_child_attrs = ()``) — an item is engine state, never walked as grammar.

    The symbol after the dot is ``arm[dot].atom`` when ``dot < len(arm)`` else
    :data:`~lexic.ir.base.IrNone`; the advanced item is
    ``EarleyItem(rule_name, arm, dot + 1, origin)``. Both are spelled inline at
    the (few) call sites rather than as methods here.

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

    def __new__(
        cls, rule_name: IrRuleRef, arm: IrSequence, dot: int, origin: int
    ) -> Self:
        """Fast positional constructor — the engine's hottest allocation.

        All four fields are always supplied positionally, so the generic
        :class:`IrNamedTuple` path (kwarg merge, defaults, cast) is never needed.
        Building the tuple directly skips two Python-level ``__new__`` frames per
        item — the dominant per-item construction cost.

        :param rule_name: The non-terminal this arm defines.
        :param arm: The single alternation arm.
        :param dot: Index into ``arm`` of the next symbol to match.
        :param origin: Input column where this arm was predicted.
        :returns: A new :class:`EarleyItem`.
        """
        return tuple.__new__(cls, (rule_name, arm, dot, origin))
