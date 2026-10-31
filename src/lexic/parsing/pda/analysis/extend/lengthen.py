"""EXTEND — what can lengthen a complete match.

Item, sequence and arm rules, the shifting bound, R3's confinement, and
:func:`rule_extensions`, the fixpoint every reader of one analysis shares.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, NamedTuple, Sequence, cast

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
    IrRule,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
)
from lexic.parsing.pda.analysis.extend.maps import (
    Arm,
    Extensions,
    Solve,
    TailsKey,
    anything,
    found_ruleref,
    nothing,
)
from lexic.parsing.pda.analysis.extend.runs import (
    apart,
    heads,
    leading_run,
    led,
    run_chars,
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
        if _confined_repeat(d, maps, atom, ext):
            return ext.union(first)
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
    (:func:`_may_shift`): readings of ``u`` and ``uw`` first part there. A
    shift confined to a run (:func:`_confined_at`) adds nothing there: such
    readings extend the rest, whose items' own terms are already counted. Where
    the ALPHABET adds nothing, nothing is asked."""
    out = CharSet.EMPTY
    after, empty_after = CharSet.EMPTY, True
    meets: list[tuple[int, CharSet, CharSet, bool]] = []
    for at in range(len(items) - 1, -1, -1):
        item = items[at]
        ext = item_extension(d, item, maps)
        if ext.overlaps(after):
            meets.append((at, ext, after, empty_after))
        if empty_after:
            out = out.union(ext)
        first = d.atom_first(item.atom)
        vanishes = item_nullable(d, item)
        after = first.union(after) if vanishes else first
        empty_after = empty_after and vanishes
    for at, ext, follows, vanishing in reversed(meets):
        if not (vanishing or _may_shift(d, items, at, follows, maps)):
            continue
        alphabet = seq_alphabet(items[at:], maps.alphabets)
        if run_chars(d, maps.confined).is_empty():
            return out.union(alphabet)
        if alphabet.within(out):
            return out
        if not _confined_at(d, items, at, ext.subtract(ext.subtract(follows)), maps):
            return out.union(alphabet)
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
    where the other arm's ALPHABET bounds what comes next, unless the two part
    on a shared leading run (:func:`~.runs.apart`)."""
    firsts = [d.seq_first(arm) for arm in arms]
    empties = [seq_nullable(d, arm) for arm in arms]
    out = CharSet.EMPTY
    for j, arm in enumerate(arms):
        out = out.union(seq_extension(d, arm, maps))
        others = [i for i in range(len(arms)) if i != j]
        if any(empties[i] for i in others):
            out = out.union(firsts[j])
        if any(firsts[i].overlaps(firsts[j]) for i in others):
            out = out.union(_unparted(d, maps, arms, firsts, j))
    return out


def _unparted(
    d: GrammarAnalysis,
    maps: Extensions,
    arms: Sequence[Arm],
    firsts: list[CharSet],
    j: int,
) -> CharSet:
    """The ALPHABET arm ``j`` lengthens by into an arm sharing a first
    character with it, unless every such arm parts from it on a run."""
    arm, memo = arms[j], maps.confined
    alphabet = seq_alphabet(arm, maps.alphabets)
    if run_chars(d, memo).is_empty():
        return alphabet
    meets = (i for i in range(len(arms)) if i != j and firsts[i].overlaps(firsts[j]))
    if all(apart(d, memo, arms[i], arm) for i in meets):
        return CharSet.EMPTY
    return alphabet


# ── R3 — a shift confined to a run ────────────────────────────────────
#
# Where two readings part at an item whose surplus K meets what follows, the
# fallback is ALPHABET. R3 drops it when the rest begins with runs of a class S
# covering K, every string of the rest is a droppable S-prefix then a character
# outside S (``led``), and every extension of the item that begins in K is all
# S or leaves S on a character the rest's strings never leave S on: its TAILS
# miss the rest's ``heads``. Then the longer reading's surplus is the rest
# lengthened, which the rest's own EXTEND already counts. TAILS is a least
# fixpoint per (rule, S): one ask's solve reads each key it meets depth-first,
# and settles a cycle among them by passes.


class _Ask(NamedTuple):
    """A TAILS question riding ``nc``: the build's maps, and the run class."""

    maps: Extensions
    run: CharSet


def _confined_at(
    d: GrammarAnalysis, items: Arm, at: int, shared: CharSet, maps: Extensions
) -> bool:
    """R3 at ``items[at]``, whose surplus meets what follows it in ``shared``."""
    memo = maps.confined
    if not shared.within(run_chars(d, memo)):
        return False
    held = memo.verdict((id(items), at), items)
    if held is not None:
        return held
    rest = items[at + 1 :]
    run = _led_run(d, maps, rest, shared)
    got = run is not None and not tails_item(d, maps, items[at], run).overlaps(
        heads(d, memo, rest, run)
    )
    memo.keep((id(items), at), items, got)
    return got


def _confined_repeat(
    d: GrammarAnalysis, maps: Extensions, atom: IrAtom, ext: CharSet
) -> bool:
    """R3 at a repetition's iteration boundary: the rest is another iteration."""
    memo = maps.confined
    runs = run_chars(d, memo)
    if runs.is_empty() or d.atom_nullable(atom):
        return False
    shared = ext.subtract(ext.subtract(d.atom_first(atom)))
    if not shared.within(runs):
        return False
    held = memo.verdict((id(atom), -1), atom)
    if held is not None:
        return held
    once = [maps.confined.once(atom)]
    run = _led_run(d, maps, once, shared)
    got = run is not None and not _tails_atom(d, maps, atom, run).overlaps(
        heads(d, memo, once, run)
    )
    memo.keep((id(atom), -1), atom, got)
    return got


def _led_run(
    d: GrammarAnalysis, maps: Extensions, rest: Arm, shared: CharSet
) -> CharSet | None:
    """The run class ``rest`` begins with where it begins in ``shared``, if it
    leads every such string; else ``None``. It covers ``shared``: each such
    character begins an item that :func:`~.runs.leading_run` reads as a run."""
    memo = maps.confined
    run = leading_run(d, memo, rest, shared)
    return run if run is not None and led(d, memo, rest, run) else None


def tails_item(
    d: GrammarAnalysis, maps: Extensions, item: IrItem, run: CharSet
) -> CharSet:
    """TAILS of one item: the first character outside ``run`` of each of its
    extensions that begins in ``run``; ANY where that cannot be read."""
    if not item_extension(d, item, maps).overlaps(run):
        return CharSet.EMPTY
    atom = item.atom
    if atom_alphabet(atom, (maps.alphabets,)).within(run):
        return CharSet.EMPTY
    once = [maps.confined.once(atom)]
    if item.quantifier.repeats():
        own = cast(CharSet, EXTEND.resolve(atom).eval(d, atom, maps))
        if not _splits_alike(d, atom, own) and not _confined_repeat(d, maps, atom, own):
            return CharSet.ANY
        return _tails_atom(d, maps, atom, run).union(heads(d, maps.confined, once, run))
    out = _tails_atom(d, maps, atom, run)
    if int(item.quantifier.lo) == 0 and d.atom_first(atom).overlaps(run):
        out = out.union(heads(d, maps.confined, once, run))
    return out


def _tails_atom(
    d: GrammarAnalysis, maps: Extensions, atom: IrAtom, run: CharSet
) -> CharSet:
    """Dispatch one atom against :data:`TAILS`."""
    return cast(CharSet, TAILS.resolve(atom).eval(d, atom, _Ask(maps, run)))


def _tails_group(d: GrammarAnalysis, n: IrSelf, nc: Sequence[object]) -> CharSet:
    """A group's TAILS are its arms'."""
    assert isinstance(n, IrAlternation)
    ask = cast(_Ask, nc)
    return tails_arms(d, ask.maps, list(n), ask.run)


def _tails_ruleref(d: GrammarAnalysis, n: IrSelf, nc: Sequence[object]) -> CharSet:
    """A reference reads its rule's TAILS, solving them on a first ask."""
    ask = cast(_Ask, nc)
    memo = ask.maps.confined
    if str(n) not in d.rules:
        return CharSet.ANY
    key = (str(n), ask.run)
    if memo.solve:
        return _tails_met(d, ask.maps, memo.solve[0], key)
    held = memo.tails.get(key)
    if held is not None:
        return held
    solve = Solve([], set(), set(), {})
    memo.solve.append(solve)
    try:
        _tails_met(d, ask.maps, solve, key)
        while solve.looped and _tails_pass(d, ask.maps, solve):
            pass
    finally:
        memo.solve.clear()
    memo.verdicts.update(solve.verdicts)
    return memo.tails[key]


def _tails_met(
    d: GrammarAnalysis, maps: Extensions, solve: Solve, key: TailsKey
) -> CharSet:
    """A key met inside a solve: read at once where it is new, so a key read
    after its own reads finished is exact; one met while busy is a cycle."""
    tails = maps.confined.tails
    if key in solve.busy:
        solve.looped.add(key)
        return tails[key]
    held = tails.get(key)
    if held is not None:
        return held
    tails[key] = CharSet.EMPTY
    solve.keys.append(key)
    solve.busy.add(key)
    try:
        tails[key] = tails_arms(d, maps, list(d.rules[key[0]].body), key[1])
    finally:
        solve.busy.discard(key)
    return tails[key]


def _tails_pass(d: GrammarAnalysis, maps: Extensions, solve: Solve) -> bool:
    """One pass over a looped solve's keys, its verdicts read afresh; whether
    any grew or a new key was met."""
    tails = maps.confined.tails
    solve.verdicts.clear()
    seen = len(solve.keys)
    changed = False
    for key in solve.keys[:seen]:
        got = tails_arms(d, maps, list(d.rules[key[0]].body), key[1])
        if got.union(tails[key]) != tails[key]:
            tails[key] = got.union(tails[key])
            changed = True
    return changed or len(solve.keys) > seen


def tails_arms(
    d: GrammarAnalysis, maps: Extensions, arms: Sequence[Arm], run: CharSet
) -> CharSet:
    """TAILS of an alternation, read by where two readings first part, as
    :func:`arms_extension` reads it."""
    firsts = [d.seq_first(arm) for arm in arms]
    empties = [seq_nullable(d, arm) for arm in arms]
    out = CharSet.EMPTY
    for j, arm in enumerate(arms):
        out = out.union(_tails_seq(d, maps, arm, run))
        others = [i for i in range(len(arms)) if i != j]
        if any(empties[i] for i in others):
            out = out.union(heads(d, maps.confined, arm, run))
        if any(firsts[i].overlaps(firsts[j]) for i in others):
            if not _unparted(d, maps, arms, firsts, j).within(run):
                return CharSet.ANY
    return out


def _tails_seq(d: GrammarAnalysis, maps: Extensions, arm: Arm, run: CharSet) -> CharSet:
    """TAILS of a sequence, read by where two readings first part, as
    :func:`seq_extension` reads it."""
    out = CharSet.EMPTY
    for at, item in enumerate(arm):
        rest = arm[at + 1 :]
        ext = item_extension(d, item, maps)
        if seq_nullable(d, rest):
            out = out.union(tails_item(d, maps, item, run))
            if ext.overlaps(run):
                out = out.union(heads(d, maps.confined, rest, run))
        if not rest or seq_alphabet(arm[at:], maps.alphabets).within(run):
            continue
        if _parts_at(d, arm, at, ext, maps):
            return CharSet.ANY
    return out


def _parts_at(
    d: GrammarAnalysis, arm: Arm, at: int, ext: CharSet, maps: Extensions
) -> bool:
    """Whether two readings of ``arm`` can part at ``at`` outside R3."""
    follows = d.seq_first(arm[at + 1 :])
    if not ext.overlaps(follows) or not _may_shift(d, arm, at, follows, maps):
        return False
    return not _confined_at(d, arm, at, ext.subtract(ext.subtract(follows)), maps)


def _still_confined(d: GrammarAnalysis, maps: Extensions) -> bool:
    """Re-ask every True verdict on the maps as they stand, TAILS solved
    afresh; whether every one still holds. One that fails is kept False."""
    return all(_reasked(d, maps, site, at) for site, at in maps.confined.reopen())


def _reasked(d: GrammarAnalysis, maps: Extensions, site: Arm | IrAtom, at: int) -> bool:
    """One verdict asked again: a repetition's (``at`` -1) or a sequence's."""
    if at < 0:
        atom = cast(IrAtom, site)
        ext = cast(CharSet, EXTEND.resolve(atom).eval(d, atom, maps))
        return _confined_repeat(d, maps, atom, ext)
    items = cast(Arm, site)
    ext = item_extension(d, items[at], maps)
    follows = d.seq_first(items[at + 1 :])
    return _confined_at(d, items, at, ext.subtract(ext.subtract(follows)), maps)


def _rule_extension(d: GrammarAnalysis, maps: Extensions, rule: IrRule) -> CharSet:
    """One rule's EXTEND, read off ``maps`` as they stand."""
    return arms_extension(d, list(rule.body), maps)


def rule_extensions(d: GrammarAnalysis) -> Extensions:
    """Every rule's EXTEND — a fixpoint grown from empty, within ALPHABET.

    Sound by induction on derivation height, which holds of any fixpoint of
    sound rules. R3's verdicts are kept across passes, a False one for good (it
    falls back to the sound bound). Once the maps stand, the True ones are
    re-asked on them (:func:`_still_confined`): if all hold, a pass would
    reproduce the maps, so they are a fixpoint; if one fails, the passes go on.
    Built once per analysis, on the first ask, and kept beside the FOLLOW
    windows (``d.follows.extended``): the stop-set settle, the island steal,
    the left-recursion fold and the speculation licence all read it.
    """
    held = d.follows.extended
    if held:
        return held[0]
    maps = Extensions.empty(d.rules)
    grow = partial(_rule_extension, d, maps)
    grow_charsets(maps.found, d.rules, grow)
    while not _still_confined(d, maps):
        grow_charsets(maps.found, d.rules, grow)
    held.append(maps)
    return maps


TAILS: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(nothing)),
    IrAction(IrCharClass, IrLambda(nothing)),
    IrAction(IrNot, IrLambda(nothing)),
    IrAction(IrAlphabet, IrLambda(anything)),
    IrAction(IrRuleRef, IrLambda(_tails_ruleref)),
    IrAction(IrAlternation, IrLambda(_tails_group)),
)

EXTEND: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(nothing)),
    IrAction(IrCharClass, IrLambda(nothing)),
    IrAction(IrNot, IrLambda(nothing)),
    IrAction(IrAlphabet, IrLambda(anything)),
    IrAction(IrRuleRef, IrLambda(found_ruleref)),
    IrAction(IrAlternation, IrLambda(_ext_alternation)),
)
