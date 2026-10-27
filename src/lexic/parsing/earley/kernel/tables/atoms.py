"""Atoms and packing — the primitives the tables are built out of.

How an item is packed into an int, how a chart's families are read, and what
a single atom accepts. Nothing here knows what a table is.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import NamedTuple, Protocol, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAction,
    IrAlphabet,
    IrAtom,
    IrCharClass,
    IrChr,
    IrLambda,
    IrLeaf,
    IrLiteral,
    IrNone,
    IrNoneType,
    IrNot,
    IrRange,
    IrSelf,
    IrTypeMap,
)
from lexic.parsing.earley.kernel.forest.forest import PayloadLeaf

MAX_CHARSET = 4096
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


class FamilyReader(Protocol):
    """What a chain walker needs of the family table: one key's families.

    A Protocol rather than the concrete mapping because a chart that factored
    reads through :class:`~lexic.parsing.earley.kernel.forest.families.FamilyTable`,
    while one that did not reads the link ``dict`` itself.
    """

    def get(self, key: int, /) -> list[KLink] | None:
        """This key's families, or ``None`` when it names none."""
        raise NotImplementedError

    def __getitem__(self, key: int, /) -> list[KLink]:
        """This key's families; raises :class:`KeyError` when it names none."""
        raise NotImplementedError

    def items(self) -> Iterable[tuple[int, list[KLink]]]:
        """Every key with its families — the decode path's whole-table read."""
        raise NotImplementedError


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


def inner_class(atom: IrSelf) -> IrCharClass:
    """The class an ``IrNot`` terminal negates.

    :raises UnsupportedConstructError: When it negates anything else.
    """
    inner = IrNot.ensure(atom)[0]
    if not isinstance(inner, IrCharClass):
        raise UnsupportedConstructError(
            f"parsing: IrNot over {type(inner).__name__} — "
            "only IrNot(IrCharClass) is a terminal atom"
        )
    return inner


def atom_unit(atom: IrSelf) -> IrCharClass | IrNoneType:
    """The exact class of characters a single-char terminal matches, or IrNone.

    Any width and either polarity: a negated class is its complement, so
    ``[^"]`` is every code point but one. A longer literal or a token is no
    one-character unit.
    """
    if isinstance(atom, IrLiteral):
        return IrCharClass(IrChr(ord(atom))) if len(atom) == 1 else IrNone
    if isinstance(atom, IrCharClass):
        return atom
    if isinstance(atom, IrNot):
        return inner_class(atom).complement()
    return IrNone


def expand_atom(atom: IrSelf) -> Charset:
    """The exact single-char set a terminal atom matches, or poisoned.

    A literal qualifies only at length 1 (a longer literal is not a
    char-unit); a range wider than :data:`MAX_CHARSET` poisons.
    """
    if isinstance(atom, IrLiteral):
        return frozenset(atom) if len(atom) == 1 else None
    if not isinstance(atom, IrCharClass):
        return None
    chars: set[str] = set()
    for element in atom:
        if isinstance(element, IrRange):
            lo, hi = ord(str(element.lo)), ord(str(element.hi))
            if hi - lo > MAX_CHARSET:
                return None
            chars.update(chr(c) for c in range(lo, hi + 1))
        else:
            chars.update(str(element))
    return frozenset(chars)


def atom_accepts(
    atom: IrLiteral | IrCharClass | IrNot | IrAlphabet | RunTerm, char: str
) -> bool:
    """Whether a terminal atom can **begin** with ``char`` — the scan filter.

    The char scan's question, so a token answers ``False``: the scan never
    tries one, though its spelling may begin with anything. The run proof
    asks the other question, :func:`may_begin_within`.

    A multi-char literal is begun by its first character (the full match is
    the scanner's ``startswith``); a negated char class (``IrNot`` over an
    ``IrCharClass``) by any char outside its set; a :class:`RunTerm` by any
    char of its set, or outside it when the run is negated.

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
        return not _charclass_contains(inner_class(atom), char)
    if isinstance(atom, RunTerm):
        return char in atom.charset
    return False


class Spans(NamedTuple):
    """A run's character set as code-point ranges — for a unit too large to list.

    ``[一-鿿]`` alone is 20,992 members and over a million non-members, so
    neither side fits a listed set. The unit's cover is computed once, and
    membership is one bisect over it (:meth:`IrCharClass.cover_holds`).

    :ivar cover: The unit's sorted, coalesced ``(lo, hi)`` ranges.
    """

    cover: tuple[tuple[int, int], ...]

    @classmethod
    def of(cls, unit: IrCharClass) -> Spans:
        """``unit``'s coalesced cover, held."""
        return cls(tuple(unit.intervals()))

    def __contains__(self, char: object) -> bool:
        """Whether ``char`` falls inside one of the ranges."""
        return IrCharClass.cover_holds(self.cover, ord(cast(str, char)))


class Excluding(frozenset[str]):
    """A co-finite run's character set: it holds every character it does NOT list.

    The scanner's run loop asks ``text[j] in charset`` of every run alike, so a
    positive run keeps the plain ``frozenset`` test and only a negated one pays
    for the inversion.

    Only membership is inverted. Iteration, ``len`` and set algebra speak of
    the EXCLUDED characters, so never iterate one or combine it with another
    set: ``in`` is the one question it answers for the run.
    """

    __slots__ = ()

    def __contains__(self, char: object) -> bool:
        """Every character but the listed ones."""
        return not frozenset.__contains__(self, char)


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

    :ivar charset: The characters the run ranges over: a ``frozenset``, an
        :class:`Excluding` when ``negated`` (``[^"]*`` lists the one quote),
        or :class:`Spans` when neither side can be listed.
    :ivar lo: The minimum run length (≥ 1 — an empty star match stays on the
        synthetic rule's empty arm).
    :ivar mode: The per-char reduction contribution (:data:`RUN_DROP` /
        :data:`RUN_STR` / :data:`RUN_LEAF`).
    :ivar negated: ``charset`` lists what the run excludes.
    """

    __slots__ = ("charset", "lo", "mode", "negated")

    charset: frozenset[str] | Spans
    lo: int
    mode: int
    negated: bool

    def __init__(
        self,
        charset: frozenset[str] | Spans,
        lo: int,
        mode: int,
        negated: bool = False,
    ) -> None:
        """Freeze one run terminal's matching and reduction metadata."""
        listed = isinstance(charset, frozenset)
        self.charset = Excluding(charset) if negated and listed else charset
        self.lo = lo
        self.mode = mode
        self.negated = negated

    @classmethod
    def over(cls, unit: IrCharClass, mode: int) -> RunTerm:
        """The run of ``unit``, listed from whichever side holds fewer points,
        or tested by its ranges when neither side fits :data:`MAX_CHARSET`."""
        listed = unit.listed(MAX_CHARSET)
        if isinstance(listed, IrNoneType):
            return cls(Spans.of(unit), 1, mode)
        chars, negated = listed
        return cls(chars, 1, mode, negated)

    @property
    def first_chars(self) -> frozenset[str] | None:
        """The characters a match may begin with, or ``None`` when they are too
        many to list — a negated or ranged run."""
        listed = isinstance(self.charset, frozenset) and not self.negated
        return cast(frozenset[str], self.charset) if listed else None


def _within_literal(_d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> bool:
    """A literal begins with its first character; the empty one with none."""
    text = str(n)
    return bool(text) and IrCharClass.ensure(nc[0]).holds(ord(text[0]))


def _within_class(_d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> bool:
    """A class begins with any member: does it meet the unit?"""
    return IrCharClass.ensure(n).meets(IrCharClass.ensure(nc[0]))


def _within_not(_d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> bool:
    """A negated class begins with anything its inner class leaves out."""
    return not IrCharClass.ensure(nc[0]).within(inner_class(n))


def _within_token(_d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf]) -> bool:
    """A token's spelling may begin with any character — the sound answer."""
    return True


MAY_BEGIN_WITHIN: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_within_literal)),
    IrAction(IrCharClass, IrLambda(_within_class)),
    IrAction(IrNot, IrLambda(_within_not)),
    IrAction(IrAlphabet, IrLambda(_within_token)),
)
"""Per terminal kind: can its text begin with a member of a unit class?

The rows are exactly the kinds a plain table layout holds. Anything else — a
:class:`RunTerm`, which only a collapsed layout holds, or a kind not yet
written — raises rather than answering no."""


def may_begin_within(atom: IrSelf, unit: IrCharClass) -> bool:
    """Whether ``atom``'s text can begin with a member of ``unit``.

    Interval work throughout, never point by point, at any width and either
    polarity: a literal is one bisect, a class or a negated class one merge
    walk over the two classes' covers.

    :param atom: A terminal of a plain table layout.
    :param unit: The characters asked about.
    :returns: ``True`` when it may; a token always may.
    :raises IrKeyError: On an atom kind no row names.
    """
    row = MAY_BEGIN_WITHIN.resolve(atom)
    return cast(bool, row.eval(IrNone, atom, (unit,)))
