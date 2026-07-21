"""Encoding family — the codec that gives a char class's ordinals meaning.

A char class is a set of **ordinals**; an :class:`IrEncoding` is what those
ordinals mean — the ``universe`` (the ceiling for complement and ``.``),
:meth:`~IrEncoding.resolve` (a source spelling → an ordinal) and
:meth:`~IrEncoding.spell` (an ordinal → its spelling). Unicode is one encoding;
a tokenizer is another. The two are peers: everything UTF-specific (the
``MAX_CODEPOINT`` ceiling, the ``chr``/``ord`` codec) is an :class:`IrUnicode`
property, not a hard-coded assumption in the set-math.

:class:`IrEncoding` is a non-generic **role marker** on
:class:`~lexic.ir.base.IrNode` (the :class:`~lexic.ir.base.IrAtom` pattern) — it
carries the shared, universe-relative complement algebra and declares the codec
surface; concrete encodings supply the codec. Absence is
:data:`~lexic.ir.base.IrNone`; a tokenizer's vocab is an
:class:`~lexic.ir.mapping.IrMap`, never a ``dict``. An encoding is referenced by
name from an :class:`~lexic.ir.nodes.IrAlphabet`, and a registry of encodings is
just an ``IrMap[IrStr, IrEncoding]``.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable
from typing import ClassVar, Self, cast

from lexic.ir.base import IrNamedTuple, IrNode, IrNone, IrNoneType, IrStr, IrTuple
from lexic.ir.mapping import IrMap
from lexic.ir.meta import IrSingleton
from lexic.ir.nodes import MAX_CODEPOINT, IrCharClass, IrChr


class IrEncoding(IrNode):
    """Role marker + shared codec surface — the :class:`IrAtom` pattern.

    Non-generic, mixed into a concrete encoding by plain inheritance. Concrete
    encodings supply :attr:`universe`, :meth:`resolve` and :meth:`spell`; the
    complement algebra is shared here, parameterised by :attr:`universe`.

    Open-set: a future encoding adds :class:`IrEncoding` to its bases without
    touching any dispatch table.
    """

    @property
    @abstractmethod
    def universe(self) -> int:
        """The highest ordinal in this alphabet — the complement / ``.`` ceiling."""

    @abstractmethod
    def resolve(self, spelling: str) -> IrChr | IrNoneType:
        """A source spelling → its ordinal, or :data:`IrNone` when unmapped.

        :param spelling: The source text of a single class member / token.
        :returns: The ordinal as an :class:`~lexic.ir.nodes.IrChr`, or
            :data:`IrNone` if this encoding does not map ``spelling`` to exactly
            one ordinal.
        """

    @abstractmethod
    def spell(self, ordinal: int) -> IrStr:
        """An ordinal → its source spelling under this encoding.

        :param ordinal: A member ordinal of this alphabet.
        :returns: The spelling as an :class:`~lexic.ir.base.IrStr`.
        """

    def complement(self, inner: IrCharClass) -> IrCharClass:
        """The complement of ``inner`` over ``[0, universe]`` — ``.`` / ``!``.

        Reuses :meth:`IrCharClass.intervals` / :meth:`IrCharClass.from_intervals`
        — the ordinal set-math is alphabet-neutral; only the ceiling is this
        encoding's :attr:`universe` rather than the Unicode ``MAX_CODEPOINT``.

        :param inner: The class to complement (ordinals in this alphabet).
        :returns: The complement class in canonical form.
        """
        spans: list[tuple[int, int]] = []
        cursor = 0
        for lo, hi in inner.intervals():
            if lo > cursor:
                spans.append((cursor, lo - 1))
            cursor = max(cursor, hi + 1)
        if cursor <= self.universe:
            spans.append((cursor, self.universe))
        return IrCharClass.from_intervals(spans)


class IrUnicode(IrEncoding, metaclass=IrSingleton):
    """The default encoding — ordinals ARE Unicode code points. A singleton.

    Its codec is algorithmic (``ord``/``chr``); escape spelling is layered on
    top by the flavour's emit half, not by the encoding.
    """

    def __new__(cls) -> Self:
        """Return the singleton instance."""
        return super().__new__(cls)

    @property
    def universe(self) -> int:
        """``MAX_CODEPOINT`` — the whole Unicode range."""
        return MAX_CODEPOINT

    def resolve(self, spelling: str) -> IrChr | IrNoneType:
        """A single glyph → its code point; anything longer is unmapped."""
        return IrChr(ord(spelling)) if len(spelling) == 1 else IrNone

    def spell(self, ordinal: int) -> IrStr:
        """The glyph for ``ordinal``."""
        return IrStr(chr(ordinal))

    def __repr__(self) -> str:
        """Codegen repr — the singleton's constructor."""
        return "IrUnicode()"


class IrTokenizer(IrNamedTuple[IrStr, IrMap, IrMap], IrEncoding, init=False):
    """A token encoding — ordinals are vocab ids. The vocab is an ``IrMap``.

    ``encode`` maps each token's spelling (``IrStr``) to its id (``IrChr``);
    ``decode`` is the inverse (``IrChr`` → ``IrStr``), so :meth:`spell` is O(1)
    — the two directions are the id↔text sections of the compiled-tokenizer
    structure. Built from the forward map alone via :meth:`from_vocab`. The
    structural base leads (the ``IrLiteral(IrStr, IrAtom)`` order);
    :class:`IrEncoding` is the role marker.

    Children: none walked — every field is codec data (``_child_attrs = ()``,
    the :class:`~lexic.ir.nodes.IrBounds` precedent).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    name: IrStr
    encode: IrMap
    decode: IrMap

    def __new__(cls, name: str, encode: IrMap, decode: IrMap) -> Self:
        """Store the two directions directly; prefer :meth:`from_vocab`.

        :param name: The registry name of this tokenizer.
        :param encode: Spelling → id map.
        :param decode: Id → spelling map (the inverse of ``encode``).
        :returns: The tokenizer encoding.
        """
        return cast(Callable[..., Self], super().__new__)(
            cls, IrStr(name), encode, decode
        )

    @classmethod
    def from_vocab(cls, name: str, encode: IrMap) -> Self:
        """Build a tokenizer from the forward ``spelling → id`` map alone.

        :param name: The registry name.
        :param encode: The vocab (``IrStr`` spelling → ``IrChr`` id).
        :returns: The tokenizer, with the inverse ``decode`` map derived.
        """
        decode = IrMap(*(IrTuple(i, s) for s, i in encode.items()))
        return cls(name, encode, decode)

    @property
    def universe(self) -> int:
        """One past the highest id — the id-space size (derived, not stored)."""
        return max((int(i) for i in self.decode.keys()), default=-1) + 1

    def resolve(self, spelling: str) -> IrChr | IrNoneType:
        """A token's text → its id, or :data:`IrNone` when not one vocab token."""
        found = self.encode.get(IrStr(spelling))
        return found if found is not None else IrNone

    def spell(self, ordinal: int) -> IrStr:
        """The token id → its text (``[id]`` fallback for an unmapped id)."""
        found = self.decode.get(IrChr(ordinal))
        return found if found is not None else IrStr(f"[{ordinal}]")

    def boundaries(self, text: str) -> list[tuple[int, int, int]]:
        """Segment ``text`` into ``(char_start, char_end, id)`` token spans.

        A deterministic longest-match segmentation over the vocab — the
        prototype segmenter, whose *algorithm* is the swappable part (ranked
        byte-level BPE is the fidelity follow-up). A position matching no vocab
        token advances one character with no token-match point (the
        unsegmentable / mid-multibyte case). These spans are what the engine
        scans a token terminal against at boundary columns.

        :param text: The instance text to segment.
        :returns: The token spans in order — ``(start, end, id)`` over ``text``.
        """
        keys = sorted(self.encode.keys(), key=len, reverse=True)
        spans: list[tuple[int, int, int]] = []
        cursor = 0
        while cursor < len(text):
            match = next((k for k in keys if k and text.startswith(k, cursor)), None)
            if match is None:
                cursor += 1
                continue
            spans.append((cursor, cursor + len(match), int(self.encode[match])))
            cursor += len(match)
        return spans

    def tokenize(self, text: str) -> list[int]:
        """The token ids of ``text`` under :meth:`boundaries`.

        :param text: The instance text to segment.
        :returns: The ids of the covering token spans, in order.
        """
        return [tid for _, _, tid in self.boundaries(text)]
