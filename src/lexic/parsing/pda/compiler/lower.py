"""Lowering — a compiled clone set into the flat int-coded program.

The step between the compiler's records and the runtime's arrays: every gate,
arm, item and selector becomes ints in one pass. What it produces is defined in
``flatten``; what it consumes comes from ``clones``.
"""

from __future__ import annotations

from typing import Any, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.fold import RuleFold
from lexic.parsing.pda.compiler.flatten import (
    BUILD_ALT,
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
    reduce_rewrite,
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
from lexic.parsing.pda.core.scanner import ScanGate


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
    clone.attempt = None
    clone.mode = BUILD_TRANSPARENT
    _bake_build(clone, None)
    return clone


def _attempt_sub(clone: FlatClone, reduce_mode: bool) -> FlatClone:
    """A single-arm sub-clone shell copying ``clone``'s FINAL baked state.

    Called after the optimize / reduce-rewrite passes, so the copied build
    plan (and, on the reduce path, the completion fields) is what the parent
    actually runs with. ``selectors``/``default`` are the caller's to set.
    """
    sub = FlatClone.__new__(FlatClone)
    sub.kwin_selectors = None
    sub.pn_selectors = None
    sub.struct_arm = None
    sub.attempt = None
    sub.mode = clone.mode
    sub.fold = clone.fold
    sub.fields = clone.fields
    sub.fast = clone.fast
    sub.defaults = clone.defaults
    sub.leaf = False
    sub.needs_ends = clone.needs_ends
    if reduce_mode:
        sub.reduce_kind = clone.reduce_kind
        sub.reduce_body = clone.reduce_body
        sub.reduce_is_yield = clone.reduce_is_yield
        sub.reduce_span = clone.reduce_span
        sub.reduce_can_drop = clone.reduce_can_drop
    return sub


def _attempt_entries(
    clone: FlatClone, reduce_mode: bool
) -> tuple[tuple[Any, Any, FlatClone], ...]:
    """An attempt clone's ordered entry list — one single-arm sub-clone each.

    Every sub-clone SHARES the parent's :class:`FlatArm` (op specialisation
    reached it once, through the parent) and the parent's baked build plan, so
    a sub-run builds exactly the model the rule would. The nullable default,
    when present, is the last entry, always admitted (``chars is None``).
    """
    entries: list[tuple[Any, Any, FlatClone]] = []
    for chars, negated, arm in clone.selectors:
        sub = _attempt_sub(clone, reduce_mode)
        sub.selectors = ((chars, negated, arm),)
        sub.default = None
        entries.append((chars, negated, sub))
    if clone.default is not None:
        sub = _attempt_sub(clone, reduce_mode)
        sub.selectors = ()
        sub.default = clone.default
        entries.append((None, None, sub))
    return tuple(entries)


def flatten_clones(
    clones: dict[CloneKey, CloneSpec],
    completions: dict[CloneKey, ReduceComp] | None,
) -> dict[CloneKey, FlatClone]:
    """Lower a compiled clone table to its live :class:`FlatClone` shells.

    Two passes: create an empty shell per clone key, then fill each (refs
    resolve to the live shells — no runtime id lookup). The model target then
    runs :func:`optimize_program`; the reduce target (``completions`` given)
    runs :func:`reduce_rewrite` instead. Shared by :func:`flatten_program`
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
        # The attempt MARKER must exist before the optimizer runs (the vstr /
        # leaf / dispatch licences all refuse attempt clones); the entries are
        # built after it, from the parent's final baked state.
        clone.attempt = (
            (spec.attempt_follow, ()) if spec.attempt_follow is not None else None
        )
        clone.mode = _build_mode(spec.fold)
        _bake_build(clone, spec.fold)
    if completions is None:
        optimize_program(list(shells.values()))
    else:
        reduce_rewrite(shells, completions)
    for key, spec in clones.items():
        if spec.attempt_follow is not None:
            clone = shells[key]
            clone.attempt = (
                spec.attempt_follow,
                _attempt_entries(clone, completions is not None),
            )
    return shells


def flatten_program(
    clones: dict[CloneKey, CloneSpec],
    start_key: CloneKey | IslandRef,
    completions: dict[CloneKey, ReduceComp] | None = None,
) -> PdaProgram:
    """Lower the compiled clone table to the flat runtime :class:`PdaProgram`
    (``completions`` given on the reduce path, ``None`` on the model path)."""
    shells = flatten_clones(clones, completions)
    start: FlatClone | IslandRef = (
        shells[start_key] if isinstance(start_key, CloneKey) else start_key
    )
    return PdaProgram(start)
