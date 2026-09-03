"""Runtime class synthesis — codegen grammar + binding view → classes + fold.

Instead of emitting Python source, writing a file and importing it, each
:class:`~lexic.compile.binding.RuleMap` becomes a class built directly with
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

from lexic.compile.foldkit import ALT_PRODUCT
from lexic.compile.pipeline.naming import VALUE_FIELD
from lexic.compile.pipeline.rulemap import (
    RuleMap,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAst,
    IrBind,
    IrItem,
    IrRule,
    IrSequence,
    rule_closure,
)
from lexic.model import GrammarModel
from lexic.parsing.product import (
    CAPTURE_FOR_BIND,
    CaptureSpec,
    RecordConstructor,
    RecordOp,
    RuleProduct,
)

# A synthesized field's annotation is a neutral placeholder — ``object``. Only
# field *names* drive ``_fields``; the annotation type is never read at runtime
# (``__binds__`` is the metadata channel), so every field annotates as ``object``.


def _binds_table(bind: RuleMap) -> dict[int, tuple[str, IrBind]]:
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


def _sequence_namespace(bind: RuleMap, rule: IrRule) -> dict[str, object]:
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


def _field_namespace(bind: RuleMap, rule: IrRule) -> dict[str, object]:
    """The kind-specific field namespace: annotations + defaults.

    ``value_str`` gets a single implicit ``value`` field; ``alternation`` is a
    field-less pass-through; ``sequence`` binds one field per item.

    :param bind: The rule's binding view.
    :param rule: The rule from the codegen grammar.
    :returns: A namespace fragment carrying ``__annotations__`` (and any
        optional-field defaults).
    """
    if bind.kind == "value_str":
        return {"__annotations__": {VALUE_FIELD: object}}
    if bind.kind == "alternation":
        return {"__annotations__": {}}
    return _sequence_namespace(bind, rule)


def _class_namespace(
    bind: RuleMap, rule: IrRule, module: str, shape: int
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
    codegen_grammar: IrAst, binding: list[RuleMap], identity: str
) -> dict[str, type]:
    """Build the model classes for a codegen grammar directly, no source emit.

    Each :class:`RuleMap` becomes a :class:`GrammarModel` subclass via
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


def _model_captures(
    bound: RuleMap, items: Sequence[IrItem]
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
        mode = CAPTURE_FOR_BIND.get(bind.mode)
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
    binding: list[RuleMap],
    classes: dict[str, type],
    omit: frozenset[str] = frozenset(),
) -> ModelPlan:
    """Author the generated-model product from the binding view.

    The generated-model specialization: what the binding view says a rule
    expressed instead as the ABI's own records, so both engines complete
    through one vocabulary. The class stays the binding's own synthesized
    class and the field order stays the binding's, so this authors the same
    construction the fold does — the difference is the shape it is written in.

    A ``value_str`` rule binds no field: its whole body is the value, so it
    captures nothing and declares instead which class field its own matched
    text fills. That is the one construction fact the bound fields cannot
    carry, because there is no item to point at. An ``alternation`` builds
    nothing at all and takes the shared pass-through, so the constructor table
    holds a row only for a rule that really constructs one.

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
        codes[bound.rule_name] = len(products)
        if bound.kind == "alternation":
            # An alternation constructs nothing — it hands its matched arm's
            # one model on. Said with the same record every authored surface
            # spells it with, rather than a constructor naming a class this
            # rule never calls.
            products.append(ALT_PRODUCT)
            continue
        specs, names, optional = _model_captures(bound, items)
        cls = classes[bound.class_name]
        constructors.append(
            RecordConstructor(
                cls,
                names,
                optional,
                _model_defaults(cls),
                VALUE_FIELD if bound.kind == "value_str" else "",
                _fast_licence(cls, bound.kind, names, optional),
            )
        )
        products.append(RuleProduct(specs, RecordOp(len(constructors) - 1), len(items)))
    return ModelPlan(tuple(products), tuple(constructors), codes)


def _model_defaults(cls: type) -> Mapping[str, object]:
    """What an omitted field of ``cls`` falls back to."""
    if not issubclass(cls, GrammarModel):
        return {}
    return cls.fast_construct()[1]


def _fast_licence(
    cls: type, kind: str, names: tuple[str, ...], optional: tuple[int, ...]
) -> bool:
    """Whether this rule may build through the class's positional constructor.

    The class-level half comes from :meth:`GrammarModel.fast_construct`
    (trivially granted on the record spine). The rule-level half asks whether
    skipping validation could ever hide a missing field: every field the
    completion can leave unset — one the record marks optional, or one the
    captures never name at all — must have a default to fall back on.

    Said in the product's own vocabulary rather than the fold's, so the
    licence the constructor carries is derived from the captures that
    constructor is built from, not from a second description of them.

    :param cls: The rule's generated model class.
    :param kind: The rule's binding kind.
    :param names: The keyword each capture fills, in capture order.
    :param optional: Capture indices the record admits being absent.
    :returns: Whether the validation-skip licence is granted.
    """
    if kind == "alternation" or not issubclass(cls, GrammarModel):
        return False
    filled = {VALUE_FIELD} if kind == "value_str" else set(names)
    model_names = set(cls._fields)
    if not filled <= model_names:
        return False
    defaults = _model_defaults(cls)
    if any(name not in filled and name not in defaults for name in model_names):
        return False
    return all(names[at] in defaults for at in optional)
