"""The per-shape build tail — one callable, composed once, at bake time.

A record's fields differ from one rule to the next; the WORK each field needs
does not. So the mode decision is made once per field per shape, when the
clone is baked, and the shape keeps a callable that never looks at a mode
again. That callable IS the build: no plan walk, no comparison chain, no
generic dispatcher underneath it.

**One contract.** :func:`shape_build` takes a class and its plan and returns
``build(text, ends, sinks) -> record``. Everything it composes comes from the
plan's own entries — mode, item, bound, default — and nothing is keyed on a
grammar, a rule or a class name. A grammar nobody has written yet gets a
builder with no new code.

**One selection point**, on arity alone: an unrolled template up to
:data:`UNROLL_LIMIT`, and above it a builder whose per-field walk is a list
comprehension. PEP 709 inlines a comprehension into its enclosing function, so
it pays no frame — the distinction a generator expression does not get, and
the reason the comprehension is the general answer rather than a fallback.

**Why the bindings are closures.** Per-shape binding IS the mechanism here,
not an implementation of it: the whole saving is that ``item``, ``lo`` and
``default`` stop being read per record, and a closure cell is how a function
holds them without being passed them. A nested ``def`` that is a helper wants
to be module-level; these are the composed product, returned and stored on the
clone. Any form that hands the per-shape state back at call time — an extra
argument, an attribute load — re-introduces the cost being removed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Never

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrSpan
from lexic.parsing.pda.compiler.program.opcodes import (
    M_CONST,
    M_GTEXT,
    M_MODEL,
    M_MODELS,
    M_SPAN,
    M_TEXT,
    M_VALUE,
)
from lexic.parsing.product.abi.construction import ProductValue

__all__ = [
    "UNROLL_LIMIT",
    "ShapeBuild",
    "Validated",
    "VstrBuild",
    "no_shape_build",
    "no_validated_build",
    "no_vstr_build",
    "shape_build",
    "validated_build",
    "vstr_build",
]

UNROLL_LIMIT = 8
"""Widest arity with a template of its own.

Unrolling is worth a flat ~125 ns per record from arity one to six, so no
measured width stops paying and the limit is not a cliff. It sits at eight
because the general builder's per-field cost FALLS as shapes widen (227 ns per
field at arity one, 88 at arity nine), so the fraction an extra template buys
shrinks while its lines do not. Nothing reads the roster: a shape wider than
this is built by the general path, correctly and without new code.

The ground-truth corpus happens to top out at arity eight as well, and that
coincidence is not what fixed the limit — the per-field trend above is. The
general builder was priced well past this width, and the unit tests exercise
nine, ten, eleven and twenty-four.
"""

type Sinks[Carry] = Sequence[Sequence[Carry] | None] | None
"""Per-item sub-model sinks, as the kernel fills them."""

type Read[Carry] = Callable[[str, Sequence[int], Sinks[Carry]], ProductValue[Carry]]
"""One field's value, read from the capture state.

A frame that never descended keeps no sinks at all, so the two reads that
touch them test for that — the same test the generic dispatcher paid.
"""

type ShapeBuild[Carry] = Callable[[str, Sequence[int], Sinks[Carry]], Carry]
"""One shape's whole build."""


def no_shape_build[Carry](
    _text: str, _ends: Sequence[int], _sinks: Sinks[Carry]
) -> Carry:
    """What a clone that builds nothing carries.

    :raises UnsupportedConstructError: Always — reaching it is a bake defect,
        never input.
    """
    raise UnsupportedConstructError("pda: this clone has no positional build")


# ── one operation per field, bound once at bake ───────────────────────


def _read_model[Carry](item: int, default: ProductValue[Carry]) -> Read[Carry]:
    """The item's sole sub-model, or the field's default."""

    def read(_text, _ends, sinks):
        sub = sinks[item] if sinks else None
        return sub[0] if sub else default

    return read


def _read_models[Carry](item: int, _default: ProductValue[Carry]) -> Read[Carry]:
    """The item's whole run, frozen."""

    def read(_text, _ends, sinks):
        return tuple((sinks[item] if sinks else None) or ())

    return read


def _read_text[Carry](item: int, _default: ProductValue[Carry]) -> Read[Carry]:
    """The characters the item consumed."""

    def read(text, ends, _sinks):
        return text[ends[item] : ends[item + 1]]

    return read


def _read_gtext[Carry](item: int, lo: int, default: ProductValue[Carry]) -> Read[Carry]:
    """A literal-only group's text; empty is absence only where it may be."""

    def read(text, ends, _sinks):
        span = text[ends[item] : ends[item + 1]]
        return span if (span or lo) else default

    return read


def _read_span[Carry](item: int, _default: ProductValue[Carry]) -> Read[Carry]:
    """Where the item was consumed, in the document's own code units."""

    def read(_text, ends, _sinks):
        return IrSpan(ends[item], ends[item + 1])

    return read


def _read_const[Carry](_item: int, default: ProductValue[Carry]) -> Read[Carry]:
    """A field no item supplies: its declared default."""

    def read(_text, _ends, _sinks):
        return default

    return read


_READS: dict[int, Callable[..., Read]] = {
    M_TEXT: _read_text,
    M_MODEL: _read_model,
    M_MODELS: _read_models,
    M_SPAN: _read_span,
    M_CONST: _read_const,
}
"""Mode to the operation it names. Read once per field, at bake.

Two modes are absent, for different reasons. ``M_GTEXT`` is the one mode that
also needs the item's lower bound, so :func:`field_read` binds it apart rather
than widening every other entry to carry an argument only one of them reads.
``M_VALUE`` is a mode no composed build can serve: it means the rule's OWN
matched extent, which is not any item's span, and the clone carrying it is
``BUILD_VALUE_STR`` — routed to ``vstr_once`` and built by
:func:`~lexic.parsing.pda.compiler.program.flatten.vstr_model`, which reads
the extent from the frame. Refused here rather than answered with item zero's
text, which is the same string only when the rule has one item.
"""


def field_read[Carry](
    mode: int, item: int, lo: int, default: ProductValue[Carry]
) -> Read[Carry]:
    """One field's operation, bound from its own plan entry and nothing else.

    :param mode: The field's mode code.
    :param item: The grammar item it reads.
    :param lo: The item's lower bound — what decides whether empty text is a
        value or an absence.
    :param default: What an absent field falls back to.
    :returns: The bound read.
    :raises UnsupportedConstructError: On a mode outside the vocabulary.
    """
    if mode == M_GTEXT:
        return _read_gtext(item, lo, default)
    make = _READS.get(mode)
    if make is None:
        raise UnsupportedConstructError(f"pda: no build operation for mode {mode!r}")
    return make(item, default)


# ── the builders: arity is the only thing selected on ─────────────────


def _general[Carry](cls: type, reads: tuple[Read[Carry], ...]) -> ShapeBuild[Carry]:
    """Any arity, any mode mix. The comprehension is inlined by PEP 709."""

    def build(text, ends, sinks):
        return tuple.__new__(cls, [read(text, ends, sinks) for read in reads])

    return build


def _at1[Carry](cls: type, reads: tuple[Read[Carry], ...]) -> ShapeBuild[Carry]:
    """Arity one, unrolled."""
    (r0,) = reads

    def build(text, ends, sinks):
        return tuple.__new__(cls, (r0(text, ends, sinks),))

    return build


def _at2[Carry](cls: type, reads: tuple[Read[Carry], ...]) -> ShapeBuild[Carry]:
    """Arity two, unrolled."""
    r0, r1 = reads

    def build(text, ends, sinks):
        return tuple.__new__(cls, (r0(text, ends, sinks), r1(text, ends, sinks)))

    return build


def _at3[Carry](cls: type, reads: tuple[Read[Carry], ...]) -> ShapeBuild[Carry]:
    """Arity three, unrolled."""
    r0, r1, r2 = reads

    def build(text, ends, sinks):
        return tuple.__new__(
            cls,
            (r0(text, ends, sinks), r1(text, ends, sinks), r2(text, ends, sinks)),
        )

    return build


def _at4[Carry](cls: type, reads: tuple[Read[Carry], ...]) -> ShapeBuild[Carry]:
    """Arity four, unrolled."""
    r0, r1, r2, r3 = reads

    def build(text, ends, sinks):
        return tuple.__new__(
            cls,
            (
                r0(text, ends, sinks),
                r1(text, ends, sinks),
                r2(text, ends, sinks),
                r3(text, ends, sinks),
            ),
        )

    return build


def _at5[Carry](cls: type, reads: tuple[Read[Carry], ...]) -> ShapeBuild[Carry]:
    """Arity five, unrolled."""
    r0, r1, r2, r3, r4 = reads

    def build(text, ends, sinks):
        return tuple.__new__(
            cls,
            (
                r0(text, ends, sinks),
                r1(text, ends, sinks),
                r2(text, ends, sinks),
                r3(text, ends, sinks),
                r4(text, ends, sinks),
            ),
        )

    return build


def _at6[Carry](cls: type, reads: tuple[Read[Carry], ...]) -> ShapeBuild[Carry]:
    """Arity six, unrolled."""
    r0, r1, r2, r3, r4, r5 = reads

    def build(text, ends, sinks):
        return tuple.__new__(
            cls,
            (
                r0(text, ends, sinks),
                r1(text, ends, sinks),
                r2(text, ends, sinks),
                r3(text, ends, sinks),
                r4(text, ends, sinks),
                r5(text, ends, sinks),
            ),
        )

    return build


def _at7[Carry](cls: type, reads: tuple[Read[Carry], ...]) -> ShapeBuild[Carry]:
    """Arity seven, unrolled."""
    r0, r1, r2, r3, r4, r5, r6 = reads

    def build(text, ends, sinks):
        return tuple.__new__(
            cls,
            (
                r0(text, ends, sinks),
                r1(text, ends, sinks),
                r2(text, ends, sinks),
                r3(text, ends, sinks),
                r4(text, ends, sinks),
                r5(text, ends, sinks),
                r6(text, ends, sinks),
            ),
        )

    return build


def _at8[Carry](cls: type, reads: tuple[Read[Carry], ...]) -> ShapeBuild[Carry]:
    """Arity eight, unrolled."""
    r0, r1, r2, r3, r4, r5, r6, r7 = reads

    def build(text, ends, sinks):
        return tuple.__new__(
            cls,
            (
                r0(text, ends, sinks),
                r1(text, ends, sinks),
                r2(text, ends, sinks),
                r3(text, ends, sinks),
                r4(text, ends, sinks),
                r5(text, ends, sinks),
                r6(text, ends, sinks),
                r7(text, ends, sinks),
            ),
        )

    return build


_TEMPLATES: dict[int, Callable[..., ShapeBuild]] = {
    1: _at1,
    2: _at2,
    3: _at3,
    4: _at4,
    5: _at5,
    6: _at6,
    7: _at7,
    8: _at8,
}
"""One per arity up to :data:`UNROLL_LIMIT`, keyed by arity.

Hand-written, never generated. A wider shape takes :func:`_general`.
"""


def shape_build[Carry](
    cls: type[Carry], plan: Sequence[tuple[int, int, int, ProductValue[Carry]]]
) -> ShapeBuild[Carry]:
    """Compose one shape's build, once, from its plan alone.

    The record is unchanged: this constructs exactly what the class's own
    positional licence constructs — ``tuple.__new__(cls, values)``, validation
    skipped, which is what the licence grants — with the per-field mode
    decision taken here instead of per record. The grant is checked where it
    is issued (``compile.pipeline.synthesis``), so a class whose positional
    constructor is not the spine's own never reaches this.

    :param cls: The record class the licence was granted for.
    :param plan: Its class-ordered plan, one ``(mode, item, lo, default)`` per
        field.
    :returns: ``build(text, ends, sinks)``.
    :raises UnsupportedConstructError: On a mode outside the vocabulary.
    """
    reads = tuple(
        field_read(mode, item, lo, default) for mode, item, lo, default in plan
    )
    template = _TEMPLATES.get(len(reads))
    return _general(cls, reads) if template is None else template(cls, reads)


# ── the value_str build: the rule's own extent, composed at bake ──────────

type VstrBuild[Carry] = Callable[[str], Carry]
"""One ``value_str`` shape's whole build, given the extent it matched."""


def no_vstr_build(_span: str) -> Never:
    """What a clone that is not a ``value_str`` carries.

    ``Never`` rather than a bound ``Carry``: this function does not return, and
    saying so is what lets it stand in for any record's build — a type variable
    appearing only in the return position has nothing to bind it.

    :raises UnsupportedConstructError: Always — reaching it is a bake defect.
    """
    raise UnsupportedConstructError("pda: this clone builds no value_str")


def _vstr_only[Carry](construct, _consts, _slot: int) -> VstrBuild[Carry]:
    """The whole record IS the matched extent — one field, one value."""

    def build(span):
        return construct([span])

    return build


def _vstr_beside[Carry](construct, consts: list, slot: int) -> VstrBuild[Carry]:
    """The extent plus constant fields — the constants are fixed at bake."""

    def build(span):
        values = consts.copy()
        values[slot] = span
        return construct(values)

    return build


def _vstr_keyword[Carry](ctor, matched: str) -> VstrBuild[Carry]:
    """No positional licence: the class's own checked constructor, by name."""

    def build(span):
        return ctor(**{matched: span})

    return build


def vstr_build[Carry](
    construct,
    plan: Sequence[tuple[int, int, int, ProductValue[Carry]]],
    ctor,
    matched: str,
) -> VstrBuild[Carry]:
    """Compose one ``value_str`` shape's build, once, from its plan alone.

    The record is unchanged: the matched extent fills the one field the plan
    marks :data:`M_VALUE` and every other field takes its constant, which is
    what the per-call plan walk computed. Only the extent varies between
    calls, so everything else is decided here.

    The one-field case is given its own form because it is overwhelmingly the
    common one — a rule whose value IS its text usually has nothing else — and
    it skips the copy the general form needs.

    :param construct: The class's positional constructor, or ``None`` when no
        licence was granted.
    :param plan: The class-ordered plan; empty without a licence.
    :param ctor: The class's keyword constructor, for the unlicensed path.
    :param matched: The field the rule's own extent fills.
    :returns: ``build(span)``.
    """
    slots = [at for at, (mode, *_rest) in enumerate(plan) if mode == M_VALUE]
    if construct is None or not plan or len(slots) != 1:
        return _vstr_keyword(ctor, matched)
    consts = [default for _m, _i, _lo, default in plan]
    if len(consts) == 1:
        return _vstr_only(construct, consts, slots[0])
    return _vstr_beside(construct, consts, slots[0])


# ── the validated build: kwargs and intern key, composed at bake ──────────

type Validated[Carry] = Callable[
    [str, Sequence[int], Sinks[Carry]], tuple[dict[str, ProductValue[Carry]], tuple]
]
"""One shape's keyword build state: ``(kwargs, key_parts)``."""


def no_validated_build[Carry](
    _text: str, _ends: Sequence[int], _sinks: Sinks[Carry]
) -> tuple[dict[str, ProductValue[Carry]], tuple]:
    """What a clone with no keyword layout carries."""
    return {}, ()


def _put_text(item: int, name: str):
    """A required TEXT capture: always present, always keyed."""

    def put(text, ends, _sinks, kwargs, keys):
        span = text[ends[item] : ends[item + 1]]
        kwargs[name] = span
        keys.append(span)

    return put


def _put_gtext(item: int, name: str):
    """An absence-bearing TEXT capture: an empty span is OMITTED, not filled."""

    def put(text, ends, _sinks, kwargs, keys):
        span = text[ends[item] : ends[item + 1]]
        if span:
            kwargs[name] = span
        keys.append(span or None)

    return put


def _put_model(item: int, name: str):
    """One sub-model, omitted when the item never produced one."""

    def put(_text, _ends, sinks, kwargs, keys):
        sub = sinks[item] if sinks else None
        if sub:
            kwargs[name] = sub[0]
        keys.append(id(sub[0]) if sub else None)

    return put


def _put_models(item: int, name: str):
    """A run of sub-models — always filled, empty where nothing descended."""

    def put(_text, _ends, sinks, kwargs, keys):
        sub = (sinks[item] if sinks else None) or []
        kwargs[name] = sub
        keys.append(tuple(id(model) for model in sub))

    return put


def _put_span(item: int, name: str):
    """Where the item was consumed, as an address."""

    def put(_text, ends, _sinks, kwargs, keys):
        extent = IrSpan(ends[item], ends[item + 1])
        kwargs[name] = extent
        keys.append(extent)

    return put


_PUTS: dict[int, Callable[[int, str], Any]] = {
    M_TEXT: _put_text,
    M_GTEXT: _put_gtext,
    M_MODEL: _put_model,
    M_MODELS: _put_models,
    M_SPAN: _put_span,
}
"""Capture mode to the operation it names. Read once per capture, at bake.

``M_CONST`` and ``M_VALUE`` are absent because neither is a CAPTURE: the
keyword layout holds only fields an item fills, and a field no item fills is
left to the class's own default.
"""


def validated_build[Carry](
    fields: Sequence[tuple[int, int, str, int]],
) -> Validated[Carry]:
    """Compose one shape's keyword build, once, from its capture layout.

    Same contract as the per-capture walk it replaces: an ABSENT capture is
    omitted from the keywords rather than filled, which is what lets a declared
    class apply its own default and an authored transform tell "the tail
    matched nothing" from "the tail matched a value" — and it is still
    represented in the key parts, so two different absences cannot collide in
    the intern memo.

    :param fields: The ``(item, mode, name, lo)`` capture layout.
    :returns: ``build(text, ends, sinks) -> (kwargs, key_parts)``.
    :raises UnsupportedConstructError: On a capture mode outside the vocabulary.
    """
    puts = []
    for item, mode, name, _lo in fields:
        make = _PUTS.get(mode)
        if make is None:
            raise UnsupportedConstructError(f"pda: unknown capture mode {mode!r}")
        puts.append(make(item, name))
    frozen = tuple(puts)

    def build(text, ends, sinks):
        kwargs: dict[str, ProductValue[Carry]] = {}
        keys: list = []
        for put in frozen:
            put(text, ends, sinks, kwargs, keys)
        return kwargs, tuple(keys)

    return build
