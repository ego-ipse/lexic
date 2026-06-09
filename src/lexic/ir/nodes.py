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
    "IrQuantifier",
    "IrItem",
    "IrNot",
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


class IrCharClass(IrStr, IrAtom):
    """Character class. The string is the canonical POSIX-style interior pattern.

    Examples: ``'a-z'``, ``'0-9'``, ``'a-zA-Z_'``.  The surrounding ``[``/``]``
    brackets are NOT stored — they are emitted by the flavour renderer.
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


class IrQuantifier(IrLeaf, IrNamedTuple[int, int | None]):
    """Repetition bounds for an ``IrItem``.

    ``min`` and ``max`` mirror POSIX/PCRE repetition bounds:

    - ``IrQuantifier(1, 1)`` — exactly once (the default; no postfix operator).
    - ``IrQuantifier(0, 1)`` — optional (``?``).
    - ``IrQuantifier(0, None)`` — zero-or-more (``*``).
    - ``IrQuantifier(1, None)`` — one-or-more (``+``).
    - ``IrQuantifier(m, n)`` — between ``m`` and ``n`` times (``{m,n}``).

    ``max=None`` means unbounded (no upper limit).  ``min``/``max`` are scalar
    payload, not IR-node children, so ``_child_attrs`` is empty.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    min: int = 1
    max: int | None = 1


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


class IrNot[Ir_co: IrAtom = IrAtom](IrNamedTuple[Ir_co], IrAtom):
    """Negation — an ``IrAtom`` that inverts a character class or atom.

    Corresponds to ``[^…]`` (negated character class) in GBNF.  The ``body``
    field is typically an ``IrCharClass`` but accepts any ``IrAtom`` subtype
    via the ``Ir_co`` parameter.

    Because ``IrNot`` IS-AN ``IrAtom``, it can be wrapped by ``IrItem``
    like any other atom.

    Children: the single ``body`` atom.

    :param Ir_co: Concrete atom type of the wrapped body (defaults to ``IrAtom``).
    """

    body: Ir_co


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
