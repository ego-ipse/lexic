"""The product-side build bake — a clone's build state from its rule product.

The flat runtime is already product-shaped:
:attr:`~lexic.parsing.pda.compiler.program.flatten.FlatClone.fields` IS a
capture layout and :attr:`~lexic.parsing.pda.compiler.program.flatten.FlatClone
.plan` IS a class-ordered construction plan. This module fills both from the
ABI's own records — one :class:`~lexic.parsing.product.RuleProduct` and the
:class:`~lexic.parsing.product.RecordConstructor` its completion names — so the
predictive runtime's build state stops being spelled in the generated model's
own vocabulary.

Two things the fold said twice and the product says once:

* **Absence, not a quantifier.** A capture's flat ``lo`` is read at exactly
  three places, every one of them a zero-test inside a text branch, so it is
  written ``0`` when the record says the capture may be absent and ``1``
  otherwise. Nothing downstream can tell a required ``{1,1}`` capture from a
  required ``{3,7}`` one, and the ABI does not pretend otherwise.
* **One text mode, carrying the absence question.** The fold held ``text`` and
  ``gtext`` apart and then asked ``lo`` which of the two it meant. There is
  one TEXT capture here, so an absence-bearing one codes :data:`M_GTEXT` and
  every other one :data:`M_TEXT` — the two branches compute the same value
  for any non-zero ``lo``, which is the only case in which they differ.

The class is read for the two things only the class knows — its field order
and its own positional constructor. Which captures fill which fields, which
may be absent, and what an omitted field falls back to all come off the
record.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.compiler.program.flatten import FlatClone
from lexic.parsing.pda.compiler.program.opcodes import (
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
    RecordConstructor,
    RecordOp,
    RuleProduct,
)


type ConstructionLicence = tuple[
    Callable[[list[Any]], object], Mapping[str, Any], tuple[str, ...]
]
"""``(positional constructor, field defaults, field order)`` — what a declared
record class says about building one of itself."""


def _licence_of(cls: type) -> ConstructionLicence:
    """The construction licence a declared record class answers with.

    The one thing the bake asks of the class a constructor record names, and
    it asks once, cold. Everything else about the construction — which
    captures fill which fields, which may be absent, what an omitted one falls
    back to — is on the record already.
    """
    construct: Callable[[], ConstructionLicence] = cls.fast_construct
    return construct()


_CAPTURE_CODES: Mapping[int, int] = {
    int(CaptureMode.ONE): M_MODEL,
    int(CaptureMode.MANY): M_MODELS,
    int(CaptureMode.EXTENT): M_SPAN,
}
"""Capture mode → flat build mode, for every mode absence does not split."""


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


def _constructor_of(
    product: RuleProduct, constructors: Sequence[RecordConstructor]
) -> RecordConstructor | None:
    """The constructor record a rule's completion names, if it names one.

    A fused build plan is a plan for constructing a DECLARED RECORD, so only a
    record completion has one. A rule that completes through an expression
    program or passes a child through builds by its own route and wants no
    plan — this is that answer, not a fallback: the clone still captures, and
    the empty plan says truthfully that nothing here constructs a record.

    :param product: The rule's authored product.
    :param constructors: The program's constructor operand table.
    :returns: The named constructor record, or ``None``.
    """
    completion = product.completion
    if not isinstance(completion, RecordOp):
        return None
    return constructors[completion.constructor]


def bake_product_build(
    clone: FlatClone,
    product: RuleProduct | None,
    constructors: Sequence[RecordConstructor],
) -> None:
    """Fill a clone's build state from its rule product, in place.

    The clone's own lifecycle — its fold, leaf licence, char table and run arm
    — belongs to whoever mints the clone; this writes the build state and
    nothing else.

    :param clone: The clone shell to fill.
    :param product: Its rule's product, or ``None`` for a transparent clone.
    :param constructors: The program's constructor operand table.
    """
    clone.needs_ends = product is not None and any(
        spec.mode == CaptureMode.TEXT for spec in product.captures
    )
    constructor = None if product is None else _constructor_of(product, constructors)
    if product is None or constructor is None or not constructor.licensed:
        clone.fields = ()
        clone.plan = ()
        clone.fast = None
        clone.defaults = None
        return
    make, _class_defaults, order = _licence_of(constructor.cls)
    absent = frozenset(constructor.optional)
    clone.fields = tuple(
        (
            spec.slot,
            _capture_code(spec.mode, at in absent),
            constructor.names[at],
            0 if at in absent else 1,
        )
        for at, spec in enumerate(product.captures)
    )
    clone.plan = _build_plan(product, constructor, order, absent)
    clone.fast = make
    clone.defaults = dict(constructor.defaults)


def _build_plan(
    product: RuleProduct,
    constructor: RecordConstructor,
    order: tuple[str, ...],
    absent: frozenset[int],
) -> tuple[tuple[int, int, int, Any], ...]:
    """The positional plan — one ``(mode, item, lo, default)`` per class field.

    Three cases, and the third is the rule whose value IS what it matched: the
    record names the field its own extent fills, so nothing here has to infer
    it from what the other two cases left over.

    :param product: The rule's authored product.
    :param constructor: Its constructor record.
    :param order: The class's field names, in construction order.
    :param absent: Capture indices the record admits being absent.
    :returns: One plan entry per field of the class.
    """
    filled = {name: at for at, name in enumerate(constructor.names)}
    defaults = constructor.defaults
    matched = constructor.matched_field
    plan: list[tuple[int, int, int, Any]] = []
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
        code = _capture_code(spec.mode, at in absent)
        plan.append((code, spec.slot, 0 if at in absent else 1, defaults.get(name)))
    return tuple(plan)
