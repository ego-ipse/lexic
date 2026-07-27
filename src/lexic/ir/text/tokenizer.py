"""Tokenizer — a vocabulary, and the segmenters that apply it.

``IrTokenizer`` with ``IrSegmenter``'s two implementations: ``IrLongestMatch``
and ``IrRankedMerge``, the BPE fixpoint. This is the only part of the family
that needs a vocabulary to mean anything.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable, Mapping, Sequence
from heapq import heappop, heappush
from typing import ClassVar, Self, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action.mapping import IrMap
from lexic.ir.grammar.nodes import IrChr
from lexic.ir.spine.meta import IrSingleton
from lexic.ir.spine.spine import IrNode, IrNone, IrNoneType
from lexic.ir.spine.records import IrNamedTuple, IrTuple
from lexic.ir.spine.scalars import IrInt, IrStr
from lexic.ir.text.encodings import IrEncoding
from lexic.ir.text.pipeline import (
    IrNormalizer,
    IrPretoken,
    IrTokenPipeline,
    WMeta,
    identity_meta,
)

Vocab = Mapping[str, int] | IrMap
"""A pythonic ``spelling → id`` vocab a builder coerces to the spine."""

Merges = Sequence[tuple[str, str]] | IrTuple
"""Ordered merge dyads — position is rank; coerced to the ``ranks`` map."""


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


def _piece_slices(
    text: str, meta: WMeta, pretokens: IrTuple
) -> list[tuple[str, WMeta]]:
    """Fold the split specs over ``text``, slicing ``meta`` alongside.

    :raises UnsupportedConstructError: On a spec that is not an
        :class:`IrPretoken`.
    """
    pieces = [(text, meta)]
    for spec in pretokens:
        if not isinstance(spec, IrPretoken):
            raise UnsupportedConstructError(
                f"tokenizer: unsupported pre-token spec {type(spec).__name__!r}"
            )
        split: list[tuple[str, WMeta]] = []
        for ptext, pmeta in pieces:
            at = 0
            for part in spec.split(ptext):
                split.append((part, pmeta[at : at + len(part)]))
                at += len(part)
        pieces = split
    return pieces


def _remap_piece(text: str, meta: WMeta, remap: IrMap) -> tuple[str, WMeta]:
    """Convert a piece to its working alphabet — utf-8 bytes through ``remap``."""
    out: list[str] = []
    out_meta: WMeta = []
    for ch, (start, end, first) in zip(text, meta):
        for k, byte in enumerate(ch.encode("utf-8")):
            out.append(str(remap[IrChr(byte)]))
            out_meta.append((start, end, first and k == 0))
    return "".join(out), out_meta


def _span_of(meta: WMeta, start: int, end: int) -> tuple[int, int] | None:
    """The original span of working range ``[start, end)`` — ``None`` when a
    boundary falls inside a source char (the documented byte-level caveat)."""
    if not meta[start][2]:
        return None
    if end < len(meta) and not meta[end][2]:
        return None
    return (meta[start][0], meta[end - 1][1])


def _merge_rank(tok: IrTokenizer, left: str, right: str) -> int | None:
    """The merge rank of the dyad, or ``None`` when it is not a merge."""
    found = tok.ranks.get(IrTuple(IrStr(left), IrStr(right)))
    return None if found is None else int(found)


def _file_pair(
    tok: IrTokenizer,
    agenda: list[tuple[int, int]],
    spell: list[str],
    left: int,
    right: int,
) -> None:
    """Queue slots ``(left, right)``'s dyad on the agenda if it merges."""
    rank = _merge_rank(tok, spell[left], spell[right])
    if rank is not None:
        heappush(agenda, (rank, left))


class IrSegmenter(IrNode):
    """Role marker for segmentation models — the :class:`IrAtom` pattern.

    A model turns one working-alphabet piece into the vocabulary symbols that
    cover it. Which model applies was a two-way branch on ``ranks`` being
    non-empty, inside the spine — a closed dispatch where the project's rule
    is an open one, and the reason Unigram (Viterbi over scores) and
    WordPiece (a continuation prefix) could not be expressed at all.

    Open-set: a new model subclasses this and a tokenizer carries it. The
    builders already know which one applies — ``from_vocab`` means longest
    match, ``from_merges`` means ranked merge — so the choice is made where
    it was always known instead of re-derived per gap.
    """

    @abstractmethod
    def symbols(self, tok: IrTokenizer, text: str) -> list[tuple[str, int, int]]:
        """The ``(spelling, start, end)`` symbols covering ``text``, in order.

        :param tok: The tokenizer whose vocabulary and data to segment with.
        :param text: One working-alphabet piece.
        """


class IrLongestMatch(IrSegmenter, metaclass=IrSingleton):
    """Longest vocabulary match at each position — the merge-free model.

    A singleton, like the stateless encodings: the model carries no data, so
    every instance IS the same one. An empty record would instead compare
    EQUAL to any other empty record, which would make a longest-match
    tokenizer indistinguishable from a ranked-merge one.
    """

    def __new__(cls) -> Self:
        """Return the singleton instance."""
        return super().__new__(cls)

    def __repr__(self) -> str:
        """Codegen repr — the singleton's constructor."""
        return "IrLongestMatch()"

    def symbols(self, tok: IrTokenizer, text: str) -> list[tuple[str, int, int]]:
        """Longest-match symbols over the vocab."""
        keys = sorted(tok.encode.keys(), key=len, reverse=True)
        symbols: list[tuple[str, int, int]] = []
        cursor = 0
        while cursor < len(text):
            match = next((k for k in keys if k and text.startswith(k, cursor)), None)
            if match is None:
                # Emit it when anything can carry it; skipping unconditionally
                # discarded the char before a fallback could apply.
                if tok.carries(text[cursor]):
                    symbols.append((text[cursor], cursor, cursor + 1))
                cursor += 1
                continue
            symbols.append((str(match), cursor, cursor + len(match)))
            cursor += len(match)
        return symbols


class IrRankedMerge(IrSegmenter, metaclass=IrSingleton):
    """The ranked-merge (BPE) rewrite — the reference fixpoint.

    Starts from single-character symbols, then repeatedly applies the
    lowest-rank adjacent merge (leftmost occurrence) until none applies,
    driven by a heap agenda over the live pairs: symbols form a doubly linked
    list of slots (a merge keeps the LEFT slot, so slot order is text order
    and the heap's ``(rank, slot)`` key reproduces leftmost-lowest exactly).
    Ranks are unique per dyad, so a popped entry is current iff the slot's
    live pair still carries the popped rank — the staleness test needs no
    versioning.

    A singleton for the same reason as :class:`IrLongestMatch`.
    """

    def __new__(cls) -> Self:
        """Return the singleton instance."""
        return super().__new__(cls)

    def __repr__(self) -> str:
        """Codegen repr — the singleton's constructor."""
        return "IrRankedMerge()"

    def symbols(self, tok: IrTokenizer, text: str) -> list[tuple[str, int, int]]:
        """The final symbols after the merge fixpoint."""
        kept = [i for i, ch in enumerate(text) if tok.carries(ch)]
        if not kept:
            return []
        spell = [text[i] for i in kept]
        ends = [i + 1 for i in kept]
        nxt = self._merge(tok, spell, ends)
        out: list[tuple[str, int, int]] = []
        slot = 0  # a merge keeps the left slot, so slot 0 is always the head
        while slot >= 0:
            out.append((spell[slot], kept[slot], ends[slot]))
            slot = nxt[slot]
        return out

    def _merge(self, tok: IrTokenizer, spell: list[str], ends: list[int]) -> list[int]:
        """Apply ranked merges until none applies, rewriting ``spell``/``ends``.

        :returns: The live-successor list — walk it from slot 0.
        """
        count = len(spell)
        nxt = list(range(1, count)) + [-1]
        prv = [-1] + list(range(count - 1))
        alive = [True] * count
        agenda: list[tuple[int, int]] = []
        for i in range(count - 1):
            _file_pair(tok, agenda, spell, i, i + 1)
        while agenda:
            rank, i = heappop(agenda)
            j = nxt[i]
            if not alive[i] or j < 0 or _merge_rank(tok, spell[i], spell[j]) != rank:
                continue  # stale — a neighbor merged since this entry filed
            spell[i] += spell[j]
            ends[i] = ends[j]
            alive[j] = False
            nxt[i] = nxt[j]
            if nxt[i] >= 0:
                prv[nxt[i]] = i
            for left in (prv[i], i):
                if left >= 0 and nxt[left] >= 0:
                    _file_pair(tok, agenda, spell, left, nxt[left])
        return nxt


class IrTokenizer(
    IrNamedTuple[IrStr, IrMap, IrMap, IrMap, IrTokenPipeline], IrEncoding, init=False
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
    the ranked-merge rewrite). ``specials`` is the atomic-match set: an
    ``IrTuple`` of ``IrStr`` spellings matched **whole**,
    before the merge/longest rewrite, so a special like ``<think>`` is one token
    even amid BPE content. Built from a Mapping alone; *how* that Mapping was
    produced (parsed from any format via a grammar/reduction, or handed in
    pre-parsed) is the caller's concern — no file format lives here. The
    builders accept pythonic ``Mapping``/``Sequence`` forms (:data:`Vocab`,
    :data:`Merges`) and coerce to the spine. Specials ride the pipeline as
    IR (``IrTuple`` of ``IrStr``). The structural
    base leads (the ``IrLiteral(IrStr, IrAtom)`` order); :class:`IrEncoding` is
    the role marker.

    The segmentation pipeline beyond the rewrite — specials, the byte-level
    ``remap``, ``Replace`` normalizers, pre-token split specs, byte fallback —
    is one :class:`IrTokenPipeline` record on the ``pipeline`` field (empty
    default: plain text in, ranked merge / longest match out).

    Children: none walked — every field is codec data (``_child_attrs = ()``,
    the :class:`~lexic.ir.grammar.nodes.IrBounds` precedent). ``ranks``/``pipeline``
    carry empty defaults so a plain tokenizer's repr elides them (repr-codegen
    stable). Construction goes through the builders (they coerce ``name`` and
    derive ``decode``); the record itself is the plain positional constructor the
    notation/repr reconstruct from.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    name: IrStr
    encode: IrMap
    decode: IrMap
    ranks: IrMap = IrMap()
    pipeline: IrTokenPipeline = IrTokenPipeline()
    segmenter: IrSegmenter = IrLongestMatch()

    @property
    def specials(self) -> IrTuple:
        """The atomic-match spellings — the pipeline's first stage."""
        return self.pipeline.specials

    @classmethod
    def from_vocab(
        cls,
        name: str,
        vocab: Vocab,
        pipeline: IrTokenPipeline = IrTokenPipeline(),
    ) -> Self:
        """Build a vocab-only tokenizer from the forward ``spelling → id`` map.

        Segmentation is longest-match over the vocab (``ranks`` empty).
        Specials ride ``pipeline`` — they are pipeline data (matched before
        remap / normalize / pre-split), so that is their one home.

        :param name: The registry name.
        :param vocab: The vocab — a pythonic ``Mapping`` or a ready ``IrMap``.
        :param pipeline: The segmentation pipeline data.
        :returns: The tokenizer, with the inverse ``decode`` map derived.
        """
        return cls._build(
            name, _vocab_map(vocab), (IrMap(), IrLongestMatch()), pipeline
        )

    @classmethod
    def from_merges(
        cls,
        name: str,
        vocab: Vocab,
        merges: Merges,
        pipeline: IrTokenPipeline = IrTokenPipeline(),
    ) -> Self:
        """Build a merge-based tokenizer from a vocab + ordered merge dyads.

        Segmentation runs the ranked-merge rewrite (the reference algorithm);
        the ordered dyads index into the stored ``ranks`` map (position = rank).
        Specials ride ``pipeline``.

        :param name: The registry name.
        :param vocab: The vocab — a pythonic ``Mapping`` or a ready ``IrMap``.
        :param merges: Ordered ``(left, right)`` dyads; position is rank.
        :param pipeline: The segmentation pipeline data.
        :returns: The tokenizer, carrying the merge model.
        """
        return cls._build(
            name, _vocab_map(vocab), (_rank_map(merges), IrRankedMerge()), pipeline
        )

    @classmethod
    def _build(
        cls,
        name: str,
        encode: IrMap,
        model: tuple[IrMap, IrSegmenter],
        pipeline: IrTokenPipeline,
    ) -> Self:
        """Derive ``decode``, coerce ``name``, validate specials, construct.

        :param name: The registry name (coerced to ``IrStr``).
        :param encode: The vocab (spelling → id).
        :param model: How symbols are formed — the merge dyad → rank map
            (empty for vocab-only) and the segmentation model that reads it.
            One parameter because the two are chosen together: a builder that
            supplies ranks means the ranked merge, and one that does not means
            longest match.
        :param pipeline: The segmentation pipeline (its specials must be in
            ``encode``).
        :returns: The constructed tokenizer.
        :raises UnsupportedConstructError: When a special is not in the vocab.
        """
        for spelling in pipeline.specials:
            if IrStr(spelling) not in encode:
                raise UnsupportedConstructError(
                    f"tokenizer: special {str(spelling)!r} is not in the vocab"
                )
        decode = IrMap(*(IrTuple(i, s) for s, i in encode.items()))
        construct = cast(Callable[..., Self], cls)
        ranks, segmenter = model
        return construct(IrStr(name), encode, decode, ranks, pipeline, segmenter)

    @property
    def universe(self) -> int:
        """The highest id — inclusive, like every other encoding.

        Derived, not stored. ``-1`` for an empty vocabulary, which makes the
        complement of anything empty rather than a single phantom ordinal.
        """
        return max((int(i) for i in self.decode.keys()), default=-1)

    def resolve(self, spelling: str) -> IrChr | IrNoneType:
        """A token's text → its id, or :data:`IrNone` when not one vocab token."""
        found = self.encode.get(IrStr(spelling))
        return found if found is not None else IrNone

    def spell(self, ordinal: int) -> IrStr:
        """The token id → its text (``[id]`` fallback for an unmapped id)."""
        found = self.decode.get(IrChr(ordinal))
        return found if found is not None else IrStr(f"[{ordinal}]")

    def with_segmenter(self, segmenter: IrSegmenter) -> Self:
        """This tokenizer under a different segmentation model.

        The attach point for the open seam: the builders name the two shipped
        models, and a model declared elsewhere — Unigram, WordPiece — reaches
        a tokenizer through here. Returns a new tokenizer; the record is
        immutable.

        :param segmenter: The model to segment with.
        :returns: A copy carrying ``segmenter``.
        """
        construct = cast(Callable[..., Self], type(self))
        return construct(
            self.name, self.encode, self.decode, self.ranks, self.pipeline, segmenter
        )

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

        The *algorithm* is the tokenizer's own data (the intrinsic,
        data-driven method — the :meth:`IrCharClass.complement` precedent):
        the pipeline's specials match atomically first, each gap normalizes,
        pre-splits and remaps per :attr:`pipeline`, then every piece runs the
        vocab model — with :attr:`ranks` empty a deterministic longest-match,
        otherwise the ranked-merge rewrite (the reference BPE algorithm —
        exact), driven entirely by :attr:`ranks` and :attr:`encode`. A token
        whose working-alphabet boundary falls inside a source char (the
        byte-level mid-char case) yields no span here — :meth:`tokenize`
        still carries its id. These spans are what the engine scans a token
        terminal against at boundary columns.

        :param text: The instance text to segment.
        :returns: The char-aligned token spans — ``(start, end, id)``.
        """
        out: list[tuple[int, int, int]] = []
        for tid, span in self._segments(text):
            if span is not None:
                out.append((span[0], span[1], tid))
        return out

    def tokenize(self, text: str) -> list[int]:
        """The COMPLETE id sequence of ``text`` — every pipeline token.

        Overrides the ABC's boundaries-derived default: under a byte-level
        pipeline a token may end mid-source-char and so carry no char-aligned
        span, but its id is still part of the segmentation.

        :param text: The instance text to segment.
        :returns: The ids of every token, in order.
        """
        return [tid for tid, _ in self._segments(text)]

    def _segments(self, text: str) -> list[tuple[int, tuple[int, int] | None]]:
        """Every token of ``text`` as ``(id, char_span_or_None)``, in order."""
        specials = sorted((str(s) for s in self.specials), key=len, reverse=True)
        if not specials:
            return self._gap_tokens(text, 0)
        out: list[tuple[int, tuple[int, int] | None]] = []
        cursor = gap = 0
        while cursor < len(text):
            hit = next((s for s in specials if text.startswith(s, cursor)), None)
            if hit is None:
                cursor += 1
                continue
            if cursor > gap:
                out.extend(self._gap_tokens(text[gap:cursor], gap))
            tid = int(self.encode[IrStr(hit)])
            out.append((tid, (cursor, cursor + len(hit))))
            cursor = gap = cursor + len(hit)
        if len(text) > gap:
            out.extend(self._gap_tokens(text[gap:], gap))
        return out

    def _gap_tokens(
        self, gap: str, base: int
    ) -> list[tuple[int, tuple[int, int] | None]]:
        """One special-free gap through the pipeline — normalize, split, remap,
        rewrite.

        **That order is the contract, not an accident.** `IrPretoken`,
        `IrNormalizer` and `IrSegmenter` are open in MEMBERSHIP — a new family
        is accepted without a dispatch-table edit — but not in PLACEMENT: a
        family joins its stage, it does not choose a new position. No known
        pipeline wants a different order, and building order-as-data with no
        consumer would be speculative. A model that genuinely needs a
        different arrangement is more plausibly a different
        :class:`IrSegmenter` than a reordered pipeline.
        """
        line = self.pipeline
        work, meta = gap, identity_meta(base, len(gap))
        for step in line.normalize:
            work, meta = IrNormalizer.ensure(step, "a normalize step").apply(work, meta)
        out: list[tuple[int, tuple[int, int] | None]] = []
        for ptext, pmeta in _piece_slices(work, meta, line.pretokens):
            if line.remap:
                ptext, pmeta = _remap_piece(ptext, pmeta, line.remap)
            symbols = self.segmenter.symbols(self, ptext)
            for spelling, start, end in symbols:
                out.extend(self._symbol_tokens(spelling, _span_of(pmeta, start, end)))
        return self._fuse_unknown(out)

    def _fuse_unknown(
        self, tokens: list[tuple[int, tuple[int, int] | None]]
    ) -> list[tuple[int, tuple[int, int] | None]]:
        """Collapse runs of the unknown token into one, when asked."""
        unknown = self.encode.get(IrStr(str(self.pipeline.unknown.spelling)))
        if unknown is None or not self.pipeline.unknown.fuse:
            return tokens
        fused: list[tuple[int, tuple[int, int] | None]] = []
        for tid, span in tokens:
            if tid == int(unknown) and fused and fused[-1][0] == int(unknown):
                continue
            fused.append((tid, span))
        return fused

    def _symbol_tokens(
        self, spelling: str, span: tuple[int, int] | None
    ) -> list[tuple[int, tuple[int, int] | None]]:
        """A final symbol's tokens — its vocab id, byte fallback, or unknown.

        :raises UnsupportedConstructError: When nothing covers the symbol.
            Returning no tokens instead would drop the input silently, which
            is a wrong answer dressed as a shorter one.
        """
        found = self.encode.get(IrStr(spelling))
        if found is not None:
            return [(int(found), span)]
        bytes_out = self._byte_tokens(spelling, span)
        if bytes_out is not None:
            return bytes_out
        unknown = self.encode.get(IrStr(str(self.pipeline.unknown.spelling)))
        if unknown is not None:
            return [(int(unknown), span)]
        raise UnsupportedConstructError(
            f"encoding: {spelling!r} is not in the vocabulary, and neither "
            "byte fallback nor an unknown symbol covers it"
        )

    def carries(self, spelling: str) -> bool:
        """Whether anything in this vocabulary can carry ``spelling``.

        The seeding filter for both models. A vocabulary need not cover every
        input — a byte-level vocabulary may simply have no entry for some of
        the 256 byte characters — and what it cannot carry is skipped HERE,
        which lets the NEIGHBOURS become adjacent and merge across the gap.
        Dropping the symbol later instead leaves those neighbours unmerged,
        a different token stream; refusing outright rejects input that
        tokenizes fine. Which bytes are uncovered is a property of the
        vocabulary, knowable when it is built rather than per input.
        """
        if self.encode.get(IrStr(spelling)) is not None:
            return True
        if self._byte_tokens(spelling, None) is not None:
            return True
        return self.encode.get(IrStr(str(self.pipeline.unknown.spelling))) is not None

    def _byte_tokens(
        self, spelling: str, span: tuple[int, int] | None
    ) -> list[tuple[int, tuple[int, int] | None]] | None:
        """``spelling`` as byte-fallback tokens, or ``None`` when uncovered."""
        table = self.pipeline.byte_fallback
        if not table:
            return None
        data = spelling.encode("utf-8")
        out: list[tuple[int, tuple[int, int] | None]] = []
        for byte in data:
            spelt = table.get(IrChr(byte))
            tid = None if spelt is None else self.encode.get(spelt)
            if tid is None:
                return None
            out.append((int(tid), span if len(data) == 1 else None))
        return out
