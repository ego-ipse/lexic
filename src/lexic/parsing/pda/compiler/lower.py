"""Lowering — a compiled clone set into the flat int-coded program.

The step between the compiler's records and the runtime's arrays: every gate,
arm, item and selector becomes ints in one pass. What it produces is defined in
``flatten``; what it consumes comes from ``clones``.
"""

from __future__ import annotations

from typing import Any, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.fold import FastCtor, RuleFold
from lexic.parsing.pda.compiler.flatten import (
    FlatArm,
    FlatClone,
    PdaProgram,
    convert_dispatch,
    optimize_program,
)
from lexic.parsing.pda.compiler.opcodes import (
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
    OP_LIT,
    OP_LIT1,
    OP_REF,
    OP_REF1,
    OP_V1,
    OP_VDISP,
    OP_VRUN,
    OP_VSTR,
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
from lexic.parsing.pda.core.scanner import ScanGate, compile_admission


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
    :data:`~lexic.parsing.pda.compiler.flatten.M_CONST` and carries its default
    outright; a ``value_str`` rule's ``value`` field is
    :data:`~lexic.parsing.pda.compiler.flatten.M_VALUE`.

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


def _step_admits_next(step: tuple[Any, ...], nxt: tuple[Any, ...]) -> bool:
    """Whether the possessive ``step`` could over-eat what ``nxt`` needs.

    The step matcher is possessive (no backtracking — src imports no regex
    engine), so a prefix may only chain steps whose alphabets are DISJOINT
    at the seam; otherwise a greedy take could falsely reject a viable arm,
    which would be an UNSOUND admission. Overlap ends the prefix instead.
    """
    kind, payload, _lo, hi = step
    if hi == 1:
        return False  # a bounded-once step never over-eats
    if kind == 0:
        lead = payload[0]
        return _member(lead, nxt)
    chars, negated = payload
    if negated:
        return True  # a co-finite step overlaps almost anything — stop
    return any(_member(ch, nxt) for ch in chars)


def _member(ch: str, step: tuple[Any, ...]) -> bool:
    """Whether ``ch`` can begin ``step``."""
    kind, payload, _lo, _hi = step
    if kind == 0:
        return payload[0] == ch
    chars, negated = payload
    return (ch not in chars) if negated else ch in chars


def _arm_prefix_steps(arm: FlatArm, depth: int) -> list[tuple[Any, ...]]:
    """The arm's leading terminal run as flat matcher steps, seen THROUGH refs.

    A leading exactly-once reference to a single-arm, default-free,
    non-attempt clone inlines transparently (hoisting puts most of a vyx
    arm's discriminator — ``key '='`` — behind such refs); any other shape,
    or a seam the possessive matcher cannot chain soundly
    (:func:`_step_admits_next`), ends the prefix. Bounded by ``depth``.
    """
    steps: list[tuple[Any, ...]] = []
    for j in range(arm.n):
        k = arm.kinds[j]
        step: tuple[Any, ...] | None = None
        if k in (OP_LIT, OP_LIT1):
            lo = arm.los[j] if k == OP_LIT else 1
            hi = arm.his[j] if k == OP_LIT else 1
            step = (0, arm.payloads[j], lo, hi)
        elif k in (OP_CC, OP_CC1):
            lo = arm.los[j] if k == OP_CC else 1
            hi = arm.his[j] if k == OP_CC else 1
            step = (1, arm.payloads[j], lo, hi)
        elif (
            k in (OP_REF, OP_REF1, OP_VSTR, OP_VRUN, OP_V1, OP_VDISP)
            and depth > 0
            and arm.los[j] == 1
            and arm.his[j] == 1
        ):
            grown = _clone_prefix_steps(arm.payloads[j], depth - 1)
            if grown is not None:
                inner, whole = grown
                if steps and _step_admits_next(steps[-1], inner[0]):
                    break
                steps.extend(inner)
                if whole:
                    continue
            break
        if step is None:
            break
        if steps and _step_admits_next(steps[-1], step):
            break
        steps.append(step)
    return steps


def _clone_prefix_steps(
    clone: Any, depth: int
) -> tuple[list[tuple[Any, ...]], bool] | None:
    """``clone``'s leading steps and whether they span the WHOLE clone (only
    then may the caller's prefix continue past it), or ``None``.

    Single-arm clones only — a default (nullable) arm, a gated selection, a
    nested attempt or an alternation yields nothing here (branch fan-out is
    handled at the entry's top level, where each arm is its own prefix).
    """
    if not isinstance(clone, FlatClone):
        return None
    gated = (
        clone.attempt is not None
        or clone.struct_arm is not None
        or clone.kwin_selectors is not None
        or clone.pn_selectors is not None
    )
    if (
        gated
        or clone.default is not None
        or clone.mode == BUILD_DISPATCH
        or len(clone.selectors) != 1
    ):
        return None
    arm = clone.selectors[0][2]
    inner = _arm_prefix_steps(arm, depth)
    if not inner:
        return None
    return inner, len(inner) == arm.n


def _arm_prefix(arm: FlatArm) -> tuple[tuple[Any, ...], ...] | None:
    """The arm's leading-terminal prefix as matcher steps, or ``None``.

    The attempt entries' cheap admission (the recognition prototype's run
    mode, applied to decisions, without importing a regex engine): one pass
    of :func:`~lexic.parsing.pda.runtime.admission.prefix_admits` decides
    whether the arm can reach past its leading terminals — a reject skips
    the arm's sub-run AND its audit, soundly (a prefix miss means the arm
    cannot match; every possessive seam was disjointness-checked at build).
    """
    steps = _arm_prefix_steps(arm, 6)
    return tuple(steps) if steps else None


def _attempt_sub(clone: FlatClone, reduce_mode: bool) -> FlatClone:
    """A single-arm sub-clone shell copying ``clone``'s FINAL baked state.

    Called after the optimize / reduce-rewrite passes, so the copied build
    plan (and, on the reduce path, the completion fields) is what the parent
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
    if reduce_mode:
        sub.reduce_kind = clone.reduce_kind
        sub.reduce_body = clone.reduce_body
        sub.reduce_is_yield = clone.reduce_is_yield
        sub.reduce_span = clone.reduce_span
        sub.reduce_can_drop = clone.reduce_can_drop
    return sub


def _attempt_entries(
    clone: FlatClone, reduce_mode: bool, arms: "tuple[ArmSpec, ...]"
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
        sub = _attempt_sub(clone, reduce_mode)
        sub.selectors = ((chars, negated, arm),)
        sub.default = None
        window = (
            compile_admission(_flat_windows(spec.attempt_window))
            if spec.attempt_window is not None
            else None
        )
        entries.append((chars, negated, _arm_prefix(arm), window, sub))
    if clone.default is not None:
        sub = _attempt_sub(clone, reduce_mode)
        sub.selectors = ()
        sub.default = clone.default
        entries.append((None, None, None, None, sub))
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
    if completions is None:
        optimize_program(list(shells.values()))
    else:
        reduce_rewrite(shells, completions)
    for key, spec in clones.items():
        if spec.attempt_follow is not None:
            clone = shells[key]
            entries = _attempt_entries(clone, completions is not None, spec.arms)
            _optimize_entries(entries, completions is not None)
            clone.attempt = (spec.attempt_follow, entries)
    return shells


def _optimize_entries(entries: tuple[Any, ...], reduce_mode: bool) -> None:
    """Give the attempt sub-clones the specialisations the main pass missed.

    :func:`optimize_program` runs over the shell set, and these sub-clones are
    built after it — so without this they enter with a frame each, though every
    one is a single-arm pass-through, the exact shape dispatch conversion
    exists to remove. On the vyx grammar that is a quarter of all clone entries.

    **The reduce path is excluded by licence, not by accident.** A dispatch
    chase is frame-less, so it would skip the completion callback a reduce
    clone needs to evaluate its reduction body, and the values would go missing
    silently. Today :func:`~lexic.parsing.pda.compiler.reduce_pda.reduce_rewrite`
    bakes every reachable clone to :data:`BUILD_REDUCE`, so the conversion's
    own ``BUILD_ALT`` test happens to refuse them — a mode-value coincidence
    that would stop holding the moment either side moved.
    """
    if reduce_mode:
        return
    for entry in entries:
        convert_dispatch(entry[-1])


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
