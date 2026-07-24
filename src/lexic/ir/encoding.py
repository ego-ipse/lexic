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
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import ClassVar, Self, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import (
    IrInt,
    IrNamedTuple,
    IrNode,
    IrNone,
    IrNoneType,
    IrStr,
    IrTuple,
)
from lexic.ir.mapping import IrMap
from lexic.ir.meta import IrSingleton
from lexic.ir.nodes import MAX_CODEPOINT, IrCharClass, IrChr

Vocab = Mapping[str, int] | IrMap
"""A pythonic ``spelling → id`` vocab a builder coerces to the spine."""

Merges = Sequence[tuple[str, str]] | IrTuple
"""Ordered merge dyads — position is rank; coerced to the ``ranks`` map."""

Specials = Sequence[str] | IrTuple
"""Atomic-match spellings a builder coerces to an ``IrTuple`` of ``IrStr``."""


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


def _vocab_map(vocab: Vocab) -> IrMap:
    """Coerce a pythonic ``spelling → id`` Mapping to the spine's ``IrMap``.

    Values coerce through ``IrChr(int(v))`` unconditionally, so reducer
    products (``IrInt`` / numeric ``IrStr`` ids) feed the builders directly.
    """
    return IrMap(*(IrTuple(IrStr(s), IrChr(int(i))) for s, i in vocab.items()))


def _rank_map(merges: Merges) -> IrMap:
    """Index ordered merge dyads by position into the ``dyad → IrInt`` rank map."""
    dyads = (IrTuple(IrStr(left), IrStr(right)) for left, right in merges)
    return IrMap(*(IrTuple(dyad, IrInt(i)) for i, dyad in enumerate(dyads)))


def _specials_tuple(specials: Specials) -> IrTuple:
    """Coerce atomic-match spellings to an ``IrTuple`` of ``IrStr``."""
    return IrTuple(*(IrStr(s) for s in specials))


class IrTokenizer(
    IrNamedTuple[IrStr, IrMap, IrMap, IrMap, IrTuple], IrEncoding, init=False
):
    """A token encoding — ordinals are vocab ids. The vocab is an ``IrMap``.

    ``encode`` maps each token's spelling (``IrStr``) to its id (``IrChr``);
    ``decode`` is the inverse (``IrChr`` → ``IrStr``), so :meth:`spell` is O(1)
    — the two directions are the id↔text sections of the compiled-tokenizer
    structure. ``ranks`` is the stored rewrite model: an ``IrMap`` from each
    ``IrTuple(left, right)`` spelling dyad to its ``IrInt`` merge rank — the
    exact structure the ranked-merge rewrite reads, O(1) per lookup with zero
    per-call derivation; the *ordered* dyad tuple is the derived view
    (:attr:`merges` — sort on rank), needed only at emission. ``ranks`` is
    **empty** for a vocab-only tokenizer (:meth:`from_vocab` — segmentation is
    longest-match) and non-empty for a merge-based one (:meth:`from_merges` —
    the ranked-merge rewrite). ``specials`` is the atomic-match set (HF's
    ``added_tokens``): an ``IrTuple`` of ``IrStr`` spellings matched **whole**,
    before the merge/longest rewrite, so a special like ``<think>`` is one token
    even amid BPE content. Built from a Mapping alone; *how* that Mapping was
    produced (parsed from any format via a grammar/reduction, or handed in
    pre-parsed) is the caller's concern — no file format lives here. The
    builders accept pythonic ``Mapping``/``Sequence`` forms (:data:`Vocab`,
    :data:`Merges`, :data:`Specials`) and coerce to the spine. The structural
    base leads (the ``IrLiteral(IrStr, IrAtom)`` order); :class:`IrEncoding` is
    the role marker.

    Children: none walked — every field is codec data (``_child_attrs = ()``,
    the :class:`~lexic.ir.nodes.IrBounds` precedent). ``ranks``/``specials`` carry
    empty defaults so a vocab-only tokenizer's repr elides them (repr-codegen
    stable). Construction goes through the builders (they coerce ``name`` and
    derive ``decode``); the record itself is the plain positional constructor the
    notation/repr reconstruct from.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    name: IrStr
    encode: IrMap
    decode: IrMap
    ranks: IrMap = IrMap()
    specials: IrTuple = IrTuple()

    @classmethod
    def from_vocab(
        cls, name: str, vocab: Vocab, specials: Specials = IrTuple()
    ) -> Self:
        """Build a vocab-only tokenizer from the forward ``spelling → id`` map.

        Segmentation is longest-match over the vocab (``ranks`` empty).

        :param name: The registry name.
        :param vocab: The vocab — a pythonic ``Mapping`` or a ready ``IrMap``.
        :param specials: Spellings matched atomically before the rewrite.
        :returns: The tokenizer, with the inverse ``decode`` map derived.
        """
        return cls._build(name, _vocab_map(vocab), IrMap(), _specials_tuple(specials))

    @classmethod
    def from_merges(
        cls, name: str, vocab: Vocab, merges: Merges, specials: Specials = IrTuple()
    ) -> Self:
        """Build a merge-based tokenizer from a vocab + ordered merge dyads.

        Segmentation runs the ranked-merge rewrite (the reference algorithm);
        the ordered dyads index into the stored ``ranks`` map (position = rank).

        :param name: The registry name.
        :param vocab: The vocab — a pythonic ``Mapping`` or a ready ``IrMap``.
        :param merges: Ordered ``(left, right)`` dyads; position is rank.
        :param specials: Spellings matched atomically before the rewrite.
        :returns: The tokenizer, carrying the merge model.
        """
        return cls._build(
            name, _vocab_map(vocab), _rank_map(merges), _specials_tuple(specials)
        )

    @classmethod
    def _build(cls, name: str, encode: IrMap, ranks: IrMap, specials: IrTuple) -> Self:
        """Derive ``decode``, coerce ``name``, validate specials, construct.

        :param name: The registry name (coerced to ``IrStr``).
        :param encode: The vocab (spelling → id).
        :param ranks: The merge dyad → rank map (empty for vocab-only).
        :param specials: The atomic-match spellings (each must be in ``encode``).
        :returns: The constructed tokenizer.
        :raises UnsupportedConstructError: When a special is not in the vocab.
        """
        for spelling in specials:
            if IrStr(spelling) not in encode:
                raise UnsupportedConstructError(
                    f"tokenizer: special {str(spelling)!r} is not in the vocab"
                )
        decode = IrMap(*(IrTuple(i, s) for s, i in encode.items()))
        construct = cast(Callable[..., Self], cls)
        return construct(IrStr(name), encode, decode, ranks, specials)

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

    @property
    def merges(self) -> IrTuple:
        """The ordered merge dyads, derived from :attr:`ranks` (sort on rank).

        The emission-time view; the rewrite itself reads :attr:`ranks` directly.
        Empty when :attr:`ranks` is (a vocab-only tokenizer).
        """
        by_rank = sorted(self.ranks.items(), key=lambda dyad_rank: int(dyad_rank[1]))
        return IrTuple(*(dyad for dyad, _ in by_rank))

    def ids(self) -> list[int]:
        """Every vocab id — the alphabet membership set."""
        return [int(i) for i in self.decode.keys()]

    def boundaries(self, text: str) -> list[tuple[int, int, int]]:
        """Segment ``text`` into ``(char_start, char_end, id)`` token spans.

        The *algorithm* is selected by the tokenizer's own data (the intrinsic,
        data-driven method — the :meth:`IrCharClass.complement` precedent):
        :attr:`specials` (if any) are matched atomically first (HF ``added_tokens``
        — a ``<think>`` is one token, never split by the rewrite), then each gap
        runs the vocab model — with :attr:`ranks` empty a deterministic
        longest-match, otherwise the ranked-merge rewrite (the reference BPE
        algorithm — exact, not an approximation), driven entirely by
        :attr:`ranks` and :attr:`encode`, no hard-coded tables. A position
        covered by no vocab token yields no token-match point (the
        unsegmentable / mid-multibyte case). These spans are what the engine
        scans a token terminal against at boundary columns.

        :param text: The instance text to segment.
        :returns: The token spans in order — ``(start, end, id)`` over ``text``.
        """
        if self.specials:
            return self._segment_with_specials(text)
        return self._segment_plain(text, 0)

    def _segment_plain(self, chunk: str, base: int) -> list[tuple[int, int, int]]:
        """Segment a special-free ``chunk`` via the vocab model, offset by ``base``.

        :param chunk: The gap text (already free of :attr:`specials`).
        :param base: The char offset of ``chunk`` within the whole input.
        :returns: The covering spans, offset into the whole input.
        """
        raw = self._merge_segment(chunk) if self.ranks else self._longest_match(chunk)
        return [(start + base, end + base, tid) for start, end, tid in raw]

    def _segment_with_specials(self, text: str) -> list[tuple[int, int, int]]:
        """Match :attr:`specials` atomically (longest-first), rewrite the gaps.

        :param text: The instance text to segment.
        :returns: The covering spans in order over ``text``.
        """
        specials = sorted((str(s) for s in self.specials), key=len, reverse=True)
        spans: list[tuple[int, int, int]] = []
        cursor = gap = 0
        while cursor < len(text):
            hit = next((s for s in specials if s and text.startswith(s, cursor)), None)
            if hit is None:
                cursor += 1
                continue
            if cursor > gap:
                spans.extend(self._segment_plain(text[gap:cursor], gap))
            spans.append((cursor, cursor + len(hit), int(self.encode[IrStr(hit)])))
            cursor = gap = cursor + len(hit)
        if len(text) > gap:
            spans.extend(self._segment_plain(text[gap:], gap))
        return spans

    def _longest_match(self, text: str) -> list[tuple[int, int, int]]:
        """Longest-match segmentation over the vocab (the ``ranks``-empty model).

        :param text: The instance text to segment.
        :returns: The covering token spans in order.
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

    def _merge_segment(self, text: str) -> list[tuple[int, int, int]]:
        """Ranked-merge (BPE) segmentation — the ``ranks``-present model.

        Starts from single-character symbols, then repeatedly applies the
        lowest-rank adjacent merge (leftmost occurrence) until none applies — the
        reference algorithm's fixpoint, order-independent in the final symbols. A
        final symbol carried by no vocab entry yields no span (unsegmentable),
        mirroring :meth:`_longest_match`.

        :param text: The instance text to segment.
        :returns: The covering token spans in order.
        """
        ranks = self.ranks
        symbols = [(ch, i, i + 1) for i, ch in enumerate(text)]
        while len(symbols) > 1:
            at = self._lowest_merge(symbols, ranks)
            if at < 0:
                break
            left, right = symbols[at], symbols[at + 1]
            symbols[at : at + 2] = [(left[0] + right[0], left[1], right[2])]
        return [
            (start, end, int(self.encode[IrStr(sp)]))
            for sp, start, end in symbols
            if IrStr(sp) in self.encode
        ]

    @staticmethod
    def _lowest_merge(symbols: list[tuple[str, int, int]], ranks: IrMap) -> int:
        """The index of the lowest-rank adjacent merge, or ``-1`` if none apply.

        :param symbols: The current ``(spelling, start, end)`` symbols in order.
        :param ranks: The merge dyad → rank index.
        :returns: The left index of the winning adjacent pair, or ``-1``.
        """
        best_rank, best_at = -1, -1
        for j in range(len(symbols) - 1):
            found = ranks.get(IrTuple(IrStr(symbols[j][0]), IrStr(symbols[j + 1][0])))
            if found is not None and (best_at < 0 or int(found) < best_rank):
                best_rank, best_at = int(found), j
        return best_at
