"""The product bake — a clone's build state from its rule product.

The flat runtime is already product-shaped:
:attr:`~lexic.parsing.pda.compiler.program.flatten.FlatClone.fields` IS a
capture layout and :attr:`~lexic.parsing.pda.compiler.program.flatten.FlatClone
.plan` IS a class-ordered construction plan. This module fills them, and
everything else a completion reads, from the ABI's own records — one
:class:`~lexic.parsing.product.RuleProduct` and the construction record its
completion names.

Two construction records reach a completion, and the bake's whole job is that
the runtime cannot tell them apart. A
:class:`~lexic.parsing.product.RecordConstructor` names a declared class; a
:class:`~lexic.parsing.product.BoundSymbol` names a surface transform already
resolved through its own whitelist. Both answer the same three questions — what
to call, which keyword each capture fills, which may be absent — so both bake
into the same slots and the completion sites branch on neither.

Three things the fold said twice and the product says once:

* **Absence, not a quantifier.** A capture's flat ``lo`` is written ``0`` when
  the record says the capture may be absent and ``1`` otherwise. Nothing
  downstream can tell a required ``{1,1}`` capture from a required ``{3,7}``
  one, and the ABI does not pretend otherwise.
* **One text mode, carrying the absence question.** The fold held ``text`` and
  ``gtext`` apart and then asked ``lo`` which of the two it meant. There is
  one TEXT capture here, so an absence-bearing one codes :data:`M_GTEXT` and
  every other one :data:`M_TEXT` — the two branches compute the same value for
  any non-zero ``lo``, which is the only case in which they differ.
* **The build mode, off the completion record.** Passing a child through,
  constructing a record, and filling a field from the rule's own extent are
  three different completions, so the record says which one this is instead of
  a parallel ``kind`` string saying it again.

The class is read for the two things only the class knows — its field order
and its own positional constructor. Which captures fill which fields, which
may be absent, and what an omitted field falls back to all come off the record.
"""

from __future__ import annotations

from typing import Mapping

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.compiler.program.flatten import (
    FlatClone,
    clear_build,
    no_construction,
    no_fast_construction,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_ALT,
    BUILD_SEQ,
    BUILD_TRANSPARENT,
    BUILD_VALUE_STR,
    M_CONST,
    M_GTEXT,
    M_MODEL,
    M_MODELS,
    M_SPAN,
    M_TEXT,
    M_VALUE,
)
from lexic.parsing.product import (
    CaptureMode,
    Construction,
    ConstructionTables,
    PassOp,
    ProductValue,
    RuleProduct,
    construction_of,
)

_CAPTURE_CODES: Mapping[int, int] = {
    int(CaptureMode.ONE): M_MODEL,
    int(CaptureMode.MANY): M_MODELS,
    int(CaptureMode.EXTENT): M_SPAN,
}
"""Capture mode → flat build mode, for every mode absence does not split."""

_ENDS_MODES = frozenset((int(CaptureMode.TEXT), int(CaptureMode.EXTENT)))
"""The capture modes that read an item's end position back off the frame.

Both of them: a TEXT capture slices the item's span out of the input and an
EXTENT capture reports it as an address. A clone with either keeps per-item
ends, and one with neither lets the driver advance past an exactly-once
reference without recording where it stopped."""


def _capture_code(mode: int, absent: bool) -> int:
    """The flat build mode one capture executes under.

    :param mode: The capture's :class:`~lexic.parsing.product.CaptureMode`.
    :param absent: Whether the record admits this capture being absent.
    :returns: The ``M_*`` build mode.
    :raises UnsupportedConstructError: On a mode that fills no model field.
    """
    if mode == CaptureMode.TEXT:
        return M_GTEXT if absent else M_TEXT
    code = _CAPTURE_CODES.get(mode)
    if code is None:
        raise UnsupportedConstructError(
            f"pda: capture mode {mode} fills no model field"
        )
    return code


def _build_mode[Carry](
    product: RuleProduct[Carry] | None,
    construction: Construction[Carry] | None,
) -> int:
    """Which shape of completion this clone runs.

    Read off the completion record rather than off a parallel ``kind`` string:
    a transparent clone has no product at all, a pass-through names no
    construction, and a construction that fills a field from the rule's own
    extent is the ``value_str`` shape. Everything else builds from its
    captured items.
    """
    if product is None:
        return BUILD_TRANSPARENT
    if construction is None:
        return BUILD_ALT if isinstance(product.completion, PassOp) else BUILD_SEQ
    return BUILD_VALUE_STR if construction.matched else BUILD_SEQ


def bake_product_build[Carry](
    clone: FlatClone[Carry],
    product: RuleProduct[Carry] | None,
    tables: ConstructionTables[Carry],
    completion: int = -1,
) -> None:
    """Fill a clone's build state from its rule product, in place.

    Writes everything a completion site reads and nothing else: the build mode,
    what construction calls, the arm width it recognises its empty alternate
    arm by, the keyword capture layout, and — only where a class granted the
    positional licence — the class-ordered plan it builds through instead.

    :param clone: The clone shell to fill.
    :param product: Its rule's product, or ``None`` for a transparent clone.
    :param tables: The program's construction operand tables.
    :param completion: The verified completion range this build state was
        derived from, or ``-1`` for a clone whose rule has none. Recorded as
        PROVENANCE: no runtime function reads it, and it exists so a clone can
        be checked against the range the verifier bounded rather than against
        a second derivation of the same answer.
    """
    clone.completion = completion
    clone.leaf = False  # granted by _mark_leaves once the arm shapes are final
    clone.chartable = None  # baked last, off the final plan, by bake_chartables
    clone.chartotal = True
    clone.runarm = None
    construction = None if product is None else construction_of(product, tables)
    clone.mode = _build_mode(product, construction)
    clone.n_items = 0 if product is None else product.n_items
    clone.needs_ends = product is not None and any(
        spec.mode in _ENDS_MODES for spec in product.captures
    )
    if product is None or construction is None:
        clone.ctor = no_construction
        clone.matched = ""
        clear_build(clone)
        return
    clone.ctor = construction.call
    clone.matched = construction.matched
    clone.fields = _capture_layout(product, construction)
    licence = construction.licence
    if licence is None:
        clone.plan = ()
        clone.fast = no_fast_construction
        clone.defaults = None
        return
    make, _class_defaults, order = licence
    clone.plan = _build_plan(product, construction, order)
    clone.fast = make
    clone.defaults = dict(construction.defaults)


def _capture_layout[Carry](
    product: RuleProduct[Carry], construction: Construction[Carry]
) -> tuple[tuple[int, int, str, int], ...]:
    """The keyword layout — one ``(item, mode, name, lo)`` per capture.

    What the validated build reads. Filled for every construction, licensed or
    not, because the licence only says whether the POSITIONAL plan may be used
    instead; a clone without one still has to know which keyword each capture
    fills.
    """
    return tuple(
        (
            spec.slot,
            _capture_code(spec.mode, at in construction.optional),
            construction.names[at],
            0 if at in construction.optional else 1,
        )
        for at, spec in enumerate(product.captures)
    )


def _build_plan[Carry](
    product: RuleProduct[Carry],
    construction: Construction[Carry],
    order: tuple[str, ...],
) -> tuple[tuple[int, int, int, ProductValue[Carry]], ...]:
    """The positional plan — one ``(mode, item, lo, default)`` per class field.

    Three cases, and the third is the rule whose value IS what it matched: the
    record names the field its own extent fills, so nothing here has to infer
    it from what the other two cases left over.

    :param product: The rule's authored product.
    :param construction: Its construction data.
    :param order: The class's field names, in construction order.
    :returns: One plan entry per field of the class.
    """
    filled = {name: at for at, name in enumerate(construction.names)}
    defaults = construction.defaults
    matched = construction.matched
    plan: list[tuple[int, int, int, ProductValue[Carry]]] = []
    for name in order:
        at = filled.get(name)
        if at is None:
            plan.append(
                (M_VALUE, 0, 0, None)
                if name == matched
                else (M_CONST, 0, 0, defaults.get(name))
            )
            continue
        spec = product.captures[at]
        absent = at in construction.optional
        code = _capture_code(spec.mode, absent)
        plan.append((code, spec.slot, 0 if absent else 1, defaults.get(name)))
    return tuple(plan)
