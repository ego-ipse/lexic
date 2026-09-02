"""Lowering — a compiled clone set into the flat int-coded program.

The step between the compiler's records and the runtime's arrays: every gate,
arm, item and selector becomes ints in one pass. What it produces is defined in
``flatten``; what it consumes comes from ``clones``.
"""

from __future__ import annotations

from typing import Any, NamedTuple, Sequence, cast

from lexic.parsing.binding import ModelBinding
from lexic.parsing.pda.compiler.program.flatten import (
    FlatArm,
    FlatClone,
    PdaProgram,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_DISPATCH,
    GATE_ATTEMPT,
    GATE_KWIN,
    GATE_PAIR,
    GATE_PEEK,
    GATE_SCAN,
    GATE_STOP,
    HI_UNBOUNDED,
    OP_AVDISP,
    OP_AVSTR,
    OP_CC,
    OP_CC1,
    OP_FAIL,
    OP_GRP,
    OP_ISLAND,
    OP_LEAF1,
    OP_LIT,
    OP_LIT1,
    OP_REF,
    OP_REF1,
    OP_V1,
    OP_VDISP,
    OP_VRUN,
    OP_VSTR,
)
from lexic.parsing.pda.compiler.eligibility import extent_pattern
from lexic.parsing.pda.compiler.program.product import bake_product_build
from lexic.parsing.pda.compiler.program.specialize import (
    convert_dispatch,
    optimize_program,
)
from lexic.parsing.pda.compiler.specs import (
    CC,
    GRP,
    LIT,
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
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import (
    Pattern,
    ScanGate,
    class_source,
    compile_admission,
    compile_source,
    literal_source,
)
from lexic.parsing.product import ConstructionTables


def _flat_windows(
    windows: tuple[tuple[CharSet, ...], ...],
) -> tuple[tuple[tuple[frozenset[str], bool], ...], ...]:
    """Pre-resolve CharSet windows to the ``((chars, negated), ...)`` flat form."""
    return tuple(tuple((cs.chars, cs.negated) for cs in win) for win in windows)


def _flatten_gate(
    gate: StopGate | AttemptGate | PairGate | KTupleGate | PeekGate | ScanGate,
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
    if isinstance(gate, AttemptGate):
        return GATE_ATTEMPT, (
            (gate.charset.chars, gate.charset.negated),
            (gate.follow.chars, gate.follow.negated),
        )
    cs = gate.charset
    return GATE_STOP, (cs.chars, cs.negated)


class Lowering(NamedTuple):
    """The lowering walk's two accumulators, carried as one.

    :ivar shells: Clone key → its live shell; a ``ref`` payload resolves here,
        so recursion needs no id indirection.
    :ivar groups: Every ATTEMPTING inline-group clone, paired with the arm
        specs its entries are built from. Filled during the walk and drained
        after :func:`~lexic.parsing.pda.compiler.program.specialize.optimize_program`,
        because an attempt's sub-clones copy their parent's FINAL baked state —
        and unlike a rule clone, a group has no key the second pass could look
        it up by.
    """

    shells: dict[CloneKey, FlatClone]
    groups: list[tuple[FlatClone, tuple[ArmSpec, ...]]]


def _flatten_arm(specs: Sequence[ItemSpec], low: Lowering) -> FlatArm:
    """Lower a sequence of :class:`ItemSpec` to a :class:`FlatArm` (refs
    resolve to the live shell objects, so recursion needs no id indirection)."""
    kinds: list[int] = []
    payloads: list[object] = []
    los: list[int] = []
    his: list[int] = []
    gate_kinds: list[int] = []
    gate_data: list[object] = []
    for spec in specs:
        kind, payload = _flatten_item(spec, low)
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


def _flatten_item(spec: ItemSpec, low: Lowering) -> tuple[int, object]:
    """Lower one :class:`ItemSpec` to its ``(op-code, payload)`` flat pair."""
    kind = spec.kind
    payload = spec.payload
    if kind == LIT:
        return OP_LIT, str(payload)
    if kind == CC:
        cs = cast(CharSet, payload)
        return OP_CC, (cs.chars, cs.negated)
    if kind == GRP:
        return OP_GRP, _flatten_group(cast(GroupSpec, payload), low)
    target = payload  # REF
    if isinstance(target, IslandRef):
        return (OP_FAIL if target.fail else OP_ISLAND), target.name
    return OP_REF, low.shells[cast(CloneKey, target)]


def _flatten_selectors(
    arms: Sequence[ArmSpec], low: Lowering
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
                _flatten_arm(arm.specs, low),
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
                _flatten_arm(arm.specs, low),
            )
            for arm in arms
        )
        return (), None, ((w.chars, w.negated), sels)
    selectors = tuple(
        (arm.first.chars, arm.first.negated, _flatten_arm(arm.specs, low))
        for arm in arms
    )
    return selectors, None, None


def _flatten_group(group: GroupSpec, low: Lowering) -> FlatClone:
    """Lower an inline group to a transparent :class:`FlatClone`.

    An attempting group gets its MARKER here and its entries later: the marker
    must exist before the optimizer runs (the vstr / leaf / dispatch licences
    all refuse an attempt clone), while the entries copy the parent's final
    baked state and so must wait for it — the same two-phase shape a rule
    clone's attempt has in :func:`flatten_clones`.
    """
    clone = FlatClone.__new__(FlatClone)
    clone.name = ""  # an inline group stands for no rule the grammar named
    clone.selectors, clone.kwin_selectors, clone.pn_selectors = _flatten_selectors(
        group.arms, low
    )
    clone.default = (
        _flatten_arm(group.default, low) if group.default is not None else None
    )
    clone.struct_arm = None
    clone.attempt = (
        (group.attempt_follow, ()) if group.attempt_follow is not None else None
    )
    if clone.attempt is not None:
        low.groups.append((clone, group.arms))
    bake_product_build(clone, None, ConstructionTables())
    return clone


_PREFIX_DEPTH = 6
"""How far an admission prefix follows references before it stops.

Also what terminates the walk on a recursive rule: a prefix is a *necessary*
condition, so stopping early only weakens the filter, never breaks it."""

_PREFIX_SOURCE_CAP = 20_000
"""Widest prefix source that earns a compiled pattern. A fan-out of wide
alternations can spell a very large source for very little discrimination;
past this the entry keeps its first-char test and its window instead."""

_PREFIX_REF_OPS = frozenset(
    {
        OP_REF,
        OP_REF1,
        OP_LEAF1,
        OP_VSTR,
        OP_VRUN,
        OP_V1,
        OP_VDISP,
        OP_AVSTR,
        OP_AVDISP,
    }
)
"""Item op-codes whose payload is a clone the prefix may descend into.

Every code that stands for a REFERENCE belongs here — this is one of the
consumers that see through references, and a code missing from the set costs
an attempt its skip silently rather than loudly."""


def _quantified(atom: str, lo: int, hi: int) -> tuple[str, bool]:
    """``atom`` under ``{lo,hi}``, and whether that bound is unbounded.

    Greedy and BACKTRACKABLE, never possessive: a prefix pattern is a
    necessary condition, and a possessive run that over-ate what a later
    item needs would turn it into a false rejection.
    """
    if (lo, hi) == (1, 1):
        return atom, False
    if hi < 0:
        return f"{atom}{{{lo},}}", True
    return f"{atom}{{{lo},{hi}}}", False


def _terminal_source(arm: FlatArm, j: int) -> tuple[str, bool] | None:
    """Item ``j``'s source when it is a terminal, else ``None``."""
    k = arm.kinds[j]
    if k == OP_LIT1:
        return literal_source(arm.payloads[j]), False
    if k == OP_CC1:
        return class_source(*arm.payloads[j]), False
    if k == OP_LIT:
        atom = literal_source(arm.payloads[j])
    elif k == OP_CC:
        atom = class_source(*arm.payloads[j])
    else:
        return None
    return _quantified(atom, arm.los[j], arm.his[j])


def _ref_source(arm: FlatArm, j: int, depth: int) -> tuple[str, bool, bool] | None:
    """Item ``j``'s referenced clone as ``(source, spans_item, unbounded)``.

    ``spans_item`` is what licenses the caller to keep going past this item.
    A quantified item may only carry its bound when the inner source spans
    the whole clone AND has no unbounded quantifier of its own: repeating a
    PREFIX is not a prefix of the repetition, and nesting one unbounded
    quantifier in another is where a backtracking engine goes exponential.
    """
    if depth <= 0 or arm.kinds[j] not in _PREFIX_REF_OPS:
        return None
    inner = _clone_prefix_source(arm.payloads[j], depth - 1)
    if inner is None:
        return None
    source, whole, unbounded = inner
    lo, hi = arm.los[j], arm.his[j]
    if (lo, hi) == (1, 1):
        return source, whole, unbounded
    if not whole or unbounded:
        # only a MANDATORY iteration is certainly present; an optional one
        # constrains nothing, so the prefix ends before it rather than at it.
        return (source, False, unbounded) if lo >= 1 else None
    bounded, grew = _quantified(source, lo, hi)
    return bounded, True, grew


def _arm_prefix_source(arm: FlatArm, depth: int) -> tuple[str, bool, bool]:
    """The arm's leading items as ``(source, spans_arm, unbounded)``.

    A NECESSARY condition, not an exact one: the source transcribes a PREFIX
    of the item sequence, so every string the arm derives is matched by it,
    and stopping early only widens what the filter admits.
    """
    parts: list[str] = []
    unbounded = False
    for j in range(arm.n):
        term = _terminal_source(arm, j)
        if term is not None:
            parts.append(term[0])
            unbounded = unbounded or term[1]
            continue
        grown = _ref_source(arm, j, depth)
        if grown is None:
            return "".join(parts), False, unbounded
        parts.append(grown[0])
        unbounded = unbounded or grown[2]
        if not grown[1]:
            return "".join(parts), False, unbounded
    return "".join(parts), True, unbounded


def _clone_arms(clone: FlatClone) -> tuple[FlatArm, ...]:
    """Every arm ``clone`` can take, whichever structure its selection uses.

    A gate CHOOSES among arms; it does not add or remove any, so the union
    below is a superset of what the clone derives however it is selected —
    which is all a necessary condition needs. A ``k``-window or peek
    selection empties ``selectors`` and holds its arms in its own table, so
    reading only ``selectors`` would silently yield nothing there.
    """
    if clone.kwin_selectors is not None:
        return tuple(arm for _windows, arm in clone.kwin_selectors)
    if clone.pn_selectors is not None:
        return tuple(arm for _chars, _negated, arm in clone.pn_selectors[1])
    return tuple(arm for _chars, _negated, arm in clone.selectors)


def _union_source(
    branches: list[tuple[str, bool, bool] | None],
) -> tuple[str, bool, bool] | None:
    """``branches`` as one alternation, or ``None`` when one spells nothing.

    A union is only as constraining as its loosest member, so a branch that
    spells nothing — or that could not be built at all — makes the whole
    alternation vacuous, and dropping it would NARROW the pattern below what
    the clone derives, which is the one way this filter could go unsound.
    """
    if not branches or any(b is None or not b[0] for b in branches):
        return None
    kept = [b for b in branches if b is not None]
    joined = "(?:" + "|".join(source for source, _w, _u in kept) + ")"
    if len(joined) > _PREFIX_SOURCE_CAP:
        return None
    return (
        joined,
        all(whole for _s, whole, _u in kept),
        any(unbounded for _s, _w, unbounded in kept),
    )


def _dispatch_prefix_source(
    clone: FlatClone, depth: int
) -> tuple[str, bool, bool] | None:
    """A frame-less dispatch alternation's targets, unioned."""
    if depth <= 0 or not clone.selectors:
        return None
    return _union_source(
        [
            _clone_prefix_source(target, depth - 1)
            for _chars, _negated, target in clone.selectors
        ]
    )


def _clone_prefix_source(clone: Any, depth: int) -> tuple[str, bool, bool] | None:
    """``clone``'s arms as one alternation source, or ``None``.

    A nullable default is refused: the clone then derives ε, so any honest
    union carries an empty branch and admits everything.
    """
    if not isinstance(clone, FlatClone) or clone.default is not None:
        return None
    if clone.mode == BUILD_DISPATCH:
        return _dispatch_prefix_source(clone, depth)
    return _union_source([_arm_prefix_source(arm, depth) for arm in _clone_arms(clone)])


def _arm_prefix(arm: FlatArm) -> Pattern | None:
    """The arm's leading prefix as one compiled pattern, or ``None``.

    The attempt entries' cheap admission: one C-level match decides whether
    the arm can reach past what its leading items must spell — a miss skips
    the arm's sub-run AND its audit, soundly, because the pattern matches
    everything the arm derives (:func:`_arm_prefix_source`).

    Spelling it as a regex rather than a possessive step walk is what lets
    the discriminator through: a rule's leading reference is usually an
    ALTERNATION (``kv-pair`` is ``key '+=' … | key '=' …``), which no
    single-arm step list can carry, and the discriminating character sits on
    the far side of an unbounded run that only backtracking can give back.
    """
    source, _whole, _unbounded = _arm_prefix_source(arm, _PREFIX_DEPTH)
    if not source or len(source) > _PREFIX_SOURCE_CAP:
        return None
    return compile_source(source)


def _attempt_sub(clone: FlatClone) -> FlatClone:
    """A single-arm sub-clone shell copying ``clone``'s FINAL baked state.

    Called after the optimizer, so the copied build plan is what the parent
    actually runs with. ``selectors``/``default`` are the caller's to set.
    """
    sub = FlatClone.__new__(FlatClone)
    sub.name = clone.name  # the sub-run stands for the parent's rule
    sub.kwin_selectors = None
    sub.pn_selectors = None
    sub.struct_arm = None
    sub.attempt = None
    sub.mode = clone.mode
    sub.ctor = clone.ctor
    sub.matched = clone.matched
    sub.n_items = clone.n_items
    sub.fields = clone.fields
    sub.plan = clone.plan
    sub.fast = clone.fast
    sub.defaults = clone.defaults
    sub.leaf = False
    sub.chartable = None  # the sub runs framed — no leaf licence, no table
    sub.chartotal = True
    sub.runarm = None
    sub.needs_ends = clone.needs_ends
    return sub


def _attempt_entries(
    clone: FlatClone, arms: "tuple[ArmSpec, ...]"
) -> tuple[tuple[Any, Any, Any, Any, FlatClone], ...]:
    """An attempt clone's ordered entry list — one single-arm sub-clone each,
    with a leading-terminal prefix regex as its C-speed admission
    (:func:`_arm_prefix_re`) and the arm's FIRST\\ :sub:`k` admission windows
    (:attr:`~lexic.parsing.pda.compiler.specs.ArmSpec.attempt_window`).

    Every sub-clone SHARES the parent's :class:`FlatArm` (op specialisation
    reached it once, through the parent) and the parent's baked build plan, so
    a sub-run builds exactly the model the rule would. ``arms`` is the spec's
    arm list — 1:1 with ``clone.selectors``, the single-char lowering — so
    the window rides its own arm. The nullable default, when present, is the
    last entry, always admitted (``chars is None``).
    """
    entries: list[tuple[Any, Any, Any, Any, FlatClone]] = []
    for (chars, negated, arm), spec in zip(clone.selectors, arms):
        sub = _attempt_sub(clone)
        sub.selectors = ((chars, negated, arm),)
        sub.default = None
        window = (
            compile_admission(_flat_windows(spec.attempt_window))
            if spec.attempt_window is not None
            else None
        )
        entries.append((chars, negated, _arm_prefix(arm), window, sub))
    if clone.default is not None:
        sub = _attempt_sub(clone)
        sub.selectors = ()
        sub.default = clone.default
        entries.append((None, None, None, None, sub))
    return tuple(entries)


def _range_of(binding: ModelBinding, name: str) -> int:
    """The verified completion range one rule names, or ``-1`` when it has none.

    Read through the binding's own rule codes rather than recomputed, so a
    clone's recorded range is by construction the one the verifier bounded.
    """
    code = binding.codes.get(name, -1)
    return -1 if code < 0 else binding.program.rules[code].completion


def _consults(clones: dict[CloneKey, CloneSpec], low: Lowering) -> dict[int, Pattern]:
    """Each proved clone's own extent pattern, keyed by the shell it belongs to.

    A clone is a rule compiled for ONE continuation and the proof was taken
    against that continuation, so the pattern rides the shell rather than the
    rule name — two clones of one rule can differ on whether it holds at all.
    """
    return {
        id(low.shells[key]): extent_pattern(spec.consult)
        for key, spec in clones.items()
        if spec.consult is not None
    }


def flatten_clones(
    clones: dict[CloneKey, CloneSpec],
    binding: ModelBinding = ModelBinding(),
) -> dict[CloneKey, FlatClone]:
    """Lower a compiled clone table to its live :class:`FlatClone` shells.

    Two passes: create an empty shell per clone key, then fill each (refs
    resolve to the live shells — no runtime id lookup), then run
    :func:`optimize_program`. Shared by :func:`flatten_program` and the
    per-island delegate compile, which each own an independent shell set the
    optimiser mutates in place.

    Attempt entries are built in a third pass, after the optimizer, because
    each sub-clone copies its parent's FINAL baked state. Inline groups attempt
    too and are drained from :attr:`Lowering.groups` in the same pass — they
    are minted mid-walk and have no key to be looked up by.
    """
    low = Lowering({key: FlatClone.__new__(FlatClone) for key in clones}, [])
    for key, spec in clones.items():
        clone = low.shells[key]
        clone.name = spec.name
        clone.selectors, clone.kwin_selectors, clone.pn_selectors = _flatten_selectors(
            spec.arms, low
        )
        clone.default = (
            _flatten_arm(spec.default, low) if spec.default is not None else None
        )
        clone.struct_arm = spec.struct_arm
        # The attempt MARKER must exist before the optimizer runs (the vstr /
        # leaf / dispatch licences all refuse attempt clones); the entries are
        # built after it, from the parent's final baked state.
        clone.attempt = (
            (spec.attempt_follow, ()) if spec.attempt_follow is not None else None
        )
        bake_product_build(
            clone, spec.product, binding.construction, _range_of(binding, spec.name)
        )
    optimize_program(list(low.shells.values()), _consults(clones, low))
    attempting = [
        (low.shells[key], spec.arms, spec.attempt_follow)
        for key, spec in clones.items()
        if spec.attempt_follow is not None
    ]
    attempting += [(clone, arms, clone.attempt[0]) for clone, arms in low.groups]
    for clone, arms, follow in attempting:
        entries = _attempt_entries(clone, arms)
        _optimize_entries(entries)
        clone.attempt = (follow, entries)
    return low.shells


def _optimize_entries(entries: tuple[Any, ...]) -> None:
    """Give the attempt sub-clones the specialisations the main pass missed.

    :func:`optimize_program` runs over the shell set, and these sub-clones are
    built after it — so without this they enter with a frame each, though every
    one is a single-arm pass-through, the exact shape dispatch conversion
    exists to remove. On the vyx grammar that is a quarter of all clone entries.

    """
    for entry in entries:
        convert_dispatch(entry[-1])


def flatten_program(
    clones: dict[CloneKey, CloneSpec],
    start_key: CloneKey | IslandRef,
    binding: ModelBinding = ModelBinding(),
) -> PdaProgram:
    """Lower the compiled clone table to the flat runtime :class:`PdaProgram`."""
    shells = flatten_clones(clones, binding)
    start: FlatClone | IslandRef = (
        shells[start_key] if isinstance(start_key, CloneKey) else start_key
    )
    return PdaProgram(start)
