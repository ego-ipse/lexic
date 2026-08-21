"""Lowering — a compiled clone set into the flat int-coded program.

The step between the compiler's records and the runtime's arrays: every gate,
arm, item and selector becomes ints in one pass. What it produces is defined in
``flatten``; what it consumes comes from ``clones``.
"""

from __future__ import annotations

from typing import Any, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.fold import FastCtor, RuleFold
from lexic.parsing.pda.compiler.program.flatten import FlatArm, FlatClone, PdaProgram
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_ALT,
    BUILD_DISPATCH,
    BUILD_SEQ,
    BUILD_TRANSPARENT,
    BUILD_VALUE_STR,
    GATE_ATTEMPT,
    GATE_KWIN,
    GATE_PAIR,
    GATE_PEEK,
    GATE_SCAN,
    GATE_STOP,
    HI_UNBOUNDED,
    M_CONST,
    M_VALUE,
    MODE_CODE,
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


def _flat_windows(
    windows: tuple[tuple[CharSet, ...], ...],
) -> tuple[tuple[tuple[frozenset[str], bool], ...], ...]:
    """Pre-resolve CharSet windows to the ``((chars, negated), ...)`` flat form."""
    return tuple(tuple((cs.chars, cs.negated) for cs in win) for win in windows)


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
    clone.chartable = None  # baked last, off the final plan, by bake_chartables
    clone.chartotal = True
    clone.runarm = None
    clone.needs_ends = fold is not None and any(
        f.mode in ("text", "gtext") for f in fold.fields
    )
    if fold is None or fold.fast is None:
        clone.fields = ()
        clone.plan = ()
        clone.fast = None
        clone.defaults = None
        return
    clone.fields = tuple((f.item, MODE_CODE[f.mode], f.name, f.lo) for f in fold.fields)
    clone.plan = _build_plan(fold, fold.fast)
    clone.fast = fold.fast.make
    clone.defaults = dict(fold.fast.defaults)


def _build_plan(
    fold: RuleFold, fast: FastCtor
) -> tuple[tuple[int, int, int, Any], ...]:
    """The clone's POSITIONAL build plan — one entry per field of the class.

    In the record's own field order, so the fused build reads it straight into
    a values list and constructs the tuple: no defaults-dict copy, no
    supplied-key set, no read-back by name. A field no bound field supplies is
    :data:`~lexic.parsing.pda.compiler.program.flatten.M_CONST` and carries its default
    outright; a ``value_str`` rule's ``value`` field is
    :data:`~lexic.parsing.pda.compiler.program.flatten.M_VALUE`.

    :param fold: The rule's fold.
    :param fast: Its granted licence — the field order and the defaults.
    :returns: ``(mode, item, lo, default)`` per class field.
    """
    bound = {f.name: f for f in fold.fields}
    defaults = fast.defaults
    plan: list[tuple[int, int, int, Any]] = []
    for name in fast.fields:
        field = bound.get(name)
        if field is not None:
            plan.append(
                (MODE_CODE[field.mode], field.item, field.lo, defaults.get(name))
            )
        elif fold.kind == "value_str" and name == "value":
            plan.append((M_VALUE, 0, 0, None))
        else:
            plan.append((M_CONST, 0, 0, defaults.get(name)))
    return tuple(plan)


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
    clone.name = ""  # an inline group stands for no rule the grammar named
    clone.selectors, clone.kwin_selectors, clone.pn_selectors = _flatten_selectors(
        group.arms, shells
    )
    clone.default = (
        _flatten_arm(group.default, shells) if group.default is not None else None
    )
    clone.struct_arm = None
    clone.attempt = None
    clone.mode = BUILD_TRANSPARENT
    _bake_build(clone, None)
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
    {OP_REF, OP_REF1, OP_LEAF1, OP_VSTR, OP_VRUN, OP_V1, OP_VDISP}
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
    sub.fold = clone.fold
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


def flatten_clones(clones: dict[CloneKey, CloneSpec]) -> dict[CloneKey, FlatClone]:
    """Lower a compiled clone table to its live :class:`FlatClone` shells.

    Two passes: create an empty shell per clone key, then fill each (refs
    resolve to the live shells — no runtime id lookup), then run
    :func:`optimize_program`. Shared by :func:`flatten_program` and the
    per-island delegate compile, which each own an independent shell set the
    optimiser mutates in place.
    """
    shells: dict[CloneKey, FlatClone] = {
        key: FlatClone.__new__(FlatClone) for key in clones
    }
    for key, spec in clones.items():
        clone = shells[key]
        clone.name = spec.name
        clone.selectors, clone.kwin_selectors, clone.pn_selectors = _flatten_selectors(
            spec.arms, shells
        )
        clone.default = (
            _flatten_arm(spec.default, shells) if spec.default is not None else None
        )
        clone.struct_arm = spec.struct_arm
        # The attempt MARKER must exist before the optimizer runs (the vstr /
        # leaf / dispatch licences all refuse attempt clones); the entries are
        # built after it, from the parent's final baked state.
        clone.attempt = (
            (spec.attempt_follow, ()) if spec.attempt_follow is not None else None
        )
        clone.mode = _build_mode(spec.fold)
        _bake_build(clone, spec.fold)
    optimize_program(list(shells.values()))
    for key, spec in clones.items():
        if spec.attempt_follow is not None:
            clone = shells[key]
            entries = _attempt_entries(clone, spec.arms)
            _optimize_entries(entries)
            clone.attempt = (spec.attempt_follow, entries)
    return shells


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
) -> PdaProgram:
    """Lower the compiled clone table to the flat runtime :class:`PdaProgram`."""
    shells = flatten_clones(clones)
    start: FlatClone | IslandRef = (
        shells[start_key] if isinstance(start_key, CloneKey) else start_key
    )
    return PdaProgram(start)
