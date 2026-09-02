"""What the clone compiler ASKS about a rule, as opposed to how it compiles one.

Two questions, both answered from the bound product and the grammar rather
than from the clone body being built, which is why they are here and not in
the compiler: the compiler decides shape, and these decide what that shape is
allowed to be.

A leaf. It takes plain arguments — a rule's product, the construction tables,
the rule table and a continuation — and imports no part of the compiler, so
neither half can drift into the other.
"""

from __future__ import annotations

from collections.abc import Mapping

from lexic.ir import IrRule
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import Pattern
from lexic.parsing.product import (
    ConstructionTables,
    RegularProof,
    RuleProduct,
    construction_of,
    prove_regular,
)

__all__ = ["extent_consult", "extent_pattern", "matches_own_text"]


def matches_own_text(product: RuleProduct | None, tables: ConstructionTables) -> bool:
    """Whether this rule's value IS its matched text — so it needs no interior.

    :param product: The rule's authored product, or ``None`` for a transparent
        helper clone.
    :param tables: The construction operand tables the completion indexes.
    :returns: ``True`` when the completion fills a field from the rule's own
        extent, which is what lets its clone be compiled match-only.
    """
    if product is None:
        return False
    construction = construction_of(product, tables)
    return construction is not None and bool(construction.matched)


def extent_consult(
    rules: Mapping[str, IrRule], name: str, match_only: bool, tail: CharSet
) -> RegularProof | None:
    """The rule's whole extent as one recognizer consult, when it is exact.

    Only a rule whose value IS its matched text can be answered this way:
    there is no interior to build, so deciding the extent decides the
    completion.

    The proof runs against THIS clone's own hard continuation rather than a
    widest follow, and the direction matters — a WIDER continuation makes the
    proof STRICTER, because the boundary obligation is that a repetition or
    nullable atom cannot steal from what follows, and a wider follow offers
    more to steal. Proving against the clone's own tail is therefore both the
    correct question and the one that can actually be answered.

    :param rules: The grammar's rule table.
    :param name: The rule the clone stands for.
    :param match_only: Whether the rule's value is its own matched text.
    :param tail: The clone's hard continuation.
    :returns: The proof, or ``None`` — declining is always safe, and the rule
        keeps its per-character program.
    """
    if not match_only:
        return None
    return prove_regular(rules, name, tail)


def extent_pattern(proof: RegularProof) -> Pattern:
    """The one-instance pattern a proof licenses over its own root.

    The proof carries a recognizer for a whole closure; what a consult runs is
    the single entry for the rule it was taken on. Spelled here so the clone
    compiler never has to index a recognizer's tables itself.

    :param proof: The accepted proof.
    :returns: The compiled possessive pattern for ``proof.root``.
    """
    return proof.recognizer.pats[proof.entry]
