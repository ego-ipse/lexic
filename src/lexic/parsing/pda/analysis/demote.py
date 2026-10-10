"""The demotion cascade — what a conflicted decision may be demoted TO.

`GrammarAnalysis` classifies a decision point and, where it conflicts, asks here
whether some gate can settle it after all. Each function returns ``True`` when
it filed a spec in the taxonomy and left a soft note, ``False`` when the
decision stays an island.

The loop cascade runs in a deliberate order: the k-window first (P2), then the
noise-skip peek (P3), then the folding-aware structured gate (P3/P5), then the
FOLLOW-window gate, and last the split-greedy licence — which is last because it
answers a DIFFERENT question. The first four ask whether the decision SEPARATES;
the licence asks whether the split rule already settles it, and a loop any of
them can decide never reaches it.

The FOLLOW-window gate is last among the separability tiers because it is the
only one that builds a whole-grammar fixpoint: it runs once every cheaper
question has been asked and declined.

Taken as a module because these are the analysis' demotions rather than its
classification, and because `conflicts` already reached across for one of them:
a shed helper becomes a PUBLIC name in its new home.
"""

from __future__ import annotations

from typing import Any, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrItem
from lexic.parsing.earley.kernel.tables.decider import SCAN_SKIP, SPLIT_GREEDY
from lexic.parsing.pda.analysis.cursors import Notes, Scope, Site
from lexic.parsing.pda.analysis.gates import kwindow
from lexic.parsing.pda.analysis.gates.greedy import greedy_loop_gate
from lexic.parsing.pda.analysis.gates.noise import (
    noise_alphabet,
    peek_arm_gate,
    peek_loop_gate,
)
from lexic.parsing.pda.analysis.gates.structured import (
    structured_arm_gate,
    structured_loop_gate,
)
from lexic.parsing.pda.analysis.gates.windows import windows_of
from lexic.parsing.pda.core.charsets import CharSet


def store_loop_gate(
    analysis: Any, item: IrItem, spec: tuple[tuple[CharSet, ...], ...]
) -> None:
    """File a demoted loop's ``taken`` windows under the item node's identity.

    :raises UnsupportedConstructError: If the same node already carries a
        *different* spec — a shared node at two decision sites with distinct
        FOLLOWs, which the identity key cannot express (a confident-wrong
        gate would be silent, so the whole grammar opts out instead).
    """
    key = id(item)
    prior = analysis.taxonomy.loop_gates.get(key)
    if prior is not None and prior != spec:
        raise UnsupportedConstructError(
            "pda analysis: conflicting k-window loop gates for one item node"
        )
    analysis.taxonomy.loop_gates[key] = spec


def demote_arms(
    analysis: Any,
    arms: list[Sequence[IrItem]],
    site: Site,
    notes: Notes,
) -> bool:
    """The arm-overlap demotion cascade — P2 k-window, then the P3
    noise-skip peek — storing the winning gate spec in its taxonomy
    channel plus the soft note. ``False`` ⇒ the overlap stays hard.

    Serves a rule body and an inline group alike: the cascade reads only
    the arms and the continuation, so ``site`` is the only thing that
    differs between them.
    """
    gate = kwindow.arm_gate(arms, kwindow.follow_depths(analysis.rules, site.follow))
    if gate is not None:
        analysis.taxonomy.store_arm_windows(site.at, kwindow.arm_windows(gate))
        notes.soft.append(f"{site.label}: arms k-window separable (demoted)")
        return True
    w = noise_alphabet(analysis)
    peek = peek_arm_gate(analysis, arms, w)
    if peek is not None:
        analysis.taxonomy.store_arm_peek(site.at, (w, peek))
        notes.soft.append(f"{site.label}: arms noise-skip separable (demoted)")
        return True
    return False


def demote_follow_windows(
    analysis: Any, arms: Sequence[Sequence[IrItem]], label: str, notes: Notes
) -> bool:
    """Empty-arm FOLLOW\\ :sub:`k` demotion: the arm gate asked at the rule's
    FOLLOW\\ :sub:`k` windows (:func:`kwindow.window_depths`); store the
    separating per-arm windows (body-arm order) in :attr:`Taxonomy.arm_gates` +
    the soft note; ``False`` ⇒ no licence."""
    depths = kwindow.window_depths(analysis.follows.windows, label)
    gate = kwindow.arm_gate(arms, depths)
    if gate is None:
        return False
    analysis.taxonomy.arm_gates[label] = kwindow.arm_windows(gate)
    notes.soft.append(f"{label}: arms FOLLOW-window separable (demoted)")
    return True


def demote_struct_arm(
    analysis: Any, arms: Sequence[Sequence[IrItem]], label: str, notes: Notes
) -> bool:
    """The empty-arm structured-noise demotion: store the scan gate + escape
    arm index in its taxonomy channel plus the soft note. ``False`` ⇒ no
    licence (the caller keeps today's greedy behavior).

    Every such gate skips its run possessively (``SG_SCAN``, ``SG_PROBE``), so
    it is withheld where the parse's decider does not grant :data:`SCAN_SKIP`."""
    if SCAN_SKIP not in notes.grants:
        return False
    gate = structured_arm_gate(analysis, list(arms), label)
    if gate is None:
        return False
    analysis.taxonomy.store_struct_arm(label, gate)
    notes.soft.append(f"{label}: empty-arm structured-noise (demoted)")
    return True


def demote_loop(
    analysis: Any, items: Sequence[IrItem], k: int, scope: Scope, notes: Notes
) -> bool:
    """The loop take/skip demotion cascade, storing the winning spec under the
    item node's identity plus the soft note. ``False`` ⇒ the decision stays an
    island note.

    Two halves, and the order between them is the point: every tier that asks
    whether the decision SEPARATES runs first, and only then the split-greedy
    licence, which asks whether the split rule already settles it.
    """
    if _separable_loop(analysis, items, k, scope, notes):
        return True
    # The split-greedy licence, last because it answers a DIFFERENT question
    # from the separability tiers: they ask whether the decision separates,
    # and this one asks whether the SPLIT RULE settles it. A loop any of them
    # can decide never reaches here.
    #
    # Withheld inside a delegate. Its condition (e) is about where the
    # INPUT ends, and an island interior runs over a doubling window whose
    # end is an artefact of the window rather than of the document
    # (`runtime/kernel/execution.py::_delegate_run`). The window-edge
    # decline would catch the consequence, but a licence that is not
    # certified against the boundary it will be executed against should not
    # be issued in the first place.
    #
    # Withheld too where the parse's decider does not grant it: the split rule
    # it reproduces is leftmost-longest's, proven for that order alone.
    if analysis.taxonomy.delegated or SPLIT_GREEDY not in notes.grants:
        return False
    greedy = greedy_loop_gate(analysis.rules, analysis.start, scope.rule, items, k)
    if greedy is not None:
        analysis.taxonomy.store_ready_loop(id(items[k]), greedy)
        notes.picks_extent(
            f"{scope.rule}[{k}]: loop split-greedy (demoted)", SPLIT_GREEDY
        )
        return True
    return False


def _separable_loop(
    analysis: Any, items: Sequence[IrItem], k: int, scope: Scope, notes: Notes
) -> bool:
    """The tiers that ask whether the loop's take/skip decision SEPARATES.

    In cost order: the P2 k-window, the P3 noise-skip peek, the folding-aware
    structured gate, and last the FOLLOW-window gate — last because it is the
    only one that builds a whole-grammar fixpoint.
    """
    gate = kwindow.loop_gate(
        items, k, kwindow.follow_depths(analysis.rules, scope.tail)
    )
    if gate is not None:
        store_loop_gate(analysis, items[k], windows_of(gate[1]))
        notes.soft.append(f"{scope.rule}[{k}]: loop k-window (demoted)")
        return True
    w = noise_alphabet(analysis)
    take = peek_loop_gate(analysis, items, k, analysis.cont_at(items, k, scope.tail), w)
    if take is not None:
        key = id(items[k])
        prior = analysis.taxonomy.pn_loop_gates.get(key)
        if prior is not None and prior != (w, take):
            raise UnsupportedConstructError(
                "pda analysis: conflicting noise-skip loop gates for one item node"
            )
        analysis.taxonomy.pn_loop_gates[key] = (w, take)
        notes.soft.append(f"{scope.rule}[{k}]: loop noise-skip (demoted)")
        return True
    struct = structured_loop_gate(analysis, items, k, scope, SCAN_SKIP in notes.grants)
    if struct is not None:
        analysis.taxonomy.store_ready_loop(id(items[k]), struct)
        notes.soft.append(f"{scope.rule}[{k}]: loop structured-noise (demoted)")
        return True
    # The last SEPARABILITY tier, and the reason it is last among them: it is
    # the only one that builds a whole-grammar fixpoint, so it runs once every
    # cheaper question has been asked and declined. It reaches what the others
    # structurally cannot — an arm-final loop, whose skip side `loop_gate` can
    # only see one character of.
    depths = kwindow.arm_final_loop_depths(
        analysis.rules, analysis.follows.windows, items, k, scope.rule
    )
    deep = None if depths is None else kwindow.loop_gate(items, k, depths)
    if deep is None:
        return False
    store_loop_gate(analysis, items[k], windows_of(deep[1]))
    notes.soft.append(f"{scope.rule}[{k}]: loop FOLLOW-window (demoted)")
    return True
