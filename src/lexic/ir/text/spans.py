"""Addresses and spans — WHERE an occurrence stands, and what it covers.

An occurrence is a value standing somewhere: a field of a record, an element
of a repeated field, a structural literal of a rule. Equal values are not
distinct on this spine — a node IS its payload, and in ``{"a": 1, "b": 1}``
under ``json.gbnf`` one ``Ws`` object really is reached seven times — so the
only thing telling two occurrences apart is where each stands. That is what
an :class:`IrAddress` is, and it is why nothing here is derived from a value.

The contract the family exists to keep:

- an address is a PATH built TOP-DOWN by whatever walk produces it, each step
  supplied POSITIONALLY by the parent. It is never recovered from a value and
  never looked up by equality — ``list.index`` on this spine finds the first
  EQUAL sibling, which is a different occurrence with the same payload.
- a walk producing addresses may not splice shared subtrees. The id-memoising
  drivers (:class:`~lexic.ir.action.walk.IrBottomUp`) transform a shared
  object once and reuse the result everywhere it appeared, which is right for
  a transform and wrong for an address: sharing is the normal case here, not
  a corner.
- the steps are in the parent's own EMISSION order — item-slot, i.e. document
  order — which is NOT field-declaration order. ``JsonText`` declares
  ``(value, ws, ws2)`` and emits ``ws, value, ws2``.
- an :class:`IrSpan` is half-open ``[start, end)`` in CODE UNITS: ``len`` of
  the emitted string, the string's own truth. Terminal columns (wide glyphs
  counted twice) and device pixels are projections a consumer computes from
  the text a span selects — never alternative units for the span itself,
  because only code units can slice the string back.

The two correspondence shapes are what a walk hands back: :class:`IrExtent`
(this occurrence is spelled over this span) and :class:`IrOrigin` (this built
occurrence came from that source occurrence). Both are pairs of the leaves
above, so anything that can point at one can point at the other — which is
the property a later trace protocol needs, its events referencing a document
through these same records rather than a vocabulary of their own.
"""

from __future__ import annotations

from typing import ClassVar, Self

from lexic.ir.spine.records import IrNamedTuple, IrSeq


class IrStep(IrNamedTuple[str, int]):
    """One step of an address — what the parent calls a part, and where it sits.

    :ivar field: The binding's field name for this part, or ``""`` where the
        parent has no name for it (a structural literal, a ``value_str``
        payload, an element of a repeated field).
    :ivar slot: The part's ordinal in the parent's emission, 0-based, in
        document order. This is the half that IDENTIFIES the occurrence —
        unique among siblings by construction, and defined even where
        ``field`` is empty; ``field`` is what the grammar calls it.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    field: str
    slot: int


class IrAddress(IrSeq[IrStep]):
    """An occurrence's path from the root — steps outermost first.

    The empty address is the root itself. Build one only by extending its
    parent (:meth:`child`); an address assembled any other way is a guess.
    """

    def child(self, field: str, slot: int) -> Self:
        """This address extended by one step — the top-down builder.

        :param field: The parent's name for the part, or ``""``.
        :param slot: The part's ordinal in the parent's emission.
        :returns: The child occurrence's address.
        """
        return type(self)(*self, IrStep(field, slot))


class IrSpan(IrNamedTuple[int, int]):
    """A half-open ``[start, end)`` stretch of a text, in code units.

    :ivar start: First code-unit offset covered.
    :ivar end: One past the last, so ``end - start`` is the width and
        ``start == end`` is a real empty span — an occurrence that spelled
        nothing, which is a fact rather than an absence.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    start: int
    end: int

    def of(self, text: str) -> str:
        """The stretch of ``text`` this span covers.

        :param text: The text the span was measured against.
        :returns: ``text[start:end]``.
        """
        return text[self.start : self.end]


class IrExtent(IrNamedTuple[IrAddress, IrSpan]):
    """One occurrence, and the span its spelling occupies.

    The emit-side correspondence, readable both ways: where in the text to
    look for an occurrence, and which occurrence a click at an offset is in.

    :ivar address: The occurrence's path from the emission's root.
    :ivar span: Where its spelling landed in the emitted text.
    """

    address: IrAddress
    span: IrSpan


class IrExtents(IrSeq[IrExtent]):
    """Every occurrence of one emission, in document order (parents first)."""


class IrEmission(IrNamedTuple[str, IrExtents]):
    """An emitted text and where every occurrence in it landed.

    One product rather than two calls, because the two halves are only
    meaningful together: spans measured against one emission cannot be
    trusted against another rendering of the same value.

    :ivar text: The emitted text — identical to the model's ``to_text()``.
    :ivar extents: One entry per emitted part, root first.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("extents",)
    text: str
    extents: IrExtents


class IrOrigin(IrNamedTuple[IrAddress, IrAddress]):
    """One built occurrence, and the source occurrence it came from.

    The transform-side correspondence, in the same vocabulary as
    :class:`IrExtent` — so a product occurrence reached through an origin can
    be pointed at in either document by an extent set of that document's own.

    :ivar address: The occurrence's path in the product.
    :ivar source: Its path in the source the transform read.
    """

    address: IrAddress
    source: IrAddress


class IrOrigins(IrSeq[IrOrigin]):
    """Every built occurrence's source, in the product's document order."""
