"""Encoding family — the codec that gives a char class's ordinals meaning.

``IrEncoding`` and the two that need no vocabulary: ``IrUnicode``, where an
ordinal IS the code point, and ``IrUtf``, where it is a byte of one.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from typing import Self

from lexic.ir.mapping import IrMap
from lexic.ir.meta import IrSingleton
from lexic.ir.nodes import MAX_CODEPOINT, IrCharClass, IrChr
from lexic.ir.records import IrTuple
from lexic.ir.scalars import IrStr
from lexic.ir.spine import IrNode, IrNone, IrNoneType, IrSelf

Vocab = Mapping[str, int] | IrMap
"""A pythonic ``spelling → id`` vocab a builder coerces to the spine."""

Merges = Sequence[tuple[str, str]] | IrTuple
"""Ordered merge dyads — position is rank; coerced to the ``ranks`` map."""


class IrEncoding(IrNode):
    """Role marker + shared codec surface — the :class:`IrAtom` pattern.

    Non-generic, mixed into a concrete encoding by plain inheritance. Concrete
    encodings supply the whole codec the engine consumes — :attr:`universe`,
    :meth:`resolve`, :meth:`spell`, :meth:`boundaries` and :meth:`ids` — and
    inherit the shared halves: the universe-relative complement algebra and the
    derived :meth:`tokenize`. The engine couples to exactly :meth:`boundaries` +
    :meth:`spell` + :meth:`ids`; that surface must not grow.

    Return-type rule: record **fields** are always IR-typed; intrinsic
    **method** returns may be plain Python (the ``IrCharClass.intervals``
    precedent).

    Open-set: a future encoding adds :class:`IrEncoding` to its bases without
    touching any dispatch table.
    """

    @property
    @abstractmethod
    def universe(self) -> int:
        """The highest ordinal in this alphabet — INCLUSIVE.

        The ceiling for complement and ``.``. Inclusive because that is what
        "highest" means and what two of the three encodings always returned;
        the third returned one PAST it, and the two consumers disagreed about
        which convention they were reading — one refused a valid ceiling
        value, the other admitted an ordinal past the end.
        """

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

    @abstractmethod
    def boundaries(self, text: str) -> list[tuple[int, int, int]]:
        """Segment ``text`` into ``(char_start, char_end, ordinal)`` spans.

        :param text: The instance text to segment.
        :returns: The covering spans in order over ``text``.
        """

    @abstractmethod
    def ids(self) -> Iterable[int]:
        """Every ordinal this encoding maps — the alphabet membership set."""

    def tokenize(self, text: str) -> list[int]:
        """The ordinals of ``text``'s covering spans under :meth:`boundaries`.

        :param text: The instance text to segment.
        :returns: The ordinals of the covering spans, in order.
        """
        return [ordinal for _, _, ordinal in self.boundaries(text)]

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

    def boundaries(self, text: str) -> list[tuple[int, int, int]]:
        """The degenerate per-char segmentation — one span per code point."""
        return [(i, i + 1, ord(ch)) for i, ch in enumerate(text)]

    def ids(self) -> range:
        """Every code point — the whole Unicode range."""
        return range(MAX_CODEPOINT + 1)

    def __repr__(self) -> str:
        """Codegen repr — the singleton's constructor."""
        return "IrUnicode()"


_HIGH_LO, _HIGH_HI = 0xD800, 0xDBFF
_LOW_LO, _LOW_HI = 0xDC00, 0xDFFF


class IrUtf(IrEncoding, metaclass=IrSingleton):
    """UTF-16 code-unit encoding — the unit-level transform child. A singleton.

    Where :class:`IrUnicode`'s ordinals ARE code points, this codec's ordinals
    are UTF-16 **code units**: an astral code point occupies two ordinals (a
    surrogate pair). The pairing knowledge lives here and nowhere else —
    :meth:`combine` folds adjacent high/low units in decoded text into their
    code points, and as an action body (:meth:`eval`) the encoding IS the
    reduce-side unit-decode step: a format whose escapes denote code units
    (json ``\\uXXXX``) decodes each escape per-unit, then pipes the assembled
    string through this codec once.
    """

    def __new__(cls) -> Self:
        """Return the singleton instance."""
        return super().__new__(cls)

    @property
    def universe(self) -> int:
        """``0xFFFF`` — the code-unit ceiling."""
        return 0xFFFF

    def resolve(self, spelling: str) -> IrChr | IrNoneType:
        """A single BMP glyph → its code unit; astral / longer is unmapped."""
        if len(spelling) == 1 and ord(spelling) <= 0xFFFF:
            return IrChr(ord(spelling))
        return IrNone

    def spell(self, ordinal: int) -> IrStr:
        """The char for a code unit (a lone surrogate spells as itself)."""
        return IrStr(chr(ordinal))

    def boundaries(self, text: str) -> list[tuple[int, int, int]]:
        """Per-unit segmentation — an astral char yields its pair on one span."""
        spans: list[tuple[int, int, int]] = []
        for i, ch in enumerate(text):
            point = ord(ch)
            if point <= 0xFFFF:
                spans.append((i, i + 1, point))
                continue
            point -= 0x10000
            spans.append((i, i + 1, _HIGH_LO + (point >> 10)))
            spans.append((i, i + 1, _LOW_LO + (point & 0x3FF)))
        return spans

    def ids(self) -> range:
        """Every code unit."""
        return range(0x10000)

    def combine(self, text: str) -> IrStr:
        """Fold adjacent high/low surrogate units into their code points.

        :param text: Text whose escape-decoded chars may hold lone units.
        :returns: The text with every adjacent pair combined; lone units
            that pair with nothing pass through unchanged.
        """
        out: list[str] = []
        i, n = 0, len(text)
        while i < n:
            high = ord(text[i])
            paired = (
                _HIGH_LO <= high <= _HIGH_HI
                and i + 1 < n
                and _LOW_LO <= ord(text[i + 1]) <= _LOW_HI
            )
            if not paired:
                out.append(text[i])
                i += 1
                continue
            low = ord(text[i + 1])
            out.append(chr(0x10000 + ((high - _HIGH_LO) << 10) + (low - _LOW_LO)))
            i += 2
        return IrStr("".join(out))

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """The codec as an action body — :meth:`combine` over the focus text."""
        return self.combine(str(n))

    def __repr__(self) -> str:
        """Codegen repr — the singleton's constructor."""
        return "IrUtf()"


# ── the pre-tokenization contract ─────────────────────────────────────────
