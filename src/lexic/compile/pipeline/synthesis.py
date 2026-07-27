"""Runtime class synthesis — codegen grammar + binding view → model classes.

Instead of emitting Python source, writing a file and importing it, each
:class:`~lexic.compile.binding.RuleBinding` becomes a class built directly with
``type(name, bases, ns)``. CPython computes the winning metaclass
(:class:`~lexic.ir.meta.IrMeta`) from the bases and delegates, so a bare
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

from lexic.compile.pipeline.binding import RuleBinding
from lexic.ir.bind import IrBind
from lexic.ir.nodes import IrAst, IrItem, IrRule, IrSequence
from lexic.model import GrammarModel

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


def _class_namespace(bind: RuleBinding, rule: IrRule, module: str) -> dict[str, object]:
    """The full ``ns`` for ``type(class_name, bases, ns)``.

    :param bind: The rule's binding view.
    :param rule: The class's rule from the codegen grammar (its ``__grammar__``).
    :param module: The synthetic module name (``__module__``).
    :returns: The class namespace.
    """
    ns = _field_namespace(bind, rule)
    ns["__module__"] = module
    ns["__qualname__"] = bind.class_name
    ns["__grammar__"] = rule
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
    module = f"generated.{identity}"
    classes: dict[str, type] = {}
    for bind in binding:
        rule = rules[bind.rule_name]
        bases = tuple(classes[name] for name in bind.parent_class_names) or (
            GrammarModel,
        )
        ns = _class_namespace(bind, rule, module)
        classes[bind.class_name] = type(bind.class_name, bases, ns)
    return classes
