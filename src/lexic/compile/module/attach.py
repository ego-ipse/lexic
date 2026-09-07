"""Runtime binding for generated twin-module model classes."""

from __future__ import annotations

from collections.abc import Mapping

from lexic.compile.pipeline.moments import build_codegen_grammar
from lexic.compile.pipeline.rulemap import RuleMap, compute_binding
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, rule_closure
from lexic.model import GrammarModel


def _expected_fields(bound: RuleMap) -> tuple[str, ...]:
    """Return the generated record fields declared by a binding view."""
    if bound.kind == "value_str":
        return ("value",)
    if bound.kind == "alternation":
        return ()
    return tuple(bound.fields)


def attach_module(grammar: IrAst, namespace: Mapping[str, object]) -> None:
    """Attach grammar, shape, and bind tables to generated module classes."""
    codegen_grammar = build_codegen_grammar(grammar)
    rules = {str(rule.name): rule for rule in codegen_grammar.rules}
    shapes = rule_closure(codegen_grammar)
    for bound in compute_binding(codegen_grammar):
        cls = namespace.get(bound.class_name)
        if not (isinstance(cls, type) and issubclass(cls, GrammarModel)):
            raise UnsupportedConstructError(
                f"attach_module: rule {bound.rule_name!r} needs a GrammarModel "
                f"class named {bound.class_name!r} in the module"
            )
        expected = _expected_fields(bound)
        declared = tuple(cls._fields)
        if declared != expected:
            raise UnsupportedConstructError(
                f"attach_module: class {bound.class_name!r} declares fields "
                f"{declared}, but rule {bound.rule_name!r} binds {expected}"
            )
        cls.__grammar__ = rules[bound.rule_name]
        cls.__shape__ = shapes[bound.rule_name]
        cls.__binds__ = {b.item: (n, b) for n, b in bound.fields.items()}
