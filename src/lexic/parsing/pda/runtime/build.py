"""Frame vocabulary + the fused model-build tail (PDA runtime leaf).

The slot layout of the :class:`~lexic.parsing.pda.runtime.runtime.PdaKernel` descent
frame (the ``F_*`` indices) and the functions that fold a completed frame into
a model — a ``sequence`` clone's per-field slot reads (fast or validated), an
``alternation``'s pass-through, and the leaf empty-arm build. Shed out of
``runtime.py`` so the frame vocabulary is shared by name with
``reduce_runtime.py`` (which walks the same frames) rather than crossing a
module boundary as a private import.

Each build site takes the kernel's per-parse **intern memo** (a plain dict —
never the cursor itself) and shares a single instance for repeated identical
sub-models: ``value_str`` keyed ``(ctor, span)``, records keyed ``(ctor,
mixed-part-tuple)`` (text / gtext by string, ``model`` fields by ``id``,
``models`` lists by element ids), the empty arm keyed ``(ctor, ())``.
Immutable models make the sharing transparent, and interning stays
pre-construction so the validated path's
:exc:`~lexic.exceptions.FieldValidationError` behaviour is unchanged.

A leaf w.r.t. the runtime: these functions read only the input ``text`` plus a
frame / clone (and the memo), never the kernel cursor, so they are free
functions the kernel and its reduce twin both call. Imports only
:mod:`lexic.parsing.pda.compiler.flatten` (the flat records + field-mode
codes), :mod:`lexic.parsing.fold` (:class:`RuleFold`) and
:mod:`lexic.parsing.pda.core.errors` (:class:`PdaFail`) — never ``runtime``.
"""

from __future__ import annotations

from typing import Any, Callable

from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.parsing.fold import RuleFold
from lexic.parsing.pda.compiler.flatten import M_GTEXT, M_MODEL, M_MODELS, FlatClone
from lexic.parsing.pda.core.errors import PdaFail

INTERN_MISS: Any = object()
"""Miss sentinel for the per-parse intern memo — distinct from any built model
(a ``dict.get`` default that no real value can equal, so a genuine ``None`` sink
is never mistaken for a hit)."""

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
        (:class:`PdaFail`), its fold refuses the span (a
        :class:`~lexic.exceptions.LexicError` — e.g. a window-truncated token
        that still completes as a valid prefix), or it reaches the window edge
        (a possibly-truncated span). Declining hands the rule back to the
        island's own Earley machinery.
    """
    try:
        end, payload = sub.prefix_run(clone, pos)
    except PdaFail, LexicError:
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


def build_sequence(
    text: str, frame: list[Any], clone: FlatClone, memo: dict[Any, object]
) -> object:
    """Build a ``sequence`` clone's model from its bound field slots.

    The per-field fold is inlined (``text`` / ``gtext`` read the item's span
    off the frame's ``F_ENDS``, ``model`` / ``models`` its ``F_SINKS``). A
    zero-item arm match builds ``ctor()`` (the rule's empty alternate arm);
    any other item-count mismatch is a compile/runtime disagreement. With a
    :class:`~lexic.parsing.fold.FastCtor` licence the parts dict is seeded
    from the clone's baked defaults and handed to the validation-skip
    constructor; without one, :func:`build_validated` runs the rule's
    validated constructor.

    :param memo: The per-parse intern memo — repeated identical sub-models are
        built once and shared (immutable models make sharing transparent).
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
        return _intern_empty(fold.ctor, memo)  # empty alternate arm matched
    if clone.fast is None:
        return build_validated(text, frame, fold, memo)
    return build_fast(
        text, clone, (frame[F_START], frame[F_ENDS], frame[F_SINKS]), memo
    )


def _intern_empty(ctor: Callable[..., object], memo: dict[Any, object]) -> object:
    """Build (or reuse) the empty alternate arm's ``ctor()`` — key ``(ctor, ())``.

    Every zero-item match of the same rule folds to the same field-less model,
    so one shared instance suffices for the whole parse.
    """
    key = (ctor, ())
    hit = memo.get(key, INTERN_MISS)
    if hit is not INTERN_MISS:
        return hit
    model = ctor()
    memo[key] = model
    return model


# A fast clone's captured span/sink data — the (start, per-item ends, per-item
# sink lists) triple grouped so the build sites stay within the argument budget;
# ``_run_leaf`` builds it from locals, ``_complete`` from the frame slots.
Spans = tuple[int, "list[int]", "list[Any] | None"]


def build_fast(
    text: str, clone: FlatClone, spans: Spans, memo: dict[Any, object]
) -> object:
    """Build a fast-licenced ``sequence`` model from item spans and sinks.

    Extracts the clone's parts (:func:`_fast_fields`) plus an intern key (text /
    gtext by string value, ``model`` fields by the sub-model's ``id``, ``models``
    lists by element ids) in one pass, then either returns the memo's already-
    built (immutable) model or constructs one through the validation-skip
    constructor and stores it. The shared build tail of :func:`build_sequence`
    and :meth:`~lexic.parsing.pda.runtime.runtime.PdaKernel._run_leaf`.

    :param text: The whole input.
    :param clone: The clone (fast licence granted).
    :param spans: The captured ``(start, ends, sinks)`` triple.
    :param memo: The per-parse intern memo.
    :returns: The built (or reused) model.
    """
    parts, keys, key_parts = _fast_fields(text, clone, spans)
    key = (clone.fold.ctor, key_parts)
    hit = memo.get(key, INTERN_MISS)
    if hit is not INTERN_MISS:
        return hit
    model = clone.fast(parts, keys)
    memo[key] = model
    return model


def _fast_fields(
    text: str, clone: FlatClone, spans: Spans
) -> tuple[dict[str, object], set[str], tuple[Any, ...]]:
    """A fast clone's parts dict, supplied-key set and intern key-parts, one pass.

    :returns: ``(parts, keys, key_parts)`` — the constructor input and the
        per-field intern key (see :func:`build_fast`).
    """
    start, ends, sinks = spans
    parts = dict(clone.defaults)
    keys: set[str] = set()
    key_parts: list[Any] = []
    for item, mode, name, lo in clone.fields:
        if mode == M_MODEL:
            sub = sinks[item] if sinks else None
            if sub:
                parts[name] = sub[0]
                keys.add(name)
                key_parts.append(id(sub[0]))
            else:
                key_parts.append(None)
        elif mode == M_MODELS:
            sub = (sinks[item] if sinks else None) or []
            parts[name] = sub
            keys.add(name)
            key_parts.append(tuple(id(m) for m in sub))
        elif mode == M_GTEXT:
            span = text[(start if item == 0 else ends[item - 1]) : ends[item]]
            if span or lo:
                parts[name] = span
                keys.add(name)
            key_parts.append(span if (span or lo) else None)
        else:  # M_TEXT
            span = text[(start if item == 0 else ends[item - 1]) : ends[item]]
            parts[name] = span
            keys.add(name)
            key_parts.append(span)
    return parts, keys, tuple(key_parts)


def build_validated(
    text: str, frame: list[Any], fold: RuleFold, memo: dict[Any, object]
) -> object:
    """Build a ``sequence`` model through the validated constructor.

    The no-licence fallback of :func:`build_sequence` — field extraction
    (:func:`_validated_fields`) is identical, but the values pass through
    ``fold.ctor`` (the checked constructor, per-field validation included).
    Interning stays **pre-construction**: a memo hit returns the already-
    validated instance, while a miss constructs (validation runs, so an invalid
    instance raises :exc:`~lexic.exceptions.FieldValidationError` and is never
    cached) and then stores the result. ``FieldValidationError`` behaviour is
    therefore unchanged.

    :param memo: The per-parse intern memo (same key scheme as
        :func:`build_fast`).
    :raises UnsupportedConstructError: On a mode outside
        :data:`~lexic.ir.bind.BIND_MODES`.
    """
    kwargs, key_parts = _validated_fields(text, frame, fold)
    key = (fold.ctor, key_parts)
    hit = memo.get(key, INTERN_MISS)
    if hit is not INTERN_MISS:
        return hit
    model = fold.ctor(**kwargs)
    memo[key] = model
    return model


def _validated_fields(
    text: str, frame: list[Any], fold: RuleFold
) -> tuple[dict[str, object], tuple[Any, ...]]:
    """A validated clone's constructor kwargs and intern key-parts, one pass.

    :returns: ``(kwargs, key_parts)`` — absent optionals omitted from ``kwargs``
        (as the validated ctor expects) yet represented in ``key_parts``.
    :raises UnsupportedConstructError: On a mode outside
        :data:`~lexic.ir.bind.BIND_MODES`.
    """
    ends = frame[F_ENDS]
    sinks = frame[F_SINKS]
    start = frame[F_START]
    kwargs: dict[str, object] = {}
    key_parts: list[Any] = []
    for item, mode, name, lo in fold.fields:
        if mode == "text":
            span = text[(start if item == 0 else ends[item - 1]) : ends[item]]
            kwargs[name] = span
            key_parts.append(span)
        elif mode == "gtext":
            span = text[(start if item == 0 else ends[item - 1]) : ends[item]]
            if span or lo != 0:
                kwargs[name] = span
            key_parts.append(span if (span or lo != 0) else None)
        elif mode == "model":
            sub = sinks[item] if sinks else None
            if sub:
                kwargs[name] = sub[0]
            key_parts.append(id(sub[0]) if sub else None)
        elif mode == "models":
            sub = (sinks[item] if sinks else None) or []
            kwargs[name] = sub
            key_parts.append(tuple(id(m) for m in sub))
        else:
            raise UnsupportedConstructError(f"pda: unknown field mode {mode!r}")
    return kwargs, tuple(key_parts)


def leaf_mismatch(
    clone: FlatClone, out: list[Any], n: int, pos: int, memo: dict[Any, object]
) -> int:
    """A leaf arm whose item count misses the fold — empty arm, or error.

    :param memo: The per-parse intern memo (the empty arm shares one instance).
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
    out.append(_intern_empty(fold.ctor, memo))  # empty alternate arm matched
    return pos


def build_vstr(clone: FlatClone, span: str, memo: dict[Any, object]) -> object:
    """Build (or reuse) a ``value_str`` model over its matched ``span``.

    The single home of the value_str build both :meth:`~lexic.parsing.pda.runtime
    .runtime.PdaKernel._complete` and :meth:`~lexic.parsing.pda.runtime.runtime
    .PdaKernel._vstr_once` call: keyed ``(ctor, span)`` in the intern memo, so
    every occurrence of the same class over the same source text shares one
    instance. Uses the clone's :class:`~lexic.parsing.fold.FastCtor` licence when
    present, else its validated constructor.

    :param clone: The ``value_str`` clone (or a ``value_str``-ref target).
    :param span: The matched source span (the model's ``value``).
    :param memo: The per-parse intern memo.
    :returns: The built (or reused) model.
    """
    key = (clone.fold.ctor, span)
    hit = memo.get(key, INTERN_MISS)
    if hit is not INTERN_MISS:
        return hit
    fast = clone.fast
    model = (
        fast({"value": span}, {"value"})
        if fast is not None
        else clone.fold.ctor(value=span)
    )
    memo[key] = model
    return model
