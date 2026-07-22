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

from lexic.exceptions import UnsupportedConstructError
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


class IrTokenizer(
    IrNamedTuple[IrStr, IrMap, IrMap, IrTuple, IrTuple], IrEncoding, init=False
):
    """A token encoding — ordinals are vocab ids. The vocab is an ``IrMap``.

    ``encode`` maps each token's spelling (``IrStr``) to its id (``IrChr``);
    ``decode`` is the inverse (``IrChr`` → ``IrStr``), so :meth:`spell` is O(1)
    — the two directions are the id↔text sections of the compiled-tokenizer
    structure. ``merges`` is the ordered rewrite model: an ``IrTuple`` of
    ``IrTuple(left, right)`` spelling dyads whose *position* is the merge rank
    (an ``IrMap`` would reorder by repr and lose the rank). It is **empty** for a
    vocab-only tokenizer (:meth:`from_vocab` — segmentation is longest-match) and
    non-empty for a merge-based one (:meth:`from_merges` — the ranked-merge
    rewrite). ``specials`` is the atomic-match set (HF's ``added_tokens``): an
    ``IrTuple`` of ``IrStr`` spellings matched **whole**, before the merge/longest
    rewrite, so a special like ``<think>`` is one token even amid BPE content.
    Built from a Mapping alone; *how* that Mapping was produced (parsed from any
    format via a grammar/reduction, or handed in pre-parsed) is the caller's
    concern — no file format lives here. The structural base leads (the
    ``IrLiteral(IrStr, IrAtom)`` order); :class:`IrEncoding` is the role marker.

    Children: none walked — every field is codec data (``_child_attrs = ()``,
    the :class:`~lexic.ir.nodes.IrBounds` precedent). ``merges``/``specials`` carry
    empty defaults so a vocab-only tokenizer's repr elides them (repr-codegen
    stable). Construction goes through the builders (they coerce ``name`` and
    derive ``decode``); the record itself is the plain positional constructor the
    notation/repr reconstruct from.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    name: IrStr
    encode: IrMap
    decode: IrMap
    merges: IrTuple = IrTuple()
    specials: IrTuple = IrTuple()

    @classmethod
    def from_vocab(
        cls, name: str, encode: IrMap, specials: IrTuple = IrTuple()
    ) -> Self:
        """Build a vocab-only tokenizer from the forward ``spelling → id`` map.

        Segmentation is longest-match over the vocab (``merges`` empty).

        :param name: The registry name.
        :param encode: The vocab (``IrStr`` spelling → ``IrChr`` id).
        :param specials: Spellings matched atomically before the rewrite.
        :returns: The tokenizer, with the inverse ``decode`` map derived.
        """
        return cls._build(name, encode, IrTuple(), specials)

    @classmethod
    def from_merges(
        cls, name: str, encode: IrMap, merges: IrTuple, specials: IrTuple = IrTuple()
    ) -> Self:
        """Build a merge-based tokenizer from a vocab + ordered merge dyads.

        Segmentation runs the ranked-merge rewrite (the reference algorithm)
        over ``merges``; ``decode`` is derived from ``encode`` as in
        :meth:`from_vocab`.

        :param name: The registry name.
        :param encode: The vocab (``IrStr`` spelling → ``IrChr`` id).
        :param merges: Ordered ``IrTuple(left, right)`` dyads; position is rank.
        :param specials: Spellings matched atomically before the rewrite.
        :returns: The tokenizer, carrying the merge model.
        """
        return cls._build(name, encode, merges, specials)

    @classmethod
    def _build(
        cls, name: str, encode: IrMap, merges: IrTuple, specials: IrTuple
    ) -> Self:
        """Derive ``decode``, coerce ``name``, validate specials, construct.

        :param name: The registry name (coerced to ``IrStr``).
        :param encode: The vocab (spelling → id).
        :param merges: The ordered merge dyads (empty for vocab-only).
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
        return construct(IrStr(name), encode, decode, merges, specials)

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
    def ranks(self) -> IrMap:
        """The merge dyad → rank index derived from :attr:`merges` (position=rank).

        An ``IrMap`` keyed by each ``IrTuple(left, right)`` dyad to its
        :class:`~lexic.ir.nodes.IrChr` rank — the rewrite lookup the ranked-merge
        segmentation reads. Empty when :attr:`merges` is (a vocab-only tokenizer).
        """
        return IrMap(*(IrTuple(pair, IrChr(i)) for i, pair in enumerate(self.merges)))

    def boundaries(self, text: str) -> list[tuple[int, int, int]]:
        """Segment ``text`` into ``(char_start, char_end, id)`` token spans.

        The *algorithm* is selected by the tokenizer's own data (the intrinsic,
        data-driven method — the :meth:`IrCharClass.complement` precedent):
        :attr:`specials` (if any) are matched atomically first (HF ``added_tokens``
        — a ``<think>`` is one token, never split by the rewrite), then each gap
        runs the vocab model — with no :attr:`merges` a deterministic longest-match,
        with merges the ranked-merge rewrite (the reference BPE algorithm — exact,
        not an approximation), driven entirely by :attr:`ranks` and :attr:`encode`,
        no hard-coded tables. A position covered by no vocab token yields no
        token-match point (the unsegmentable / mid-multibyte case). These spans are
        what the engine scans a token terminal against at boundary columns.

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
        raw = self._merge_segment(chunk) if self.merges else self._longest_match(chunk)
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
        """Longest-match segmentation over the vocab (the ``merges``-empty model).

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
        """Ranked-merge (BPE) segmentation — the ``merges``-present model.

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

    def tokenize(self, text: str) -> list[int]:
        """The token ids of ``text`` under :meth:`boundaries`.

        :param text: The instance text to segment.
        :returns: The ids of the covering token spans, in order.
        """
        return [tid for _, _, tid in self.boundaries(text)]
