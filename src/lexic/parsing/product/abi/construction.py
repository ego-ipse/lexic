"""Construction records — what a completion builds its value WITH.

Two of them reach a completion and the split is deliberate. A
:class:`RecordConstructor` names a declared record CLASS; a
:class:`SymbolConstructor` names a registry KEY standing for an authored
surface's transform. They are separate types because their contracts differ —
only a class can grant the positional validation-skip licence, and only a
registry key needs resolving — and yet both answer the same three questions a
completion asks: what to call, which keyword each capture fills, and which
captures may be absent.

Nothing here holds a callable except :class:`BoundSymbol`, which IS the
resolved form and is built by lowering alone. That is what keeps the authored
layer inert: a surface hands over names, and only the compiler turns one into
something callable, through that surface's own whitelist.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import NamedTuple, Protocol, cast

from lexic.ir import IrSpan

__all__ = [
    "BoundSymbol",
    "Construction",
    "ConstructionLicence",
    "ProductValue",
    "RecordConstructor",
    "SymbolConstructor",
    "record_construction",
    "symbol_construction",
]


type ProductValue[Carry] = Carry | str | list[Carry] | tuple[Carry, ...] | IrSpan | None
"""The values a model-product capture or constructor default may carry."""


type ConstructionLicence[Carry] = tuple[
    Callable[[list[ProductValue[Carry]]], Carry],
    Mapping[str, ProductValue[Carry]],
    tuple[str, ...],
]
"""A record's positional constructor, defaults, and field order."""


class _LicensedRecord[Carry](Protocol):
    """The cold class-side protocol behind a granted construction licence."""

    @classmethod
    def fast_construct(cls) -> ConstructionLicence[Carry]:
        """Return the class's positional construction licence."""
        ...


class RecordConstructor[Carry](NamedTuple):
    """A declared constructor and the spelling its captures are laid out in.

    A bare class cannot build a record: construction needs which captures fill
    which fields, which may be ABSENT, and what an absent one falls back to.
    Those are the rule's binding, not the class, so they travel with it here.
    Everything is binding-owned; ``cls`` is the one class object a declaration
    named, and no factory, lambda or bound method appears anywhere in the
    record — which is what keeps :class:`RecordOp` callable-free at a frequent
    completion.

    :ivar cls: The class to construct.
    :ivar names: The field each capture fills, in capture order.
    :ivar optional: Capture indices that may be absent. An absent one is
        OMITTED so the class's default applies; passing empty text instead
        would turn "matched nothing" into "matched the empty string".
    :ivar defaults: What an omitted field falls back to on the licensed
        positional path, which cannot omit. The value type stays open because
        a declared record's defaults are the record's own. Measured, not
        assumed: every generated-model default in the ground-truth corpus is
        Python ``None`` (90 of 90) — the model layer's absent-optional
        concession, deliberately not ``IrNone`` — so narrowing to that would
        encode one product's fact into an ABI other products share.
    :ivar matched_field: The field the occurrence's OWN matched text fills,
        ``""`` when no field does. Distinct from a TEXT capture, which takes
        one CHILD slot's text: this is the whole extent the rule consumed, and
        a rule whose value IS what it matched has no slot to point at.
        Declared rather than inferred — it is derivable (a field no capture
        fills and no default covers can only be this one), and lowering keeps
        that derivation as a cross-check, but a record whose defaults later
        changed would flip the inference silently.
    :ivar licensed: Whether construction may skip per-field validation — a
        flag rather than a bound constructor, so the table holds no callable.
    """

    cls: type[Carry]
    names: tuple[str, ...] = ()
    optional: tuple[int, ...] = ()
    defaults: Mapping[str, ProductValue[Carry]] = MappingProxyType({})
    matched_field: str = ""
    licensed: bool = False


class SymbolConstructor(NamedTuple):
    """A registry-named transform and the keywords its captures fill.

    The symbol-side twin of :class:`RecordConstructor`, for the authored
    compile-time surfaces whose completions are transforms rather than declared
    record classes. Everything here is INERT: ``symbol`` is a registry key, and
    lowering is what turns it into a callable — the same no-``exec`` boundary
    :class:`~lexic.parsing.product.abi.expressions.SymbolExpr` draws.

    Application is BY KEYWORD, which is load-bearing rather than stylistic: an
    absent optional capture is OMITTED from the call, so a transform whose job
    is to tell "the tail matched nothing" from "the tail matched ``IrNone``"
    (``foldkit.absent_tail``) can still tell them apart. Applying positionally,
    or filling an omitted keyword, destroys that distinction silently.

    :ivar symbol: The registry key the surface's whitelist resolves.
    :ivar names: The keyword each capture fills, in capture order.
    :ivar optional: Capture indices that may be absent; an absent one is
        omitted from the keywords rather than passed as anything.
    :ivar matched: The keyword the rule's OWN matched extent fills — the
        surface-side spelling of :attr:`RecordConstructor.matched_field`.
    """

    symbol: str
    names: tuple[str, ...] = ()
    optional: tuple[int, ...] = ()
    matched: str = ""


class BoundSymbol[Carry](NamedTuple):
    """One :class:`SymbolConstructor` with its registry key already resolved.

    The only place a surface transform appears as a callable, and lowering is
    its only writer — which is what keeps the authored records callable-free
    while the completion still has something to call. The carve-out is the one
    :attr:`OperandTables.symbols` states.

    :ivar apply: The resolved transform, applied by keyword.
    :ivar names: The keyword each capture fills, in capture order.
    :ivar optional: Capture indices that may be absent.
    :ivar matched: The keyword the rule's own matched extent fills.
    """

    apply: Callable[..., Carry]
    names: tuple[str, ...] = ()
    optional: tuple[int, ...] = ()
    matched: str = ""


class Construction[Carry]:
    """Resolved construction data shared by both model completion engines.

    The authored records keep class objects and symbol keys inert. This is the
    one resolved view both the PDA bake and ParseTree completion consume, so
    capture names, absence, matched-text ownership, and the positional licence
    cannot drift between engines.
    """

    __slots__ = ("call", "defaults", "licence", "matched", "names", "optional")

    def __init__(
        self,
        call: Callable[..., Carry],
        names: tuple[str, ...],
        optional: frozenset[int],
        defaults: Mapping[str, ProductValue[Carry]] = MappingProxyType({}),
        matched: str = "",
        licence: ConstructionLicence[Carry] | None = None,
    ) -> None:
        """Bind one completion's resolved construction data."""
        self.call = call
        self.names = names
        self.optional = optional
        self.defaults = defaults
        self.matched = matched
        self.licence = licence


def _licence_of[Carry](cls: type[Carry]) -> ConstructionLicence[Carry]:
    """Read the cold class-side licence after the authored flag grants it."""
    licensed = cast(_LicensedRecord[Carry], cls)
    return licensed.fast_construct()


def record_construction[Carry](entry: RecordConstructor[Carry]) -> Construction[Carry]:
    """Resolve a declared record constructor into the shared view."""
    return Construction(
        entry.cls,
        entry.names,
        frozenset(entry.optional),
        entry.defaults,
        entry.matched_field,
        _licence_of(entry.cls) if entry.licensed else None,
    )


def symbol_construction[Carry](entry: BoundSymbol[Carry]) -> Construction[Carry]:
    """Resolve an authored surface transform into the shared view."""
    return Construction(
        entry.apply, entry.names, frozenset(entry.optional), matched=entry.matched
    )
