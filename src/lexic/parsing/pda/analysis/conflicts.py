"""Late conflict classifiers shared by the PDA grammar analysis."""

# This module is the split implementation half of GrammarAnalysis.
# pylint: disable=protected-access

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Sequence

from lexic.ir import (
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNoneType,
    IrNot,
    IrRule,
    IrRuleRef,
    has_reference,
)
from lexic.parsing.earley.kernel.tables.decider import (
    ATTEMPT,
    GREEDY_SPLIT,
    NOISE_GREEDY,
    STOP_SET,
)
from lexic.parsing.pda.analysis.cursors import ConflictCtx, Cont, Notes, Scope, Site
from lexic.parsing.pda.analysis.demote import demote_loop
from lexic.parsing.pda.analysis.gates.kwindow import FOLLOW_LOOP_K
from lexic.parsing.pda.analysis.gates.noise import noise_greedy_licensed
from lexic.parsing.pda.analysis.gates.windows import (
    END,
    MORE,
    UNK,
    KWindowFirst,
    separable,
)
from lexic.parsing.pda.analysis.predicates import SEQ_ATOM, STOPSET_ATOM, seq_nullable
from lexic.parsing.pda.analysis.taxonomy import AttemptSpec
from lexic.parsing.pda.core.charsets import CharSet


def file_attempt_loop(
    analysis: Any, items: Sequence[IrItem], k: int, scope: Scope, notes: Notes
) -> bool:
    """Cover an ungatable loop's conflict note with the attempt licence — a
    greedy take with rollback, committed as the decider's split answer — where
    the decider grants it; otherwise the note stands and the rule islands.

    :returns: Whether the note is covered.
    """
    if ATTEMPT not in notes.grants:
        return False
    license_attempt(analysis, items, k, scope)
    notes.covered += 1
    return True


def license_attempt(
    analysis: Any, items: Sequence[IrItem], k: int, scope: Scope
) -> None:
    """Give loop ``k`` the attempt licence: each iteration a sub-run that closes
    the loop when it fails, audited where stopping goes on too."""
    analysis.taxonomy.loops.attempt[id(items[k])] = analysis.beyond_at(items, k, scope)


def defer_stop_set(
    analysis: Any,
    at: tuple[Sequence[IrItem], int],
    scope: Scope,
    notes: Notes,
    unexited: bool,
) -> None:
    """File the stop-set of item ``k`` (``at`` is ``(items, k)``) that neither
    two characters nor its run's end decide.

    With no exit in reach it runs longest. Otherwise it is deferred to the
    rule's longest take (``GrammarAnalysis._settle``), unless the loop meets a
    loopback: a character in its FIRST that only a repetition's next
    iteration takes after it (its soft continuation, less its structural one).
    A take that runs on through that character is not the rule's answer
    there, since the stop at it may be the carving that completes, and the
    longest take's span check cannot see past the rule. Such a stop-set reaches
    FOLLOW, and the rule islands.
    """
    items, k = at
    note = f"{scope.rule}[{k}]: loop stop-set applied"
    first = analysis.atom_first(items[k].atom)
    soft = analysis.cont_at(items, k, scope.tail)
    loopback = soft.subtract(
        analysis.structural_cont_at(items, k, scope.structural_tail)
    )
    if unexited and not first.overlaps(loopback):
        notes.picks_extent(f"{note} (runs longest)", STOP_SET)
        return
    if unexited:
        # A run with no exit in reach still meets a repetition's next iteration:
        # attempted, it stops there where the take cannot complete.
        notes.picks_extent(f"{scope.rule}[{k}]: loop iterations attempted", ATTEMPT)
        if ATTEMPT in notes.grants:
            analysis.taxonomy.loops.attempt[id(items[k])] = analysis.beyond_at(
                items, k, scope
            )
        return
    if first.overlaps(loopback) and _swallows_a_site(analysis, scope.rule, first):
        notes.hard.append(f"{scope.rule}[{k}]: loop stop-set meets a loopback")
        return
    notes.stop_sets.append(note)


def _swallows_a_site(analysis: Any, name: str, first: CharSet) -> bool:
    """Whether at some site rule ``name`` is followed at, every character that
    may follow it is one ``first`` takes: there the run swallows the site's
    closer whole, so the longest take always runs past its end and its span
    check asks the island every time. A rule that is only ever a whole arm is
    read at its rule's sites, the closer being theirs. A site the text may end
    at closes nothing."""
    windows = analysis.follows.windows(FOLLOW_LOOP_K)
    return any(
        site and all(chars and chars[0].within(first) for chars, _state in site)
        for site in _closing_sites(analysis, windows, name, set())
    )


def _closing_sites(analysis: Any, windows: Any, name: str, seen: set[str]) -> list:
    """The window sets of every site rule ``name`` is followed at, read through
    the rules it is a whole arm of where it is nothing else."""
    seen.add(name)
    owners = [
        rule
        for rule, body in analysis.rules.items()
        for arm in body.body
        if any(_names(item, name) for item in arm)
    ]
    whole = [
        rule
        for rule, body in analysis.rules.items()
        for arm in body.body
        if len(arm) == 1 and _names(arm[0], name) and arm[0].quantifier.upper() == 1
    ]
    if not owners or len(whole) != len(owners) or seen.intersection(whole):
        return windows.site_windows(name)
    return [
        site for rule in whole for site in _closing_sites(analysis, windows, rule, seen)
    ]


def _names(item: IrItem, name: str) -> bool:
    """Whether ``item`` references rule ``name``, exactly once."""
    return (
        isinstance(item.atom, IrRuleRef)
        and str(item.atom) == name
        and int(item.quantifier.lo) == 1
    )


def soft_gap_conflict(
    analysis: Any,
    items: Sequence[IrItem],
    k: int,
    scope: Scope,
    notes: Notes,
) -> None:
    """Classify a loop whose FIRST overlaps only soft followers."""
    gap = analysis.cont_at(items, k, scope.tail).subtract(
        analysis.hard_cont_at(items, k, scope.hard_tail)
    )
    first = analysis.atom_first(items[k].atom)
    if not first.overlaps(gap):
        return
    structural_gap = analysis.structural_cont_at(
        items, k, scope.structural_tail
    ).subtract(analysis.hard_cont_at(items, k, scope.hard_tail))
    if not first.overlaps(structural_gap):
        if not _iteration_meets_a_follower(analysis, items, k, first):
            notes.picks_extent(f"{scope.rule}[{k}]: loop greedy split", GREEDY_SPLIT)
            return
        notes.picks_extent(f"{scope.rule}[{k}]: loop iterations attempted", ATTEMPT)
        if ATTEMPT in notes.grants:
            license_attempt(analysis, items, k, scope)
        return
    if noise_greedy_licensed(analysis, items, k, scope):
        notes.picks_extent(
            f"{scope.rule}[{k}]: loop stop-set applied (noise-greedy)", NOISE_GREEDY
        )
        return
    if not demote_loop(analysis, items, k, scope, notes):
        notes.hard.append(f"{scope.rule}[{k}]: loop over-eats soft FOLLOW, not gatable")
        file_attempt_loop(analysis, items, k, scope, notes)


def _iteration_meets_a_follower(
    analysis: Any, items: Sequence[IrItem], k: int, first: CharSet
) -> bool:
    """Whether loop ``k``'s iteration can fail after its gate admitted it where
    an optional follower of another atom could have read the character.

    A greedy split commits each iteration on its first character, and a plain
    stop-set fails the arm on a later mismatch inside it. That is sound only
    where nothing after the loop could have started there: the loop's own
    next copy is the split, another item is not. A one-character atom's
    iteration cannot fail once admitted.
    """
    atom = items[k].atom
    if STOPSET_ATOM.resolve(atom).eval(analysis, atom, ()):
        return False
    for item in items[k + 1 :]:
        if item.atom != atom and first.overlaps(analysis.atom_first(item.atom)):
            return True
        if not analysis.item_nullable(item):
            return False
    return False


def attempt_spec(analysis: Any, arms: Sequence[Sequence[IrItem]]) -> AttemptSpec:
    """The ordered-attempt plan for one conflicted alternation.

    Authored arm order, nullable arms last: a nullable arm tried first
    succeeds vacuously and makes every later arm dead code (the same rule the
    PEG emitter applies to spell a faithful ordered choice). A pure function
    of the arm list, so a rule body and an inline group derive it identically
    and deterministically.
    """
    solid = tuple(i for i, arm in enumerate(arms) if not seq_nullable(analysis, arm))
    empty = tuple(i for i, arm in enumerate(arms) if seq_nullable(analysis, arm))
    return AttemptSpec(solid + empty)


def attempt_group(
    analysis: Any,
    arms: Sequence[Sequence[IrItem]],
    site: Site,
    notes: Notes,
    count: int,
) -> None:
    """License an inline group's undemotable overlap for ordered attempt.

    Rule bodies are excluded: their licence is ``_classify``'s, decided against
    the whole note ledger once every arm has been walked. A group's notes are
    raised mid-walk, so its licence is recorded here — and counted as
    ``covered``, the same channel an ungatable loop uses, which is what keeps
    ``_classify``'s "every hard note is settled" test true and the enclosing
    rule attemptable instead of islanded.

    :param count: How many hard notes this overlap raised — one per arm pair.
    """
    if isinstance(site.at, str):
        return
    analysis.taxonomy.store_group_attempt(
        site.at, (attempt_spec(analysis, arms), site.follow)
    )
    notes.covered += count


def sub_conflict(
    analysis: Any,
    items: Sequence[IrItem],
    k: int,
    scope: Scope,
    notes: Notes,
) -> None:
    """Dispatch one atom for undefined-ref and group-recursion checks."""
    item = items[k]
    atom = item.atom
    hi_value = item.quantifier.hi
    hi = None if isinstance(hi_value, IrNoneType) else int(hi_value)
    eff = analysis.cont_at(items, k, scope.tail)
    hard_eff = analysis.hard_cont_at(items, k, scope.hard_tail)
    structural_eff = analysis.structural_cont_at(items, k, scope.structural_tail)
    if hi is None or hi > 1:
        eff = eff.union(analysis.atom_first(atom))
    ctx = ConflictCtx(notes, Cont(eff, hard_eff, structural_eff), scope.rule, k)
    SEQ_ATOM.resolve(atom).eval(analysis, atom, (ctx,))


def text_only(rule: IrRule) -> bool:
    """Whether no rule reference appears anywhere in ``rule``'s body, inline
    groups included — its model is then its matched text."""
    return not has_reference(rule.body)


def may_steal(analysis: Any, rule: IrRule) -> bool:
    """Whether ``rule``'s text is matched item by item with nothing to say the
    match is right: a text-only rule with an arm of two items or more that
    :func:`greedy_exact` does not cover. Whether its own extent proof declines
    is the compiler's to ask. Withheld from a delegate's analysis, whose end is
    not the document's."""
    return (
        not analysis.taxonomy.delegated
        and text_only(rule)
        and any(len(arm) > 1 for arm in rule.body)
        and not greedy_exact(analysis, rule)
    )


def greedy_exact(analysis: Any, rule: IrRule) -> bool:
    """Whether a greedy left-to-right match of ``rule`` ends where its longest
    match does, so the match stands for the island's own longest completion.

    Every item is a literal or a class, the arms start apart so the first
    character picks one, and no loop but the last can take a character what
    follows it needs, unless what follows is one optional run that holds every
    character the loop can take. The runtime still checks the character after
    the match against the rule's EXTEND before it relies on it.

    Every arm holds two items or more: the runtime checks the span on the
    matcher's multi-item path, and a one-item arm takes the one-item path,
    which is left as it is.
    """
    arms = list(rule.body)
    if any(len(arm) < 2 for arm in arms):
        return False
    firsts = [{((analysis.seq_first(arm),), END)} for arm in arms]
    return separable(firsts) and all(_arm_greedy_exact(analysis, arm) for arm in arms)


def _arm_greedy_exact(analysis: Any, items: Sequence[IrItem]) -> bool:
    """One arm's half of :func:`greedy_exact`."""
    for j, item in enumerate(items):
        if not isinstance(item.atom, (IrLiteral, IrCharClass, IrNot)):
            return False
        if j + 1 == len(items) or item.quantifier.fixed():
            continue
        rest, first = items[j + 1 :], analysis.atom_first(item.atom)
        if not first.overlaps(analysis.seq_first(rest)):
            continue
        last = rest[-1]
        absorbs = (
            len(rest) == 1
            and int(last.quantifier.lo) == 0
            and not last.quantifier.fixed()
        )
        if not absorbs or not first.within(analysis.atom_first(last.atom)):
            return False
    return True


def same_ref_extent_split(
    rules: Mapping[str, IrRule], items: Sequence[IrItem], k: int
) -> bool:
    """Whether adjacent required refs need extent-aware splitting.

    A variable-width child followed by another required occurrence of the
    same rule cannot be cut by a one-character stop set: that assigns all
    shared FIRST text to the right child. The Earley island owns this cold
    structural case until the PDA has an extent-aware boundary primitive.
    """
    if k + 1 >= len(items):
        return False
    left, right = items[k], items[k + 1]
    if not isinstance(left.atom, IrRuleRef) or not isinstance(right.atom, IrRuleRef):
        return False
    if str(left.atom) != str(right.atom):
        return False
    if int(left.quantifier.lo) < 1 or int(right.quantifier.lo) < 1:
        return False
    prefixes = KWindowFirst(rules, 5).rule_prefixes(str(left.atom), 5)
    complete = [len(prefix) for prefix, state in prefixes if state == END]
    if not complete:
        return any(state == UNK for _prefix, state in prefixes)
    shortest = min(complete)
    return any(
        len(prefix) > shortest and state in (END, MORE) for prefix, state in prefixes
    )
