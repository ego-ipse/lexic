"""Clone-compiler intermediate specs — the NamedTuple vocabulary tests pin.

The flat, tuple-coded records :func:`~lexic.parsing.pda.compiler.clones.compile_pda`
produces before :func:`~lexic.parsing.pda.compiler.clones.flatten_program` lowers them
into the int-coded runtime :class:`~lexic.parsing.pda.compiler.program.flatten.PdaProgram`: the
clone/arm/item/group specs plus the loop gates (:class:`StopGate`,
:class:`PairGate`, :class:`KTupleGate`, :class:`PeekGate` — the folding-aware
:class:`~lexic.parsing.pda.core.scanner.ScanGate` completes the union), and the
clone key / island reference targets.

A leaf w.r.t. the compiler — pure data definitions, imported by
:mod:`lexic.parsing.pda.compiler.clones` (which re-exposes them as its public surface);
imports only :class:`~lexic.parsing.pda.core.charsets.CharSet`,
:class:`~lexic.parsing.product.RuleProduct`, and
:class:`~lexic.parsing.pda.core.scanner.ScanGate`.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import ArmGate, ScanGate
from lexic.parsing.product import RegularProof, RuleProduct

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
    "PairGate",
    "KTupleGate",
    "PeekGate",
    "ItemSpec",
    "ArmSpec",
    "GroupSpec",
    "CloneSpec",
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
    """

    name: str
    fail: bool = False


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


class PairGate(NamedTuple):
    """An LL(2) loop gate (pivot 6): take another iteration only when
    ``text[pos:pos+2]`` is a taken prefix (chess ``fxf5`` vs ``f5``).

    :ivar pairs: The 2-char prefixes that select "take another iteration".
    """

    pairs: frozenset[str]


class KTupleGate(NamedTuple):
    """A ``k``-window loop gate (P2): take another iteration iff
    ``text[pos:pos+k]`` EOF-exactly matches a ``taken`` window.

    The analysis-sourced generalisation of :class:`PairGate` past ``k = 2``
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
    gate: StopGate | AttemptGate | PairGate | KTupleGate | PeekGate | ScanGate


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
    :ivar product: The rule's authored :class:`~lexic.parsing.product
        .RuleProduct`, or ``None`` for a transparent helper clone — what the
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
    """

    name: str
    arms: tuple[ArmSpec, ...]
    default: tuple[ItemSpec, ...] | None
    product: RuleProduct | None
    match_only: bool
    struct_arm: ScanGate | None = None
    attempt_follow: CharSet | None = None
    consult: RegularProof | None = None
