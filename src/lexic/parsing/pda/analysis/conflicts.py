"""Late conflict classifiers shared by the PDA grammar analysis."""

# This module is the split implementation half of GrammarAnalysis.
# pylint: disable=protected-access

from __future__ import annotations

from typing import Any, Sequence

from lexic.ir import IrItem, IrNoneType
from lexic.parsing.pda.analysis.cursors import ConflictCtx, Cont, Notes, Scope, Site
from lexic.parsing.pda.analysis.gates.noise import noise_greedy_licensed
from lexic.parsing.pda.analysis.predicates import SEQ_ATOM, seq_nullable
from lexic.parsing.pda.analysis.taxonomy import AttemptSpec


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
        notes.soft.append(f"{scope.rule}[{k}]: loop greedy split")
        return
    if noise_greedy_licensed(analysis, items, k, scope):
        notes.soft.append(f"{scope.rule}[{k}]: loop stop-set applied (noise-greedy)")
        return
    if not analysis._demote_loop(items, k, scope, notes):
        notes.hard.append(f"{scope.rule}[{k}]: loop over-eats soft FOLLOW, not gatable")
        analysis.taxonomy.attempt_loops[id(items[k])] = analysis.beyond_at(
            items, k, scope
        )
        notes.covered += 1


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
