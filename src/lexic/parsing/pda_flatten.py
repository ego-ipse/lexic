"""Flat int-coded runtime program + post-flatten optimizer passes (Task 8).

The leaf half of the PDA compiler: the spec NamedTuples in
:mod:`lexic.parsing.pda_tables` are the compiler's *intermediate* (and the shape
the structural tests pin); :func:`~lexic.parsing.pda_tables._flatten_program`
lowers them, once per :func:`~lexic.parsing.pda_tables.compile_pda`, into the
flat int-coded artifact this module defines — :class:`_FlatClone` /
:class:`_FlatArm` carrying ``_OP_*`` op-codes and pre-resolved
``(chars, negated)`` membership sets, which :class:`~lexic.parsing.pda_kernel.PdaKernel`
walks with integer dispatch (the ``tables.py``/``kernel.py`` philosophy).

:func:`_optimize_program` then runs the specialisation passes that carve the
hot-loop op-codes (exactly-once terminals, inlinable ``value_str`` references,
frame-less leaf clones, pass-through dispatch clones, exactly-once calls).
Everything here is a build-time cost only — the program is shared, immutable,
across every parse. This module imports nothing from ``pda_tables`` (it is a
leaf w.r.t. the compiler and the spec types); the ``spec → flat`` bridge lives
in ``pda_tables`` beside the specs it reads.
"""

from __future__ import annotations

from typing import Any

from lexic.ir.base import IrLeaf, IrSelf

_OP_LIT, _OP_CC, _OP_REF, _OP_GRP, _OP_ISLAND, _OP_FAIL = 0, 1, 2, 3, 4, 5
"""Flat item op-codes: literal, char class, clone reference, inline group,
parse-island reference, fail-island reference."""

_OP_LIT1, _OP_CC1, _OP_VSTR, _OP_REF1 = 6, 7, 8, 9
"""Specialised op-codes cut by the post-flatten passes: an exactly-once
(``lo == hi == 1``) literal / char class (no quantifier loop, no gate); a
reference to a terminal-only ``value_str`` clone the runtime matches inline —
whole quantifier loop, arm selection, span slice and model build — without
pushing a frame; and an exactly-once clone entry (ref or group) in an arm that
keeps no item ends, so the driver advances past it before descending (no
count bookkeeping, no resume re-check)."""

_TERMINAL_OPS = frozenset((_OP_LIT, _OP_CC, _OP_LIT1, _OP_CC1))
"""The op-codes that consume input without descending — the ``_OP_VSTR``
inlining licence (a clone is inlinable iff every arm is all-terminal)."""

_GATE_STOP, _GATE_PAIR = 0, 1
"""Flat loop-gate codes: single-char stop-set, LL(2) 2-char pair set."""

_BUILD_TRANSPARENT, _BUILD_VALUE_STR, _BUILD_ALT, _BUILD_SEQ = 0, 1, 2, 3
"""Flat clone build-modes — how a completed frame folds to a model (or, for
``transparent``, funnels its children through without building)."""

_BUILD_DISPATCH = 4
"""A frame-less ``alternation`` clone: after hoist_arms every arm is a single
unit ruleref, and the alternation itself is a pass-through (the matched arm's
sub-model reports straight to the parent sink) — so the post-flatten pass
rewrites qualifying clones into dispatch tables whose selectors carry the
target :class:`_FlatClone` directly and the runtime chases them in
:meth:`~lexic.parsing.pda_kernel.PdaKernel._enter` without a frame."""

_DISPATCH_EMPTY = object()
"""The ``default`` sentinel of a dispatch clone whose alternation carried an
empty (nullable) arm — on a selector miss the runtime consumes nothing and
produces nothing, exactly as the empty arm's zero-item frame would."""

_M_TEXT, _M_GTEXT, _M_MODEL, _M_MODELS = 0, 1, 2, 3
"""Int-coded field-bind modes (:data:`~lexic.ir.bind.BIND_MODES`, in order) —
what :attr:`_FlatClone.fields` carries so the fused build never compares mode
strings."""

_MODE_CODE = {
    "text": _M_TEXT,
    "gtext": _M_GTEXT,
    "model": _M_MODEL,
    "models": _M_MODELS,
}
"""Bind-mode string → flat int code."""

_HI_UNBOUNDED = -1
"""The flat ``his`` sentinel for an unbounded (``None``) quantifier upper bound."""


class _FlatArm(IrLeaf[IrSelf, IrSelf]):
    """One arm lowered to parallel int-coded arrays — the hot-loop unit.

    Every per-item field is a positional tuple indexed by item number, so the
    runtime binds one local per array at frame entry and indexes with ``[i]``
    (no NamedTuple attribute descriptors on the hot path).

    :ivar n: Item count.
    :ivar kinds: Per-item op-code (one of the ``_OP_*`` constants).
    :ivar payloads: Per-item body — a ``str`` (lit), a ``(chars, negated)``
        membership pair (cc), the target :class:`_FlatClone` (ref), a
        :class:`_FlatClone` group body (grp), or the island rule name. Typed
        ``Any`` (a heterogeneous op-stream, the ``tables.py`` int-array
        precedent) so the hot loop reads it without a per-access ``cast``.
    :ivar los: Per-item quantifier lower bound.
    :ivar his: Per-item quantifier upper bound (``_HI_UNBOUNDED`` for none).
    :ivar gate_kinds: Per-item loop-gate code (``_GATE_STOP`` / ``_GATE_PAIR``).
    :ivar gate_data: Per-item gate body — a ``(chars, negated)`` pair (stop) or
        a frozenset of 2-char prefixes (pair). ``Any``-typed for the same reason
        as :attr:`payloads`.
    """

    __slots__ = ("n", "kinds", "payloads", "los", "his", "gate_kinds", "gate_data")

    n: int
    kinds: tuple[int, ...]
    payloads: tuple[Any, ...]
    los: tuple[int, ...]
    his: tuple[int, ...]
    gate_kinds: tuple[int, ...]
    gate_data: tuple[Any, ...]

    # Built field-by-field by ``_flatten_arm`` (via ``__new__``) — the parallel
    # arrays are too many for a positional ``__init__`` signature.


class _FlatClone(IrLeaf[IrSelf, IrSelf]):
    """A clone (or inline group) lowered to arm selectors + a build-mode.

    Groups reuse this shape with :data:`_BUILD_TRANSPARENT` and no fold —
    entering either selects a FIRST-gated arm at the lookahead char and pushes a
    frame. Constructed empty (``__new__``) then filled by ``_flatten_program``'s
    second pass so a recursive reference resolves to the live object (no id
    indirection on the hot path).

    A :data:`_BUILD_DISPATCH` clone (cut by :func:`_convert_dispatch`) reuses
    :attr:`selectors` and :attr:`default` with clone payloads instead of arms —
    the runtime chases them frame-lessly.

    :ivar selectors: FIRST-gated arms as ``(chars, negated, arm)`` triples;
        ``arm`` is the target :class:`_FlatClone` on a dispatch clone.
    :ivar default: The all-nullable default :class:`_FlatArm`, or ``None``; on
        a dispatch clone the default target clone or :data:`_DISPATCH_EMPTY`.
    :ivar mode: The build-mode (one of the ``_BUILD_*`` constants).
    :ivar fold: The rule's :class:`~lexic.parsing.fold.RuleFold`, or ``None``
        (transparent).
    :ivar fields: The fold's bound fields with int-coded modes —
        ``(item, mode, name, lo)`` tuples (empty without a fast licence).
    :ivar fast: The fold's :attr:`~lexic.parsing.fold.FastCtor.make` parts
        constructor, or ``None`` (the runtime uses the validated ``ctor``).
    :ivar defaults: The fold's :attr:`~lexic.parsing.fold.FastCtor.defaults`
        the fused build seeds each parts dict from, or ``None``.
    :ivar leaf: ``True`` for a fast-licenced ``sequence`` clone whose every arm
        is all-terminal (``_OP_VSTR`` included) — the runtime runs it
        frame-lessly in :meth:`~lexic.parsing.pda_kernel.PdaKernel._run_leaf`.
    :ivar needs_ends: ``True`` when any bound field reads an item span (a
        ``text``/``gtext`` mode) — only then does a frame allocate and write
        per-item end positions.
    """

    __slots__ = (
        "selectors",
        "default",
        "mode",
        "fold",
        "fields",
        "fast",
        "defaults",
        "leaf",
        "needs_ends",
    )

    selectors: tuple[tuple[frozenset[str], bool, Any], ...]
    default: Any
    mode: int
    fold: Any  # RuleFold | None — Any-typed like payloads: hot-loop reads
    fields: tuple[tuple[int, int, str, int], ...]
    fast: Any
    defaults: Any
    leaf: bool
    needs_ends: bool


class PdaProgram(IrLeaf[IrSelf, IrSelf]):
    """The flat int-coded runtime program — what :class:`PdaKernel` walks.

    :ivar start: The start :class:`_FlatClone`, or an
        :class:`~lexic.parsing.pda_tables.IslandRef` when the start rule is
        itself an island (the whole-grammar opt-out).
    """

    __slots__ = ("start",)

    start: Any  # _FlatClone | IslandRef — the island marker lives in pda_tables

    def __init__(self, start: Any) -> None:
        """Bind the entry clone (or island opt-out marker)."""
        self.start = start


# ── post-flatten optimizer passes ──────────────────────────────────────────


def _clone_arms(clone: _FlatClone) -> list[_FlatArm]:
    """A clone's arms (gated + default), skipping dispatch clones' targets."""
    if clone.mode == _BUILD_DISPATCH:
        return []
    arms = [arm for _chars, _negated, arm in clone.selectors]
    if clone.default is not None:
        arms.append(clone.default)
    return arms


def _all_clones(roots: list[_FlatClone]) -> list[_FlatClone]:
    """Every clone reachable from ``roots``, groups included (worklist walk)."""
    seen: set[int] = set()
    out: list[_FlatClone] = []
    work = list(roots)
    while work:
        clone = work.pop()
        if id(clone) in seen:
            continue
        seen.add(id(clone))
        out.append(clone)
        for arm in _clone_arms(clone):
            for kind, payload in zip(arm.kinds, arm.payloads):
                if kind == _OP_GRP:
                    work.append(payload)
    return out


def _specialize_terminals(arm: _FlatArm) -> None:
    """Rewrite exactly-once terminals to their loop-free op-codes in place."""
    kinds = list(arm.kinds)
    for i, kind in enumerate(kinds):
        if arm.los[i] == 1 and arm.his[i] == 1:
            if kind == _OP_LIT:
                kinds[i] = _OP_LIT1
            elif kind == _OP_CC:
                kinds[i] = _OP_CC1
    arm.kinds = tuple(kinds)


def _vstr_inlinable(clone: Any) -> bool:
    """The ``_OP_VSTR`` licence: a terminal-only ``value_str`` clone."""
    return clone.mode == _BUILD_VALUE_STR and all(
        all(kind in _TERMINAL_OPS for kind in arm.kinds) for arm in _clone_arms(clone)
    )


def _inline_value_strs(arm: _FlatArm) -> None:
    """Rewrite refs to inlinable ``value_str`` clones to ``_OP_VSTR`` in place."""
    kinds = list(arm.kinds)
    for i, kind in enumerate(kinds):
        if kind == _OP_REF and _vstr_inlinable(arm.payloads[i]):
            kinds[i] = _OP_VSTR
    arm.kinds = tuple(kinds)


def _unit_ref_target(arm: _FlatArm) -> "_FlatClone | None":
    """The arm's sole exactly-once clone reference, or ``None``."""
    if arm.n == 1 and arm.kinds[0] == _OP_REF and arm.los[0] == 1 and arm.his[0] == 1:
        return arm.payloads[0]
    return None


def _convert_dispatch(clone: _FlatClone) -> None:
    """Rewrite a qualifying ``alternation`` clone into a dispatch table.

    Qualifies when every gated arm is a single unit clone reference and the
    default (if any) is empty or itself a unit clone reference — the exact
    shape hoist_arms guarantees for rule alternations. The alternation is a
    pass-through, so entering the selected target with the parent's sink is
    observationally identical to the frame it replaces.
    """
    if clone.mode != _BUILD_ALT:
        return
    targets = [_unit_ref_target(arm) for _chars, _negated, arm in clone.selectors]
    if any(target is None for target in targets):
        return
    default: Any = None
    if clone.default is not None:
        if clone.default.n == 0:
            default = _DISPATCH_EMPTY
        else:
            default = _unit_ref_target(clone.default)
            if default is None:
                return
    clone.selectors = tuple(
        (chars, negated, target)
        for (chars, negated, _arm), target in zip(clone.selectors, targets)
    )
    clone.default = default
    clone.mode = _BUILD_DISPATCH


def _mark_leaves(clone: _FlatClone) -> None:
    """Grant the frame-less licence to an all-terminal ``sequence`` clone.

    A leaf is a fast-licenced ``sequence`` clone whose every arm consists of
    terminal (``_OP_VSTR`` included) items only — no descent can occur under
    it, so the runtime builds its model inline without a frame.
    """
    if clone.mode != _BUILD_SEQ or clone.fast is None:
        return
    inline_ops = _TERMINAL_OPS | {_OP_VSTR}
    clone.leaf = all(
        all(kind in inline_ops for kind in arm.kinds) for arm in _clone_arms(clone)
    )


def _specialize_calls(clone: _FlatClone) -> None:
    """Rewrite exactly-once clone entries to ``_OP_REF1`` where ends are unkept.

    Licenced only in clones that never record item ends (non-``sequence``
    modes, or a ``sequence`` with no span-reading field) — the driver then
    advances past the item before descending, skipping the resume re-check
    that exists solely to write the item's end position.
    """
    if clone.mode == _BUILD_SEQ and clone.needs_ends:
        return
    for arm in _clone_arms(clone):
        kinds = list(arm.kinds)
        for i, kind in enumerate(kinds):
            if kind in (_OP_REF, _OP_GRP) and arm.los[i] == 1 and arm.his[i] == 1:
                kinds[i] = _OP_REF1
        arm.kinds = tuple(kinds)


def _optimize_program(roots: list[_FlatClone]) -> None:
    """Run the post-flatten passes over every reachable clone, in order.

    Terminal specialisation first (``_OP_LIT1``/``_OP_CC1``), then
    ``value_str`` inlining (its licence reads the specialised op-codes), then
    leaf marking (which reads ``_OP_VSTR``) and dispatch conversion, then call
    specialisation (``_OP_REF1``, which must not pre-empt the dispatch pass's
    unit-ref shape check). All compile-time only — nothing here is a per-parse
    cost.
    """
    clones = _all_clones(roots)
    for clone in clones:
        for arm in _clone_arms(clone):
            _specialize_terminals(arm)
    for clone in clones:
        for arm in _clone_arms(clone):
            _inline_value_strs(arm)
    for clone in clones:
        _mark_leaves(clone)
        _convert_dispatch(clone)
    for clone in clones:
        _specialize_calls(clone)
