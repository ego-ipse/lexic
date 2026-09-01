"""Frame vocabulary + the fused model-build tail (PDA runtime leaf).

The slot layout of the :class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel` descent
frame (the ``F_*`` indices) and the functions that fold a completed frame into
a model — a ``sequence`` clone's per-field slot reads (fast or validated), an
``alternation``'s pass-through, and the leaf empty-arm build. Shed out of
``kernel/kernel.py`` so the paid loop and build tail remain separately sized.

The record build is POSITIONAL: the clone's plan carries one entry per field
of the model class, so a build fills one values list and constructs the tuple
— no defaults-dict copy, no supplied-key set, no read-back by name.

Interning is kept only where its key is already at hand and cheap: ``value_str``
by ``(ctor, span)`` and the empty alternate arm by ``(ctor, ())``. The record
path is NOT interned — its key needed a second projection of every field
(strings by value, sub-models by ``id``) that cost more than the tuple
construction a hit saves. Interning stays pre-construction, so the validated
path's :exc:`~lexic.exceptions.FieldValidationError` behaviour is unchanged.

A leaf w.r.t. the runtime: these functions read only the input ``text`` plus a
frame / clone (and the memo), never the kernel cursor. Imports only
:mod:`lexic.parsing.pda.compiler.program.flatten` (the flat records + capture-mode
codes) and :mod:`lexic.parsing.pda.core.errors` (:class:`PdaFail`) — never
``runtime``, and no longer the fold.
"""

from __future__ import annotations

from typing import Any, Callable

from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.ir import IrSpan
from lexic.parsing.pda.compiler.program.flatten import (
    FlatClone,
    vstr_model,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    M_CONST,
    M_GTEXT,
    M_MODEL,
    M_MODELS,
    M_SPAN,
    M_TEXT,
)
from lexic.parsing.pda.core.errors import PdaFail

INTERN_MISS: Any = object()
"""Miss sentinel for the per-parse intern memo — distinct from any built model
(a ``dict.get`` default that no real value can equal, so a genuine ``None`` sink
is never mistaken for a hit)."""

# ── frame layout ───────────────────────────────────────────────────────────
#
# A frame is one in-progress arm execution on the kernel's explicit descent
# stack — a flat list (the ``kernel.py`` int-array explicit-stack precedent; the
# class *cursor* is :class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel` itself),
# indexed by the constants below. A *clone frame* (a non-transparent ``F_MODE``)
# captures what its completion needs and builds a single model on pop; a
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
#   F_CLONE the frame's :class:`FlatClone` (its constructor and build plan)
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

    The fail-soft completion body used by
    :meth:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel._delegate_run`.

    :param sub: A fresh model sub-kernel over ``window_text``.
    :param clone: The delegable rule's flat clone.
    :param window_text: The island window (the sub-parse's whole input).
    :param pos: The start position within ``window_text``.
    :returns: ``(end, payload)``, or ``None`` when the sub-run fails
        (:class:`PdaFail`), its completion refuses the span (a
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

    The per-capture read is inlined (a text capture reads the item's span
    off the frame's ``F_ENDS``, ``model`` / ``models`` its ``F_SINKS``). A
    zero-item arm match builds ``ctor()`` (the rule's empty alternate arm);
    any other item-count mismatch is a compile/runtime disagreement. With a
    positional licence the values list is read straight off the clone's baked
    plan and handed to the validation-skip constructor; without one,
    :func:`build_validated` builds by keyword.

    :param memo: The per-parse intern memo — repeated identical sub-models are
        built once and shared (immutable models make sharing transparent).
    :raises UnsupportedConstructError: On an item count that matches neither
        the bound fields nor the empty arm, or a capture mode outside the
        build vocabulary.
    """
    arm = frame[F_ARM]
    if arm.n != clone.n_items:
        if arm.n:
            raise UnsupportedConstructError(
                f"pda: {clone.ctor!r}: {arm.n} items match neither "
                f"{clone.n_items} slots nor the empty arm"
            )
        return _intern_empty(clone.ctor, memo)  # empty alternate arm matched
    if clone.fast is None:
        return build_validated(text, frame, clone, memo)
    return clone.fast(
        fast_values(text, clone, (frame[F_START], frame[F_ENDS], frame[F_SINKS]))
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


def fast_values(text: str, clone: FlatClone, spans: Spans) -> list[Any]:
    """A fast clone's field values, in the record's own field order.

    The fast build IS ``clone.fast(fast_values(text, clone, spans))`` — one pass
    over the plan into a values list, then one tuple construction. It is spelled
    at each call site rather than wrapped in a function of its own: the engine
    builds about one model per character of input, so a wrapper whose whole body
    is that expression is a Python frame per character for no work.

    **Not interned.** The record path's intern key had to project the values a
    second way (strings by value, sub-models by ``id``), and that projection
    plus its tuple, its nested hash and two dict operations cost more than the
    ``tuple.__new__`` a hit saves. Measured hit rates ran 0.0% (csv) to 57.3%
    (vyx), so the memo was not even reliably answering. ``value_str`` models
    still intern (:func:`build_vstr`): that key is ``(ctor, span)``, already at
    hand, and hits 50-95%.

    One pass over :attr:`~lexic.parsing.pda.compiler.program.flatten.FlatClone.plan`,
    which already carries each field's mode, the item it reads and the default
    it falls back on — so the build allocates one list and nothing else.

    :param text: The whole input.
    :param clone: The clone (fast licence granted).
    :param spans: The captured ``(start, ends, sinks)`` triple.
    :returns: One value per field of the model class.
    """
    start, ends, sinks = spans
    values: list[Any] = []
    for mode, item, lo, default in clone.plan:
        if mode == M_MODEL:
            sub = sinks[item] if sinks else None
            values.append(sub[0] if sub else default)
        elif mode == M_MODELS:
            sub = (sinks[item] if sinks else None) or ()
            values.append(tuple(sub))
        elif mode == M_GTEXT:
            span = text[(start if item == 0 else ends[item - 1]) : ends[item]]
            values.append(span if (span or lo) else default)
        elif mode == M_SPAN:
            # The offsets the kernel already has — kept, not recomputed.
            values.append(IrSpan(start if item == 0 else ends[item - 1], ends[item]))
        elif mode == M_CONST:
            values.append(default)
        else:  # M_TEXT
            values.append(text[(start if item == 0 else ends[item - 1]) : ends[item]])
    return values


def build_validated(
    text: str, frame: list[Any], clone: FlatClone, memo: dict[Any, object]
) -> object:
    """Build a ``sequence`` value through the keyword constructor.

    The no-licence path of :func:`build_sequence` — capture extraction
    (:func:`_validated_fields`) is identical, but the values pass through
    ``clone.ctor`` BY KEYWORD: a declared class then validates per field, and
    an authored surface's transform sees exactly the keywords its rule filled.
    Interning stays **pre-construction**: a memo hit returns the already-
    validated instance, while a miss constructs (validation runs, so an invalid
    instance raises :exc:`~lexic.exceptions.FieldValidationError` and is never
    cached) and then stores the result. ``FieldValidationError`` behaviour is
    therefore unchanged.

    :param memo: The per-parse intern memo (same key scheme as
        :func:`fast_values`).
    :raises UnsupportedConstructError: On a capture mode outside the build
        vocabulary.
    """
    kwargs, key_parts = _validated_fields(text, frame, clone)
    key = (clone.ctor, key_parts)
    hit = memo.get(key, INTERN_MISS)
    if hit is not INTERN_MISS:
        return hit
    model = clone.ctor(**kwargs)
    memo[key] = model
    return model


def _validated_fields(
    text: str, frame: list[Any], clone: FlatClone
) -> tuple[dict[str, object], tuple[Any, ...]]:
    """A validated clone's constructor kwargs and intern key-parts, one pass.

    An ABSENT capture is OMITTED from the keywords rather than filled: that is
    what lets a declared class apply its own default and an authored transform
    tell "the tail matched nothing" from "the tail matched a value". Absence is
    :data:`M_GTEXT` for text (the mode the bake writes exactly when the record
    admits one) and an empty sink for a sub-model.

    :returns: ``(kwargs, key_parts)`` — absent captures omitted from ``kwargs``
        yet represented in ``key_parts``.
    :raises UnsupportedConstructError: On a capture mode outside the build
        vocabulary.
    """
    ends = frame[F_ENDS]
    sinks = frame[F_SINKS]
    start = frame[F_START]
    kwargs: dict[str, object] = {}
    key_parts: list[Any] = []
    for item, mode, name, _lo in clone.fields:
        if mode == M_TEXT:
            span = text[(start if item == 0 else ends[item - 1]) : ends[item]]
            kwargs[name] = span
            key_parts.append(span)
        elif mode == M_GTEXT:
            span = text[(start if item == 0 else ends[item - 1]) : ends[item]]
            if span:
                kwargs[name] = span
            key_parts.append(span or None)
        elif mode == M_MODEL:
            sub = sinks[item] if sinks else None
            if sub:
                kwargs[name] = sub[0]
            key_parts.append(id(sub[0]) if sub else None)
        elif mode == M_MODELS:
            sub = (sinks[item] if sinks else None) or []
            kwargs[name] = sub
            key_parts.append(tuple(id(m) for m in sub))
        elif mode == M_SPAN:
            kwargs[name] = IrSpan(start if item == 0 else ends[item - 1], ends[item])
            key_parts.append(kwargs[name])
        else:
            raise UnsupportedConstructError(f"pda: unknown capture mode {mode!r}")
    return kwargs, tuple(key_parts)


def leaf_mismatch(
    clone: FlatClone, out: list[Any], n: int, pos: int, memo: dict[Any, object]
) -> int:
    """A leaf arm whose item count misses the rule's arm — empty arm, or error.

    :param memo: The per-parse intern memo (the empty arm shares one instance).
    :returns: ``pos`` unchanged (the empty alternate arm consumed nothing).
    :raises UnsupportedConstructError: On a non-empty mismatch (a
        compile/runtime disagreement).
    """
    if n:
        raise UnsupportedConstructError(
            f"pda: {clone.ctor!r}: {n} items match neither "
            f"{clone.n_items} slots nor the empty arm"
        )
    out.append(_intern_empty(clone.ctor, memo))  # empty alternate arm matched
    return pos


def build_vstr(clone: FlatClone, span: str, memo: dict[Any, object]) -> object:
    """Build (or reuse) a ``value_str`` model over its matched ``span``.

    The single home of the value_str build both :meth:`~lexic.parsing.pda.runtime
    .runtime.PdaKernel._complete` and :meth:`~lexic.parsing.pda.runtime.kernel.kernel
    .PdaKernel._vstr_once` call: keyed ``(ctor, span)`` in the intern memo, so
    every occurrence of the same class over the same source text shares one
    instance. Uses the clone's positional licence when present, else its
    keyword constructor.

    :param clone: The ``value_str`` clone (or a ``value_str``-ref target).
    :param span: The matched source span (the value the rule's own extent
        fills the field :attr:`~lexic.parsing.pda.compiler.program.flatten
        .FlatClone.matched` names).
    :param memo: The per-parse intern memo.
    :returns: The built (or reused) model.
    """
    key = (clone.ctor, span)
    hit = memo.get(key, INTERN_MISS)
    if hit is not INTERN_MISS:
        return hit
    model = vstr_model(clone, span)
    memo[key] = model
    return model
