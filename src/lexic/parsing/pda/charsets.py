"""Polarity-aware character sets — the pivot-1 algebra as a real value type.

A grammar's FIRST/FOLLOW analysis needs exact set algebra over single
characters, including sets defined by EXCLUSION: an ``IrNot([^"])`` loop's
FIRST is "every character except ``\\"``" — a co-finite set no bare
``frozenset`` can represent without either enumerating up to ~1.1M Unicode
code points or being approximated away.

:class:`CharSet` stores ``(chars, negated)``: when ``negated`` is ``False``
the set IS ``chars``; when ``True`` the set is every possible character
EXCEPT ``chars``. Every operation (:meth:`~CharSet.has`,
:meth:`~CharSet.union`, :meth:`~CharSet.subtract`, :meth:`~CharSet.overlaps`)
is exact across all four polarity combinations, so an ``IrNot`` loop or a
huge charclass range stays exactly analysable instead of "poisoning" its
rule into a fake island — the mistake the hybrid-parsing PoC's v1 analysis
made (see ``zzz_current_work/260705-hybrid-parse-poc/INVESTIGATION.md``,
pivot 1).

**The EOF sentinel.** FOLLOW-set seeding represents "end of input" as the
character ``""`` living inside a POSITIVE set. A negated (co-finite) set
never contains ``""`` — :attr:`CharSet.ANY` (every real character) still
excludes end-of-input, since EOF is not a character to exclude *from*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Final

from lexic.ir.nodes import IrCharClass, IrRange

__all__ = ["CharSet", "MAX_RANGE_EXPANSION"]

MAX_RANGE_EXPANSION: Final[int] = 300_000
"""Widest single :class:`IrRange` that :meth:`CharSet.from_charclass` will
enumerate; a wider range falls back to the conservative :attr:`CharSet.ANY`
rather than materialising up to the full Unicode code-point space."""

_EOF_ONLY: Final[frozenset[str]] = frozenset({""})
"""Used to keep the EOF sentinel out of set-difference tests against a
negated operand — a negated set's ``has("")`` is always ``False`` (see
:meth:`CharSet.has`), so ``""`` can never be the character that makes two
sets overlap, or that a negated operand fails to remove, regardless of
whether ``""`` happens to sit in its (otherwise real-character) ``chars``."""


@dataclass(frozen=True, slots=True)
class CharSet:
    """A polarity-aware, co-finite-capable set of single characters.

    :ivar chars: The explicit member characters (positive sets) or the
        explicit exclusions (negated sets).
    :ivar negated: ``False`` — the set IS ``chars``. ``True`` — the set is
        every character except ``chars`` (co-finite).

    Hashable and comparable by value, so a ``CharSet`` can key a dict (used
    as part of a clone key, ``(rule, continuation)``, by the PDA compiler).

    Invariant: a negated set's ``chars`` never contains the EOF sentinel
    ``""`` — every constructor below upholds this (:meth:`from_charclass`/
    :meth:`from_not` only ever see real code points; :meth:`from_chars`
    always returns a positive set), and the algebra methods preserve it.
    Constructing ``CharSet`` directly with ``""`` in a negated ``chars``
    breaks :meth:`has`'s EOF-exclusion guarantee for that value.
    """

    chars: frozenset[str]
    negated: bool = False

    EMPTY: ClassVar["CharSet"]
    ANY: ClassVar["CharSet"]

    def has(self, ch: str) -> bool:
        """Whether ``ch`` is a member.

        The EOF sentinel ``""`` is never a member of a negated set — see the
        module docstring.

        :param ch: A single character, or the empty-string EOF sentinel.
        :returns: ``True`` iff ``ch`` is covered by this set.
        """
        if self.negated:
            return ch != "" and ch not in self.chars
        return ch in self.chars

    def union(self, other: "CharSet") -> "CharSet":
        """Set union — exact for every real character.

        .. note::
           When the union of a negated operand with a positive operand
           carrying the EOF sentinel produces a negated result, that EOF
           membership is lost: a negated ``CharSet`` can never carry ``""``
           (see :meth:`has`), so there is no way to represent "co-finite over
           reals, plus EOF" in this shape. This is a structural limit of
           ``(chars, negated)``, not an approximation — callers that must
           track EOF across such a union (e.g. FOLLOW-set fixpoints) should
           track it as a separate flag alongside the ``CharSet``.

        :param other: The set to union with.
        :returns: ``self ∪ other``.
        """
        if not self.negated and not other.negated:
            return CharSet(self.chars | other.chars, False)
        if self.negated and other.negated:
            return CharSet(self.chars & other.chars, True)
        if self.negated:
            return CharSet(self.chars - other.chars, True)
        return CharSet(other.chars - self.chars, True)

    def subtract(self, other: "CharSet") -> "CharSet":
        """Set difference ``self − other``, exact across all four polarity
        combinations, including the EOF sentinel.

        :param other: The set to subtract.
        :returns: ``self − other``.
        """
        if not self.negated and not other.negated:
            return CharSet(self.chars - other.chars, False)
        if not self.negated and other.negated:
            # A negated `other` never removes "" (it never has it to remove),
            # so self's own EOF membership always passes through, even
            # though `other.chars` itself can never contain "".
            return CharSet(self.chars & (other.chars | _EOF_ONLY), False)
        if self.negated and not other.negated:
            return CharSet(self.chars | other.chars, True)
        return CharSet(other.chars - self.chars, False)

    def overlaps(self, other: "CharSet") -> bool:
        """Whether ``self`` and ``other`` share any member, including the EOF
        sentinel, exact across all four polarity combinations.

        Two negated (co-finite) sets always overlap: each excludes only a
        finite set of characters, so their intersection excludes at most the
        union of those exclusions and is still co-finite, hence non-empty.

        :param other: The set to test against.
        :returns: ``True`` iff the two sets intersect.
        """
        if not self.negated and not other.negated:
            return bool(self.chars & other.chars)
        if self.negated and other.negated:
            return True
        # "" can never be the shared member here: a negated operand's
        # has("") is always False, so exclude it before testing the
        # remaining (real-character) difference for a genuine overlap.
        if self.negated:
            return bool((other.chars - self.chars) - _EOF_ONLY)
        return bool((self.chars - other.chars) - _EOF_ONLY)

    def is_empty(self) -> bool:
        """Whether this set has no members.

        A negated set is never empty (it excludes only finitely many
        characters out of an effectively unbounded alphabet).

        :returns: ``True`` iff this is the positive empty set.
        """
        return not self.negated and not self.chars

    @classmethod
    def from_charclass(cls, cc: IrCharClass) -> "CharSet":
        """Expand a character class to its exact positive member set.

        Each :class:`IrRange` expands to its constituent glyphs; each single
        :class:`IrChr` contributes one glyph. A range wider than
        :data:`MAX_RANGE_EXPANSION` is not enumerated — it falls back to the
        conservative :attr:`ANY` instead.

        :param cc: The character class to expand.
        :returns: The exact positive set, or :attr:`ANY` if a range exceeded
            the expansion cap.
        """
        chars: set[str] = set()
        for element in cc:
            if isinstance(element, IrRange):
                lo, hi = int(element.lo), int(element.hi)
                if hi - lo > MAX_RANGE_EXPANSION:
                    return cls.ANY
                chars.update(chr(point) for point in range(lo, hi + 1))
            else:
                chars.add(str(element))
        return cls(frozenset(chars), False)

    @classmethod
    def from_not(cls, inner: IrCharClass) -> "CharSet":
        """Complement of ``inner``'s expansion — the ``IrNot(charclass)`` case.

        The positive expansion is negated; if ``inner`` itself only fit the
        conservative :attr:`ANY` (its expansion exceeded the cap), the
        complement is unknown too, so this stays :attr:`ANY` rather than
        guessing.

        :param inner: The character class being negated.
        :returns: The complement set, or :attr:`ANY` when ``inner`` itself
            exceeded the expansion cap.
        """
        positive = cls.from_charclass(inner)
        if positive.negated:
            return cls.ANY
        return cls(positive.chars, True)

    @classmethod
    def from_chars(cls, *chars: str) -> "CharSet":
        """Build an exact positive set from explicit single-character strings.

        Used for e.g. a literal's leading character, or FOLLOW-set EOF
        seeding (``from_chars("")``).

        :param chars: The member characters (or the EOF sentinel ``""``).
        :returns: The positive set containing exactly ``chars``.
        """
        return cls(frozenset(chars), False)


CharSet.EMPTY = CharSet(frozenset(), False)
"""The empty set — no characters, including no EOF sentinel."""

CharSet.ANY = CharSet(frozenset(), True)
"""Every character — the co-finite universal set, and the conservative
"unknown" value returned when a set cannot be computed exactly (e.g. a
range past :data:`MAX_RANGE_EXPANSION`)."""
