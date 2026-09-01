"""Runtime class synthesis — codegen grammar + binding view → classes + fold.

Instead of emitting Python source, writing a file and importing it, each
:class:`~lexic.compile.binding.RuleBinding` becomes a class built directly with
``type(name, bases, ns)``. CPython computes the winning metaclass
(:class:`~lexic.ir.spine.meta.IrMeta`) from the bases and delegates, so a bare
``type(...)`` call yields a proper :class:`~lexic.model.GrammarModel` record —
no source, no import.

The namespace each class carries:

- ``__module__`` / ``__qualname__`` — set explicitly (``type`` would otherwise
  default ``__module__`` to *this* module's name);
- ``__grammar__`` — the class's rule from the codegen grammar;
- ``__binds__`` — the item-slot → ``(field name, IrBind)`` table, written
  directly (settled 14: no annotation pass, no rebuild). ``_child_attrs``
  falls out of :meth:`GrammarModel.__init_subclass__` reading it;
- ``__annotations__`` — one entry per field, in item order, so
  :class:`~lexic.ir.base.IrNamedTuple`'s ``__init_subclass__`` derives
  ``_fields``. The annotation *value* is never read at runtime (the binds
  table is the metadata channel), so a neutral placeholder is used;
- a ``None`` class attribute for every optional field, the record's default.

Bases come in binding order (parents before subclasses — the binding view is
emitted parents-first), so a subclass's parent classes always exist when it is
built. A parentless rule subclasses :class:`GrammarModel` directly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NamedTuple

from lexic.compile.pipeline.binding import (
    RuleBinding,
    check_supplied_class,
    field_kwargs,
)
from lexic.ir import (
    IrAst,
    IrBind,
    IrItem,
    IrLambda,
    IrMap,
    IrNone,
    IrRule,
    IrRuleRef,
    IrSequence,
    IrTuple,
    rule_closure,
)
from lexic.model import GrammarModel
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing import FastCtor, FieldFold, ModelBody
from lexic.parsing.product import (
    CaptureMode,
    CaptureSpec,
    RecordConstructor,
    RecordOp,
    RuleProduct,
)

# A synthesized field's annotation is a neutral placeholder — ``object``. Only
# field *names* drive ``_fields``; the annotation type is never read at runtime
# (``__binds__`` is the metadata channel), so every field annotates as ``object``.


def _binds_table(bind: RuleBinding) -> dict[int, tuple[str, IrBind]]:
    """The class's ``__binds__``: item slot → ``(field name, IrBind)``.

    :param bind: The rule's binding view (``fields`` is name → :class:`IrBind`,
        in item order).
    :returns: The slot-keyed binds table :meth:`GrammarModel.bound_fields`
        returns.
    """
    return {ibind.item: (name, ibind) for name, ibind in bind.fields.items()}


def _sequence_arm(rule: IrRule) -> IrSequence:
    """The rule's single non-empty sequence arm (empty when it has none)."""
    return next((arm for arm in rule.body if arm), IrSequence())


def _is_optional_field(bind: IrBind, item: IrItem, empty_arm: bool) -> bool:
    """Whether a bound field takes a ``None`` default — the emitter's rule.

    A field is optional (and so record-defaulted to ``None``) when its rule
    carries an empty alternate arm (every field may then be absent), or when a
    non-``models`` field's item can match nothing (``lo == 0``). ``models``
    fields stay a list and only default under the empty-arm force.

    :param bind: The field's binding.
    :param item: The bound item in the rule's sequence arm.
    :param empty_arm: Whether the rule body has an empty (epsilon) arm.
    :returns: ``True`` when the field defaults to ``None``.
    """
    return empty_arm or (bind.mode != "models" and item.quantifier.lo == 0)


def _sequence_namespace(bind: RuleBinding, rule: IrRule) -> dict[str, object]:
    """Field annotations + optional-field ``None`` defaults for a sequence class.

    :param bind: The rule's binding view.
    :param rule: The rule from the codegen grammar.
    :returns: A namespace fragment carrying ``__annotations__`` and defaults.
    """
    arm = _sequence_arm(rule)
    empty_arm = any(not a for a in rule.body)
    annotations: dict[str, object] = {}
    ns: dict[str, object] = {}
    for name, ibind in bind.fields.items():
        annotations[name] = object
        if _is_optional_field(ibind, arm[ibind.item], empty_arm):
            ns[name] = None
    ns["__annotations__"] = annotations
    return ns


def _field_namespace(bind: RuleBinding, rule: IrRule) -> dict[str, object]:
    """The kind-specific field namespace: annotations + defaults.

    ``value_str`` gets a single implicit ``value`` field; ``alternation`` is a
    field-less pass-through; ``sequence`` binds one field per item.

    :param bind: The rule's binding view.
    :param rule: The rule from the codegen grammar.
    :returns: A namespace fragment carrying ``__annotations__`` (and any
        optional-field defaults).
    """
    if bind.kind == "value_str":
        return {"__annotations__": {"value": object}}
    if bind.kind == "alternation":
        return {"__annotations__": {}}
    return _sequence_namespace(bind, rule)


def _class_namespace(
    bind: RuleBinding, rule: IrRule, module: str, shape: int
) -> dict[str, object]:
    """The full ``ns`` for ``type(class_name, bases, ns)``.

    :param bind: The rule's binding view.
    :param rule: The class's rule from the codegen grammar (its ``__grammar__``).
    :param module: The synthetic module name (``__module__``).
    :param shape: The rule's closure digest (its ``__shape__``).
    :returns: The class namespace.
    """
    ns = _field_namespace(bind, rule)
    ns["__module__"] = module
    ns["__qualname__"] = bind.class_name
    ns["__grammar__"] = rule
    ns["__shape__"] = shape
    ns["__binds__"] = _binds_table(bind)
    return ns


def synthesize(
    codegen_grammar: IrAst, binding: list[RuleBinding], identity: str
) -> dict[str, type]:
    """Build the model classes for a codegen grammar directly, no source emit.

    Each :class:`RuleBinding` becomes a :class:`GrammarModel` subclass via
    ``type(name, bases, ns)`` — multiple-inheritance bases in binding order
    (parents-first), the class's ``__grammar__`` rule, and its ``__binds__``
    table written directly. No file is written and no module is imported.

    :param codegen_grammar: The post-pass grammar (each rule is a class's
        ``__grammar__``).
    :param binding: The binding view, parents before subclasses.
    :param identity: The grammar's content identity — the synthetic
        ``__module__`` is ``generated.<identity>``. NOT the artefact's ``stem``,
        which names the exported file: two different grammars can share a
        filename, and a consumer telling two ``Root``s apart has only this.
    :returns: ``{class_name: class}`` for every synthesized class.
    """
    rules = {str(rule.name): rule for rule in codegen_grammar.rules}
    shapes = rule_closure(codegen_grammar)
    module = f"generated.{identity}"
    classes: dict[str, type] = {}
    for bind in binding:
        rule = rules[bind.rule_name]
        bases = tuple(classes[name] for name in bind.parent_class_names) or (
            GrammarModel,
        )
        ns = _class_namespace(bind, rule, module, shapes[bind.rule_name])
        classes[bind.class_name] = type(bind.class_name, bases, ns)
    return classes


def _fast_ctor(cls: type, kind: str, fields: tuple[FieldFold, ...]) -> FastCtor | None:
    """Grant a rule's :class:`~lexic.parsing.fold.FastCtor` licence, or refuse.

    The class-level half comes from :meth:`GrammarModel.fast_construct`
    (trivially granted on the record spine); the fold-level half checks
    that every field the fold can leave unset (a ``gtext`` or ``model``
    bind whose item can match nothing, ``lo == 0``) has a default to fall
    back on, and that the fold's field names cover every non-defaulted
    model field.

    :param cls: The rule's generated model class.
    :param kind: The rule's fold kind.
    :param fields: The rule's bound fields.
    :returns: The licence, or ``None`` (validated construction only).
    """
    if kind == "alternation" or not issubclass(cls, GrammarModel):
        return None
    make, defaults, order = cls.fast_construct()
    names = {"value"} if kind == "value_str" else {f.name for f in fields}
    model_names = set(cls._fields)
    if not names <= model_names:
        return None
    if any(n not in names and n not in defaults for n in model_names):
        return None
    for field in fields:
        skippable = field.mode in ("gtext", "model") and field.lo == 0
        if skippable and field.name not in defaults:
            return None
    return FastCtor(make, defaults, order)


def _derive_body(bound: RuleBinding, cls: type, items: Sequence[IrItem]) -> ModelBody:
    """Derive a rule's :class:`~lexic.parsing.fold.ModelBody` from a supplied class.

    The supplied-class sugar of the open binding table (settled 7): the class
    is the fold constructor, and the body's structural metadata comes from the
    binding view + the codegen grammar's sequence arm.

    :param bound: The rule's binding view.
    :param cls: The supplied constructor class.
    :param items: The rule's single non-empty sequence arm (empty otherwise).
    :returns: The rule's fold body.
    """
    fields = tuple(
        FieldFold(bind.item, bind.mode, name, int(items[bind.item].quantifier.lo))
        for name, bind in bound.fields.items()
    )
    if bound.kind == "alternation":
        return ModelBody("alternation", IrNone, len(items), fields, None)
    return ModelBody(
        bound.kind,
        IrLambda(cls),
        len(items),
        fields,
        _fast_ctor(cls, bound.kind, fields),
    )


def fold_config(
    codegen_grammar: IrAst,
    binding: list[RuleBinding],
    classes: dict[str, type],
    overrides: Mapping[str, ModelBody | type] | None = None,
    omit: frozenset[str] = frozenset(),
) -> IrMap:
    """Build the fold's IR body-table from the binding view — the open table.

    Per rule the compile seam accepts EITHER a full authored
    :class:`~lexic.parsing.fold.ModelBody` (the primitive — used verbatim) OR a
    class serving as the fold constructor (the sugar — :func:`_derive_body`
    builds the body from the binding view). With no ``overrides`` entry a rule
    falls back to its synthesized class (also a supplied class). ``kind`` /
    ``n_items`` / ``FieldFold``\\ s all come from the codegen grammar's single
    non-empty sequence arm (``lo`` from the bound item's quantifier, consumed by
    the ``gtext`` absence rule).

    :param codegen_grammar: The post-pass grammar the binding was computed on.
    :param binding: The binding view, in emission order.
    :param classes: Generated classes by class name.
    :param overrides: Per-rule fold-body override — a
        :class:`~lexic.parsing.fold.ModelBody` (primitive) or a constructor
        class (sugar); ``None`` uses the synthesized classes throughout.
    :param omit: Rules kept recognition-only by leaving them out of the table.
    :returns: An :class:`~lexic.ir.action.mapping.IrMap` from each rule's
        :class:`~lexic.ir.grammar.nodes.IrRuleRef` to its
        :class:`~lexic.parsing.fold.ModelBody`.
    """
    overrides = overrides or {}
    rules = {str(rule.name): rule for rule in codegen_grammar.rules}
    dyads: list[IrTuple] = []
    for bound in binding:
        if bound.rule_name in omit:
            continue
        override = overrides.get(bound.rule_name)
        if isinstance(override, ModelBody):
            dyads.append(IrTuple(IrRuleRef(bound.rule_name), override))
            continue
        arms = [arm for arm in rules[bound.rule_name].body if arm]
        items = arms[0] if bound.kind == "sequence" and arms else ()
        if override is not None:  # a supplied class (sugar) — enforce the contract
            check_supplied_class(override, field_kwargs(bound))
            cls = override
        else:  # the trusted synthesized class
            cls = classes[bound.class_name]
        body = _derive_body(bound, cls, items)
        dyads.append(IrTuple(IrRuleRef(bound.rule_name), body))
    return IrMap(*dyads)


# ── the generated-model product (the §4 specialization) ───────────────


class ModelPlan(NamedTuple):
    """The generated-model product, authored from the binding view.

    Three things a bound product needs and one record to carry them, rather
    than a three-tuple every caller has to decode.

    :ivar rules: One :class:`~lexic.parsing.product.RuleProduct` per rule, in
        contextual-code order.
    :ivar constructors: The constructor operand table lowering validates.
    :ivar codes: Rule name → its contextual code, so a completion site can
        find the rule it is completing.
    """

    rules: tuple[RuleProduct[GrammarModel], ...]
    constructors: tuple[RecordConstructor, ...]
    codes: dict[str, int]


_CAPTURE_MODES: Mapping[str, CaptureMode] = {
    "text": CaptureMode.TEXT,
    "gtext": CaptureMode.TEXT,
    "model": CaptureMode.ONE,
    "models": CaptureMode.MANY,
    "span": CaptureMode.EXTENT,
}
"""The bind vocabulary in the ABI's terms. ``text`` and ``gtext`` capture the
same way — a slot's consumed text — and differ only in what an EMPTY capture
means, which is the rule's ``optional`` set rather than a second mode."""


def _model_captures(
    bound: RuleBinding, items: Sequence[IrItem]
) -> tuple[tuple[CaptureSpec, ...], tuple[str, ...], tuple[int, ...]]:
    """One rule's captures, the field each fills, and which may be absent.

    A ``gtext`` bind whose item can match nothing (``lo == 0``) is the absence
    case: empty text there means the field was NOT THERE, so it is omitted
    from construction and the class's default applies. Recording it as an
    ``optional`` capture index is what carries that rule into the ABI, where
    :class:`~lexic.parsing.product.CaptureSpec` has no room for a quantifier.
    """
    specs: list[CaptureSpec] = []
    names: list[str] = []
    optional: list[int] = []
    for name, bind in bound.fields.items():
        mode = _CAPTURE_MODES.get(bind.mode)
        if mode is None:
            raise UnsupportedConstructError(
                f"model product: {bound.rule_name}.{name} binds through "
                f"unknown mode {bind.mode!r}"
            )
        if bind.mode == "gtext" and int(items[bind.item].quantifier.lo) == 0:
            optional.append(len(specs))
        specs.append(CaptureSpec(int(mode), bind.item))
        names.append(name)
    return tuple(specs), tuple(names), tuple(optional)


def model_plan(
    codegen_grammar: IrAst,
    binding: list[RuleBinding],
    classes: dict[str, type],
    omit: frozenset[str] = frozenset(),
) -> ModelPlan:
    """Author the generated-model product from the binding view.

    The §4 specialization: what :func:`fold_config` expresses as a fold body,
    expressed instead as the ABI's own records, so both engines complete
    through one vocabulary. The class stays the binding's own synthesized
    class and the field order stays the binding's, so this authors the same
    construction the fold does — the difference is the shape it is written in.

    :param codegen_grammar: The post-pass grammar the binding was computed on.
    :param binding: The binding view, in emission order.
    :param classes: Generated classes by class name.
    :param omit: Rules kept recognition-only by leaving them out.
    :returns: The authored plan.
    :raises UnsupportedConstructError: On a bind mode the ABI has no capture
        for.
    """
    rules = {str(rule.name): rule for rule in codegen_grammar.rules}
    products: list[RuleProduct[GrammarModel]] = []
    constructors: list[RecordConstructor] = []
    codes: dict[str, int] = {}
    for bound in binding:
        if bound.rule_name in omit:
            continue
        arms = [arm for arm in rules[bound.rule_name].body if arm]
        items = arms[0] if bound.kind == "sequence" and arms else ()
        specs, names, optional = _model_captures(bound, items)
        cls = classes[bound.class_name]
        codes[bound.rule_name] = len(products)
        constructors.append(
            RecordConstructor(
                cls,
                names,
                optional,
                _model_defaults(cls),
                _fast_ctor(cls, bound.kind, _fold_fields(bound, items)) is not None,
            )
        )
        products.append(RuleProduct(specs, RecordOp(len(constructors) - 1)))
    return ModelPlan(tuple(products), tuple(constructors), codes)


def _model_defaults(cls: type) -> Mapping[str, object]:
    """What an omitted field of ``cls`` falls back to."""
    if not issubclass(cls, GrammarModel):
        return {}
    return cls.fast_construct()[1]


def _fold_fields(bound: RuleBinding, items: Sequence[IrItem]) -> tuple[FieldFold, ...]:
    """The rule's bound fields in the fold's spelling — the licence's input.

    Reads the SAME binding the captures do, so the licence the product carries
    is the licence the fold grants, not a second judgement about the class.
    """
    return tuple(
        FieldFold(bind.item, bind.mode, name, int(items[bind.item].quantifier.lo))
        for name, bind in bound.fields.items()
    )
