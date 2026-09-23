"""Clone-compiler intermediate specs — the NamedTuple vocabulary tests pin.

The flat, tuple-coded records :func:`~lexic.parsing.pda.compiler.clones.compile_pda`
produces before :func:`~lexic.parsing.pda.compiler.clones.flatten_program` lowers them
into the int-coded runtime :class:`~lexic.parsing.pda.compiler.program.flatten.PdaProgram`: the
clone/arm/item/group specs plus the loop gates (:class:`StopGate`,
:class:`KTupleGate`, :class:`PeekGate` — the folding-aware
:class:`~lexic.parsing.pda.core.scanner.ScanGate` completes the union), and the
clone key / island reference targets.

Also the small arm helpers the compiler and its lowering both read — what an
arm's items ARE, an item's upper bound, whether two arms' FIRST sets collide.
They live here rather than in ``clones`` because a helper both halves use is
vocabulary, and a second reader had to duplicate one to avoid a private import.

A leaf w.r.t. the compiler — pure data definitions, imported by
:mod:`lexic.parsing.pda.compiler.clones` (which re-exposes them as its public surface);
imports only :class:`~lexic.parsing.pda.core.charsets.CharSet`,
:class:`~lexic.parsing.product.RuleRoutine`,
:class:`~lexic.parsing.pda.core.scanner.ScanGate`, and the
:data:`~lexic.parsing.pda.analysis.gates.windows.Pref` window type.
"""

from __future__ import annotations

from typing import NamedTuple, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrItem, IrNoneType, IrSelf
from lexic.parsing.pda.analysis.gates.windows import Pref
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import ArmGate, Pattern, ScanGate
from lexic.parsing.product import RegularProof, RuleRoutine

LIT, CC, REF, GRP = "lit", "cc", "ref", "grp"
"""The :attr:`ItemSpec.kind` tags: literal, char class, rule reference, group.

Here rather than in ``clones`` because the lowering reads them too, and a tag
shared by the compiler and its lowering belongs to the vocabulary between them."""

__all__ = [
    "CloneKey",
    "IslandRef",
    "ArmGates",
    "StopGate",
    "AttemptGate",
    "KTupleGate",
    "PeekGate",
    "ItemSpec",
    "ArmSpec",
    "GroupSpec",
    "CloneSpec",
    "LongestTake",
]


# ── clone keys and reference targets ──────────────────────────────────────


class CloneKey(NamedTuple):
    """A clone's identity — a rule compiled for one hard continuation.

    :ivar name: The rule name.
    :ivar tail: The hard continuation the clone's loop stop-sets are exact for.
    """

    name: str
    tail: CharSet


class IslandRef(NamedTuple):
    """A reference to an island rule — not cloned; parsed by Earley sub-parse.

    The ``ref`` :class:`ItemSpec` target for a rule in :attr:`PdaTables.islands`,
    resolved via :meth:`PdaTables.island_tables` rather than a clone.

    :ivar name: The island rule name.
    :ivar fail: When ``True``, a fail-island (a semantic F1 stop-set-escape
        rule) — the reference raises :class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaFail`
        (engine fallback) rather than risking a divergent longest-match parse.
    :ivar cont: What the ENCLOSING rule puts after this occurrence — the
        characters that could follow the island *here*, which the seam's
        two-ends check reads. Deliberately not the island rule's own FOLLOW:
        in ``expr ::= expr op term`` that FOLLOW contains ``op``'s FIRST,
        because the rule puts ``expr`` before ``op``, so a shorter end
        followed by ``+`` reads as the caller accepting it when it is the
        island continuing itself. Empty is *unknown*, which accepts plain
        longest-match, and is what the start-rule marker carries.
    :ivar exact: The island cannot derive ANY character of :attr:`cont`, so no
        completion of it reaches past the first one — the window is that
        distance and one sub-parse at it settles the island. False keeps the
        doubling climb, which is what an island whose own alphabet meets its
        continuation needs.
    :ivar windows: The same continuation a few characters deep, which the
        two-ends check asks only where :attr:`cont` admits the next character.
        Empty is no deeper evidence: one character decides.
    """

    name: str
    fail: bool = False
    cont: CharSet = CharSet.EMPTY
    exact: bool = False
    windows: tuple[Pref, ...] = ()


IslandPayload = tuple[str, CharSet, bool, tuple[Pref, ...]]
"""An island reference as the runtime reads it: ``(name, cont, exact,
windows)`` — :class:`IslandRef` without the fail flag, which the opcode says."""


class LongestTake(NamedTuple):
    """A text-only rule's clone for one continuation: its longest match, which
    answers for the rule's island unless the span holds a follower.

    The island takes the longest completion and refuses only where a shorter
    end is followed by a character this reference can continue with. A
    shorter end of a match lies before a character in EXTEND, so the match is
    the island's answer when no character of the span after its first is in
    :attr:`exits`, and the character after the match is outside
    :attr:`extend` (the match cannot be lengthened). Otherwise the runtime asks
    :attr:`island`, the question this reference's island would have asked.

    :ivar exits: This reference's followers the rule can extend over:
        its continuation ∩ EXTEND, the end of input left out.
    :ivar extend: The rule's EXTEND.
    :ivar island: The island reference ``(name, cont, exact, windows)``.
    :ivar lead: Where in the span a shorter end can first sit: ``0`` for a
        nullable rule, whose empty match is one, else ``1``.
    :ivar exit_at: :attr:`exits` as a one-character pattern, searched over the
        span from :attr:`lead` in one call.
    :ivar extends_at: :attr:`extend` as a one-character pattern, matched at the
        character after the span; ``None`` where every arm ends in an unbounded
        run over a class holding all of EXTEND, since the greedy run already
        stopped at a character outside it.
    """

    exits: CharSet
    extend: CharSet
    island: IslandPayload
    lead: int
    exit_at: Pattern
    extends_at: Pattern | None


# ── loop gates (pivot 4 / pivot 6) ────────────────────────────────────────


class StopGate(NamedTuple):
    """A non-greedy single-char loop gate (pivot 4): continue while the next
    char is in ``charset`` (``FIRST(atom) − hard-continuation``).

    :ivar charset: The chars that keep the loop going.
    """

    charset: CharSet


class AttemptGate(NamedTuple):
    """An attempt-licensed loop gate — the atom's full FIRST, as ADMISSION.

    Past the mandatory count, an admitted iteration is ATTEMPTED as a
    self-contained sub-run; a failure closes the loop at the current count
    instead of failing the arm. The loop thereby takes maximally subject to
    its iterations actually parsing — the split's defined answer (the first
    slot owns the text) — where a plain stop-set take would COMMIT on one
    character and fail the arm on a later mismatch.

    :ivar charset: The atom's FIRST — a pre-filter, never a commitment.
    :ivar follow: The decision's SOFT continuation. A boundary char in BOTH
        sets is an arm choice in loop clothing — a shorter extent may compose
        into a different-valued whole parse — so the runtime bails to the
        gated engine there instead of committing another iteration.
    """

    charset: CharSet
    follow: CharSet


class KTupleGate(NamedTuple):
    """A ``k``-window loop gate (P2): take another iteration iff
    ``text[pos:pos+k]`` EOF-exactly matches a ``taken`` window.

    The analysis-sourced 2-or-more-character window gate
    (:attr:`~lexic.parsing.pda.analysis.analysis.Taxonomy.loop_gates`, never
    recomputed) — chess ``nonpawn``, separable at ``k = 3`` via rule-FOLLOW.

    :ivar windows: The ``taken`` windows — ``≤k``-length CharSet tuples.
    """

    windows: tuple[tuple[CharSet, ...], ...]


class PeekGate(NamedTuple):
    """A P3 noise-skip loop gate: skip the maximal ``W`` run without consuming,
    take another iteration iff the first post-noise char is in ``take``.

    Analysis-sourced (:attr:`~lexic.parsing.pda.analysis.analysis.Taxonomy
    .pn_loop_gates`), never recomputed; the iteration re-parses the noise
    normally, so the peek is recognition-only and fail-soft.

    :ivar w: The skippable noise alphabet.
    :ivar take: The post-noise chars that select another iteration.
    """

    w: CharSet
    take: CharSet


# ── item and arm specs ────────────────────────────────────────────────────


class ItemSpec(NamedTuple):
    """One compiled arm item — flat, tuple-coded, production-named.

    :ivar kind: One of :data:`~lexic.parsing.pda.compiler.clones.ITEM_KINDS`.
    :ivar payload: The kind-specific body: the literal ``str`` (``lit``), the
        member :class:`CharSet` (``cc``), the resolved :class:`CloneKey` /
        :class:`IslandRef` target (``ref``), or the :class:`GroupSpec` (``grp``).
    :ivar lo: The quantifier lower bound (mandatory iterations).
    :ivar hi: The quantifier upper bound, or ``None`` (unbounded).
    :ivar gate: The loop gate consulted past the ``lo`` mandatory iterations.
    """

    kind: str
    payload: str | CharSet | CloneKey | IslandRef | GroupSpec
    lo: int
    hi: int | None
    gate: LoopGate


class GreedyGate(NamedTuple):
    """Exit the loop exactly where the leftmost chain does, and nowhere else.

    The split-greedy licence
    (:mod:`~lexic.parsing.pda.analysis.gates.greedy`) as the clone compiler
    carries it. No ``k`` separates the decision this settles and none has to:
    the loop runs greedily because the split rule does, so the only place it
    may stop is where the unit's tail and its certified continuation are all
    that remain.

    :ivar tail: ``m`` copies of the item's terminator.
    :ivar close: The continuation matched in full after the tail; ``""`` where
        the certified boundary is the end of the input.
    :ivar starters: What the continuation may BEGIN with, where those cannot
        begin an item; ``None`` where it is matched by spelling instead.
    """

    tail: str
    close: str
    starters: frozenset[str] | None

    @property
    def width(self) -> int:
        """Characters this gate reads: the tail plus the charged continuation."""
        return len(self.tail) + len(self.close) + 1


type LoopGate = StopGate | AttemptGate | KTupleGate | PeekGate | ScanGate | GreedyGate
"""Every gate a loop's take/skip decision can compile to."""


class ArmSpec(NamedTuple):
    """One FIRST-gated arm of a rule clone or inline group.

    :ivar first: The arm's FIRST char set — the runtime selects this arm when
        the lookahead char is a member.
    :ivar specs: The arm's item specs, in order.
    :ivar windows: The arm's k-window selection set (analysis-sourced —
        :attr:`~lexic.parsing.pda.analysis.analysis.Taxonomy.arm_gates`), or ``None``;
        every gated arm of a P2-demoted alternation carries its own set.
    :ivar peek: The arm's P3 noise-skip ``(W, post-noise chars)`` selector
        (analysis-sourced — :attr:`~lexic.parsing.pda.analysis.analysis.Taxonomy
        .pn_arm_gates`), or ``None``; every gated arm of a P3-demoted
        alternation carries one (same ``W``).
    :ivar attempt_window: The arm's FIRST\\ :sub:`k` admission windows on an
        ATTEMPT clone's arm, or ``None``. Purely an exclusion filter: a
        lookahead inconsistent with every window cannot begin this arm, so
        the trial sub-run (which would fail) is skipped — never a selector,
        so overlapping windows stay tried in order.
    """

    first: CharSet
    specs: tuple[ItemSpec, ...]
    windows: tuple[tuple[CharSet, ...], ...] | None = None
    peek: tuple[CharSet, CharSet] | None = None
    attempt_window: tuple[tuple[CharSet, ...], ...] | None = None


class ArmGates(NamedTuple):
    """The analysis-sourced arm-demotion specs for one alternation, bundled.

    An alternation's stored gate specs, read from the
    :class:`~lexic.parsing.pda.analysis.analysis.Taxonomy` and handed to
    :meth:`~lexic.parsing.pda.compiler.clones.PdaCompiler.compile_arms` together so the
    per-arm alignment stays inside one enumeration. A rule body reads them by
    name, an inline group by node identity; ``struct_arm`` is rule-body-only.

    :ivar windows: P2 k-window per-arm selection sets, or ``None``.
    :ivar peeks: P3 noise-skip ``(W, per-arm post-noise selectors)``, or ``None``.
    :ivar struct_arm: The empty-arm structured-noise :class:`ArmGate`, or ``None``.
    """

    windows: tuple[tuple[tuple[CharSet, ...], ...], ...] | None = None
    peeks: tuple[CharSet, tuple[CharSet, ...]] | None = None
    struct_arm: ArmGate | None = None


class GroupSpec(NamedTuple):
    """An inline ``(...)`` group's arm selection — the ``grp`` payload.

    :ivar arms: The gated arms — in ATTEMPT order when :attr:`attempt_follow`
        is set, authored order otherwise.
    :ivar default: The all-nullable default arm's specs, or ``None``.
    :ivar attempt_follow: The soft continuation at this group's item, when its
        overlap is settled by ordered attempt; ``None`` otherwise. Both the
        marker that the group attempts and the second-success gate the runtime
        audits against, exactly as :attr:`CloneSpec.attempt_follow` is.
    """

    arms: tuple[ArmSpec, ...]
    default: tuple[ItemSpec, ...] | None
    attempt_follow: CharSet | None = None


class CloneSpec(NamedTuple):
    """One rule compiled for one hard continuation — a clone body.

    :ivar name: The rule name this clone stands for.
    :ivar arms: The FIRST-gated arms (after arm hoisting every non-empty arm
        selects on its own FIRST).
    :ivar default: The all-nullable default arm's specs, or ``None``.
    :ivar routine: The rule's verified :class:`~lexic.parsing.product
        .RuleRoutine`, or ``None`` for a transparent helper clone — what the
        clone's capture layout and build plan are baked from.
    :ivar match_only: ``True`` for a rule whose value IS its own matched text
        — pure-terminal interior, the runtime slices ``text[a:b]`` instead of
        building below.
    :ivar struct_arm: The empty-arm structured-noise gate (a
        :class:`~lexic.parsing.pda.core.scanner.ScanGate`), or ``None``. When set, the
        runtime consults it before the FIRST-gated selection: a take admits the
        gated arms, a refusal selects the nullable :attr:`default` (escape) arm.
    :ivar attempt_follow: The rule's soft-FOLLOW :class:`CharSet` on an
        ATTEMPT clone, else ``None``. Non-``None`` marks the clone's arms as
        ordered attempts — :attr:`arms` is stored already in attempt order
        (nullable arms last), FIRSTs may overlap, and the runtime tries arms
        with rollback instead of selecting one; the follow set is the
        cross-span composition evidence its second-success audit reads.
    :ivar consult: The authoritative regular proof for a :attr:`match_only`
        rule whose whole extent one recognizer can decide, else ``None``.
        Proved against the rule's OWN continuation rather than a widest
        follow, because a consult that could run past its terminator would
        answer a different question than the per-character program it
        replaces.
    :ivar longest: The rule's longest-take plan (:class:`LongestTake`), else
        ``None``.
    """

    name: str
    arms: tuple[ArmSpec, ...]
    default: tuple[ItemSpec, ...] | None
    routine: RuleRoutine | None
    match_only: bool
    struct_arm: ScanGate | None = None
    attempt_follow: CharSet | None = None
    consult: RegularProof | None = None
    longest: LongestTake | None = None


# ── arm helpers ────────────────────────────────────────────────────────────


def arm_items(seq: Sequence[IrSelf]) -> list[IrItem]:
    """The :class:`IrItem` members of a sequence arm, in order."""
    return [i for i in seq if isinstance(i, IrItem)]


def upper_bound(item: IrItem) -> int | None:
    """The item's quantifier upper bound as an ``int``, or ``None`` (unbounded)."""
    hi = item.quantifier.hi
    return None if isinstance(hi, IrNoneType) else int(hi)


def firsts_overlap(arms: Sequence[ArmSpec]) -> bool:
    """Whether any two gated arms' FIRST sets overlap (the drift tripwire)."""
    return any(
        arms[i].first.overlaps(arms[j].first)
        for i in range(len(arms))
        for j in range(i + 1, len(arms))
    )


def resolve_struct_arm(
    struct_arm: ArmGate | None, default_idx: int | None
) -> ScanGate | None:
    """The empty-arm gate's :class:`ScanGate`, validated against the default arm.

    :param struct_arm: The stored :class:`~lexic.parsing.pda.core.scanner.ArmGate`, or
        ``None``.
    :param default_idx: The body index of the nullable default arm the compiler
        picked, or ``None`` when no arm is all-nullable.
    :returns: The gate's :class:`ScanGate` (its escape aligned to ``default_idx``),
        or ``None`` when no gate is stored.
    :raises UnsupportedConstructError: When the gate's escape index does not
        match ``default_idx`` (analysis/compiler drift).
    """
    if struct_arm is None:
        return None
    if default_idx != struct_arm.escape:
        raise UnsupportedConstructError(
            "pda: structured arm gate escape does not match the nullable default arm"
        )
    return struct_arm.gate
