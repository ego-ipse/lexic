"""EXTEND — what can lengthen a complete match.

Item, sequence and arm rules, the shifting bound, and :func:`rule_extensions`,
the fixpoint every reader of one analysis shares.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence, cast

from lexic.ir import (
    IrAction,
    IrAlphabet,
    IrAlternation,
    IrAtom,
    IrCharClass,
    IrItem,
    IrLambda,
    IrLiteral,
    IrNot,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
)
from lexic.parsing.pda.analysis.extend.maps import (
    Extensions,
    anything,
    found_ruleref,
    nothing,
)
from lexic.parsing.pda.analysis.predicates import (
    atom_alphabet,
    grow_charsets,
    item_nullable,
    seq_alphabet,
    seq_nullable,
)
from lexic.parsing.pda.core.charsets import CharSet

if TYPE_CHECKING:  # `analysis` imports this module, so the reference is mutual
    from lexic.parsing.pda.analysis.analysis import GrammarAnalysis


# ── EXTEND — what can lengthen a complete match ───────────────────────
#
# EXTEND(L) holds every ``w[0]`` for which some ``u`` and ``uw`` are both in L:
# the characters at which a complete match can go on and still be a match.
# Every rule below over-approximates it, and ALPHABET bounds it outright
# (``w[0]`` is a character of ``uw``), which is the fallback wherever a
# boundary inside the construct is not settled.


def _ext_alternation(d: GrammarAnalysis, n: IrSelf, nc: Sequence[object]) -> CharSet:
    """A group extends as the alternation of its arms."""
    assert isinstance(n, IrAlternation)
    return arms_extension(d, list(n), cast(Extensions, nc))


def item_extension(d: GrammarAnalysis, item: IrItem, maps: Extensions) -> CharSet:
    """EXTEND of one quantified item.

    Up to one occurrence, an optional one also extends its own absence. A
    repetition extends its last iteration, or starts another if its count may
    grow, PROVIDED no iteration can itself be extended by an iteration's first
    character; otherwise its boundaries shift and ALPHABET is the bound.
    """
    atom = item.atom
    ext = cast(CharSet, EXTEND.resolve(atom).eval(d, atom, maps))
    lo, hi = int(item.quantifier.lo), item.quantifier.upper()
    first = d.atom_first(atom)
    if hi == 0:
        return CharSet.EMPTY
    if hi == 1:
        return ext if lo == 1 else ext.union(first)
    if not _splits_alike(d, atom, ext):
        return atom_alphabet(atom, (maps.alphabets,))
    return ext if hi == lo else ext.union(first)


def _splits_alike(d: GrammarAnalysis, atom: IrAtom, ext: CharSet) -> bool:
    """Whether a run of ``atom`` and a longer one split alike up to the shorter's
    end: no occurrence is empty, and none lengthens (``ext``) into the next."""
    return not d.atom_nullable(atom) and not ext.overlaps(d.atom_first(atom))


def seq_extension(
    d: GrammarAnalysis, items: Sequence[IrItem], maps: Extensions
) -> CharSet:
    """EXTEND of a sequence: its items' own where all after them can vanish,
    plus the ALPHABET from the leftmost item whose boundary can shift on
    (:func:`_may_shift`): readings of ``u`` and ``uw`` first part there."""
    out = CharSet.EMPTY
    after, empty_after = CharSet.EMPTY, True
    meets: list[tuple[int, CharSet, bool]] = []
    for at in range(len(items) - 1, -1, -1):
        item = items[at]
        ext = item_extension(d, item, maps)
        if ext.overlaps(after):
            meets.append((at, after, empty_after))
        if empty_after:
            out = out.union(ext)
        first = d.atom_first(item.atom)
        vanishes = item_nullable(d, item)
        after = first.union(after) if vanishes else first
        empty_after = empty_after and vanishes
    for at, follows, vanishing in reversed(meets):
        if vanishing or _may_shift(d, items, at, follows, maps):
            return out.union(seq_alphabet(items[at:], maps.alphabets))
    return out


def _may_shift(
    d: GrammarAnalysis,
    items: Sequence[IrItem],
    at: int,
    follows: CharSet,
    maps: Extensions,
) -> bool:
    """Whether two readings can part at item ``at``: the item's surplus must
    begin what follows it (``follows``, its FIRST). A longer last occurrence
    starts in the atom's EXTEND (its ALPHABET where occurrences may split
    otherwise); failing that, the windows decide (:meth:`KWindowFirst.shifts`)."""
    atom = items[at].atom
    own = cast(CharSet, EXTEND.resolve(atom).eval(d, atom, maps))
    if items[at].quantifier.repeats() and not _splits_alike(d, atom, own):
        own = atom_alphabet(atom, (maps.alphabets,))
    return own.overlaps(follows) or maps.windows.shifts(items, at, own)


def arms_extension(
    d: GrammarAnalysis, arms: Sequence[Sequence[IrItem]], maps: Extensions
) -> CharSet:
    """EXTEND of an alternation: each arm's own, plus one arm lengthened into
    another — from nothing (a nullable arm), or from a shared first character,
    where the other arm's ALPHABET bounds what comes next."""
    firsts = [d.seq_first(arm) for arm in arms]
    empties = [seq_nullable(d, arm) for arm in arms]
    out = CharSet.EMPTY
    for j, arm in enumerate(arms):
        out = out.union(seq_extension(d, arm, maps))
        others = [i for i in range(len(arms)) if i != j]
        if any(empties[i] for i in others):
            out = out.union(firsts[j])
        if any(firsts[i].overlaps(firsts[j]) for i in others):
            out = out.union(seq_alphabet(arm, maps.alphabets))
    return out


def rule_extensions(d: GrammarAnalysis) -> Extensions:
    """Every rule's EXTEND — the least fixpoint, grown from empty.

    Every rule above is monotone and stays within ALPHABET, so the iteration
    terminates, and the least fixpoint is sound by induction on derivation
    height. Built once per analysis, on the first ask, and kept beside the
    FOLLOW windows (``d.follows.extended``): the stop-set settle, the island
    steal, the left-recursion fold and the speculation licence all read it.
    """
    held = d.follows.extended
    if held:
        return held[0]
    maps = Extensions.empty(d.rules)
    grow_charsets(
        maps.found, d.rules, lambda rule: arms_extension(d, list(rule.body), maps)
    )
    held.append(maps)
    return maps


EXTEND: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(nothing)),
    IrAction(IrCharClass, IrLambda(nothing)),
    IrAction(IrNot, IrLambda(nothing)),
    IrAction(IrAlphabet, IrLambda(anything)),
    IrAction(IrRuleRef, IrLambda(found_ruleref)),
    IrAction(IrAlternation, IrLambda(_ext_alternation)),
)
