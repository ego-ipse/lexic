"""Taxonomy — the analysis' classified-notes + gate-spec result record.

Moved out of ``analysis.py`` by pure motion (C0302 headroom, Task 6.6). A leaf
w.r.t. the analysis: imports only :mod:`~lexic.parsing.pda.core.charsets` and
:mod:`~lexic.parsing.pda.core.scanner`; :class:`~lexic.parsing.pda.analysis.analysis.
GrammarAnalysis` owns the instance and re-exports the class.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrLeaf, IrSelf
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import ArmGate, ScanGate

__all__ = ["AttemptSpec", "Taxonomy"]


class AttemptSpec(NamedTuple):
    """One conflicted rule's ordered-attempt plan — the third gate class.

    Between k-window demotion (bounded lookahead decides) and islanding
    (Earley decides), an attemptable rule's arms are TRIED in this order with
    rollback; a second success is the ambiguity gate's question, asked at the
    decision point itself.

    :ivar order: Body-arm indices in attempt order — authored order with
        nullable arms last (a nullable arm tried first succeeds vacuously and
        makes every later arm dead).
    """

    order: tuple[int, ...]


def _spec_key(gate: ScanGate) -> tuple:
    """A :class:`ScanGate`'s stable identity — its spec fields, sans the
    recognizer object (built fresh per call, so identity-unstable). The
    conflicting-re-store tripwire compares these, not the whole gate."""
    return (gate.kind, gate.roots, gate.take, gate.probe)


def _arm_spec_key(arm: ArmGate) -> tuple:
    """An :class:`ArmGate`'s stable identity — its scan gate's spec plus the
    escape arm index; the conflicting-re-store tripwire compares these."""
    return (_spec_key(arm.gate), arm.escape)


class _GateStore(IrLeaf[IrSelf, IrSelf]):
    """The six gate-spec families, one slot each — :class:`Taxonomy`'s store.

    :ivar arm: Rule name → per-arm k-window sets (P2).
    :ivar loop: ``id(item)`` → the ``taken`` k-window set (P2).
    :ivar pn_arm: Rule name → ``(W, per-arm post-noise selectors)`` (P3).
    :ivar pn_loop: ``id(item)`` → ``(W, take set)`` (P3).
    :ivar struct_loop: ``id(item)`` → a folding-aware ScanGate (P3/P5).
    :ivar struct_arm: Rule name → a folding-aware :class:`ArmGate` (empty-arm
        structured-noise / probe demotion, P3/P5).
    """

    __slots__ = ("arm", "loop", "pn_arm", "pn_loop", "struct_loop", "struct_arm")

    arm: dict[str, tuple[tuple[tuple[CharSet, ...], ...], ...]]
    loop: dict[int, tuple[tuple[CharSet, ...], ...]]
    pn_arm: dict[str, tuple[CharSet, tuple[CharSet, ...]]]
    pn_loop: dict[int, tuple[CharSet, CharSet]]
    struct_loop: dict[int, ScanGate]
    struct_arm: dict[str, ArmGate]

    def __init__(self) -> None:
        """Seed every gate family empty."""
        self.arm = {}
        self.loop = {}
        self.pn_arm = {}
        self.pn_loop = {}
        self.struct_loop = {}
        self.struct_arm = {}


class Taxonomy(IrLeaf[IrSelf, IrSelf]):
    """The classified per-rule notes + gate specs — the taxonomy result.

    Also the **gate-spec channel** (Task 6.3 part c, option a): when P2 demotion
    is on, the k-window gates the classification consulted are *stored* here —
    single source of truth — and the clone compiler reads them back instead of
    recomputing (which would risk a divergent second derivation). The six gate
    families live on one :class:`_GateStore`; the named accessors below are the
    public channel.

    :ivar conflicts: Rule name → island-worthy notes (presence marks an island).
    :ivar demoted: Rule name → stop-set / LL(2) demotion notes.
    :ivar fail: The fail-island rule names — semantic rules that fired the F1
        stop-set-escape branch (a subset of :attr:`conflicts`' keys).
    :ivar attempts: Conflicted-but-attemptable rule name → its
        :class:`AttemptSpec`. A subset of :attr:`conflicts`' keys: rules whose
        EVERY island-worthy note an attempt can settle — a body-arm FIRST
        overlap (ordered attempt + the second-success gate) or an ungatable
        loop (greedy take + rollback; a loop extent is a SPLIT with a defined
        answer, so no gate). Never left-recursive rules (no arm order helps
        re-entry at the same position) and never fail islands.
    :ivar attempt_loops: ``id(item)`` of every ungatable-loop decision an
        attempt licence covers (the identity-key convention of
        :attr:`loop_gates` — analysis and clone compiler walk the same lifted
        tree). Greedy take with rollback IS Earley's split answer (the first
        slot owns the text), so membership is the whole spec.
    :ivar gates: The :class:`_GateStore` behind the per-family accessors.
    """

    __slots__ = ("conflicts", "demoted", "fail", "attempts", "attempt_loops", "gates")

    conflicts: dict[str, list[str]]
    demoted: dict[str, list[str]]
    fail: set[str]
    attempts: dict[str, AttemptSpec]
    attempt_loops: set[int]
    gates: _GateStore

    def __init__(self) -> None:
        """Seed the note maps, the fail-island set and the gate store empty."""
        self.conflicts = {}
        self.demoted = {}
        self.fail = set()
        self.attempts = {}
        self.attempt_loops = set()
        self.gates = _GateStore()

    @property
    def arm_gates(self) -> dict[str, tuple[tuple[tuple[CharSet, ...], ...], ...]]:
        """Rule name → per-arm k-window sets (aligned to the rule body's arms)
        for a demoted rule-body arm selection. Rule bodies only — an inline
        group's arm overlap stays a hard note (the rule islands)."""
        return self.gates.arm

    @property
    def loop_gates(self) -> dict[int, tuple[tuple[CharSet, ...], ...]]:
        """``id(item)`` (the looping :class:`~lexic.ir.grammar.nodes.IrItem` node —
        analysis and clone compiler walk the same lifted tree, so node identity
        is the exact decision key) → the ``taken`` k-window set for a demoted
        loop take/skip decision."""
        return self.gates.loop

    @property
    def pn_arm_gates(self) -> dict[str, tuple[CharSet, tuple[CharSet, ...]]]:
        """Rule name → ``(W, per-arm post-noise selectors)`` for a P3 noise-skip
        arm demotion (rule bodies only, aligned like :attr:`arm_gates`)."""
        return self.gates.pn_arm

    @property
    def pn_loop_gates(self) -> dict[int, tuple[CharSet, CharSet]]:
        """``id(item)`` → ``(W, take set)`` for a P3 noise-skip loop demotion."""
        return self.gates.pn_loop

    @property
    def struct_loop_gates(self) -> dict[int, ScanGate]:
        """``id(item)`` → the folding-aware
        :class:`~lexic.parsing.pda.core.scanner.ScanGate` for a P3 *structured*
        noise-skip (comment-bearing / LWS folding) or P5 rulename-probe loop
        demotion — the runtime-ready gate the clone compiler stores and returns
        verbatim (Task 6.6)."""
        return self.gates.struct_loop

    @property
    def struct_arm_gates(self) -> dict[str, ArmGate]:
        """Rule name → the folding-aware
        :class:`~lexic.parsing.pda.core.scanner.ArmGate` for an empty-arm alternation
        demoted by structured noise-skip / rulename-probe — the scan gate plus
        the escape arm index, stored verbatim for the clone compiler. Rule
        bodies only (the store key is the rule name); an inline group's empty
        arm stays a hard note (the rule islands)."""
        return self.gates.struct_arm

    def store_struct_loop(self, key: int, gate: ScanGate) -> None:
        """File a structured loop gate under the looping item node's identity.

        :raises UnsupportedConstructError: If the node already carries a
            *different* spec — a shared node at two decision sites with
            distinct FOLLOWs, which the identity key cannot express (a
            confident-wrong gate would be silent, so the whole grammar opts
            out instead).
        """
        prior = self.gates.struct_loop.get(key)
        if prior is not None and _spec_key(prior) != _spec_key(gate):
            raise UnsupportedConstructError(
                "pda analysis: conflicting structured loop gates for one item node"
            )
        self.gates.struct_loop[key] = gate

    def store_struct_arm(self, name: str, gate: ArmGate) -> None:
        """File a structured empty-arm gate under its enclosing rule name.

        :raises UnsupportedConstructError: If the rule already carries a
            *different* spec — the identity key (rule name) cannot express two
            distinct arm decisions for one rule, so the whole grammar opts out
            rather than carry a confident-wrong gate.
        """
        prior = self.gates.struct_arm.get(name)
        if prior is not None and _arm_spec_key(prior) != _arm_spec_key(gate):
            raise UnsupportedConstructError(
                "pda analysis: conflicting structured arm gates for one rule"
            )
        self.gates.struct_arm[name] = gate
