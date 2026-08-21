"""Atoms and packing — the primitives the tables are built out of.

How an item is packed into an int, how a chart link is walked back, and what
a single atom accepts. Nothing here knows what a table is.
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlphabet,
    IrAtom,
    IrCharClass,
    IrLeaf,
    IrLiteral,
    IrNot,
    IrRange,
    IrSelf,
)
from lexic.parsing.earley.kernel.forest.forest import PayloadLeaf
from lexic.parsing.earley.kernel.tables.splits import ChainSpec, leftmost_chain

_MAX_CHARSET = 4096
"""Expansion cap for a char-class range — beyond it the set poisons."""
TIERS = (28, 40)
"""The packing tiers parse entries choose from, smallest first."""
Charset = frozenset[str] | None
"""An exact character set, or ``None`` — poisoned (unknown / too large)."""
KLink = tuple[int, int, int | str | PayloadLeaf]
"""One packed SPPF family: ``(predecessor_item, predecessor_end, child)`` —
``child`` is a packed handle (completed sub-derivation), the scanned char, or a
delegated :class:`~lexic.parsing.earley.kernel.forest.forest.PayloadLeaf` (island-interior
delegation — a pre-folded child spliced onto the waiter it advances)."""


def tier_for(length: int) -> int:
    """The smallest packing tier whose capacity covers ``length``.

    :param length: The input length in characters.
    :returns: The first tier of :data:`TIERS` with ``length < 2**bits`` — the
        last tier when none covers it (the kernel capacity raise stays the
        backstop).
    """
    for bits in TIERS:
        if length < (1 << bits):
            return bits
    return TIERS[-1]


class Packing(IrLeaf[IrSelf, IrSelf]):
    """One packing tier — the origin-bits triple as a single value-object.

    :ivar bits: Bits reserved for an origin / end column in a packed item.
    :ivar mask: ``(1 << bits) - 1`` — extracts the origin (or a handle's end).
    :ivar advance: ``1 << bits`` — the dot-advance addend and the input-length
        capacity ceiling.
    """

    __slots__ = ("bits", "mask", "advance")

    bits: int
    mask: int
    advance: int

    def __init__(self, bits: int) -> None:
        """Derive the mask and advance of tier ``bits``."""
        self.bits = bits
        self.mask = (1 << bits) - 1
        self.advance = 1 << bits


def predecessor_chain(
    links: dict[int, list[KLink]],
    handle: int,
    spec: ChainSpec,
    choices: dict[int, int] | None = None,
) -> list[KLink] | None:
    """Walk a packed handle's single-link predecessor chain down to ``base``.

    Shared by forest readers that walk a packed predecessor chain.

    :param links: The parse's SPPF family table.
    :param handle: The packed ``(item << bits) | end`` — the same spelling
        every other site carries the pair in.
    :param spec: The arm base, packing tier and choice table to cut against.
    :param choices: keys pinned to one family. When given, a packed key is no
        longer a reason to bail — the chain is resolved by
        :func:`~lexic.parsing.earley.kernel.tables.splits.leftmost_chain`, which
        gives the text of an adjacent-nullable run to the FIRST slot that can
        take it, and a pinned entry overrides it at that key (which is how the
        ambiguity check flips one point). When ``None`` a packed key bails,
        which is the fast path's contract.
    :returns: The chain's ``(predecessor_item, predecessor_end, child)``
        triples in source order, or ``None`` when a key is missing, or packs
        more than one family and no choice was supplied — the caller's cue to
        bail (no build, or fall back to the ambiguity-aware path).
    """
    if choices is not None:
        return leftmost_chain(links, handle, spec, choices)
    base, bits = spec.base, spec.bits
    chain: list[KLink] = []
    item, end = handle >> bits, handle & ((1 << bits) - 1)
    while (item >> bits) != base:
        bucket = links.get((item << bits) | end)
        if bucket is None or len(bucket) > 1:
            return None
        item, end, child = bucket[0]
        chain.append((item, end, child))
    chain.reverse()
    return chain


def _charclass_contains(charclass: IrCharClass, char: str) -> bool:
    """Whether ``char`` is a member of ``charclass``.

    :param charclass: A character class of :class:`IrRange` spans and single
        :class:`~lexic.ir.base.IrChr` code points.
    :param char: A single character.
    :returns: ``True`` when ``char`` falls in a range or equals a listed char.
    """
    for element in charclass:
        if isinstance(element, IrRange):
            if str(element.lo) <= char <= str(element.hi):
                return True
        elif char in str(element):
            return True
    return False


def expand_atom(atom: IrSelf) -> Charset:
    """The exact single-char set a terminal atom matches, or poisoned.

    A literal qualifies only at length 1 (a longer literal is not a
    char-unit); a range wider than :data:`_MAX_CHARSET` poisons.
    """
    if isinstance(atom, IrLiteral):
        return frozenset(atom) if len(atom) == 1 else None
    if not isinstance(atom, IrCharClass):
        return None
    chars: set[str] = set()
    for element in atom:
        if isinstance(element, IrRange):
            lo, hi = ord(str(element.lo)), ord(str(element.hi))
            if hi - lo > _MAX_CHARSET:
                return None
            chars.update(chr(c) for c in range(lo, hi + 1))
        else:
            chars.update(str(element))
    return frozenset(chars)


def atom_accepts(
    atom: IrLiteral | IrCharClass | IrNot | IrAlphabet | RunTerm, char: str
) -> bool:
    """Whether a terminal atom can **begin** with ``char`` — the scan filter.

    A multi-char literal is begun by its first character (the full match is
    the scanner's ``startswith``); a negated char class (``IrNot`` over an
    ``IrCharClass``) by any char outside its set; a :class:`RunTerm` by any
    char of its set.

    :param atom: A terminal atom (``IrLiteral``, ``IrCharClass``,
        ``IrNot(IrCharClass)``, ``RunTerm``).
    :param char: A single character.
    :returns: ``True`` when a match at ``char`` is possible.
    :raises UnsupportedConstructError: When ``atom`` is an ``IrNot`` over
        anything other than an ``IrCharClass``.
    """
    # A token terminal (always an IrAlphabet; negation is inside it) matches an
    # id at a boundary, never a char — the token-scan branch handles it, so the
    # char scan skips it.
    if isinstance(atom, IrAlphabet):
        return False
    if isinstance(atom, IrLiteral):
        return atom.startswith(char)  # IrLiteral IS-A str
    if isinstance(atom, IrCharClass):
        return _charclass_contains(atom, char)
    if isinstance(atom, IrNot):
        inner = atom[0]
        if isinstance(inner, IrCharClass):
            return not _charclass_contains(inner, char)
        raise UnsupportedConstructError(
            f"parsing: IrNot over {type(inner).__name__} — "
            "only IrNot(IrCharClass) is a terminal atom"
        )
    if isinstance(atom, RunTerm):
        return char in atom.charset
    return False


class RunTerm(IrLeaf[IrSelf, IrSelf], IrAtom):
    """A compiled maximal-munch run terminal — one scan step per whole run.

    Replaces the body of a *synthetic* star/plus rule whose unit resolves to
    a fixed charset, whose iteration is derivation-unique, and whose FOLLOW
    set is disjoint from the charset (so maximal munch is complete, not a
    heuristic — see :mod:`lexic.parsing.earley.lexruns`). The scanner consumes the
    maximal run in one loop and lands the advance at its end.

    IS-A :class:`~lexic.ir.base.IrAtom`: in the compiled-tables world a run
    terminal fills exactly the atom slot a literal or char class would in an
    uncollapsed grammar (:meth:`TableBuilder._compile_run_rule` wraps one in
    an ``IrItem`` alongside them).

    :ivar charset: The characters the run ranges over.
    :ivar lo: The minimum run length (≥ 1 — an empty star match stays on the
        synthetic rule's empty arm).
    :ivar mode: The per-char reduction contribution (:data:`RUN_DROP` /
        :data:`RUN_STR` / :data:`RUN_LEAF`).
    """

    __slots__ = ("charset", "lo", "mode")

    charset: frozenset[str]
    lo: int
    mode: int

    def __init__(self, charset: frozenset[str], lo: int, mode: int) -> None:
        """Freeze one run terminal's matching and reduction metadata."""
        self.charset = charset
        self.lo = lo
        self.mode = mode
