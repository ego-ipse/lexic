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

from collections.abc import Callable, Hashable, Sequence
from enum import Enum
from typing import Any

from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.ir import IrSpan
from lexic.parsing.pda.compiler.program.flatten import (
    FlatArm,
    FlatClone,
    no_fast_construction,
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
from lexic.parsing.product.abi.construction import ProductValue


class InternMiss(Enum):
    """The typed miss marker for a construction intern lookup."""

    TOKEN = 0


INTERN_MISS = InternMiss.TOKEN
"""Miss sentinel for the per-parse intern memo — distinct from any built model
(a ``dict.get`` default that no real value can equal, so a genuine ``None`` sink
is never mistaken for a hit)."""

# ── the frame ──────────────────────────────────────────────────────────────


class Frame[Carry]:
    """One in-progress arm execution on the kernel's explicit descent stack.

    A *clone frame* (a non-transparent :attr:`mode`) captures what its
    completion needs and builds a single model on pop; a *transparent frame*
    (``BUILD_TRANSPARENT`` — an inline group or look-through clone) owns no
    capture and funnels every model produced inside it straight to :attr:`out`.

    Slotted and typed rather than a flat list: the lanes have different types
    and the driver reads them by name, so a nine-wide list erased every one of
    them and made the sink lane in particular unnameable. The slots cost what
    the list indices cost — one descriptor read — and the layout is now stated
    where it is used rather than by a comment beside nine constants.

    :ivar arm: The selected arm's flat item arrays.
    :ivar i: The current item index.
    :ivar count: Iterations completed for the current item, which is what
        resumes a descending loop across sub-frame pushes.
    :ivar out: The parent sink list — where a clone frame's model appends, or
        a transparent frame's children funnel.
    :ivar clone: The frame's clone (its constructor, build plan and mode).
    :ivar ends: Item boundaries, ``arm.n + 1`` of them: ``ends[0]`` is where
        the frame began and ``ends[i + 1]`` is where item ``i`` finished, so
        item ``i``'s span is ``(ends[i], ends[i + 1])`` with no first-item
        special case anywhere that reads one. ``None`` for a clone whose build
        reads no position at all (``needs_ends`` false), which on the benchmark
        grammars is EVERY frame: those filled a list nothing read.
    :ivar sinks: Per-item descent sub-model lists, allocated lazily on first
        descent (capture frames), else ``None``.
    """

    __slots__ = ("arm", "i", "count", "out", "clone", "ends", "sinks")

    arm: FlatArm
    i: int
    count: int
    out: list[Carry]
    clone: FlatClone[Carry]
    ends: list[int] | None
    sinks: list[list[Carry] | None] | None

    def __init__(
        self, arm: FlatArm, out: list[Carry], clone: FlatClone[Carry], start: int
    ) -> None:
        """Begin one execution of ``arm`` at ``start``, funnelling into ``out``."""
        self.arm = arm
        self.i = 0
        self.count = 0
        self.out = out
        self.clone = clone
        self.ends = [start] * (arm.n + 1) if clone.needs_ends else None
        self.sinks = None

    def span_start(self) -> int:
        """Where the frame began, or ``-1`` when it keeps no boundaries.

        The sentinel is not a fallback but the honest answer: a frame whose
        build reads no position never asks (every clone that reads one keeps
        boundaries), and a caller comparing control states wants exactly
        "this frame's start cannot reach any value".
        """
        ends = self.ends
        return -1 if ends is None else ends[0]

    def close_loop(self, i: int, pos: int) -> int:
        """Close item ``i``'s loop at the current count, and advance past it.

        The frame's own bookkeeping, so the driver states the decision and the
        frame states what the decision does to it.

        :returns: The next item index.
        """
        self.count = 0
        self.i = i + 1
        ends = self.ends
        if ends is not None:
            ends[i + 1] = pos
        return i + 1

    def alt_model(self) -> Carry | None:
        """The first sub-model under an ``alternation`` frame's matched arm."""
        if self.sinks:
            for sub in self.sinks:
                if sub:
                    return sub[0]
        return None


type InternKey[Carry] = tuple[Callable[..., Carry], str | tuple[Hashable, ...]]
type InternMemo[Carry] = dict[InternKey[Carry], Carry]


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


def build_sequence[Carry](
    text: str,
    frame: Frame[Carry],
    clone: FlatClone[Carry],
    memo: InternMemo[Carry],
) -> Carry:
    """Build a ``sequence`` clone's model from its bound field slots.

    The per-capture read is inlined (a text capture reads the item's span
    off the frame's ``ends``, ``model`` / ``models`` its ``sinks``). A
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
    if frame.arm.n != clone.n_items:
        if frame.arm.n:
            raise UnsupportedConstructError(
                f"pda: {clone.ctor!r}: {frame.arm.n} items match neither "
                f"{clone.n_items} slots nor the empty arm"
            )
        return _intern_empty(clone.ctor, memo)  # empty alternate arm matched
    spans = (frame.ends or (), frame.sinks)
    if clone.fast is no_fast_construction:
        return build_validated(text, spans, clone, memo)
    return clone.fast(fast_values(text, clone, spans))


def _intern_empty[Carry](ctor: Callable[..., Carry], memo: InternMemo[Carry]) -> Carry:
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


# A fast clone's captured span/sink data — the (item boundaries, per-item sink
# lists) pair grouped so the build sites stay within the argument budget;
# ``_run_leaf`` builds it from locals, ``_complete`` from the frame slots.
# ``ends[0]`` is the span start, so no reader tests for the first item. A clone
# whose build reads no position keeps no boundaries at all and passes ``()``:
# its plan carries no span mode, so nothing indexes it.
type Spans[Carry] = tuple[Sequence[int], list[list[Carry] | None] | None]


def fast_values[Carry](
    text: str, clone: FlatClone[Carry], spans: Spans[Carry]
) -> list[ProductValue[Carry]]:
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
    :param spans: The captured ``(ends, sinks)`` pair.
    :returns: One value per field of the model class.
    """
    ends, sinks = spans
    values: list[ProductValue[Carry]] = []
    for mode, item, lo, default in clone.plan:
        if mode == M_MODEL:
            sub = sinks[item] if sinks else None
            values.append(sub[0] if sub else default)
        elif mode == M_MODELS:
            sub = (sinks[item] if sinks else None) or ()
            values.append(tuple(sub))
        elif mode == M_GTEXT:
            span = text[ends[item] : ends[item + 1]]
            values.append(span if (span or lo) else default)
        elif mode == M_SPAN:
            # The offsets the kernel already has — kept, not recomputed.
            values.append(IrSpan(ends[item], ends[item + 1]))
        elif mode == M_CONST:
            values.append(default)
        else:  # M_TEXT
            values.append(text[ends[item] : ends[item + 1]])
    return values


def build_validated[Carry](
    text: str,
    spans: Spans[Carry],
    clone: FlatClone[Carry],
    memo: InternMemo[Carry],
) -> Carry:
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
    kwargs, key_parts = _validated_fields(text, spans, clone)
    key = (clone.ctor, key_parts)
    hit = memo.get(key, INTERN_MISS)
    if hit is not INTERN_MISS:
        return hit
    model = clone.ctor(**kwargs)
    memo[key] = model
    return model


def _validated_fields[Carry](
    text: str, spans: Spans[Carry], clone: FlatClone[Carry]
) -> tuple[dict[str, ProductValue[Carry]], tuple[Hashable, ...]]:
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
    ends, sinks = spans
    kwargs: dict[str, ProductValue[Carry]] = {}
    key_parts: list[Hashable] = []
    for item, mode, name, _lo in clone.fields:
        if mode == M_TEXT:
            span = text[ends[item] : ends[item + 1]]
            kwargs[name] = span
            key_parts.append(span)
        elif mode == M_GTEXT:
            span = text[ends[item] : ends[item + 1]]
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
            extent = IrSpan(ends[item], ends[item + 1])
            kwargs[name] = extent
            key_parts.append(extent)
        else:
            raise UnsupportedConstructError(f"pda: unknown capture mode {mode!r}")
    return kwargs, tuple(key_parts)


def leaf_mismatch[Carry](
    clone: FlatClone[Carry],
    out: list[Carry],
    n: int,
    pos: int,
    memo: InternMemo[Carry],
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


def build_vstr[Carry](
    clone: FlatClone[Carry], span: str, memo: InternMemo[Carry]
) -> Carry:
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
