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

from typing import ClassVar

from lexic.ir.base import (
    IrAtom,
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
    "IrRuleRef",
    "IrSequence",
    "IrAlternation",
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


class IrRange[T: (str, int)](IrLeaf, IrNamedTuple[T, T | IrNoneType]):
    """Inclusive ``lo``-``hi`` range — the shared shape of quantifier bounds
    and char ranges.

    Quantifier bounds are int ranges (:class:`IrQuantifier`); char ranges are
    single-char str ranges (a char range IS an int range via ord/chr).  The
    open upper bound is :data:`~lexic.ir.base.IrNone` — int ranges only; char
    ranges are always closed.

    ``lo``/``hi`` are scalar payload, not IR-node children, so
    ``_child_attrs`` is empty; actions read them via
    :class:`~lexic.ir.action.IrField`.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: int | str
    hi: int | str | IrNoneType


class IrCharClass(IrSeq[IrRange | IrStr], IrAtom):
    """Character class — the variadic union of its interior elements.

    The node IS its element tuple: :class:`IrRange` entries for explicit
    ``x-y`` ranges, bare :class:`~lexic.ir.base.IrStr` runs for maximal
    stretches of single chars — ``[abc0-9]`` →
    ``IrCharClass(IrStr("abc"), IrRange("0", "9"))``.

    Brackets are NOT stored — the flavour renderer emits them.  Negation is
    NOT stored — ``[^...]`` parses to ``IrNot(IrCharClass(...))``; the
    negation hands its mark to the class action via the argument channel.

    Element payloads are flavour-encoded escape units (a range endpoint may
    be ``"\\x1F"`` — four source chars, one unit), so emission reproduces
    the source byte-exactly; decode-canonicalization arrives with the
    IR-native parser that obsoletes the Lark metagrammars.
    """


class IrQuantifier(IrRange):
    """Repetition bounds for an ``IrItem`` — the int-flavoured :class:`IrRange`.

    ``lo`` and ``hi`` mirror POSIX/PCRE repetition bounds:

    - ``IrQuantifier(1, 1)`` — exactly once (the default; no postfix operator).
    - ``IrQuantifier(0, 1)`` — optional (``?``).
    - ``IrQuantifier(0, IrNone)`` — zero-or-more (``*``).
    - ``IrQuantifier(1, IrNone)`` — one-or-more (``+``).
    - ``IrQuantifier(m, n)`` — between ``m`` and ``n`` times (``{m,n}``).

    ``hi=IrNone`` means unbounded (no upper limit).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: int = 1
    hi: int | IrNoneType = 1


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
