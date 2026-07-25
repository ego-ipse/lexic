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

import unicodedata
from abc import abstractmethod
from collections.abc import Callable, Iterable, Mapping, Sequence
from heapq import heappop, heappush
from typing import ClassVar, Literal, Self, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import (
    IrInt,
    IrNamedTuple,
    IrNode,
    IrNone,
    IrNoneType,
    IrSelf,
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


# ── the pre-tokenization contract ─────────────────────────────────────────


class IrPretoken(IrNode):
    """Role marker for pre-token split specs — the :class:`IrAtom` pattern.

    A spec is a data record whose :meth:`split` partitions one piece of text
    into smaller pieces (their concatenation IS the input — offsets stay
    derivable). Open-set: a new family subclasses this and the pipeline
    accepts it without any dispatch-table edit.
    """

    @abstractmethod
    def split(self, text: str) -> list[str]:
        """Partition ``text`` into pre-token pieces (concatenation-preserving)."""


class IrUnknown(IrNamedTuple[str, bool]):
    """The fallback symbol for input the vocabulary does not cover.

    :ivar spelling: The vocab spelling emitted for an uncovered symbol.
        Empty ⇒ there is no fallback, and an uncovered symbol REFUSES rather
        than vanishing.
    :ivar fuse: Whether consecutive fallbacks collapse into one token.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    spelling: str = ""
    fuse: bool = False


class IrTokenPipeline(IrNamedTuple[IrTuple, IrMap, IrTuple, IrTuple, IrMap, IrUnknown]):
    """The segmentation pipeline's data — everything before/around the rewrite.

    :ivar specials: Atomic-match spellings, matched whole before anything else.
    :ivar remap: utf-8 BYTE → working char; empty ⇒ text is its own working
        alphabet. Non-empty means the vocabulary is spelled over a byte
        alphabet, so each source char is decomposed to its utf-8 bytes and
        each byte mapped through this table. The table is data, but the utf-8
        decomposition is not — a vocabulary over some other byte encoding is
        not expressible today. Named honestly rather than as the more general
        "ordinal → char" it is not.
    :ivar normalize: Ordered :class:`IrNormalizer` steps applied to each gap
        before pre-splitting.
    :ivar pretokens: Ordered :class:`IrPretoken` split specs.
    :ivar byte_fallback: Byte ordinal → the vocabulary's spelling for that
        byte. Non-empty ⇒ an uncovered symbol yields its utf-8 bytes as those
        tokens instead of no token. The SPELLING is data because it is a
        vocabulary's own convention; the spine does not know how any format
        spells a byte.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    specials: IrTuple = IrTuple()
    remap: IrMap = IrMap()
    normalize: IrTuple = IrTuple()
    pretokens: IrTuple = IrTuple()
    byte_fallback: IrMap = IrMap()
    unknown: IrUnknown = IrUnknown()


_WMeta = list[tuple[int, int, bool]]
"""Per working char: its original span ``(start, end)`` + a starts-source
flag (the first working char derived from that source instance)."""


def _identity_meta(base: int, length: int) -> _WMeta:
    """The no-pipeline meta — every char is its own aligned source."""
    return [(base + i, base + i + 1, True) for i in range(length)]


def _replace_pass(text: str, meta: _WMeta, src: str, dst: str) -> tuple[str, _WMeta]:
    """One ordered replace over ``(text, meta)`` — dst chars share src's span."""
    out: list[str] = []
    out_meta: _WMeta = []
    i = 0
    while i < len(text):
        if not src or not text.startswith(src, i):
            out.append(text[i])
            out_meta.append(meta[i])
            i += 1
            continue
        span = (meta[i][0], meta[i + len(src) - 1][1])
        for k, ch in enumerate(dst):
            out.append(ch)
            out_meta.append((span[0], span[1], k == 0))
        i += len(src)
    return "".join(out), out_meta


class IrNormalizer(IrNode):
    """Role marker for text-normalization steps — the :class:`IrAtom` pattern.

    A step rewrites the working text before pre-splitting, carrying the
    char-span metadata forward so token offsets stay derivable. Open-set: a
    new family subclasses this and the pipeline accepts it without any
    dispatch-table edit — the :class:`IrPretoken` arrangement, one stage
    earlier.
    """

    @abstractmethod
    def apply(self, text: str, meta: _WMeta) -> tuple[str, _WMeta]:
        """Rewrite ``text``, mapping each output char back to a source span."""


class IrReplace(IrNamedTuple[str, str], IrNormalizer):
    """Replace every occurrence of ``src`` with ``dst``."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    src: str
    dst: str

    def apply(self, text: str, meta: _WMeta) -> tuple[str, _WMeta]:
        """The replaced text; each ``dst`` char shares the matched span."""
        return _replace_pass(text, meta, str(self.src), str(self.dst))


UnicodeForm = Literal["NFC", "NFD", "NFKC", "NFKD"]
"""The four Unicode normalization forms — the only values that normalize."""


class IrUnicodeForm(IrNamedTuple[str], IrNormalizer):
    """A Unicode normalization form (``NFC`` / ``NFD`` / ``NFKC`` / ``NFKD``).

    Applied over the largest chunks that can be normalized independently,
    so that every output char stays attributable to one source span while
    the result equals normalizing the whole text at once.

    Chunking is the subtle part. "A starter plus its combining marks" is NOT
    the right unit: composition and canonical reordering both cross that
    boundary whenever a STARTER participates — Hangul jamo (``U+1100 U+1161``
    → ``U+AC00``), Indic two-part vowels (``U+09C7 U+09BE`` → ``U+09CB``),
    halfwidth voiced marks that decompose to a reordering mark. A chunk may
    therefore end before a char only when that char attaches to nothing
    before it AND the junction pair is already normalized — a conservative
    test, so a doubtful boundary merges rather than splits.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    form: UnicodeForm = "NFC"

    def apply(self, text: str, meta: _WMeta) -> tuple[str, _WMeta]:
        """The normalized text; a chunk's output chars share its source span."""
        out: list[str] = []
        out_meta: _WMeta = []
        i = 0
        n = len(text)
        while i < n:
            j = i + 1
            while j < n and not self._divides(text, j):
                j += 1
            span = (meta[i][0], meta[j - 1][1])
            for k, ch in enumerate(unicodedata.normalize(self.form, text[i:j])):
                out.append(ch)
                out_meta.append((span[0], span[1], k == 0))
            i = j
        return "".join(out), out_meta

    def _divides(self, text: str, i: int) -> bool:
        """Whether a chunk may end before ``text[i]`` without changing the result.

        Conservative: anything that might interact merges into one chunk.
        """
        prev, cur = text[i - 1], text[i]
        if prev < "\x80" and cur < "\x80":
            return True  # ASCII interacts with nothing — the common path
        if unicodedata.combining(cur):
            return False  # attaches to what precedes
        pair = prev + cur
        return unicodedata.normalize(self.form, pair) == pair


def _piece_slices(
    text: str, meta: _WMeta, pretokens: IrTuple
) -> list[tuple[str, _WMeta]]:
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
        split: list[tuple[str, _WMeta]] = []
        for ptext, pmeta in pieces:
            at = 0
            for part in spec.split(ptext):
                split.append((part, pmeta[at : at + len(part)]))
                at += len(part)
        pieces = split
    return pieces


def _remap_piece(text: str, meta: _WMeta, remap: IrMap) -> tuple[str, _WMeta]:
    """Convert a piece to its working alphabet — utf-8 bytes through ``remap``."""
    out: list[str] = []
    out_meta: _WMeta = []
    for ch, (start, end, first) in zip(text, meta):
        for k, byte in enumerate(ch.encode("utf-8")):
            out.append(str(remap[IrChr(byte)]))
            out_meta.append((start, end, first and k == 0))
    return "".join(out), out_meta


def _span_of(meta: _WMeta, start: int, end: int) -> tuple[int, int] | None:
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
    the :class:`~lexic.ir.nodes.IrBounds` precedent). ``ranks``/``pipeline``
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
        work, meta = gap, _identity_meta(base, len(gap))
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
