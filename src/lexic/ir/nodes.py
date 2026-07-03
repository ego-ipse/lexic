"""IR AST node dataclasses — primitive node model.

Nodes *are* their payload:

- str-leaves subclass :class:`str` (``IrStr`` tier);
- variadic collections subclass :class:`tuple` (``IrSeq`` tier);
- fixed-arity records are :class:`IrNamedTuple` named tuples.

The abstract spine — :class:`IrSelf`, :class:`IrNode`, :class:`IrLeaf`,
:class:`IrAtom`, the primitive bases :class:`IrScalar`/:class:`IrStr`/
:class:`IrInt`/:class:`IrTuple`/:class:`IrNamedTuple`, and the absence sentinel
:data:`IrNone` — lives in :mod:`lexic.ir.base` and is re-exported here so that
``from lexic.ir.nodes import IrSelf`` keeps working. This module defines the
*concrete* grammar-AST nodes built on those bases.

Every IR node implements the structural protocol from :class:`IrSelf`:

- ``__call__(d, n, nc) -> Self``       identity evaluation
- ``eval(d, n, nc) -> Ir_co``          action-body protocol
- ``children() -> Sequence[Ir_co]``    children in traversal order
- ``rebuild(new_children) -> Self``    reconstruct under transformation

``__repr__`` is codegen: every node reproduces its own constructor call.
"""

from __future__ import annotations

from typing import ClassVar, Self

from lexic.ir.base import (
    IrAtom,
    IrChr,
    IrLeaf,
    IrNamedTuple,
    IrNoneType,
    IrSeq,
    IrStr,
)

__all__ = [
    # Concrete grammar-AST nodes (defined here)
    "IrLiteral",
    "IrCharClass",
    "IrChr",
    "IrRuleRef",
    "IrSequence",
    "IrAlternation",
    "IrBounds",
    "IrRange",
    "IrQuantifier",
    "IrItem",
    "IrRule",
    "IrAst",
]


# ── Concrete str-leaf atoms ───────────────────────────────────────────


class IrLiteral(IrStr, IrAtom):
    """Literal string. The string itself is the payload (escapes already decoded).

    Carries a dual role in the IR:

    - As a grammar AST leaf: the literal characters that must appear verbatim.
    - As an action-language constant: a baked-in string an action body returns.

    The two roles are distinguished at eval time by the ``nc`` parameter — see
    the IR-shapes wiki entry.  Both roles produce the same ``str`` value, so
    the same node class serves both.
    """


class IrRuleRef(IrStr, IrAtom):
    """Reference to another rule. The string is the rule name.

    Used in rule bodies to denote a non-terminal; the name matches the
    ``IrRule.name`` of the referenced rule.
    """


# ── Concrete tuple-tier collections ───────────────────────────────────


class IrSequence(IrSeq["IrItem"]):
    """Concatenation (sequence) of ``IrItem`` nodes.

    Represents an ordered sequence of grammar items that must all match in
    order.  Corresponds to the ``items`` tuple in a single alternation arm.
    A homogeneous :class:`IrSeq` of ``IrItem``.
    """


class IrAlternation(IrSeq[IrSequence], IrAtom):
    """Ordered choice (alternation) between ``IrSequence`` arms.

    Represents the ``|``-separated alternatives in a grammar rule body.
    Each arm is an ``IrSequence``; the first matching arm wins.
    A homogeneous :class:`IrSeq` of ``IrSequence``.
    """


# ── Concrete composite records ────────────────────────────────────────


class IrBounds(IrLeaf, IrNamedTuple[int, "int | IrNoneType"]):
    """Shared ``(lo, hi)`` bounds — type-aware equality plus in-bounds membership.

    Abstract base for :class:`IrQuantifier` (int counts) and :class:`IrRange`
    (code-point spans). The two are siblings, not a chain — neither is
    substitutable for the other. ``lo``/``hi`` are scalar payload, not IR-node
    children, so ``_child_attrs`` is empty.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: int
    hi: int | IrNoneType

    def __eq__(self, other: object) -> bool:
        """Equal only to the same bounds subtype with equal endpoints."""
        if type(self) is not type(other):
            return False
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        """Negation of :meth:`__eq__` (``tuple`` supplies its own ``__ne__``)."""
        return not self == other

    def __hash__(self) -> int:
        """Hash by endpoint tuple (defining ``__eq__`` nulls the inherited hash)."""
        return super().__hash__()

    def __contains__(self, value: object) -> bool:
        """``lo <= value <= hi``; ``hi=IrNone`` means unbounded above."""
        if not isinstance(value, int):
            return False
        hi = self.hi
        if isinstance(hi, IrNoneType):
            return self.lo <= value
        return self.lo <= value <= hi


class IrQuantifier(IrBounds):
    """Repetition bounds for an ``IrItem`` — int counts; ``hi`` may be ``IrNone``.

    - ``IrQuantifier(1, 1)`` — exactly once (the default; no postfix operator).
    - ``IrQuantifier(0, 1)`` — optional (``?``).
    - ``IrQuantifier(0, IrNone)`` — zero-or-more (``*``).
    - ``IrQuantifier(1, IrNone)`` — one-or-more (``+``).
    - ``IrQuantifier(m, n)`` — between ``m`` and ``n`` times.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: int = 1
    hi: int | IrNoneType = 1

    def __new__(cls, lo: int = 1, hi: int | IrNoneType = 1) -> Self:
        """Store endpoints as plain ``int`` — ``hi`` alone may stay ``IrNone``.

        Reductions build bounds from :class:`~lexic.ir.action.IrUnradix`, which
        yields :class:`~lexic.ir.base.IrInt`. The canonical quantifier shape is
        plain ``int`` counts (repr-is-codegen emits the endpoints verbatim), so
        an int-like endpoint is narrowed to ``int`` here at construction.

        :param lo: Lower bound (any int-like value).
        :param hi: Upper bound (any int-like value) or :data:`IrNone`.
        :returns: The quantifier with plain-int endpoints.
        """
        hi_val = hi if isinstance(hi, IrNoneType) else int(hi)
        return super().__new__(cls, int(lo), hi_val)


class IrRange(IrBounds):
    """Inclusive char range — ``IrChr`` code-point endpoints, always closed.

    Endpoints are required (no defaults): a range is always built from explicit
    code points, so there is no placeholder bound.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: IrChr
    hi: IrChr


class IrCharClass(IrSeq[IrRange | IrChr], IrAtom):
    """Character class over code points — ``IrRange`` spans and single ``IrChr``.

    The node IS its element tuple: :class:`IrRange` entries for explicit
    ``x-y`` ranges, single :class:`~lexic.ir.base.IrChr` code points otherwise —
    ``[a0-9]`` → ``IrCharClass(IrChr("a"), IrRange(IrChr("0"), IrChr("9")))``.

    Brackets are NOT stored — the flavour renderer emits them. Negation is NOT
    stored — ``[^...]`` parses to ``IrNot(IrCharClass(...))``; the negation hands
    its mark to the class action via the argument channel. Glyph/escape spelling
    happens only at emit time, per flavour.
    """


class IrItem(IrNamedTuple[IrAtom, IrQuantifier]):
    """An atom paired with a quantifier — the universal wrapper node.

    ``IrItem`` is the fundamental unit of a grammar sequence.  Every element
    in an ``IrSequence`` is an ``IrItem``.  The ``atom`` field accepts any
    ``IrAtom`` subclass (``IrLiteral``, ``IrCharClass``, ``IrRuleRef``,
    ``IrNot``).

    Children: ``atom``, ``quantifier`` (both IR nodes — the whole tuple).
    """

    atom: IrAtom
    quantifier: IrQuantifier = IrQuantifier()


class IrRule(IrNamedTuple[IrStr, IrAlternation]):
    """A named grammar rule.

    The ``body`` is always an ``IrAlternation``, even for single-arm rules
    (a single arm is an ``IrAlternation`` containing one ``IrSequence``).

    Children: the single ``body`` ``IrAlternation``.
    Non-child payload: ``name`` (the rule identifier string).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    name: str
    body: IrAlternation


class IrAst(IrNamedTuple[IrSeq[IrRule], IrStr]):
    """Full grammar AST: a collection of rules plus the start-rule name.

    ``rules`` is an ``IrTuple`` of ``IrRule`` nodes (wrapped so a single
    child attribute can hold the whole collection and be replaced atomically
    by tree transformations).  ``start`` is the plain string name of the
    start rule.

    Children: the single ``rules`` ``IrTuple``.
    Non-child payload: ``start`` (start-rule name).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("rules",)

    rules: IrSeq = IrSeq()
    start: str = ""
