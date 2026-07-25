"""The ``tokenizer.json`` pre-token split specs — this format's vocabulary.

These are Hugging Face's pipeline stages, so they live with the format that
names them, NOT in ``lexic.ir``: the spine models what a pre-token split IS
(:class:`~lexic.ir.encoding.IrPretoken` — a spec whose ``split`` partitions
text) and stays neutral about whose pipeline it is. ``IrPretoken`` is
open-set precisely so a vendor's families can be declared out here without
touching a dispatch table in the engine.

The GPT-2 pre-token pattern and its byte table are likewise a *specific
vocabulary's* data, not IR: the pattern is hand-implemented rather than
compiled from a regex, since its ``\\p{L}`` / ``\\p{N}`` classes have no
stdlib ``re`` spelling.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from typing import ClassVar

from lexic.ir.base import IrNamedTuple, IrStr, IrTuple
from lexic.ir.encoding import IrPretoken
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import IrChr

__all__ = [
    "BYTE_LEVEL_REMAP",
    "CL100K_PATTERN",
    "IrByteLevel",
    "IrCl100k",
    "IrDigits",
    "IrSplitMerged",
]


_CONTRACTIONS = ("'s", "'t", "'re", "'ve", "'m", "'ll", "'d")
"""The GPT-2 pattern's literal contraction alternatives, in pattern order."""


def _is_letter(ch: str) -> bool:
    """Unicode ``\\p{L}`` membership."""
    return unicodedata.category(ch).startswith("L")


def _is_number(ch: str) -> bool:
    """Unicode ``\\p{N}`` membership."""
    return unicodedata.category(ch).startswith("N")


def _is_other(ch: str) -> bool:
    """The GPT-2 pattern's ``[^\\s\\p{L}\\p{N}]`` class."""
    return not ch.isspace() and not _is_letter(ch) and not _is_number(ch)


def _run_end(text: str, i: int, pred: Callable[[str], bool]) -> int:
    """The end of the ``pred``-satisfying run starting at ``i``."""
    n = len(text)
    while i < n and pred(text[i]):
        i += 1
    return i


def _gpt2_piece(text: str, i: int) -> str:
    """One GPT-2 pre-token at ``i`` — the pattern's first-match alternative.

    The alternatives in order: a literal contraction; an optional single
    space then a letter / number / other run; a whitespace run not followed
    by non-space (backtracking one char when it is — the last whitespace char
    is left to prefix the next piece); a whitespace run.
    """
    n = len(text)
    for word in _CONTRACTIONS:
        if text.startswith(word, i):
            return word
    j = i + 1 if text[i] == " " and i + 1 < n else i
    head = text[j] if j < n else ""
    if head and _is_letter(head):
        return text[i : _run_end(text, j, _is_letter)]
    if head and _is_number(head):
        return text[i : _run_end(text, j, _is_number)]
    if head and _is_other(head):
        return text[i : _run_end(text, j, _is_other)]
    k = _run_end(text, i, str.isspace)
    if k < n and k - i >= 2:
        return text[i : k - 1]
    return text[i:k]


def _gpt2_split(text: str) -> list[str]:
    """Split ``text`` into GPT-2 pre-tokens (the fixed byte-level pattern)."""
    pieces: list[str] = []
    i = 0
    while i < len(text):
        piece = _gpt2_piece(text, i)
        pieces.append(piece)
        i += len(piece)
    return pieces


CL100K_PATTERN = (
    "(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\\r\\n\\p{L}\\p{N}]?\\p{L}+|\\p{N}| "
    "?[^\\s\\p{L}\\p{N}]+[\\r\\n]*|\\s*[\\r\\n]+|\\s+(?!\\S)|\\s+"
)
"""The cl100k / GPT-4 pre-token pattern, verbatim as documents spell it.

Matched as a LITERAL, never compiled: it is the discriminator that says
"this document wants :class:`IrCl100k`". A document carrying any other regex
is refused rather than approximated.
"""


def _cl100k_piece(text: str, i: int) -> str:
    """One cl100k pre-token at ``i`` — the pattern's first-match alternative.

    In order: a case-insensitive contraction; an optional single non-newline
    non-alphanumeric prefix then a letter run; ONE number char (this pattern
    does not run them together); an optional space then a symbol run then any
    trailing newlines; a whitespace run ending in newlines; a whitespace run
    not followed by non-space (backtracking one char when it is); whitespace.
    """
    n = len(text)
    low = text[i : i + 3].lower()
    for word in _CONTRACTIONS:
        if low.startswith(word):
            return text[i : i + len(word)]
    head = text[i]
    if _is_letter(head):
        return text[i : _run_end(text, i, _is_letter)]
    # an optional single prefix char that is neither newline nor alphanumeric
    if head not in "\r\n" and not _is_number(head) and i + 1 < n:
        if _is_letter(text[i + 1]):
            return text[i : _run_end(text, i + 1, _is_letter)]
    if _is_number(head):
        return head
    j = i + 1 if head == " " and i + 1 < n else i
    if j < n and _is_other(text[j]):
        end = _run_end(text, j, _is_other)
        return text[i : _run_end(text, end, lambda c: c in "\r\n")]
    return _cl100k_space(text, i)


def _cl100k_space(text: str, i: int) -> str:
    """The pattern's three whitespace alternatives, in order.

    ``\\s*[\\r\\n]+`` (through the final newline run), then
    ``\\s+(?!\\S)`` (leaving one space to prefix the next piece), then a
    plain ``\\s+``.
    """
    k = _run_end(text, i, str.isspace)
    nl = _last_newline_run(text, i, k)
    if nl > i:
        return text[i:nl]
    if k < len(text) and k - i >= 2:
        return text[i : k - 1]
    return text[i:k]


def _last_newline_run(text: str, start: int, end: int) -> int:
    """End of the trailing newline run inside ``text[start:end]``, else ``start``."""
    last = start
    i = start
    while i < end:
        if text[i] in "\r\n":
            i = _run_end(text, i, lambda c: c in "\r\n")
            last = i
            continue
        i += 1
    return last


def _cl100k_split(text: str) -> list[str]:
    """Split ``text`` into cl100k pre-tokens."""
    pieces: list[str] = []
    i = 0
    while i < len(text):
        piece = _cl100k_piece(text, i)
        pieces.append(piece)
        i += len(piece)
    return pieces


def _byte_unicode() -> dict[int, str]:
    """The GPT-2 byte → printable-char table (the byte-level remap)."""
    keep = [*range(0x21, 0x7F), *range(0xA1, 0xAD), *range(0xAE, 0x100)]
    table = {b: chr(b) for b in keep}
    fill = 0
    for b in range(256):
        if b not in table:
            table[b] = chr(0x100 + fill)
            fill += 1
    return table


BYTE_LEVEL_REMAP: IrMap = IrMap(
    *(IrTuple(IrChr(b), IrStr(ch)) for b, ch in sorted(_byte_unicode().items()))
)
"""The standard byte-level working alphabet — byte ordinal → working char
(space → ``Ġ``, newline → ``Ċ``, …); the ``remap`` a ByteLevel tokenizer
carries."""


class IrDigits(IrNamedTuple[bool], IrPretoken):
    """HF ``Digits`` — separate number chars from everything else.

    ``individual`` splits every number char into its own piece; otherwise
    number runs stay whole.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    individual: bool = True

    def split(self, text: str) -> list[str]:
        """Pieces alternating number / non-number content."""
        pieces: list[str] = []
        start = 0
        i = 0
        while i < len(text):
            if not _is_number(text[i]):
                i += 1
                continue
            if start < i:
                pieces.append(text[start:i])
            end = i + 1 if self.individual else _run_end(text, i, _is_number)
            pieces.append(text[i:end])
            start = i = end
        if start < len(text):
            pieces.append(text[start:])
        return pieces


class IrByteLevel(IrNamedTuple, IrPretoken):
    """HF ``ByteLevel(use_regex=True)`` — the fixed GPT-2 pre-token pattern.

    The regex split only; the byte → working-char conversion is the
    tokenizer's ``remap`` data (:data:`BYTE_LEVEL_REMAP`), applied after
    splitting.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()

    def split(self, text: str) -> list[str]:
        """The GPT-2 pattern's pieces."""
        return _gpt2_split(text)


class IrSplitMerged(IrNamedTuple[str], IrPretoken):
    """HF ``Split(pattern, MergedWithPrevious)`` — separator sticks backward."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    text: str

    def split(self, text: str) -> list[str]:
        """Pieces ending at (and including) each separator occurrence."""
        sep = str(self.text)
        if not sep:
            return [text] if text else []
        pieces: list[str] = []
        start = i = 0
        while i < len(text):
            if not text.startswith(sep, i):
                i += 1
                continue
            pieces.append(text[start : i + len(sep)])
            i += len(sep)
            start = i
        if start < len(text):
            pieces.append(text[start:])
        return pieces


class IrCl100k(IrNamedTuple, IrPretoken):
    """The cl100k / GPT-4 pre-token pattern — a fixed pattern, like ByteLevel.

    Documents spell it as a ``Split`` step carrying :data:`CL100K_PATTERN`
    with ``Isolated`` behaviour. Hand-implemented rather than compiled,
    because its ``\\p{L}`` / ``\\p{N}`` classes have no stdlib ``re``
    spelling — the same reason :class:`IrByteLevel` is.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()

    def split(self, text: str) -> list[str]:
        """The cl100k pattern's pieces."""
        return _cl100k_split(text)
