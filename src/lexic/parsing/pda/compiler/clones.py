"""Clone compiler — the predictive-parser artifact beside :class:`ParserTables`.

:func:`compile_pda` turns a *lifted codegen grammar*
(``lift_optional_nullables(build_codegen_grammar(canonical))`` — the shape
:class:`~lexic.parsing.pda.analysis.analysis.GrammarAnalysis` runs on) into
:class:`PdaTables`: the per-(rule, hard-continuation) **clones** the runtime
walks, plus the island set and a lazy per-island :class:`ParserTables` cache
for the conflicted rules that fall back to Earley sub-parses.

**Clones (pivot 3).** A rule is compiled once per distinct *hard continuation*
that reaches it (its loop stop-sets are call-site-exact, pivot 4).
:meth:`PdaCompiler.ensure_rule` reserves the clone key with a :data:`_PENDING`
placeholder before compiling, so recursion resolves to the in-progress key and
a repeat ``(name, tail)`` reuses the clone. Island rules are never cloned — a
reference carries an :class:`IslandRef` (a ``fail`` one raises
:class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaFail`, forcing the engine fallback).

**Item specs.** Each item compiles to a flat :class:`ItemSpec`
(``lit``/``cc``/``ref``/``grp``) with its bounds and a loop gate —
:class:`StopGate` (pivot 4), :class:`PairGate` (pivot 6), :class:`KTupleGate`
(P2), :class:`PeekGate` (P3 char-set) or :class:`ScanGate` (P3 structured
noise-skip / P5 probe, folding-aware via :mod:`~lexic.parsing.pda.core.scanner`).
Arm selection is FIRST-gated :class:`ArmSpec` plus at most one nullable default.
Every rule clone carries its :class:`~lexic.parsing.product.RuleProduct`; a
clone whose value IS its own matched text is :attr:`~CloneSpec.match_only`
(the runtime slices ``text[a:b]`` instead of building below).

**Open dispatch.** Per-atom compilation routes through the module-level
:data:`_ATOM_SPEC` :class:`~lexic.ir.action.mapping.IrTypeMap` (the ``analysis.py``
idiom — compiler on ``d``, per-item context on ``nc`` via :class:`_ItemCtx`);
an unregistered atom raises :exc:`~lexic.exceptions.UnsupportedConstructError`
(the Task-6 "no PDA" seam).

The spec NamedTuples are the compiler's *intermediate* (the shape tests pin);
:func:`flatten_program` lowers them once into the flat int-coded
:class:`PdaProgram` the :class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel` walks. The
two stay in lockstep on :class:`PdaTables` (``.clones`` for introspection,
``.program`` for the hot loop).
"""

from __future__ import annotations

from typing import Mapping, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAction,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLambda,
    IrLeaf,
    IrLiteral,
    IrNoneType,
    IrNot,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
)
from lexic.parsing.binding import ModelBinding
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.gates.windows import KWindowFirst, windows_of
from lexic.parsing.pda.compiler.delegate_compile import DelegateSource
from lexic.parsing.pda.compiler.program.flatten import (
    PdaProgram,
)
from lexic.parsing.pda.compiler.program.lower import flatten_clones
from lexic.parsing.pda.compiler.specs import (
    CC,
    GRP,
    LIT,
    REF,
    ArmGates,
    ArmSpec,
    AttemptGate,
    CloneKey,
    CloneSpec,
    GroupSpec,
    IslandRef,
    ItemSpec,
    KTupleGate,
    PairGate,
    PeekGate,
    StopGate,
)
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import ArmGate, ScanGate
from lexic.parsing.product import ConstructionTables, RuleProduct, construction_of

__all__ = [
    "compile_pda",
    "PdaTables",
    "PdaProgram",
    "CloneSpec",
    "CloneKey",
    "IslandRef",
    "ItemSpec",
    "ArmSpec",
    "ArmGates",
    "GroupSpec",
    "StopGate",
    "PairGate",
    "KTupleGate",
    "PeekGate",
    "ITEM_KINDS",
    "LIT",
    "CC",
    "REF",
    "GRP",
]


ITEM_KINDS: tuple[str, ...] = (LIT, CC, REF, GRP)
"""The full :attr:`ItemSpec.kind` vocabulary."""


# ── compiler intermediate: the clone/arm/item specs + loop gates ──────────
#
# The NamedTuple vocabulary (:class:`CloneKey`, :class:`IslandRef`, the loop
# gates, :class:`ItemSpec` / :class:`ArmSpec` / :class:`GroupSpec` /
# :class:`CloneSpec`) lives in :mod:`lexic.parsing.pda.compiler.specs`; this module
# re-exposes it as its public surface (``__all__``).


_PENDING = CloneSpec("", (), None, None, False)
"""In-progress placeholder installed by :meth:`PdaCompiler.ensure_rule` before
a clone body is compiled — reserves the key so recursion resolves to it, then
is overwritten by the finished :class:`CloneSpec`."""

_EOF: CharSet = CharSet.from_chars("")
"""The start clone's hard continuation — end-of-input only (the ``""``
sentinel), mirroring the FOLLOW-set seed in :mod:`lexic.parsing.pda.analysis.analysis`."""

ATTEMPT_WINDOW_K = 5
"""The attempt-entry admission window width. Measured on the vyx corpus:
failed trial runs die within 1 char in ~38% of cases, 4 in ~83%, and ~13%
run 7+ chars deep where no bounded window reaches — 5 is where the
exclusion curve flattens against the derivation's fan-out cost."""


# ── helpers ────────────────────────────────────────────────────────────────


def _items(seq: Sequence[IrSelf]) -> list[IrItem]:
    """The :class:`IrItem` members of a sequence arm, in order."""
    return [i for i in seq if isinstance(i, IrItem)]


def _hi(item: IrItem) -> int | None:
    """The item's quantifier upper bound as an ``int``, or ``None`` (unbounded)."""
    hi = item.quantifier.hi
    return None if isinstance(hi, IrNoneType) else int(hi)


def _firsts_overlap(arms: Sequence[ArmSpec]) -> bool:
    """Whether any two gated arms' FIRST sets overlap (the drift tripwire)."""
    return any(
        arms[i].first.overlaps(arms[j].first)
        for i in range(len(arms))
        for j in range(i + 1, len(arms))
    )


def _resolve_struct_arm(
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


# ── per-item context cursor (rides the argument channel) ───────────────────


class _ItemCtx(IrLeaf[IrSelf, IrSelf]):
    """The per-item compile context the :data:`_ATOM_SPEC` bodies read off ``nc``.

    :ivar lo: The item's quantifier lower bound.
    :ivar hi: The item's quantifier upper bound, or ``None``.
    :ivar cont: The item's hard continuation (the loop-gate / ref-tail base).
    :ivar gate: The precomputed loop-continuation gate.
    """

    __slots__ = ("lo", "hi", "cont", "gate")

    lo: int
    hi: int | None
    cont: CharSet
    gate: StopGate | AttemptGate | PairGate | KTupleGate | PeekGate | ScanGate

    def __init__(
        self,
        lo: int,
        hi: int | None,
        cont: CharSet,
        gate: StopGate | AttemptGate | PairGate | KTupleGate | PeekGate | ScanGate,
    ) -> None:
        """Bind one item's bounds, continuation and gate."""
        self.lo = lo
        self.hi = hi
        self.cont = cont
        self.gate = gate


# ── atom-type dispatch bodies ──────────────────────────────────────────────


def _spec_literal(_d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> ItemSpec:
    """Compile a literal atom to a ``lit`` spec carrying its text."""
    ctx = cast(_ItemCtx, nc[0])
    return ItemSpec(LIT, str(n), ctx.lo, ctx.hi, ctx.gate)


def _spec_charclass(_d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> ItemSpec:
    """Compile a char class to a ``cc`` spec carrying its member set."""
    ctx = cast(_ItemCtx, nc[0])
    return ItemSpec(
        CC, CharSet.from_charclass(cast(IrCharClass, n)), ctx.lo, ctx.hi, ctx.gate
    )


def _spec_not(_d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> ItemSpec:
    """Compile ``IrNot(charclass)`` to a co-finite ``cc`` spec (polarity
    flipped); anything but an inner :class:`IrCharClass` raises."""
    ctx = cast(_ItemCtx, nc[0])
    inner = cast(IrNot, n)[0]
    if not isinstance(inner, IrCharClass):
        raise UnsupportedConstructError(
            f"pda: IrNot over {type(inner).__name__} — "
            "only IrNot(IrCharClass) is a PDA atom"
        )
    return ItemSpec(CC, CharSet.from_not(inner), ctx.lo, ctx.hi, ctx.gate)


def _spec_ruleref(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> ItemSpec:
    """Compile a rule reference to a ``ref`` spec — an island marker or a clone.

    An island reference carries an :class:`IslandRef` (flagged for a
    fail-island); otherwise the target clone's tail is the item's hard
    continuation, and the clone is compiled (or reused) via ``ensure_rule``.
    Optional loopback stays out of that hard tail: it is a split opportunity,
    not text the child must leave for a successor.
    """
    ctx = cast(_ItemCtx, nc[0])
    compiler = cast(PdaCompiler, d)
    name = str(n)
    if name in compiler.islands:
        fail = name in compiler.fail_islands
        return ItemSpec(REF, IslandRef(name, fail), ctx.lo, ctx.hi, ctx.gate)
    if name in compiler.analysis.taxonomy.attempts:
        # ONE canonical clone per attemptable rule (the analysis-level hard
        # FOLLOW as its tail): its decisions are attempted, not stop-set-cut,
        # so call-site tail exactness buys nothing — and a single identity is
        # what lets the packrat memo see a repeat as a repeat (per-tail clones
        # made every (rule, pos) re-attempt a fresh key: measured 60% of all
        # sub-runs on the vyx corpus).
        canonical = compiler.ensure_rule(name, compiler.analysis.hard_follow[name])
        return ItemSpec(REF, canonical, ctx.lo, ctx.hi, ctx.gate)
    tail = ctx.cont
    return ItemSpec(REF, compiler.ensure_rule(name, tail), ctx.lo, ctx.hi, ctx.gate)


def _spec_alternation(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> ItemSpec:
    """Compile an inline group to a ``grp`` spec — gated arms + default.

    The arms compile against the item's hard continuation. Repeat loopback
    stays out of that tail: it is a split opportunity, not text an inner child
    must leave for another copy.

    A group whose arms' FIRSTs overlap carries the analysis' stored settlement,
    keyed by this node's identity — the same read-back a rule body does, so an
    alternation that ``@lexical`` inlining moved into a group is still decided
    rather than islanded. A window/peek demotion SELECTS an arm; an attempt
    licence orders them and hands the runtime its second-success gate.

    That gate is the analysis' SOFT continuation, taken from the store rather
    than from ``ctx.cont``: this item's tail omits repeat loopback (see above),
    and an arm ending exactly where another iteration would begin must read as
    live, not dead. The per-clone tail is unioned in because widening the gate
    only ever costs a bail — it can never let a commit through.
    """
    ctx = cast(_ItemCtx, nc[0])
    compiler = cast(PdaCompiler, d)
    eff = ctx.cont
    tax = compiler.analysis.taxonomy
    windows, peeks, attempt = tax.grp_arm_gates.get(id(n), (None, None, None))
    order = attempt[0].order if attempt is not None else None
    follow = attempt[1].union(eff) if attempt is not None else None
    arms, default, _ = compiler.compile_arms(
        cast(IrAlternation, n), eff, ArmGates(windows, peeks), order
    )
    return ItemSpec(GRP, GroupSpec(arms, default, follow), ctx.lo, ctx.hi, ctx.gate)


_ATOM_SPEC: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_spec_literal)),
    IrAction(IrCharClass, IrLambda(_spec_charclass)),
    IrAction(IrNot, IrLambda(_spec_not)),
    IrAction(IrRuleRef, IrLambda(_spec_ruleref)),
    IrAction(IrAlternation, IrLambda(_spec_alternation)),
)
"""Open atom-type dispatch — an unregistered atom raises
:exc:`~lexic.exceptions.UnsupportedConstructError` on the miss."""


# ── the compiler ───────────────────────────────────────────────────────────


class PdaCompiler(IrLeaf[IrSelf, IrSelf]):
    """Builds the per-(rule, hard-continuation) clone table for one grammar.

    Holds the compile-time state and IS the dispatcher slot ``d`` handed to
    every :data:`_ATOM_SPEC` body.

    :ivar analysis: The grammar analysis (FIRST/hard/FOLLOW/nullability +
        loop taxonomy) the clones are cut against.
    :ivar product_config: Rule name → its authored
        :class:`~lexic.parsing.product.RuleProduct` — what each rule clone's
        capture layout and build plan are baked from.
    :ivar construction: The construction operand tables a completion indexes;
        read here only to ask whether a rule's value IS its own matched text.
    :ivar islands: The island rule names — never cloned.
    :ivar fail_islands: The fail-island subset — references raise ``PdaFail``.
    :ivar clones: The compiled clone table, keyed by :class:`CloneKey`.
    """

    __slots__ = (
        "analysis",
        "construction",
        "product_config",
        "clones",
        "pending",
        "draining",
    )

    analysis: GrammarAnalysis
    product_config: Mapping[str, RuleProduct]
    construction: ConstructionTables
    clones: dict[CloneKey, CloneSpec]
    pending: list[CloneKey]
    draining: bool

    def __init__(
        self,
        analysis: GrammarAnalysis,
        product_config: Mapping[str, RuleProduct] | None = None,
        construction: ConstructionTables | None = None,
    ) -> None:
        """Prepare the compiler for one model product target."""
        self.analysis = analysis
        self.product_config = product_config or {}
        self.construction = (
            ConstructionTables() if construction is None else construction
        )
        self.clones = {}
        self.pending = []
        self.draining = False

    def _attempt_window(
        self, items: Sequence[IrItem]
    ) -> tuple[tuple[CharSet, ...], ...] | None:
        """An attempt arm's FIRST\\ :sub:`k` admission windows, or ``None``.

        Computed by the full :class:`KWindowFirst` derivation — through refs,
        alternations and nullables, with cycle/fan-out poisoning to the
        always-consistent empty window — so exclusion is language-based: a
        lookahead inconsistent with every window has NO derivation of this
        arm, and the trial run it skips could only have failed. An END-state
        prefix yields a short window whose tail admits anything (the
        continuation's characters are not the arm's to constrain), which is
        what keeps the filter sound without FOLLOW extension.

        A whole-set poison (every window empty — nothing to test) returns
        ``None``: no filter. Width costs nothing at consult time — the set
        compiles to one alternation pattern
        (:func:`~lexic.parsing.pda.core.scanner.compile_admission`), so a
        wide set is one C-level match like a narrow one.
        """
        solver = KWindowFirst(self.analysis.rules, ATTEMPT_WINDOW_K)
        windows = windows_of(solver.arm_prefixes(items, ATTEMPT_WINDOW_K))
        if all(len(window) == 0 for window in windows):
            return None
        return windows

    @property
    def islands(self) -> frozenset[str]:
        """The island residue — conflicted rules no attempt can settle, never
        cloned. Attemptable rules (``taxonomy.attempts``) clone instead, with
        their arms in attempt order."""
        return self.analysis.islands - frozenset(self.analysis.taxonomy.attempts)

    @property
    def fail_islands(self) -> frozenset[str]:
        """The fail-island subset — references raise ``PdaFail``."""
        return self.analysis.fail_islands

    def compile_start(self) -> CloneKey | IslandRef:
        """Compile the start clone (EOF-only tail), or return the
        :class:`IslandRef` opt-out when the start rule is itself an island."""
        start = self.analysis.start
        if start in self.islands:
            return IslandRef(start, start in self.fail_islands)
        return self.ensure_rule(start, _EOF)

    def ensure_rule(self, name: str, tail: CharSet) -> CloneKey:
        """Compile (or reuse) the clone of ``name`` for continuation ``tail``.

        Cycle- AND depth-safe: the key is reserved with :data:`_PENDING` and
        queued; a recursive or repeated reference resolves to the key without
        re-queueing. The outermost call drains the queue iteratively — a
        nested call (an :data:`_ATOM_SPEC` body reaching a fresh ref mid-body)
        only enqueues, so a long rule chain compiles at constant Python stack
        depth instead of one frame set per rule. On return every queued clone
        is complete (the callers' contract is unchanged). ``name`` is never an
        island — callers check first.
        """
        key = CloneKey(name, tail)
        if key not in self.clones:
            self.clones[key] = _PENDING
            self.pending.append(key)
        if not self.draining:
            self.draining = True
            try:
                while self.pending:
                    self._compile_clone(self.pending.pop())
            finally:
                self.draining = False
        return key

    def _clone_shape(
        self, name: str, rule: IrRule, tail: CharSet
    ) -> tuple[
        tuple[ArmSpec, ...],
        tuple[ItemSpec, ...] | None,
        ScanGate | None,
        CharSet | None,
    ]:
        """One clone body's compiled arms — the attempt / gated split.

        An attemptable rule's arms compile in attempt order with no gate
        specs; every other rule gets its stored demotion gates. A
        single-gated-arm attempt rule (islanded for its loops alone) has no
        arm choice to try — its licensed loops carry the whole licence in
        their gates, so it runs as an ordinary clone (``follow`` is ``None``).

        :returns: ``(arms, default, struct gate, attempt follow | None)``.
        """
        tax = self.analysis.taxonomy
        attempt = tax.attempts.get(name)
        if attempt is not None:
            arms, default, struct = self.compile_arms(
                rule.body, tail, order=attempt.order
            )
            follow = self.analysis.follow[name] if len(arms) > 1 else None
            return arms, default, struct, follow
        arms, default, struct = self.compile_arms(
            rule.body,
            tail,
            ArmGates(
                tax.arm_gates.get(name),
                tax.pn_arm_gates.get(name),
                tax.struct_arm_gates.get(name),
            ),
        )
        return arms, default, struct, None

    def _compile_clone(self, key: CloneKey) -> None:
        """Compile one queued clone body into :attr:`clones` (drain step)."""
        name = key.name
        rule = self.analysis.rules[name]
        arms, default, struct, follow = self._clone_shape(name, rule, key.tail)
        product = self.product_config.get(name)
        self.clones[key] = CloneSpec(
            name,
            arms,
            default,
            product,
            self._matches_own_text(product),
            struct,
            follow,
        )

    def _matches_own_text(self, product: RuleProduct | None) -> bool:
        """Whether this rule's value IS its matched text — so it needs no interior."""
        if product is None:
            return False
        construction = construction_of(product, self.construction)
        return construction is not None and bool(construction.matched)

    def compile_arms(
        self,
        node: IrAlternation,
        tail: CharSet,
        gates: ArmGates = ArmGates(),
        order: tuple[int, ...] | None = None,
    ) -> tuple[tuple[ArmSpec, ...], tuple[ItemSpec, ...] | None, ScanGate | None]:
        """Compile the arms of a rule body or inline group against ``tail``.

        Each arm becomes a FIRST-gated :class:`ArmSpec` (dropped when its FIRST
        is empty — an empty arm never gates); an all-nullable arm additionally
        becomes the single default (last such arm wins). ``gates`` bundles a
        demoted rule body's stored specs — ``windows`` (P2) / ``peeks`` (P3)
        aligned to ``node``'s arms, and the empty-arm ``struct_arm`` gate — all
        attached inside this one enumeration, so spec↔arm alignment cannot drift
        past the empty-FIRST drop; the ``struct_arm`` escape index is validated
        here against the nullable default arm the compiler actually picks.

        With ``order`` (an ATTEMPT rule's ``AttemptSpec.order``) the arms are
        emitted in attempt order rather than authored order, and the
        overlap-without-gate raise is skipped — overlapping FIRSTs are the
        attempt case, tried in order by the runtime rather than selected.

        :returns: ``(gated arms, default specs | None, struct-arm ScanGate | None)``.
        :raises UnsupportedConstructError: When gated arms' FIRSTs overlap with
            no gate spec to select by (and no attempt ``order``), or a
            ``struct_arm`` gate's escape index does not match the nullable
            default arm (analysis/compiler drift — a wrong arm would silently
            mis-parse, so the grammar opts out).
        """
        windows, peeks = gates.windows, gates.peeks
        arms: list[ArmSpec] = []
        default: tuple[ItemSpec, ...] | None = None
        default_idx: int | None = None
        for idx, arm in (
            enumerate(node) if order is None else ((i, node[i]) for i in order)
        ):
            items = _items(arm)
            specs = self._compile_seq(items, tail)
            first = self.analysis.seq_first(items)
            if all(self.analysis.item_nullable(i) for i in items):
                default = specs
                default_idx = idx
            if not first.is_empty():
                arms.append(
                    ArmSpec(
                        first,
                        specs,
                        windows[idx] if windows is not None else None,
                        (peeks[0], peeks[1][idx]) if peeks is not None else None,
                        self._attempt_window(items) if order is not None else None,
                    )
                )
        if (
            order is None
            and windows is None
            and peeks is None
            and _firsts_overlap(arms)
        ):
            raise UnsupportedConstructError(
                "pda: arm FIRST overlap without a gate spec"
            )
        return tuple(arms), default, _resolve_struct_arm(gates.struct_arm, default_idx)

    def _compile_seq(
        self, items: Sequence[IrItem], tail: CharSet
    ) -> tuple[ItemSpec, ...]:
        """Compile a sequence of items, each cut against its hard continuation."""
        analysis = self.analysis
        return tuple(
            self._compile_item(items, k, analysis.hard_cont_at(items, k, tail))
            for k in range(len(items))
        )

    def _compile_item(
        self, items: Sequence[IrItem], idx: int, cont: CharSet
    ) -> ItemSpec:
        """Compile item ``idx`` to its :class:`ItemSpec` via the atom dispatch table.

        :param items: The enclosing arm's items.
        :param idx: The item's index in ``items``.
        :param cont: The item's hard continuation (loop-gate / ref-tail base).
        :returns: The item's spec.
        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        item = items[idx]
        atom = item.atom
        lo = int(item.quantifier.lo)
        hi = _hi(item)
        gate = self._loop_gate(items, idx, cont)
        ctx = _ItemCtx(lo, hi, cont, gate)
        return cast(ItemSpec, _ATOM_SPEC.resolve(atom).eval(self, atom, (ctx,)))

    def _loop_gate(
        self, items: Sequence[IrItem], idx: int, cont: CharSet
    ) -> StopGate | AttemptGate | PairGate | KTupleGate | PeekGate | ScanGate:
        """The loop-continuation gate — stop-set, LL(2) pair, or k-window set.

        Defaults to the non-greedy stop-set (``FIRST(atom) − continuation``); a
        looping item whose FIRST overlaps its continuation upgrades to an LL(2)
        :class:`PairGate` when the taxonomy says ``pairs``, or to the
        :class:`KTupleGate` the analysis stored for exactly this item node
        (:attr:`~lexic.parsing.pda.analysis.analysis.Taxonomy.loop_gates` — the demoted
        take/skip decision a single-char stop-set could not make).

        :param items: The enclosing arm's items.
        :param idx: The looping item's index.
        :param cont: The item's hard continuation.
        :returns: The loop gate.
        """
        analysis = self.analysis
        item = items[idx]
        rest = list(items[idx + 1 :])
        lo = int(item.quantifier.lo)
        hi = _hi(item)
        first = analysis.atom_first(item.atom)
        if hi is None or hi > lo:
            # A stored gate is the analysis's DECISION for this item node —
            # honor it in EVERY clone, before any overlap heuristic: `cont` is
            # one clone's hard tail, and no overlap there does NOT make a
            # plain stop-set safe (it could still eat the soft-only noise run
            # the gate exists to adjudicate).
            kspec = analysis.taxonomy.loop_gates.get(id(item))
            if kspec is not None:
                return KTupleGate(kspec)
            pspec = analysis.taxonomy.pn_loop_gates.get(id(item))
            if pspec is not None:
                return PeekGate(*pspec)
            sspec = analysis.taxonomy.struct_loop_gates.get(id(item))
            if sspec is not None:
                return sspec  # a folding-aware ScanGate (P3 structured / P5)
            licence = analysis.taxonomy.attempt_loops.get(id(item))
            if licence is not None:
                # The attempt licence: FIRST admits an iteration ATTEMPT —
                # the runtime runs it as a sub-run and a failure closes the
                # loop, so the loop takes maximally subject to its iterations
                # actually parsing (the split's defined answer). A plain
                # stop-set here would commit on one character and fail the
                # arm on any later mismatch inside the iteration. The stored
                # soft continuation guards the boundary where taking and
                # stopping are BOTH viable — an arm choice in loop clothing.
                return AttemptGate(first, licence)
            if first.overlaps(cont):
                policy = analysis.loop_policy(item, rest)
                if isinstance(policy, tuple):
                    return PairGate(policy[1])
        return StopGate(first.subtract(cont))


# ── the artifact ───────────────────────────────────────────────────────────


def _attach_delegates(tables: PdaTables, lifted: IrAst, binding: ModelBinding) -> None:
    """Attach the island-interior :class:`DelegateSource` to ``tables.program``
    (built from ``lifted`` + the compiler's bound product; the injected
    ``(PdaCompiler, flatten_clones)`` seam keeps the delegate leaf import-free
    of this module)."""
    name_to_rid = {
        str(rule.name): i for i, rule in enumerate(tables.instance_grammar.rules)
    }
    tables.program.delegates = DelegateSource(
        lifted,
        name_to_rid,
        binding,
        (PdaCompiler, flatten_clones),
    )


def compile_pda(
    lifted: IrAst,
    instance_grammar: IrAst,
    binding: ModelBinding,
) -> PdaTables:
    """Compile the predictive-parser tables for one grammar.

    :param lifted: The lifted codegen grammar
        (``lift_optional_nullables(build_codegen_grammar(canonical))``) — the
        grammar the analysis and the clones are cut against.
    :param instance_grammar: The Earley-normalised instance grammar
        (``normalize(lifted)``) — the island sub-parses run over it.
    :param binding: The bound model product — its rules are baked into each
        clone's capture layout, constructor and build plan, and its
        construction tables are what a completion indexes.
    :returns: The compiled :class:`PdaTables`.
    :raises UnsupportedConstructError: On anything the analysis or the clone
        compiler cannot handle (the Task-6 seam reads this as "no PDA").
    """
    analysis = GrammarAnalysis(lifted)
    compiler = PdaCompiler(analysis, binding.rules, binding.construction)
    start_key = compiler.compile_start()
    tables = PdaTables(compiler, start_key, instance_grammar, binding)
    _attach_delegates(tables, lifted, binding)
    return tables
