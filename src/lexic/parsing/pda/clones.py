"""Clone compiler — the predictive-parser artifact beside :class:`ParserTables`.

:func:`compile_pda` turns a *lifted codegen grammar*
(``lift_optional_nullables(build_codegen_grammar(canonical))`` — the shape
:class:`~lexic.parsing.pda.analysis.GrammarAnalysis` runs on) into
:class:`PdaTables`: the per-(rule, hard-continuation) **clones** the runtime
walks, plus the island set and a lazy per-island :class:`ParserTables` cache
for the conflicted rules that fall back to Earley sub-parses.

**Clones (pivot 3).** A rule is compiled once per distinct *hard continuation*
that reaches it (its loop stop-sets are call-site-exact, pivot 4).
:meth:`_PdaCompiler.ensure_rule` reserves the clone key with a :data:`_PENDING`
placeholder before compiling, so recursion resolves to the in-progress key and
a repeat ``(name, tail)`` reuses the clone. Island rules are never cloned — a
reference carries an :class:`IslandRef` (a ``fail`` one raises
:class:`~lexic.parsing.pda.runtime.PdaFail`, forcing the engine fallback).

**Item specs.** Each item compiles to a flat :class:`ItemSpec`
(``lit``/``cc``/``ref``/``grp``) with its bounds and a loop gate —
:class:`StopGate` (pivot 4), :class:`PairGate` (pivot 6), :class:`KTupleGate`
(P2), :class:`PeekGate` (P3 char-set) or :class:`ScanGate` (P3 structured
noise-skip / P5 probe, folding-aware via :mod:`~lexic.parsing.pda.scanner`).
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
:class:`PdaProgram` the :class:`~lexic.parsing.pda.runtime.PdaKernel` walks. The
two stay in lockstep on :class:`PdaTables` (``.clones`` for introspection,
``.program`` for the hot loop).
"""

from __future__ import annotations

from typing import Mapping, NamedTuple, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction
from lexic.ir.base import IrAtom, IrLambda, IrLeaf, IrNoneType, IrSelf
from lexic.ir.mapping import IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRuleRef,
)
from lexic.ir.operators import IrNot
from lexic.parsing.earley.reduce import _OTHER_KIND, Reducer, _plan_for
from lexic.parsing.earley.tables import ParserTables, compile_tables
from lexic.parsing.fold import RuleFold
from lexic.parsing.pda.analysis import GrammarAnalysis
from lexic.parsing.pda.charsets import CharSet
from lexic.parsing.pda.delegate_compile import DelegateSource
from lexic.parsing.pda.flatten import (
    _BUILD_ALT,
    _BUILD_SEQ,
    _BUILD_TRANSPARENT,
    _BUILD_VALUE_STR,
    _GATE_KWIN,
    _GATE_PAIR,
    _GATE_PEEK,
    _GATE_SCAN,
    _GATE_STOP,
    _HI_UNBOUNDED,
    _MODE_CODE,
    _OP_CC,
    _OP_FAIL,
    _OP_GRP,
    _OP_ISLAND,
    _OP_LIT,
    _OP_REF,
    PdaProgram,
    _FlatArm,
    _FlatClone,
    _optimize_program,
)
from lexic.parsing.pda.reduce_pda import (
    ReduceComp,
    ReduceRun,
    _reduce_rewrite,
    _ReduceCompile,
)
from lexic.parsing.pda.scanner import ScanGate

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
        rule) — the reference raises :class:`~lexic.parsing.pda.runtime.PdaFail`
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
    (:attr:`~lexic.parsing.pda.analysis.Taxonomy.loop_gates`, never
    recomputed) — chess ``nonpawn``, separable at ``k = 3`` via rule-FOLLOW.

    :ivar windows: The ``taken`` windows — ``≤k``-length CharSet tuples.
    """

    windows: tuple[tuple[CharSet, ...], ...]


class PeekGate(NamedTuple):
    """A P3 noise-skip loop gate: skip the maximal ``W`` run without consuming,
    take another iteration iff the first post-noise char is in ``take``.

    Analysis-sourced (:attr:`~lexic.parsing.pda.analysis.Taxonomy
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

    :ivar kind: One of :data:`ITEM_KINDS`.
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
    gate: StopGate | PairGate | KTupleGate | PeekGate | ScanGate


class ArmSpec(NamedTuple):
    """One FIRST-gated arm of a rule clone or inline group.

    :ivar first: The arm's FIRST char set — the runtime selects this arm when
        the lookahead char is a member.
    :ivar specs: The arm's item specs, in order.
    :ivar windows: The arm's k-window selection set (analysis-sourced —
        :attr:`~lexic.parsing.pda.analysis.Taxonomy.arm_gates`), or ``None``;
        every gated arm of a P2-demoted alternation carries its own set.
    :ivar peek: The arm's P3 noise-skip ``(W, post-noise chars)`` selector
        (analysis-sourced — :attr:`~lexic.parsing.pda.analysis.Taxonomy
        .pn_arm_gates`), or ``None``; every gated arm of a P3-demoted
        alternation carries one (same ``W``).
    """

    first: CharSet
    specs: tuple[ItemSpec, ...]
    windows: tuple[tuple[CharSet, ...], ...] | None = None
    peek: tuple[CharSet, CharSet] | None = None


class GroupSpec(NamedTuple):
    """An inline ``(...)`` group's arm selection — the ``grp`` payload.

    :ivar arms: The FIRST-gated arms.
    :ivar default: The all-nullable default arm's specs, or ``None``.
    """

    arms: tuple[ArmSpec, ...]
    default: tuple[ItemSpec, ...] | None


class CloneSpec(NamedTuple):
    """One rule compiled for one hard continuation — a clone body.

    :ivar name: The rule name this clone stands for.
    :ivar arms: The FIRST-gated arms (after arm hoisting every non-empty arm
        selects on its own FIRST).
    :ivar default: The all-nullable default arm's specs, or ``None``.
    :ivar fold: The rule's baked :class:`~lexic.parsing.fold.RuleFold`, or
        ``None`` for a transparent helper clone.
    :ivar match_only: ``True`` for a ``value_str`` rule — pure-terminal
        interior, the runtime slices ``text[a:b]`` instead of building below.
    """

    name: str
    arms: tuple[ArmSpec, ...]
    default: tuple[ItemSpec, ...] | None
    fold: RuleFold | None
    match_only: bool


_PENDING = CloneSpec("", (), None, None, False)
"""In-progress placeholder installed by :meth:`_PdaCompiler.ensure_rule` before
a clone body is compiled — reserves the key so recursion resolves to it, then
is overwritten by the finished :class:`CloneSpec`."""

_EOF: CharSet = CharSet.from_chars("")
"""The start clone's hard continuation — end-of-input only (the ``""``
sentinel), mirroring the FOLLOW-set seed in :mod:`lexic.parsing.pda.analysis`."""


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
    arms, default = compiler.compile_arms(cast(IrAlternation, n), eff)
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
        "islands",
        "fail_islands",
        "clones",
        "reduce",
        "completions",
    )

    analysis: GrammarAnalysis
    fold_config: Mapping[str, RuleFold]
    islands: frozenset[str]
    fail_islands: frozenset[str]
    clones: dict[CloneKey, CloneSpec]
    reduce: "_ReduceCompile | None"
    completions: dict[CloneKey, ReduceComp]

    def __init__(
        self,
        analysis: GrammarAnalysis,
        fold_config: Mapping[str, RuleFold] | None = None,
        *,
        reduce: "_ReduceCompile | None" = None,
    ) -> None:
        """Prepare the compiler for one target (model fold, or reduce)."""
        self.analysis = analysis
        self.fold_config = fold_config or {}
        self.islands = analysis.islands
        self.fail_islands = analysis.fail_islands
        self.clones = {}
        self.reduce = reduce
        self.completions = {}

    def compile_start(self) -> CloneKey | IslandRef:
        """Compile the start clone (EOF-only tail), or return the
        :class:`IslandRef` opt-out when the start rule is itself an island."""
        start = self.analysis.start
        if start in self.islands:
            return IslandRef(start, start in self.fail_islands)
        return self.ensure_rule(start, _EOF)

    def ensure_rule(self, name: str, tail: CharSet) -> CloneKey:
        """Compile (or reuse) the clone of ``name`` for continuation ``tail``.

        Cycle-safe: the key is reserved with :data:`_PENDING` before the body is
        compiled, so a recursive reference resolves to it; a second call with
        the same key reuses the finished clone. ``name`` is never an island —
        callers check first.
        """
        key = CloneKey(name, tail)
        if key in self.clones:
            return key
        self.clones[key] = _PENDING
        rule = self.analysis.rules[name]
        tax = self.analysis.taxonomy
        arms, default = self.compile_arms(
            rule.body, tail, tax.arm_gates.get(name), tax.pn_arm_gates.get(name)
        )
        fold = self.fold_config.get(name)
        match_only = fold is not None and fold.kind == "value_str"
        self.clones[key] = CloneSpec(name, arms, default, fold, match_only)
        if self.reduce is not None:
            self.completions[key] = self.reduce.comp_for(name)
        return key

    def compile_arms(
        self,
        node: IrAlternation,
        tail: CharSet,
        windows: "tuple[tuple[tuple[CharSet, ...], ...], ...] | None" = None,
        peeks: "tuple[CharSet, tuple[CharSet, ...]] | None" = None,
    ) -> tuple[tuple[ArmSpec, ...], tuple[ItemSpec, ...] | None]:
        """Compile the arms of a rule body or inline group against ``tail``.

        Each arm becomes a FIRST-gated :class:`ArmSpec` (dropped when its FIRST
        is empty — an empty arm never gates); an all-nullable arm additionally
        becomes the single default (last such arm wins). ``windows`` (P2) /
        ``peeks`` (P3) — a demoted rule body's stored gate spec, aligned to
        ``node``'s arms — are attached inside this same enumeration, so
        spec↔arm alignment cannot drift past the empty-FIRST drop.

        :returns: ``(gated arms, default specs | None)``.
        :raises UnsupportedConstructError: When gated arms' FIRSTs overlap with
            no gate spec to select by (analysis/compiler drift — a wrong arm
            would silently mis-parse, so the grammar opts out instead).
        """
        arms: list[ArmSpec] = []
        default: tuple[ItemSpec, ...] | None = None
        for idx, arm in enumerate(node):
            items = _items(arm)
            specs = self._compile_seq(items, tail)
            first = self.analysis.seq_first(items)
            if all(self.analysis.item_nullable(i) for i in items):
                default = specs
            if not first.is_empty():
                win = windows[idx] if windows is not None else None
                peek = (peeks[0], peeks[1][idx]) if peeks is not None else None
                arms.append(ArmSpec(first, specs, win, peek))
        if windows is None and peeks is None and _firsts_overlap(arms):
            raise UnsupportedConstructError(
                "pda: arm FIRST overlap without a gate spec"
            )
        return tuple(arms), default

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
        (:attr:`~lexic.parsing.pda.analysis.Taxonomy.loop_gates` — the demoted
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
        return _BUILD_TRANSPARENT
    kind = fold.kind
    if kind == "value_str":
        return _BUILD_VALUE_STR
    if kind == "alternation":
        return _BUILD_ALT
    if kind == "sequence":
        return _BUILD_SEQ
    raise UnsupportedConstructError(f"pda: unknown fold kind {kind!r}")


def _flatten_gate(
    gate: StopGate | PairGate | KTupleGate | PeekGate | ScanGate,
) -> tuple[int, object]:
    """Lower a loop gate to its ``(code, data)`` flat pair."""
    if isinstance(gate, PairGate):
        return _GATE_PAIR, gate.pairs
    if isinstance(gate, KTupleGate):
        return _GATE_KWIN, _flat_windows(gate.windows)
    if isinstance(gate, PeekGate):
        return _GATE_PEEK, (
            (gate.w.chars, gate.w.negated),
            (gate.take.chars, gate.take.negated),
        )
    if isinstance(gate, ScanGate):
        return _GATE_SCAN, gate  # runtime-ready; scan_gate_take reads it directly
    cs = gate.charset
    return _GATE_STOP, (cs.chars, cs.negated)


def _flatten_arm(
    specs: Sequence[ItemSpec], shells: "dict[CloneKey, _FlatClone]"
) -> _FlatArm:
    """Lower a sequence of :class:`ItemSpec` to a :class:`_FlatArm` (refs
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
        his.append(_HI_UNBOUNDED if spec.hi is None else spec.hi)
        gate_kind, gate_body = _flatten_gate(spec.gate)
        gate_kinds.append(gate_kind)
        gate_data.append(gate_body)
    arm = _FlatArm.__new__(_FlatArm)
    arm.n = len(kinds)
    arm.kinds = tuple(kinds)
    arm.payloads = tuple(payloads)
    arm.los = tuple(los)
    arm.his = tuple(his)
    arm.gate_kinds = tuple(gate_kinds)
    arm.gate_data = tuple(gate_data)
    return arm


def _flatten_item(
    spec: ItemSpec, shells: "dict[CloneKey, _FlatClone]"
) -> tuple[int, object]:
    """Lower one :class:`ItemSpec` to its ``(op-code, payload)`` flat pair."""
    kind = spec.kind
    payload = spec.payload
    if kind == LIT:
        return _OP_LIT, str(payload)
    if kind == CC:
        cs = cast(CharSet, payload)
        return _OP_CC, (cs.chars, cs.negated)
    if kind == GRP:
        return _OP_GRP, _flatten_group(cast(GroupSpec, payload), shells)
    target = payload  # REF
    if isinstance(target, IslandRef):
        return (_OP_FAIL if target.fail else _OP_ISLAND), target.name
    return _OP_REF, shells[cast(CloneKey, target)]


def _bake_build(clone: _FlatClone, fold: RuleFold | None) -> None:
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
    clone.fields = tuple(
        (f.item, _MODE_CODE[f.mode], f.name, f.lo) for f in fold.fields
    )
    clone.fast = fold.fast.make
    clone.defaults = dict(fold.fast.defaults)


def _flatten_selectors(
    arms: Sequence[ArmSpec], shells: "dict[CloneKey, _FlatClone]"
) -> tuple[tuple[tuple[frozenset[str], bool, _FlatArm], ...], object, object]:
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


def _flatten_group(
    group: GroupSpec, shells: "dict[CloneKey, _FlatClone]"
) -> _FlatClone:
    """Lower an inline group to a transparent :class:`_FlatClone`."""
    clone = _FlatClone.__new__(_FlatClone)
    clone.selectors, clone.kwin_selectors, clone.pn_selectors = _flatten_selectors(
        group.arms, shells
    )
    clone.default = (
        _flatten_arm(group.default, shells) if group.default is not None else None
    )
    clone.mode = _BUILD_TRANSPARENT
    _bake_build(clone, None)
    return clone


def _flatten_clones(
    clones: "dict[CloneKey, CloneSpec]",
    completions: "dict[CloneKey, ReduceComp] | None",
) -> "dict[CloneKey, _FlatClone]":
    """Lower a compiled clone table to its live :class:`_FlatClone` shells.

    Two passes: create an empty shell per clone key, then fill each (refs
    resolve to the live shells — no runtime id lookup). The model target then
    runs :func:`_optimize_program`; the reduce target (``completions`` given)
    runs :func:`_reduce_rewrite` instead. Shared by :func:`_flatten_program`
    and the per-island delegate compile, which each own an independent shell
    set the optimiser mutates in place.
    """
    shells: dict[CloneKey, _FlatClone] = {
        key: _FlatClone.__new__(_FlatClone) for key in clones
    }
    for key, spec in clones.items():
        clone = shells[key]
        clone.selectors, clone.kwin_selectors, clone.pn_selectors = _flatten_selectors(
            spec.arms, shells
        )
        clone.default = (
            _flatten_arm(spec.default, shells) if spec.default is not None else None
        )
        clone.mode = _build_mode(spec.fold)
        _bake_build(clone, spec.fold)
    if completions is None:
        _optimize_program(list(shells.values()))
    else:
        _reduce_rewrite(shells, completions)
    return shells


def _flatten_program(
    clones: "dict[CloneKey, CloneSpec]",
    start_key: "CloneKey | IslandRef",
    completions: "dict[CloneKey, ReduceComp] | None" = None,
) -> PdaProgram:
    """Lower the compiled clone table to the flat runtime :class:`PdaProgram`
    (``completions`` given on the reduce path, ``None`` on the model path)."""
    shells = _flatten_clones(clones, completions)
    start: _FlatClone | IslandRef = (
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
        :attr:`~lexic.parsing.pda.analysis.GrammarAnalysis.islands`).
    :ivar instance_grammar: The Earley-normalised instance grammar island
        tables are built over.
    :ivar program: The flat int-coded runtime program (:class:`PdaProgram`)
        :class:`~lexic.parsing.pda.runtime.PdaKernel` walks.
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
    reduce: "ReduceRun | None"
    _island_tables: dict[str, ParserTables]

    def __init__(
        self,
        compiler: "_PdaCompiler",
        start_key: CloneKey | IslandRef,
        instance_grammar: IrAst,
        reduce: "ReduceRun | None" = None,
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

    def island_tables(self, name: str) -> ParserTables:
        """The :class:`ParserTables` for island rule ``name``, built once and
        cached — compiled over :attr:`instance_grammar` with ``name`` as the
        start rule (the Earley sub-parser for a conflicted rule)."""
        cached = self._island_tables.get(name)
        if cached is None:
            cached = compile_tables(IrAst(self.instance_grammar.rules, name))
            self._island_tables[name] = cached
        return cached

    def island_delegates(self, name: str) -> "dict[int, _FlatClone]":
        """The island-interior delegate clones for island ``name`` (rule_id →
        clone), computed once by the program's
        :class:`~lexic.parsing.pda.delegate_compile.DelegateSource` — empty when
        nothing delegates. The runtime wraps each into a fail-soft callable and
        threads it through the island Earley sub-parse (the keys are island
        tables rule ids, the predictor's ``rid``)."""
        return cast("dict[int, _FlatClone]", self.program.delegates.for_island(name))

    def reset_delegate_cache(self) -> None:
        """Drop the per-island delegate cache — a test seam for the A/B parity
        gate, which toggles ``DELEGATES_ENABLED`` and recomputes each side."""
        self.program.delegates.reset()


def _attach_delegates(
    tables: PdaTables, lifted: IrAst, compiler: "_PdaCompiler"
) -> None:
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

    :returns: The compiled :class:`PdaTables` (its :attr:`~PdaTables.reduce` set).
    :raises UnsupportedConstructError: On an atom the clone compiler cannot
        handle, a custom rule noise policy, or a custom terminal-leaf policy the
        reduce runtime cannot reconstruct (the whole-grammar opt-out).
    """
    tables = compile_tables(instance_grammar)
    plan = _plan_for(reducer, tables)
    if plan.literal_kind == _OTHER_KIND:
        raise UnsupportedConstructError("reduce: custom terminal-leaf policy")
    name_to_rid = {name: rid for rid, name in enumerate(tables.decode.rule_names)}
    analysis = GrammarAnalysis(lifted)
    compiler = _PdaCompiler(analysis, reduce=_ReduceCompile(reducer, plan, name_to_rid))
    start_key = compiler.compile_start()
    run = ReduceRun(reducer, plan, tables, name_to_rid)
    pda = PdaTables(compiler, start_key, instance_grammar, reduce=run)
    _attach_delegates(pda, lifted, compiler)
    return pda
