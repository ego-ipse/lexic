"""Late conflict classifiers shared by the PDA grammar analysis."""

# This module is the split implementation half of GrammarAnalysis.
# pylint: disable=protected-access

from __future__ import annotations

from typing import Any, Sequence

from lexic.ir import IrItem, IrNoneType
from lexic.parsing.pda.analysis.cursors import ConflictCtx, Cont, Notes, Scope
from lexic.parsing.pda.analysis.gates.noise import noise_greedy_licensed
from lexic.parsing.pda.analysis.predicates import SEQ_ATOM


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
