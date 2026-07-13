"""Frame vocabulary + the fused model-build tail (PDA runtime leaf).

The slot layout of the :class:`~lexic.parsing.pda.runtime.runtime.PdaKernel` descent
frame (the ``F_*`` indices) and the functions that fold a completed frame into
a model — a ``sequence`` clone's per-field slot reads (fast or validated), an
``alternation``'s pass-through, and the leaf empty-arm build. Shed out of
``runtime.py`` so the frame vocabulary is shared by name with
``reduce_runtime.py`` (which walks the same frames) rather than crossing a
module boundary as a private import.

A leaf w.r.t. the runtime: these functions read only the input ``text`` plus a
frame / clone, never the kernel cursor, so they are free functions the kernel
and its reduce twin both call. Imports only :mod:`lexic.parsing.pda.compiler.flatten`
(the flat records + field-mode codes), :mod:`lexic.parsing.fold`
(:class:`RuleFold`) and :mod:`lexic.parsing.pda.core.errors`
(:class:`PdaFail`) — never ``runtime``.
"""

from __future__ import annotations

from typing import Any

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.fold import RuleFold
from lexic.parsing.pda.compiler.flatten import M_GTEXT, M_MODEL, M_MODELS, FlatClone
from lexic.parsing.pda.core.errors import PdaFail

# ── frame layout ───────────────────────────────────────────────────────────
#
# A frame is one in-progress arm execution on the kernel's explicit descent
# stack — a flat list (the ``kernel.py`` int-array explicit-stack precedent; the
# class *cursor* is :class:`~lexic.parsing.pda.runtime.runtime.PdaKernel` itself),
# indexed by the constants below. A *clone frame* (a non-transparent ``F_MODE``)
# captures what its fold needs and, on completion, builds a single model; a
# *transparent frame* (``BUILD_TRANSPARENT`` — an inline group or look-through
# clone) owns no capture and funnels every model produced inside it straight to
# ``F_OUT``.
#
#   F_ARM   the selected arm's flat item arrays (:class:`FlatArm`)
#   F_I     the current item index
#   F_COUNT iterations completed for the current item (resumes a descending
#            loop across sub-frame pushes)
#   F_OUT   the parent sink list — where a clone frame's model appends, or a
#            transparent frame's children funnel
#   F_MODE  the build-mode (one of the ``BUILD_*`` constants)
#   F_CLONE the frame's :class:`FlatClone` (its fold and baked build plan)
#   F_START the cursor position where the frame began (its span start)
#   F_ENDS  per-item end positions (``ends[i]`` written as each item finishes);
#            item ``i``'s span is ``(start if i==0 else ends[i-1], ends[i])``.
#            Allocated for every frame so the driver's write stays branch-free;
#            only span-reading ``sequence`` clones read it back
#   F_SINKS per-item descent sub-model lists, allocated lazily on first descent
#            (capture frames), else ``None``
F_ARM, F_I, F_COUNT, F_OUT, F_MODE, F_CLONE, F_START, F_ENDS, F_SINKS = range(9)


def finish_delegate(
    sub: Any, clone: FlatClone, window_text: str, pos: int
) -> tuple[int, object] | None:
    """Drive a delegate sub-kernel to completion — fail-soft + window-edge rule.

    The shared body of both :meth:`~lexic.parsing.pda.runtime.runtime.PdaKernel
    ._delegate_run` and its reduce twin: the only per-path difference is which
    sub-kernel (model vs reduce) is built, so that construction stays on each
    override and the completion / decline logic lives here.

    :param sub: A fresh sub-kernel over ``window_text`` (model or reduce).
    :param clone: The delegable rule's flat clone.
    :param window_text: The island window (the sub-parse's whole input).
    :param pos: The start position within ``window_text``.
    :returns: ``(end, payload)``, or ``None`` when the sub-run fails
        (:class:`PdaFail`) or reaches the window edge (a possibly-truncated span
        — fall through so the island doubling window grows).
    """
    try:
        end, payload = sub.prefix_run(clone, pos)
    except PdaFail:
        return None
    if end == len(window_text):
        return None
    return end, payload


def alt_model(frame: list[Any]) -> object:
    """The first sub-model under an ``alternation`` frame's matched arm."""
    sinks = frame[F_SINKS]
    if sinks:
        for sub in sinks:
            if sub:
                return sub[0]
    return None


def build_sequence(text: str, frame: list[Any], clone: FlatClone) -> object:
    """Build a ``sequence`` clone's model from its bound field slots.

    The per-field fold is inlined (``text`` / ``gtext`` read the item's span
    off the frame's ``F_ENDS``, ``model`` / ``models`` its ``F_SINKS``). A
    zero-item arm match builds ``ctor()`` (the rule's empty alternate arm);
    any other item-count mismatch is a compile/runtime disagreement. With a
    :class:`~lexic.parsing.fold.FastCtor` licence the parts dict is seeded
    from the clone's baked defaults and handed to the validation-skip
    constructor; without one, :func:`build_validated` runs the rule's
    validated constructor.

    :raises UnsupportedConstructError: On an item count that matches neither
        the bound fields nor the empty arm, or a mode outside
        :data:`~lexic.ir.bind.BIND_MODES`.
    """
    fold = clone.fold
    arm = frame[F_ARM]
    if arm.n != fold.n_items:
        if arm.n:
            raise UnsupportedConstructError(
                f"pda: {fold.ctor!r}: {arm.n} items match neither "
                f"{fold.n_items} slots nor the empty arm"
            )
        return fold.ctor()  # empty alternate arm matched
    if clone.fast is None:
        return build_validated(text, frame, fold)
    return build_fast(text, clone, frame[F_START], frame[F_ENDS], frame[F_SINKS])


def build_fast(
    text: str,
    clone: FlatClone,
    start: int,
    ends: list[int],
    sinks: list[Any] | None,
) -> object:
    """Build a fast-licenced ``sequence`` model from item spans and sinks.

    Seeds the parts dict from the clone's baked defaults, fills each bound
    field per its int-coded mode, and hands the parts to the
    validation-skip constructor — the shared build tail of
    :func:`build_sequence` and :meth:`~lexic.parsing.pda.runtime.runtime.PdaKernel
    ._run_leaf`.

    :param text: The whole input.
    :param clone: The clone (fast licence granted).
    :param start: The match's span start.
    :param ends: Per-item end positions.
    :param sinks: Per-item sub-model lists, or ``None``.
    :returns: The built model.
    """
    parts = dict(clone.defaults)
    keys: set[str] = set()
    for item, mode, name, lo in clone.fields:
        if mode == M_MODEL:
            sub = sinks[item] if sinks else None
            if sub:
                parts[name] = sub[0]
                keys.add(name)
        elif mode == M_MODELS:
            sub = sinks[item] if sinks else None
            parts[name] = sub if sub is not None else []
            keys.add(name)
        elif mode == M_GTEXT:
            span = text[(start if item == 0 else ends[item - 1]) : ends[item]]
            if span or lo:
                parts[name] = span
                keys.add(name)
        else:  # M_TEXT
            parts[name] = text[(start if item == 0 else ends[item - 1]) : ends[item]]
            keys.add(name)
    return clone.fast(parts, keys)


def build_validated(text: str, frame: list[Any], fold: RuleFold) -> object:
    """Build a ``sequence`` model through the validated constructor.

    The no-licence fallback of :func:`build_sequence` — field extraction
    is identical, but the values pass through ``fold.ctor`` (pydantic
    validation included).

    :raises UnsupportedConstructError: On a mode outside
        :data:`~lexic.ir.bind.BIND_MODES`.
    """
    fold_fields = fold.fields
    ends = frame[F_ENDS]
    sinks = frame[F_SINKS]
    start = frame[F_START]
    kwargs: dict[str, object] = {}
    for item, mode, name, lo in fold_fields:
        if mode == "text":
            kwargs[name] = text[(start if item == 0 else ends[item - 1]) : ends[item]]
        elif mode == "gtext":
            span = text[(start if item == 0 else ends[item - 1]) : ends[item]]
            if span or lo != 0:
                kwargs[name] = span
        elif mode == "model":
            sub = sinks[item] if sinks else None
            if sub:
                kwargs[name] = sub[0]
        elif mode == "models":
            sub = sinks[item] if sinks else None
            kwargs[name] = sub if sub is not None else []
        else:
            raise UnsupportedConstructError(f"pda: unknown field mode {mode!r}")
    return fold.ctor(**kwargs)


def leaf_mismatch(clone: FlatClone, out: list[Any], n: int, pos: int) -> int:
    """A leaf arm whose item count misses the fold — empty arm, or error.

    :returns: ``pos`` unchanged (the empty alternate arm consumed nothing).
    :raises UnsupportedConstructError: On a non-empty mismatch (a
        compile/runtime disagreement).
    """
    fold = clone.fold
    if n:
        raise UnsupportedConstructError(
            f"pda: {fold.ctor!r}: {n} items match neither "
            f"{fold.n_items} slots nor the empty arm"
        )
    out.append(fold.ctor())  # empty alternate arm matched
    return pos
