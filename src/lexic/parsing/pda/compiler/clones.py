"""Clone compiler — the predictive-parser artifact beside :class:`ParserTables`.

:func:`compile_pda` turns a *lifted codegen grammar*
(``lift_optional_nullables(build_codegen_grammar(canonical))`` — the shape
:class:`~lexic.parsing.pda.analysis.analysis.GrammarAnalysis` runs on) into
:class:`PdaTables`: the per-(rule, hard-continuation) **clones** the runtime
walks, plus the island set and a lazy per-island :class:`ParserTables` cache
for the conflicted rules that fall back to Earley sub-parses.

**Clones (pivot 3).** A rule is compiled once per distinct *hard continuation*
that reaches it (its loop stop-sets are call-site-exact, pivot 4).
:meth:`_PdaCompiler.ensure_rule` reserves the clone key with a :data:`_PENDING`
placeholder before compiling, so recursion resolves to the in-progress key and
a repeat ``(name, tail)`` reuses the clone. Island rules are never cloned — a
reference carries an :class:`IslandRef` (a ``fail`` one raises
:class:`~lexic.parsing.pda.runtime.runtime.PdaFail`, forcing the engine fallback).

**Item specs.** Each item compiles to a flat :class:`ItemSpec`
(``lit``/``cc``/``ref``/``grp``) with its bounds and a loop gate —
:class:`StopGate` (pivot 4), :class:`PairGate` (pivot 6), :class:`KTupleGate`
(P2), :class:`PeekGate` (P3 char-set) or :class:`ScanGate` (P3 structured
noise-skip / P5 probe, folding-aware via :mod:`~lexic.parsing.pda.core.scanner`).
Arm selection is FIRST-gated :class:`ArmSpec` plus at most one nullable default.
Every rule clone bakes its :class:`~lexic.parsing.fold.RuleFold`; a
``value_str`` clone is :attr:`~CloneSpec.match_only` (the runtime slices
``text[a:b]`` instead of building below).

**Open dispatch.** Per-atom compilation routes through the module-level
:data:`_ATOM_SPEC` :class:`~lexic.ir.mapping.IrTypeMap` (the ``analysis.py``
idiom — compiler on ``d``, per-item context on ``nc`` via :class:`_ItemCtx`);
an unregistered atom raises :exc:`~lexic.exceptions.UnsupportedConstructError`
(the Task-6 "no PDA" seam).

The spec NamedTuples are the compiler's *intermediate* (the shape tests pin);
:func:`_flatten_program` lowers them once into the flat int-coded
:class:`PdaProgram` the :class:`~lexic.parsing.pda.runtime.runtime.PdaKernel` walks. The
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
    IrAtom,
    IrCharClass,
    IrItem,
    IrLambda,
    IrLeaf,
    IrLiteral,
    IrNoneType,
    IrNot,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
)
from lexic.parsing.earley.reduce import OTHER_KIND, Reducer, plan_for
from lexic.parsing.earley.tables import ORIGIN_BITS, ParserTables, compile_tables
from lexic.parsing.fold import RuleFold
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.delegate_compile import DelegateSource
from lexic.parsing.pda.compiler.flatten import (
    BUILD_ALT,
    BUILD_SEQ,
    BUILD_TRANSPARENT,
    BUILD_VALUE_STR,
    GATE_KWIN,
    GATE_PAIR,
    GATE_PEEK,
    GATE_SCAN,
    GATE_STOP,
    HI_UNBOUNDED,
    MODE_CODE,
    OP_CC,
    OP_FAIL,
    OP_GRP,
    OP_ISLAND,
    OP_LIT,
    OP_REF,
    FlatArm,
    FlatClone,
    PdaProgram,
    optimize_program,
)
from lexic.parsing.pda.compiler.reduce_pda import (
    ReduceComp,
    ReduceCompile,
    ReduceRun,
    reduce_rewrite,
)
from lexic.parsing.pda.compiler.specs import (
    ArmGates,
    ArmSpec,
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
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import ArmGate, ScanGate

__all__ = [
    "compile_pda",
    "compile_reduce_pda",
    "PdaTables",
    "PdaProgram",
    "ReduceComp",
    "ReduceRun",
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

LIT, CC, REF, GRP = "lit", "cc", "ref", "grp"
"""The :attr:`ItemSpec.kind` tags: literal, char class, rule reference, group."""

ITEM_KINDS: tuple[str, ...] = (LIT, CC, REF, GRP)
"""The full :attr:`ItemSpec.kind` vocabulary."""


# ── compiler intermediate: the clone/arm/item specs + loop gates ──────────
#
# The NamedTuple vocabulary (:class:`CloneKey`, :class:`IslandRef`, the loop
# gates, :class:`ItemSpec` / :class:`ArmSpec` / :class:`GroupSpec` /
# :class:`CloneSpec`) lives in :mod:`lexic.parsing.pda.compiler.specs`; this module
# re-exposes it as its public surface (``__all__``).


_PENDING = CloneSpec("", (), None, None, False)
"""In-progress placeholder installed by :meth:`_PdaCompiler.ensure_rule` before
a clone body is compiled — reserves the key so recursion resolves to it, then
is overwritten by the finished :class:`CloneSpec`."""

_EOF: CharSet = CharSet.from_chars("")
"""The start clone's hard continuation — end-of-input only (the ``""``
sentinel), mirroring the FOLLOW-set seed in :mod:`lexic.parsing.pda.analysis.analysis`."""


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


def _flat_windows(
    windows: tuple[tuple[CharSet, ...], ...],
) -> tuple[tuple[tuple[frozenset[str], bool], ...], ...]:
    """Pre-resolve CharSet windows to the ``((chars, negated), ...)`` flat form."""
    return tuple(tuple((cs.chars, cs.negated) for cs in win) for win in windows)


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
    gate: StopGate | PairGate | KTupleGate | PeekGate | ScanGate

    def __init__(
        self,
        lo: int,
        hi: int | None,
        cont: CharSet,
        gate: StopGate | PairGate | KTupleGate | PeekGate | ScanGate,
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
    continuation, widened by the atom's own hard-FIRST when the reference
    repeats, and the clone is compiled (or reused) via ``ensure_rule``.
    """
    ctx = cast(_ItemCtx, nc[0])
    compiler = cast(_PdaCompiler, d)
    name = str(n)
    if name in compiler.islands:
        fail = name in compiler.fail_islands
        return ItemSpec(REF, IslandRef(name, fail), ctx.lo, ctx.hi, ctx.gate)
    tail = ctx.cont
    if ctx.hi is None or ctx.hi > 1:
        tail = tail.union(compiler.analysis.atom_hard(cast(IrAtom, n)))
    return ItemSpec(REF, compiler.ensure_rule(name, tail), ctx.lo, ctx.hi, ctx.gate)


def _spec_alternation(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> ItemSpec:
    """Compile an inline group to a ``grp`` spec — FIRST-gated arms + default.

    The arms compile against an effective tail that, for a repeating group,
    unions in the group's own hard-FIRST (the group may follow itself).
    """
    ctx = cast(_ItemCtx, nc[0])
    compiler = cast(_PdaCompiler, d)
    eff = ctx.cont
    if ctx.hi is None or ctx.hi > 1:
        eff = eff.union(compiler.analysis.atom_hard(cast(IrAtom, n)))
    arms, default, _ = compiler.compile_arms(cast(IrAlternation, n), eff)
    return ItemSpec(GRP, GroupSpec(arms, default), ctx.lo, ctx.hi, ctx.gate)


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


class _PdaCompiler(IrLeaf[IrSelf, IrSelf]):
    """Builds the per-(rule, hard-continuation) clone table for one grammar.

    Holds the compile-time state and IS the dispatcher slot ``d`` handed to
    every :data:`_ATOM_SPEC` body.

    :ivar analysis: The grammar analysis (FIRST/hard/FOLLOW/nullability +
        loop taxonomy) the clones are cut against.
    :ivar fold_config: Rule name → its :class:`~lexic.parsing.fold.RuleFold`.
    :ivar islands: The island rule names — never cloned.
    :ivar fail_islands: The fail-island subset — references raise ``PdaFail``.
    :ivar clones: The compiled clone table, keyed by :class:`CloneKey`.
    :ivar reduce: The reduce completion source, or ``None`` for the model path.
    :ivar completions: Clone key → its :class:`ReduceComp` (reduce path only).
    """

    __slots__ = (
        "analysis",
        "fold_config",
        "clones",
        "reduce",
        "completions",
        "pending",
        "draining",
    )

    analysis: GrammarAnalysis
    fold_config: Mapping[str, RuleFold]
    clones: dict[CloneKey, CloneSpec]
    reduce: ReduceCompile | None
    completions: dict[CloneKey, ReduceComp]
    pending: list[CloneKey]
    draining: bool

    def __init__(
        self,
        analysis: GrammarAnalysis,
        fold_config: Mapping[str, RuleFold] | None = None,
        *,
        reduce: ReduceCompile | None = None,
    ) -> None:
        """Prepare the compiler for one target (model fold, or reduce)."""
        self.analysis = analysis
        self.fold_config = fold_config or {}
        self.clones = {}
        self.reduce = reduce
        self.completions = {}
        self.pending = []
        self.draining = False

    @property
    def islands(self) -> frozenset[str]:
        """The island rule names — never cloned (a view onto the analysis)."""
        return self.analysis.islands

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

    def _compile_clone(self, key: CloneKey) -> None:
        """Compile one queued clone body into :attr:`clones` (drain step)."""
        name = key.name
        rule = self.analysis.rules[name]
        tax = self.analysis.taxonomy
        arms, default, struct = self.compile_arms(
            rule.body,
            key.tail,
            ArmGates(
                tax.arm_gates.get(name),
                tax.pn_arm_gates.get(name),
                tax.struct_arm_gates.get(name),
            ),
        )
        fold = self.fold_config.get(name)
        match_only = fold is not None and fold.kind == "value_str"
        self.clones[key] = CloneSpec(name, arms, default, fold, match_only, struct)
        if self.reduce is not None:
            self.completions[key] = self.reduce.comp_for(name)

    def compile_arms(
        self,
        node: IrAlternation,
        tail: CharSet,
        gates: ArmGates = ArmGates(),
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

        :returns: ``(gated arms, default specs | None, struct-arm ScanGate | None)``.
        :raises UnsupportedConstructError: When gated arms' FIRSTs overlap with
            no gate spec to select by, or a ``struct_arm`` gate's escape index
            does not match the nullable default arm (analysis/compiler drift —
            a wrong arm would silently mis-parse, so the grammar opts out).
        """
        windows, peeks = gates.windows, gates.peeks
        arms: list[ArmSpec] = []
        default: tuple[ItemSpec, ...] | None = None
        default_idx: int | None = None
        for idx, arm in enumerate(node):
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
                    )
                )
        if windows is None and peeks is None and _firsts_overlap(arms):
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
    ) -> StopGate | PairGate | KTupleGate | PeekGate | ScanGate:
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
            if first.overlaps(cont):
                policy = analysis.loop_policy(item, rest)
                if isinstance(policy, tuple):
                    return PairGate(policy[1])
        return StopGate(first.subtract(cont))


def _build_mode(fold: RuleFold | None) -> int:
    """Map a clone's fold to its flat build-mode.

    :param fold: The clone's :class:`~lexic.parsing.fold.RuleFold`, or ``None``.
    :returns: One of the ``_BUILD_*`` constants.
    :raises UnsupportedConstructError: On a fold kind outside the vocabulary.
    """
    if fold is None:
        return BUILD_TRANSPARENT
    kind = fold.kind
    if kind == "value_str":
        return BUILD_VALUE_STR
    if kind == "alternation":
        return BUILD_ALT
    if kind == "sequence":
        return BUILD_SEQ
    raise UnsupportedConstructError(f"pda: unknown fold kind {kind!r}")


def _flatten_gate(
    gate: StopGate | PairGate | KTupleGate | PeekGate | ScanGate,
) -> tuple[int, object]:
    """Lower a loop gate to its ``(code, data)`` flat pair."""
    if isinstance(gate, PairGate):
        return GATE_PAIR, gate.pairs
    if isinstance(gate, KTupleGate):
        return GATE_KWIN, _flat_windows(gate.windows)
    if isinstance(gate, PeekGate):
        return GATE_PEEK, (
            (gate.w.chars, gate.w.negated),
            (gate.take.chars, gate.take.negated),
        )
    if isinstance(gate, ScanGate):
        return GATE_SCAN, gate  # runtime-ready; scan_gate_take reads it directly
    cs = gate.charset
    return GATE_STOP, (cs.chars, cs.negated)


def _flatten_arm(
    specs: Sequence[ItemSpec], shells: dict[CloneKey, FlatClone]
) -> FlatArm:
    """Lower a sequence of :class:`ItemSpec` to a :class:`FlatArm` (refs
    resolve to the live shell objects, so recursion needs no id indirection)."""
    kinds: list[int] = []
    payloads: list[object] = []
    los: list[int] = []
    his: list[int] = []
    gate_kinds: list[int] = []
    gate_data: list[object] = []
    for spec in specs:
        kind, payload = _flatten_item(spec, shells)
        kinds.append(kind)
        payloads.append(payload)
        los.append(spec.lo)
        his.append(HI_UNBOUNDED if spec.hi is None else spec.hi)
        gate_kind, gate_body = _flatten_gate(spec.gate)
        gate_kinds.append(gate_kind)
        gate_data.append(gate_body)
    arm = FlatArm.__new__(FlatArm)
    arm.n = len(kinds)
    arm.kinds = tuple(kinds)
    arm.payloads = tuple(payloads)
    arm.los = tuple(los)
    arm.his = tuple(his)
    arm.gate_kinds = tuple(gate_kinds)
    arm.gate_data = tuple(gate_data)
    return arm


def _flatten_item(
    spec: ItemSpec, shells: dict[CloneKey, FlatClone]
) -> tuple[int, object]:
    """Lower one :class:`ItemSpec` to its ``(op-code, payload)`` flat pair."""
    kind = spec.kind
    payload = spec.payload
    if kind == LIT:
        return OP_LIT, str(payload)
    if kind == CC:
        cs = cast(CharSet, payload)
        return OP_CC, (cs.chars, cs.negated)
    if kind == GRP:
        return OP_GRP, _flatten_group(cast(GroupSpec, payload), shells)
    target = payload  # REF
    if isinstance(target, IslandRef):
        return (OP_FAIL if target.fail else OP_ISLAND), target.name
    return OP_REF, shells[cast(CloneKey, target)]


def _bake_build(clone: FlatClone, fold: RuleFold | None) -> None:
    """Bake a clone's fold and fused-build plan (fields/fast/defaults) in place."""
    clone.fold = fold
    clone.leaf = False  # granted by _mark_leaves once the arm shapes are final
    clone.needs_ends = fold is not None and any(
        f.mode in ("text", "gtext") for f in fold.fields
    )
    if fold is None or fold.fast is None:
        clone.fields = ()
        clone.fast = None
        clone.defaults = None
        return
    clone.fields = tuple((f.item, MODE_CODE[f.mode], f.name, f.lo) for f in fold.fields)
    clone.fast = fold.fast.make
    clone.defaults = dict(fold.fast.defaults)


def _flatten_selectors(
    arms: Sequence[ArmSpec], shells: dict[CloneKey, FlatClone]
) -> tuple[tuple[tuple[frozenset[str], bool, FlatArm], ...], object, object]:
    """Lower an alternation's arm selectors — single-char, k-window, or peek.

    P2 (:attr:`ArmSpec.windows`) lowers to ``kwin_selectors``; P3
    (:attr:`ArmSpec.peek`) to ``pn_selectors``; otherwise the FIRST-gated
    single-char triples are built.

    :returns: ``(selectors, kwin_selectors, pn_selectors)`` — at most one set.
    """
    if arms and arms[0].windows is not None:
        kwin = tuple(
            (
                _flat_windows(cast("tuple[tuple[CharSet, ...], ...]", arm.windows)),
                _flatten_arm(arm.specs, shells),
            )
            for arm in arms
        )
        return (), kwin, None
    if arms and arms[0].peek is not None:
        w = cast("tuple[CharSet, CharSet]", arms[0].peek)[0]
        sels = tuple(
            (
                cast("tuple[CharSet, CharSet]", arm.peek)[1].chars,
                cast("tuple[CharSet, CharSet]", arm.peek)[1].negated,
                _flatten_arm(arm.specs, shells),
            )
            for arm in arms
        )
        return (), None, ((w.chars, w.negated), sels)
    selectors = tuple(
        (arm.first.chars, arm.first.negated, _flatten_arm(arm.specs, shells))
        for arm in arms
    )
    return selectors, None, None


def _flatten_group(group: GroupSpec, shells: dict[CloneKey, FlatClone]) -> FlatClone:
    """Lower an inline group to a transparent :class:`FlatClone`."""
    clone = FlatClone.__new__(FlatClone)
    clone.selectors, clone.kwin_selectors, clone.pn_selectors = _flatten_selectors(
        group.arms, shells
    )
    clone.default = (
        _flatten_arm(group.default, shells) if group.default is not None else None
    )
    clone.struct_arm = None
    clone.mode = BUILD_TRANSPARENT
    _bake_build(clone, None)
    return clone


def _flatten_clones(
    clones: dict[CloneKey, CloneSpec],
    completions: dict[CloneKey, ReduceComp] | None,
) -> dict[CloneKey, FlatClone]:
    """Lower a compiled clone table to its live :class:`FlatClone` shells.

    Two passes: create an empty shell per clone key, then fill each (refs
    resolve to the live shells — no runtime id lookup). The model target then
    runs :func:`optimize_program`; the reduce target (``completions`` given)
    runs :func:`reduce_rewrite` instead. Shared by :func:`_flatten_program`
    and the per-island delegate compile, which each own an independent shell
    set the optimiser mutates in place.
    """
    shells: dict[CloneKey, FlatClone] = {
        key: FlatClone.__new__(FlatClone) for key in clones
    }
    for key, spec in clones.items():
        clone = shells[key]
        clone.selectors, clone.kwin_selectors, clone.pn_selectors = _flatten_selectors(
            spec.arms, shells
        )
        clone.default = (
            _flatten_arm(spec.default, shells) if spec.default is not None else None
        )
        clone.struct_arm = spec.struct_arm
        clone.mode = _build_mode(spec.fold)
        _bake_build(clone, spec.fold)
    if completions is None:
        optimize_program(list(shells.values()))
    else:
        reduce_rewrite(shells, completions)
    return shells


def _flatten_program(
    clones: dict[CloneKey, CloneSpec],
    start_key: CloneKey | IslandRef,
    completions: dict[CloneKey, ReduceComp] | None = None,
) -> PdaProgram:
    """Lower the compiled clone table to the flat runtime :class:`PdaProgram`
    (``completions`` given on the reduce path, ``None`` on the model path)."""
    shells = _flatten_clones(clones, completions)
    start: FlatClone | IslandRef = (
        shells[start_key] if isinstance(start_key, CloneKey) else start_key
    )
    return PdaProgram(start)


# ── the artifact ───────────────────────────────────────────────────────────


class PdaTables(IrLeaf[IrSelf, IrSelf]):
    """The compiled predictive-parser artifact — the sibling of :class:`ParserTables`.

    Complete and immutable after :func:`compile_pda`; only the island cache
    fills lazily (in place, the :class:`ParserTables` scanning-cache precedent).

    :ivar clones: Clone key → its :class:`CloneSpec`.
    :ivar start_key: The start clone's key, or an :class:`IslandRef` when the
        start rule is an island (the whole-grammar opt-out signal for Task 6).
    :ivar islands: The island rule names (from
        :attr:`~lexic.parsing.pda.analysis.analysis.GrammarAnalysis.islands`).
    :ivar instance_grammar: The Earley-normalised instance grammar island
        tables are built over.
    :ivar program: The flat int-coded runtime program (:class:`PdaProgram`)
        :class:`~lexic.parsing.pda.runtime.runtime.PdaKernel` walks.
    :ivar reduce: The reduce runtime context (:class:`ReduceRun`) on a
        grammar-text (reducer) PDA, else ``None`` — the model path.
    """

    __slots__ = (
        "clones",
        "start_key",
        "islands",
        "instance_grammar",
        "program",
        "reduce",
        "_island_tables",
    )

    clones: dict[CloneKey, CloneSpec]
    start_key: CloneKey | IslandRef
    islands: frozenset[str]
    instance_grammar: IrAst
    program: PdaProgram
    reduce: ReduceRun | None
    _island_tables: dict[tuple[str, int], ParserTables]

    def __init__(
        self,
        compiler: _PdaCompiler,
        start_key: CloneKey | IslandRef,
        instance_grammar: IrAst,
        reduce: ReduceRun | None = None,
    ) -> None:
        """Freeze the clone table, lower it to the flat program, seed the caches.

        The clones, island set and reduce completions come off ``compiler``.
        The island-interior delegate source is attached to :attr:`program` by
        the compile entry points (:func:`_attach_delegates`), so the artifact's
        own attribute set stays put.
        """
        completions = compiler.completions if compiler.reduce is not None else None
        self.clones = compiler.clones
        self.start_key = start_key
        self.islands = compiler.islands
        self.instance_grammar = instance_grammar
        self.program = _flatten_program(compiler.clones, start_key, completions)
        self.reduce = reduce
        self._island_tables = {}

    def island_tables(self, name: str, bits: int = ORIGIN_BITS) -> ParserTables:
        """The :class:`ParserTables` for island rule ``name``, built once per
        ``(name, bits)`` and cached — compiled over :attr:`instance_grammar`
        with ``name`` as the start rule (the Earley sub-parser for a
        conflicted rule), at the run's packing tier ``bits`` (an island window
        can span the whole remaining input)."""
        cached = self._island_tables.get((name, bits))
        if cached is None:
            cached = compile_tables(IrAst(self.instance_grammar.rules, name), bits)
            self._island_tables[(name, bits)] = cached
        return cached

    def island_delegates(self, name: str) -> "dict[int, FlatClone]":
        """The island-interior delegate clones for island ``name`` (rule_id →
        clone), computed once by the program's
        :class:`~lexic.parsing.pda.compiler.delegate_compile.DelegateSource` — empty when
        nothing delegates. The runtime wraps each into a fail-soft callable and
        threads it through the island Earley sub-parse (the keys are island
        tables rule ids, the predictor's ``rid``)."""
        return cast("dict[int, FlatClone]", self.program.delegates.for_island(name))

    def reset_delegate_cache(self) -> None:
        """Drop the per-island delegate cache — a test seam for the A/B parity
        gate, which swaps in a no-delegates :class:`DelegateSource` and
        recomputes each side."""
        self.program.delegates.reset()


def _attach_delegates(tables: PdaTables, lifted: IrAst, compiler: _PdaCompiler) -> None:
    """Attach the island-interior :class:`DelegateSource` to ``tables.program``
    (built from ``lifted`` + the compiler's fold/reduce target; the injected
    ``(_PdaCompiler, _flatten_clones)`` seam keeps the delegate leaf import-free
    of this module)."""
    name_to_rid = {
        str(rule.name): i for i, rule in enumerate(tables.instance_grammar.rules)
    }
    tables.program.delegates = DelegateSource(
        lifted,
        name_to_rid,
        (compiler.fold_config, compiler.reduce),
        (_PdaCompiler, _flatten_clones),
    )


def compile_pda(
    lifted: IrAst,
    instance_grammar: IrAst,
    fold_config: Mapping[str, RuleFold],
) -> PdaTables:
    """Compile the predictive-parser tables for one grammar.

    :param lifted: The lifted codegen grammar
        (``lift_optional_nullables(build_codegen_grammar(canonical))``) — the
        grammar the analysis and the clones are cut against.
    :param instance_grammar: The Earley-normalised instance grammar
        (``normalize(lifted)``) — the island sub-parses run over it.
    :param fold_config: Rule name → its :class:`~lexic.parsing.fold.RuleFold`,
        baked into each rule clone.
    :returns: The compiled :class:`PdaTables`.
    :raises UnsupportedConstructError: On anything the analysis or the clone
        compiler cannot handle (the Task-6 seam reads this as "no PDA").
    """
    analysis = GrammarAnalysis(lifted)
    compiler = _PdaCompiler(analysis, fold_config)
    start_key = compiler.compile_start()
    tables = PdaTables(compiler, start_key, instance_grammar)
    _attach_delegates(tables, lifted, compiler)
    return tables


def compile_reduce_pda(
    lifted: IrAst, instance_grammar: IrAst, reducer: Reducer
) -> PdaTables:
    """Compile the predictive-parser tables for a grammar-text (reducer) parse.

    The b1 twin of :func:`compile_pda`: one recognition compile (same analysis,
    clones, islands), but each clone bakes a :class:`ReduceComp` completion read
    from the reducer's compiled :class:`~lexic.parsing.earley.reduce.ReducePlan`
    (H5 — the single home the Earley fused path also reads) rather than a model
    :class:`~lexic.parsing.fold.RuleFold`. The runtime feeds each clone's cleaned
    children to its reduction ``body.eval`` — no intermediate ParseTree.

    Always returns tables (the compiler is total). A reducer whose terminal-leaf
    policy the reduce runtime cannot reconstruct (a grammar-global condition with
    no enclosing rule) compiles to an **immediate-PdaFail start** — an
    :class:`IslandRef` start over an empty clone table, so
    :func:`~lexic.parsing.pda.runtime.reduce_runtime.pda_model` raises
    :class:`~lexic.parsing.pda.runtime.runtime.PdaFail` on the first step and the caller
    completes on the Earley reduce per parse (no ``None`` channel, no windowed
    self-parse of the whole input).

    :returns: The compiled :class:`PdaTables` (its :attr:`~PdaTables.reduce` set).
    :raises UnsupportedConstructError: On an atom the clone compiler cannot
        handle (a genuine boundary error, never a downgrade).
    """
    tables = compile_tables(instance_grammar)
    plan = plan_for(reducer, tables)
    name_to_rid = {name: rid for rid, name in enumerate(tables.decode.rule_names)}
    analysis = GrammarAnalysis(lifted)
    run = ReduceRun(reducer, plan, tables, name_to_rid)
    if plan.literal_kind == OTHER_KIND:
        # Reduce policy the runtime cannot reconstruct → immediate-PdaFail start.
        return PdaTables(
            _PdaCompiler(analysis),
            IslandRef(analysis.start),
            instance_grammar,
            reduce=run,
        )
    compiler = _PdaCompiler(analysis, reduce=ReduceCompile(reducer, plan, name_to_rid))
    start_key = compiler.compile_start()
    pda = PdaTables(compiler, start_key, instance_grammar, reduce=run)
    _attach_delegates(pda, lifted, compiler)
    return pda
