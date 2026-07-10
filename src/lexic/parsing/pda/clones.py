"""Clone compiler — the predictive-parser artifact beside :class:`ParserTables`.

:func:`compile_pda` turns a *lifted codegen grammar* (the same shape
:class:`~lexic.parsing.pda.analysis.GrammarAnalysis` runs on —
``lift_optional_nullables(build_codegen_grammar(canonical))``) into
:class:`PdaTables`: the per-(rule, hard-continuation) **clones** a
deterministic table-driven parser (Task 4's runtime) walks, plus the island
set and a lazy per-island :class:`ParserTables` cache for the conflicted rules
that fall back to Earley sub-parses.

**Clones (pivot 3).** A rule is compiled once per distinct *hard continuation*
that reaches it, because the loop stop-sets it bakes are call-site-exact
(pivot 4). :meth:`_PdaCompiler.ensure_rule` reserves the clone key before
compiling the body (a :data:`_PENDING` placeholder), so a recursive reference
resolves to the in-progress key rather than looping; a second reference with
the same ``(name, tail)`` reuses the same clone. Island rules are never cloned
— a reference to one carries an :class:`IslandRef` marker instead of a
:class:`CloneKey`. A **fail-island** reference (``IslandRef.fail`` — a semantic
F1 stop-set-escape rule, from
:attr:`~lexic.parsing.pda.analysis.GrammarAnalysis.fail_islands`) is not even
parsed: the runtime raises :class:`~lexic.parsing.pda.runtime.PdaFail` so the
compile seam falls back to the full engine rather than risk a silently divergent
longest-match split.

**Item specs.** Each item compiles to a flat, tuple-coded :class:`ItemSpec`
(``lit`` / ``cc`` / ``ref`` / ``grp``) carrying its quantifier bounds and a
loop gate — a :class:`StopGate` (non-greedy on ``FIRST(atom) − continuation``,
pivot 4) or an :class:`PairGate` (an LL(2) 2-char prefix set, pivot 6). Arm
selection (rule body and inline group) is a list of FIRST-gated
:class:`ArmSpec` plus at most one nullable default arm. Every rule clone bakes
its :class:`~lexic.parsing.fold.RuleFold` so Task 4's fused runtime needs no
per-parse config lookup; a ``value_str`` clone is flagged
:attr:`~CloneSpec.match_only` (its interior is pure-terminal — the runtime
slices ``text[a:b]`` rather than building sub-models).

**Open dispatch, no isinstance ladders.** Per-atom-type compilation routes
through the module-level :data:`_ATOM_SPEC` :class:`~lexic.ir.mapping.IrTypeMap`
whose bodies are :class:`~lexic.ir.base.IrLambda` leaves — the ``analysis.py``
idiom: the atom is dispatched, the compiler rides the dispatcher slot ``d``,
and the per-item context (bounds, gate, continuation) rides ``nc`` on a small
:class:`_ItemCtx` cursor. An unregistered atom type misses every table and
raises :exc:`~lexic.exceptions.UnsupportedConstructError` (via ``IrTypeMap``'s
:exc:`~lexic.exceptions.IrKeyError`) — the Task-6 seam converts that to "no PDA
for this grammar".

The spec NamedTuples are the compiler's *intermediate* (and the shape the
structural tests pin). :func:`_flatten_program` lowers them, once per
:func:`compile_pda`, into the flat int-coded :class:`PdaProgram`
(:class:`_FlatClone` / :class:`_FlatArm`, ``_OP_*`` op-codes, pre-resolved
``(chars, negated)`` membership sets) that :class:`~lexic.parsing.pda.runtime.PdaKernel`
walks with integer dispatch — the ``tables.py``/``kernel.py`` philosophy. The
lowering is a build-time cost only; the two representations are kept in lockstep
on :class:`PdaTables` (``.clones`` for islands/introspection, ``.program`` for
the hot loop).
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
from lexic.parsing.earley.tables import ParserTables, compile_tables
from lexic.parsing.fold import RuleFold
from lexic.parsing.pda.analysis import GrammarAnalysis
from lexic.parsing.pda.charsets import CharSet
from lexic.parsing.pda.flatten import (
    _BUILD_ALT,
    _BUILD_SEQ,
    _BUILD_TRANSPARENT,
    _BUILD_VALUE_STR,
    _GATE_PAIR,
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

__all__ = [
    "compile_pda",
    "PdaTables",
    "PdaProgram",
    "CloneSpec",
    "CloneKey",
    "IslandRef",
    "ItemSpec",
    "ArmSpec",
    "GroupSpec",
    "StopGate",
    "PairGate",
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

    Hashable (``str`` + frozen :class:`CharSet`), so it keys
    :attr:`PdaTables.clones` and rides a ``ref`` :class:`ItemSpec` as its
    resolved target.

    :ivar name: The rule name.
    :ivar tail: The hard continuation the clone's loop stop-sets are exact for.
    """

    name: str
    tail: CharSet


class IslandRef(NamedTuple):
    """A reference to an island rule — not cloned; parsed by Earley sub-parse.

    The ``ref`` :class:`ItemSpec` target for a rule in :attr:`PdaTables.islands`;
    the runtime resolves it via :meth:`PdaTables.island_tables` rather than a
    clone — unless :attr:`fail` is set, when the reference instead raises
    :class:`~lexic.parsing.pda.runtime.PdaFail` so the compile seam falls back to
    the full engine (a semantic F1 stop-set-escape rule, whose longest-match
    split would silently diverge — see
    :attr:`~lexic.parsing.pda.analysis.GrammarAnalysis.fail_islands`).

    :ivar name: The island rule name.
    :ivar fail: When ``True``, a fail-island — the reference raises ``PdaFail``
        rather than being parsed by longest-match.
    """

    name: str
    fail: bool = False


# ── loop gates (pivot 4 / pivot 6) ────────────────────────────────────────


class StopGate(NamedTuple):
    """A non-greedy single-char loop gate: continue while the next char matches.

    The stop-set semantics of pivot 4 — the loop keeps consuming while the
    lookahead char is in ``charset`` (``FIRST(atom) − hard-continuation``) and
    stops the moment the continuation could begin.

    :ivar charset: The chars that keep the loop going.
    """

    charset: CharSet


class PairGate(NamedTuple):
    """An LL(2) loop gate: continue while the next two chars are a taken prefix.

    The pivot-6 discriminator for an optional atom whose FIRST collides with
    its continuation (chess ``fxf5`` vs ``f5``) — the loop takes another
    iteration only when ``text[pos:pos+2]`` is in ``pairs``.

    :ivar pairs: The 2-char prefixes that select "take another iteration".
    """

    pairs: frozenset[str]


# ── item and arm specs ────────────────────────────────────────────────────


class ItemSpec(NamedTuple):
    """One compiled arm item — flat, tuple-coded, production-named.

    :ivar kind: One of :data:`ITEM_KINDS`.
    :ivar payload: The kind-specific body: the literal ``str`` (``lit``), the
        member :class:`CharSet` (``cc``), the resolved :class:`CloneKey` /
        :class:`IslandRef` target (``ref``), or the :class:`GroupSpec`
        (``grp``).
    :ivar lo: The quantifier lower bound (mandatory iterations).
    :ivar hi: The quantifier upper bound, or ``None`` (unbounded).
    :ivar gate: The loop-continuation gate consulted past the ``lo``
        mandatory iterations.
    """

    kind: str
    payload: str | CharSet | CloneKey | IslandRef | GroupSpec
    lo: int
    hi: int | None
    gate: StopGate | PairGate


class ArmSpec(NamedTuple):
    """One FIRST-gated arm of a rule clone or inline group.

    :ivar first: The arm's FIRST char set — the runtime selects this arm when
        the lookahead char is a member.
    :ivar specs: The arm's item specs, in order.
    """

    first: CharSet
    specs: tuple[ItemSpec, ...]


class GroupSpec(NamedTuple):
    """An inline ``(...)`` group's arm selection — the ``grp`` payload.

    :ivar arms: The FIRST-gated arms.
    :ivar default: The all-nullable default arm's specs, or ``None`` when the
        group has no nullable arm.
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
        ``None`` for a helper rule with no fold config (a transparent,
        no-constructor clone the runtime descends through).
    :ivar match_only: ``True`` for a ``value_str`` rule — its interior is
        pure-terminal, so the runtime matches to find the span end and slices
        ``text[a:b]`` instead of building sub-models below it.
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
    """The :class:`IrItem` members of a sequence arm, in order.

    :param seq: A sequence arm (or any node sequence).
    :returns: Its :class:`IrItem` children — anything else is skipped.
    """
    return [i for i in seq if isinstance(i, IrItem)]


def _hi(item: IrItem) -> int | None:
    """The item's quantifier upper bound as an ``int``, or ``None`` (unbounded).

    :param item: The quantified item.
    :returns: ``int(hi)``, or ``None`` for the unbounded sentinel.
    """
    hi = item.quantifier.hi
    return None if isinstance(hi, IrNoneType) else int(hi)


# ── per-item context cursor (rides the argument channel) ───────────────────


class _ItemCtx(IrLeaf[IrSelf, IrSelf]):
    """The per-item compile context the :data:`_ATOM_SPEC` bodies read off ``nc``.

    Rides ``nc`` so the atom-type bodies build their :class:`ItemSpec` without
    threading the bounds, gate and continuation as extra positional arguments
    through the typed dispatch protocol.

    :ivar lo: The item's quantifier lower bound.
    :ivar hi: The item's quantifier upper bound, or ``None``.
    :ivar cont: The item's hard continuation (the loop-gate / ref-tail base).
    :ivar gate: The precomputed loop-continuation gate.
    """

    __slots__ = ("lo", "hi", "cont", "gate")

    lo: int
    hi: int | None
    cont: CharSet
    gate: StopGate | PairGate

    def __init__(
        self, lo: int, hi: int | None, cont: CharSet, gate: StopGate | PairGate
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
    """Compile ``IrNot(charclass)`` to a co-finite ``cc`` spec (polarity flipped).

    :raises UnsupportedConstructError: If the negation wraps anything other
        than an :class:`IrCharClass`.
    """
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

    A reference to an island rule carries an :class:`IslandRef` (flagged
    :attr:`~IslandRef.fail` for a fail-island — a semantic F1 escape); otherwise
    the target clone's tail is the item's hard continuation, widened by the
    atom's own hard-FIRST when the reference repeats (it may follow itself), and
    the clone is compiled (or reused) via :meth:`_PdaCompiler.ensure_rule`.
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

    Holds the compile-time state (the growing ``clones`` table, the analysis,
    the island set, the baked fold config) and IS the dispatcher slot ``d``
    handed to every :data:`_ATOM_SPEC` body, whose ``ensure_rule`` /
    ``compile_arms`` / ``analysis`` / ``islands`` it reads directly.

    :ivar analysis: The grammar analysis (FIRST/hard/FOLLOW/nullability +
        loop taxonomy) the clones are cut against.
    :ivar fold_config: Rule name → its :class:`~lexic.parsing.fold.RuleFold`.
    :ivar islands: The island rule names — never cloned.
    :ivar fail_islands: The fail-island subset — references raise ``PdaFail``.
    :ivar clones: The compiled clone table, keyed by :class:`CloneKey`.
    """

    __slots__ = ("analysis", "fold_config", "islands", "fail_islands", "clones")

    analysis: GrammarAnalysis
    fold_config: Mapping[str, RuleFold]
    islands: frozenset[str]
    fail_islands: frozenset[str]
    clones: dict[CloneKey, CloneSpec]

    def __init__(
        self, analysis: GrammarAnalysis, fold_config: Mapping[str, RuleFold]
    ) -> None:
        """:param analysis: the grammar analysis; :param fold_config: the fold table."""
        self.analysis = analysis
        self.fold_config = fold_config
        self.islands = analysis.islands
        self.fail_islands = analysis.fail_islands
        self.clones = {}

    def compile_start(self) -> CloneKey | IslandRef:
        """Compile the start clone (EOF-only tail), or mark the start an island.

        :returns: The start :class:`CloneKey`, or an :class:`IslandRef` when the
            start rule is itself an island (the Task-6 whole-grammar opt-out),
            flagged :attr:`~IslandRef.fail` for a fail-island start.
        """
        start = self.analysis.start
        if start in self.islands:
            return IslandRef(start, start in self.fail_islands)
        return self.ensure_rule(start, _EOF)

    def ensure_rule(self, name: str, tail: CharSet) -> CloneKey:
        """Compile (or reuse) the clone of ``name`` for continuation ``tail``.

        Cycle-safe: the key is reserved with :data:`_PENDING` before the body is
        compiled, so a recursive reference resolves to it; a second call with
        the same key reuses the finished clone.

        :param name: The rule to clone (never an island — callers check first).
        :param tail: The clone's hard continuation.
        :returns: The clone's key.
        """
        key = CloneKey(name, tail)
        if key in self.clones:
            return key
        self.clones[key] = _PENDING
        rule = self.analysis.rules[name]
        arms, default = self.compile_arms(rule.body, tail)
        fold = self.fold_config.get(name)
        match_only = fold is not None and fold.kind == "value_str"
        self.clones[key] = CloneSpec(name, arms, default, fold, match_only)
        return key

    def compile_arms(
        self, node: IrAlternation, tail: CharSet
    ) -> tuple[tuple[ArmSpec, ...], tuple[ItemSpec, ...] | None]:
        """Compile the arms of a rule body or inline group against ``tail``.

        Each arm becomes a FIRST-gated :class:`ArmSpec` (dropped when its FIRST
        is empty — an empty arm never gates); an all-nullable arm additionally
        becomes the single default (last such arm wins).

        :param node: The :class:`IrAlternation` (rule body or inline group).
        :param tail: The continuation the arms' items are cut against.
        :returns: ``(gated arms, default specs | None)``.
        """
        arms: list[ArmSpec] = []
        default: tuple[ItemSpec, ...] | None = None
        for arm in node:
            items = _items(arm)
            specs = self._compile_seq(items, tail)
            first = self.analysis.seq_first(items)
            if all(self.analysis.item_nullable(i) for i in items):
                default = specs
            if not first.is_empty():
                arms.append(ArmSpec(first, specs))
        return tuple(arms), default

    def _compile_seq(
        self, items: Sequence[IrItem], tail: CharSet
    ) -> tuple[ItemSpec, ...]:
        """Compile a sequence of items, each cut against its hard continuation."""
        analysis = self.analysis
        return tuple(
            self._compile_item(
                item, analysis.hard_cont_at(items, k, tail), items[k + 1 :]
            )
            for k, item in enumerate(items)
        )

    def _compile_item(
        self, item: IrItem, cont: CharSet, rest: Sequence[IrItem]
    ) -> ItemSpec:
        """Compile one item to its :class:`ItemSpec` via the atom dispatch table.

        :param item: The quantified item.
        :param cont: The item's hard continuation (loop-gate / ref-tail base).
        :param rest: The items following ``item`` in the arm (the LL(2) skip
            side).
        :returns: The item's spec.
        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        atom = item.atom
        lo = int(item.quantifier.lo)
        hi = _hi(item)
        gate = self._loop_gate(item, cont, rest)
        ctx = _ItemCtx(lo, hi, cont, gate)
        return cast(ItemSpec, _ATOM_SPEC.resolve(atom).eval(self, atom, (ctx,)))

    def _loop_gate(
        self, item: IrItem, cont: CharSet, rest: Sequence[IrItem]
    ) -> StopGate | PairGate:
        """The loop-continuation gate — a stop-set, or an LL(2) pair set.

        Defaults to the non-greedy stop-set (``FIRST(atom) − continuation``); a
        looping item whose FIRST overlaps its continuation upgrades to an LL(2)
        :class:`PairGate` when the taxonomy says ``pairs`` (a ``stopset`` /
        ``island`` verdict keeps the stop-set — an island's enclosing rule is
        not cloned, so reaching it here is the non-gatable fallback).

        :param item: The quantified item.
        :param cont: The item's hard continuation.
        :param rest: The items following ``item`` in the arm (the LL(2) skip side).
        :returns: The loop gate.
        """
        analysis = self.analysis
        lo = int(item.quantifier.lo)
        hi = _hi(item)
        first = analysis.atom_first(item.atom)
        if (hi is None or hi > lo) and first.overlaps(cont):
            policy = analysis.loop_policy(item, list(rest))
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


def _flatten_gate(gate: StopGate | PairGate) -> tuple[int, object]:
    """Lower a loop gate to its ``(code, data)`` flat pair."""
    if isinstance(gate, PairGate):
        return _GATE_PAIR, gate.pairs
    cs = gate.charset
    return _GATE_STOP, (cs.chars, cs.negated)


def _flatten_arm(
    specs: Sequence[ItemSpec], shells: "dict[CloneKey, _FlatClone]"
) -> _FlatArm:
    """Lower a sequence of :class:`ItemSpec` to a :class:`_FlatArm`.

    :param specs: The arm's item specs, in order.
    :param shells: The clone-key → :class:`_FlatClone` map (refs resolve to the
        live shell object, so recursion needs no id indirection).
    :returns: The flattened arm.
    """
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
    """Bake a clone's fold and fused-build plan (fields/fast/defaults) in place.

    :param clone: The clone (or group) being filled.
    :param fold: Its :class:`~lexic.parsing.fold.RuleFold`, or ``None``.
    """
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


def _flatten_group(
    group: GroupSpec, shells: "dict[CloneKey, _FlatClone]"
) -> _FlatClone:
    """Lower an inline group to a transparent :class:`_FlatClone`."""
    clone = _FlatClone.__new__(_FlatClone)
    clone.selectors = tuple(
        (arm.first.chars, arm.first.negated, _flatten_arm(arm.specs, shells))
        for arm in group.arms
    )
    clone.default = (
        _flatten_arm(group.default, shells) if group.default is not None else None
    )
    clone.mode = _BUILD_TRANSPARENT
    _bake_build(clone, None)
    return clone


def _flatten_program(
    clones: "dict[CloneKey, CloneSpec]", start_key: "CloneKey | IslandRef"
) -> PdaProgram:
    """Lower the compiled clone table to the flat runtime :class:`PdaProgram`.

    Two passes: create an empty :class:`_FlatClone` shell per clone key, then
    fill each (its refs resolve to the live shells, so a recursive reference
    holds the target object directly — no runtime id lookup).

    :param clones: The compiled clone table (:meth:`_PdaCompiler` output).
    :param start_key: The start clone key, or an :class:`IslandRef` opt-out.
    :returns: The flat program.
    """
    shells: dict[CloneKey, _FlatClone] = {
        key: _FlatClone.__new__(_FlatClone) for key in clones
    }
    for key, spec in clones.items():
        clone = shells[key]
        clone.selectors = tuple(
            (arm.first.chars, arm.first.negated, _flatten_arm(arm.specs, shells))
            for arm in spec.arms
        )
        clone.default = (
            _flatten_arm(spec.default, shells) if spec.default is not None else None
        )
        clone.mode = _build_mode(spec.fold)
        _bake_build(clone, spec.fold)
    _optimize_program(list(shells.values()))
    start: _FlatClone | IslandRef = (
        shells[start_key] if isinstance(start_key, CloneKey) else start_key
    )
    return PdaProgram(start)


# ── the artifact ───────────────────────────────────────────────────────────


class PdaTables(IrLeaf[IrSelf, IrSelf]):
    """The compiled predictive-parser artifact — the sibling of :class:`ParserTables`.

    Owns the clone table, the start key, the island set, and a lazy per-island
    :class:`ParserTables` cache (Task 4/5's runtime resolves island references
    through :meth:`island_tables`). The clone table is complete and immutable
    after :func:`compile_pda`; only the island cache fills lazily (in place, the
    :class:`ParserTables` scanning-cache precedent).

    :ivar clones: Clone key → its :class:`CloneSpec`.
    :ivar start_key: The start clone's key, or an :class:`IslandRef` when the
        start rule is an island (the whole-grammar opt-out signal for Task 6).
    :ivar islands: The island rule names (from
        :attr:`~lexic.parsing.pda.analysis.GrammarAnalysis.islands`).
    :ivar instance_grammar: The Earley-normalised instance grammar island
        tables are built over.
    :ivar program: The flat int-coded runtime program
        (:class:`PdaProgram`) :class:`~lexic.parsing.pda.runtime.PdaKernel`
        walks — the compiled clone table lowered once for the hot loop.
    """

    __slots__ = (
        "clones",
        "start_key",
        "islands",
        "instance_grammar",
        "program",
        "_island_tables",
    )

    clones: dict[CloneKey, CloneSpec]
    start_key: CloneKey | IslandRef
    islands: frozenset[str]
    instance_grammar: IrAst
    program: PdaProgram
    _island_tables: dict[str, ParserTables]

    def __init__(
        self,
        clones: dict[CloneKey, CloneSpec],
        start_key: CloneKey | IslandRef,
        islands: frozenset[str],
        instance_grammar: IrAst,
    ) -> None:
        """Freeze the clone table, lower it to the flat program, seed the cache."""
        self.clones = clones
        self.start_key = start_key
        self.islands = islands
        self.instance_grammar = instance_grammar
        self.program = _flatten_program(clones, start_key)
        self._island_tables = {}

    def island_tables(self, name: str) -> ParserTables:
        """The :class:`ParserTables` for island rule ``name``, built once and cached.

        Compiled over :attr:`instance_grammar` with ``name`` as the start rule —
        the Earley sub-parser the runtime runs for a conflicted rule.

        :param name: The island rule name.
        :returns: Its compiled tables (memoised per island rule).
        """
        cached = self._island_tables.get(name)
        if cached is None:
            cached = compile_tables(IrAst(self.instance_grammar.rules, name))
            self._island_tables[name] = cached
        return cached


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
    :raises UnsupportedConstructError: On an atom the analysis or the clone
        compiler cannot handle (the Task-6 seam reads this as "no PDA for this
        grammar").
    """
    analysis = GrammarAnalysis(lifted)
    compiler = _PdaCompiler(analysis, fold_config)
    start_key = compiler.compile_start()
    return PdaTables(compiler.clones, start_key, compiler.islands, instance_grammar)
