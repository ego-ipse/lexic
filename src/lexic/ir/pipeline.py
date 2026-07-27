"""Token pipeline — normalizers, pretokens, and the order they run in.

What happens to text BEFORE a segmenter sees it: ``IrNormalizer`` and its
family, ``IrPretoken`` as an open role, and ``IrTokenPipeline`` holding the
sequence. None of it knows what a vocabulary is.
"""

from __future__ import annotations

import unicodedata
from abc import abstractmethod
from collections.abc import Mapping, Sequence
from typing import ClassVar, Literal

from lexic.ir.mapping import IrMap
from lexic.ir.records import IrNamedTuple, IrTuple
from lexic.ir.spine import IrNode

Vocab = Mapping[str, int] | IrMap
"""A pythonic ``spelling → id`` vocab a builder coerces to the spine."""

Merges = Sequence[tuple[str, str]] | IrTuple
"""Ordered merge dyads — position is rank; coerced to the ``ranks`` map."""


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


WMeta = list[tuple[int, int, bool]]
"""Per working char: its original span ``(start, end)`` + a starts-source
flag (the first working char derived from that source instance).

Public because it is the second argument of :meth:`IrNormalizer.apply`: a caller
writing a normalizer has to name it, and the tokenizer threads it too."""


def identity_meta(base: int, length: int) -> WMeta:
    """The no-pipeline meta — every char is its own aligned source."""
    return [(base + i, base + i + 1, True) for i in range(length)]


def _replace_pass(text: str, meta: WMeta, src: str, dst: str) -> tuple[str, WMeta]:
    """One ordered replace over ``(text, meta)`` — dst chars share src's span."""
    out: list[str] = []
    out_meta: WMeta = []
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
    def apply(self, text: str, meta: WMeta) -> tuple[str, WMeta]:
        """Rewrite ``text``, mapping each output char back to a source span."""


class IrReplace(IrNamedTuple[str, str], IrNormalizer):
    """Replace every occurrence of ``src`` with ``dst``."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    src: str
    dst: str

    def apply(self, text: str, meta: WMeta) -> tuple[str, WMeta]:
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

    def apply(self, text: str, meta: WMeta) -> tuple[str, WMeta]:
        """The normalized text; a chunk's output chars share its source span."""
        out: list[str] = []
        out_meta: WMeta = []
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
