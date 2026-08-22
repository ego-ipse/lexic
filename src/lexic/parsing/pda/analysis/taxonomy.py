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


Windows = tuple[tuple[tuple[CharSet, ...], ...], ...]
"""One alternation's per-arm k-window selection sets, in arm order."""

Peek = tuple[CharSet, tuple[CharSet, ...]]
"""One alternation's P3 noise-skip gate — ``(W, per-arm post-noise selectors)``."""

GroupGate = tuple[Windows | None, Peek | None]
"""An inline group's demotion, both families in one entry. The cascade stops at
the first licence that fires, so exactly one half is ever set — keeping them
together is what lets one node key address the whole decision."""


class _GateStore(IrLeaf[IrSelf, IrSelf]):
    """The seven gate-spec families, one slot each — :class:`Taxonomy`'s store.

    An arm decision is filed under a rule NAME when the alternation is a rule
    body and under the alternation node's ``id()`` when it is an inline group
    — two key spaces, because a group has no name and two groups in one rule
    share a label that would collide.

    :ivar arm: Rule name → per-arm k-window sets (P2).
    :ivar loop: ``id(item)`` → the ``taken`` k-window set (P2).
    :ivar pn_arm: Rule name → ``(W, per-arm post-noise selectors)`` (P3).
    :ivar pn_loop: ``id(item)`` → ``(W, take set)`` (P3).
    :ivar grp_arm: ``id(group)`` → an inline group's :data:`GroupGate` — the
        P2 and P3 families in one entry, since one node key addresses both.
    :ivar struct_loop: ``id(item)`` → a folding-aware ScanGate (P3/P5).
    :ivar struct_arm: Rule name → a folding-aware :class:`ArmGate` (empty-arm
        structured-noise / probe demotion, P3/P5).
    """

    __slots__ = (
        "arm",
        "loop",
        "pn_arm",
        "pn_loop",
        "grp_arm",
        "struct_loop",
        "struct_arm",
    )

    arm: dict[str, Windows]
    loop: dict[int, tuple[tuple[CharSet, ...], ...]]
    pn_arm: dict[str, Peek]
    pn_loop: dict[int, tuple[CharSet, CharSet]]
    grp_arm: dict[int, GroupGate]
    struct_loop: dict[int, ScanGate]
    struct_arm: dict[str, ArmGate]

    def __init__(self) -> None:
        """Seed every gate family empty."""
        self.arm = {}
        self.loop = {}
        self.pn_arm = {}
        self.pn_loop = {}
        self.grp_arm = {}
        self.struct_loop = {}
        self.struct_arm = {}


class Taxonomy(IrLeaf[IrSelf, IrSelf]):
    """The classified per-rule notes + gate specs — the taxonomy result.

    Also the **gate-spec channel** (Task 6.3 part c, option a): when P2 demotion
    is on, the k-window gates the classification consulted are *stored* here —
    single source of truth — and the clone compiler reads them back instead of
    recomputing (which would risk a divergent second derivation). The seven gate
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
        tree) → the decision's SOFT continuation. Greedy attempted take is
        Earley's split answer (the first slot owns the text) — EXCEPT at a
        boundary whose char is viable both as another iteration and as the
        continuation: there a shorter extent may compose into a
        different-valued whole parse, which is an arm choice in loop
        clothing, so the runtime bails to the gated engine instead of
        committing. The stored set is that check's evidence.
    :ivar gates: The :class:`_GateStore` behind the per-family accessors.
    """

    __slots__ = ("conflicts", "demoted", "fail", "attempts", "attempt_loops", "gates")

    conflicts: dict[str, list[str]]
    demoted: dict[str, list[str]]
    fail: set[str]
    attempts: dict[str, AttemptSpec]
    attempt_loops: dict[int, CharSet]
    gates: _GateStore

    def __init__(self) -> None:
        """Seed the note maps, the fail-island set and the gate store empty."""
        self.conflicts = {}
        self.demoted = {}
        self.fail = set()
        self.attempts = {}
        self.attempt_loops = {}
        self.gates = _GateStore()

    @property
    def arm_gates(self) -> dict[str, Windows]:
        """Rule name → per-arm k-window sets (aligned to the rule body's arms)
        for a demoted rule-body arm selection. An inline group's demotion is
        keyed by node identity instead — :attr:`grp_arm_gates`."""
        return self.gates.arm

    @property
    def grp_arm_gates(self) -> dict[int, GroupGate]:
        """``id(group)`` → a demoted INLINE GROUP's ``(windows, peek)`` pair.

        The group twin of :attr:`arm_gates` / :attr:`pn_arm_gates`, keyed like
        :attr:`loop_gates` because a group has no name. It exists because
        ``@lexical`` inlining relocates a rule body's alternation into a group:
        without it, the very decision the k-window settles one level up becomes
        a hard note and the enclosing rule islands.
        """
        return self.gates.grp_arm

    @property
    def loop_gates(self) -> dict[int, tuple[tuple[CharSet, ...], ...]]:
        """``id(item)`` (the looping :class:`~lexic.ir.grammar.nodes.IrItem` node —
        analysis and clone compiler walk the same lifted tree, so node identity
        is the exact decision key) → the ``taken`` k-window set for a demoted
        loop take/skip decision."""
        return self.gates.loop

    @property
    def pn_arm_gates(self) -> dict[str, Peek]:
        """Rule name → ``(W, per-arm post-noise selectors)`` for a P3 noise-skip
        rule-body arm demotion (aligned like :attr:`arm_gates`)."""
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

    def store_arm_windows(self, at: str | int, windows: Windows) -> None:
        """File a demoted arm selection's per-arm k-window sets.

        ``at`` is the alternation's key in whichever space it belongs to — a
        rule name for a body, the node's ``id()`` for an inline group.

        :raises UnsupportedConstructError: When a group node already carries a
            *different* spec. ``@lexical`` inlining splices one body into
            several sites, so one node CAN stand at two decision points with
            distinct continuations, which the identity key cannot express; a
            confident-wrong gate would be silent, so the grammar opts out.
        """
        if isinstance(at, str):
            self.gates.arm[at] = windows
            return
        self._store_group_gate(at, (windows, None))

    def store_arm_peek(self, at: str | int, peek: Peek) -> None:
        """File a demoted arm selection's P3 noise-skip gate.

        Keyed and tripwired exactly like :meth:`store_arm_windows`.

        :raises UnsupportedConstructError: When a group node already carries a
            different spec.
        """
        if isinstance(at, str):
            self.gates.pn_arm[at] = peek
            return
        self._store_group_gate(at, (None, peek))

    def _store_group_gate(self, at: int, gate: GroupGate) -> None:
        """File one group node's demotion, refusing a conflicting re-store."""
        prior = self.gates.grp_arm.get(at)
        if prior is not None and prior != gate:
            raise UnsupportedConstructError(
                "pda analysis: conflicting group arm gates for one alternation node"
            )
        self.gates.grp_arm[at] = gate

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
