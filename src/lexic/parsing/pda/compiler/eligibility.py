"""What the clone compiler ASKS about a rule, as opposed to how it compiles one.

Two questions, both answered from the bound product and the grammar rather
than from the clone body being built, which is why they are here and not in
the compiler: the compiler decides shape, and these decide what that shape is
allowed to be.

A leaf. It takes plain arguments — a rule's verified routine, the rule table
and a continuation — and imports no part of the compiler, so neither half can
drift into the other.
"""

from __future__ import annotations

from collections.abc import Mapping

from lexic.ir import IrRule
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import Pattern
from lexic.parsing.product import RegularProof, RuleRoutine, prove_regular

__all__ = ["extent_consult", "extent_pattern", "matches_own_text"]


def matches_own_text(routine: RuleRoutine | None) -> bool:
    """Whether this rule's value IS its matched text — so it needs no interior.

    :param routine: The rule's verified completion routine, or ``None`` for a
        transparent helper clone.
    :returns: ``True`` when the completion fills a field from the rule's own
        extent, which is what lets its clone be compiled match-only.
    """
    if routine is None or routine.construction is None:
        return False
    return bool(routine.construction.matched)


def extent_consult(
    rules: Mapping[str, IrRule],
    name: str,
    match_only: bool,
    tail: CharSet,
    follow: CharSet,
) -> RegularProof | None:
    """The rule's whole extent as one recognizer consult, when it is exact.

    Only a rule whose value IS its matched text can be answered this way:
    there is no interior to build, so deciding the extent decides the
    completion.

    The proof runs against the clone's hard continuation UNIONED with the
    rule's soft FOLLOW, and the direction is the reason. A wider continuation
    makes the proof STRICTER — the boundary obligation is that a repetition or
    nullable atom cannot steal from what follows, and a wider follow offers
    more to steal. The clone's tail alone is narrower than what can really
    follow it: it is the next MANDATORY item's first set, so every nullable
    follower between the two is skipped and the obligation is never asked
    whether the rule's own trailing optional can take that follower's first
    character. Unioning the rule's soft FOLLOW puts them back, and everything
    else it drags in only makes the question harder to answer.

    :param rules: The grammar's rule table.
    :param name: The rule the clone stands for.
    :param match_only: Whether the rule's value is its own matched text.
    :param tail: The clone's hard continuation.
    :param follow: The rule's soft FOLLOW — every character that can follow a
        reference to it anywhere, nullable followers included.
    :returns: The proof, or ``None`` — declining is always safe, and the rule
        keeps its per-character program.
    """
    if not match_only:
        return None
    return prove_regular(rules, name, tail.union(follow))


def extent_pattern(proof: RegularProof) -> Pattern:
    """The one-instance pattern a proof licenses over its own root.

    The proof carries a recognizer for a whole closure; what a consult runs is
    the single entry for the rule it was taken on. Spelled here so the clone
    compiler never has to index a recognizer's tables itself.

    :param proof: The accepted proof.
    :returns: The compiled possessive pattern for ``proof.root``.
    """
    return proof.recognizer.pats[proof.entry]
