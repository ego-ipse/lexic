"""Cross-check generated module text against its compiled binding view."""

from __future__ import annotations

from typing import ClassVar

from lexic.compile.artifact import CompiledGrammar
from lexic.compile.module.export import docstring_lines, field_type, value_str_type
from lexic.compile.module.selfgrammar import MClass, MField, MModule, parse_module
from lexic.compile.pipeline.binding import RuleBinding, compute_binding
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import get_flavour
from lexic.ir import IrBind, IrNamedTuple, IrNoneType, IrRule, IrSequence, rule_closure


def _expected_fields(
    bound: RuleBinding, rule: IrRule, class_by_rule: dict[str, str]
) -> tuple[MField, ...]:
    """Recompute the field records the exporter renders for ``bound``."""
    if bound.kind == "value_str":
        return (MField("value", value_str_type(rule), False),)
    if bound.kind == "alternation":
        return ()
    arm = next((a for a in rule.body if a), IrSequence())
    empty_arm = any(not a for a in rule.body)
    out = []
    for name, ibind in bound.fields.items():
        item = arm[ibind.item]
        optional = empty_arm or (ibind.mode != "models" and item.quantifier.lo == 0)
        type_str = field_type(ibind.mode, item, class_by_rule, optional=optional)
        out.append(MField(name, type_str, optional and ibind.mode != "models"))
    return tuple(out)


def _expected_doc(rule: IrRule, flavour_name: str) -> str:
    rendered = docstring_lines(str(get_flavour(flavour_name).apply(rule, width=None)))
    text = "\n".join(line[4:] if line.startswith("    ") else line for line in rendered)
    return text[3:-3]


def _collapse_wrap(doc: str) -> str:
    return " ".join(
        line if i == 0 else line.lstrip() for i, line in enumerate(doc.split("\n"))
    )


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise UnsupportedConstructError(f"verify_module: {message}")


class _VerifyCtx(IrNamedTuple[dict, str, bool, dict, dict]):
    _child_attrs: ClassVar[tuple[str, ...]] = ()
    class_by_rule: dict
    flavour: str
    inline: bool
    shapes: dict
    authored: dict


def _verify_class(
    mclass: MClass, bound: RuleBinding, rule: IrRule, ctx: _VerifyCtx
) -> None:
    class_by_rule, flavour_name, inline, shapes, authored = ctx
    _check(
        mclass.name == bound.class_name,
        f"class {mclass.name!r} where {bound.class_name!r} expected",
    )
    expected_bases = bound.parent_class_names or ("GrammarModel",)
    _check(
        tuple(mclass.bases) == tuple(expected_bases),
        f"{mclass.name}: bases {mclass.bases!r} != {expected_bases!r}",
    )
    _check(
        _collapse_wrap(mclass.doc) == _collapse_wrap(_expected_doc(rule, flavour_name)),
        f"{mclass.name}: docstring drift",
    )
    expected = _expected_fields(bound, rule, class_by_rule)
    _check(
        tuple(mclass.fields) == expected,
        f"{mclass.name}: fields {tuple(mclass.fields)!r} != {expected!r}",
    )
    if inline:
        _check(
            mclass.inline_grammar == authored.get(bound.rule_name, rule),
            f"{mclass.name}: inline __grammar__ != the rule the runtime carries",
        )
        _check(
            mclass.inline_shape == shapes[bound.rule_name],
            f"{mclass.name}: inline __shape__ != the rule's closure digest",
        )
        expected_binds = tuple(
            (b.item, name, IrBind(b.item, b.mode, b.semantic))
            for name, b in bound.fields.items()
        )
        _check(
            tuple(mclass.inline_binds) == expected_binds,
            f"{mclass.name}: inline __binds__ drift",
        )
    else:
        _check(
            isinstance(mclass.inline_grammar, IrNoneType)
            and not mclass.inline_shape
            and not mclass.inline_binds,
            f"{mclass.name}: inline tables in a bind-mode module",
        )


def verify_module(compiled: CompiledGrammar, text: str) -> MModule:
    """Parse module text and cross-check it against ``compiled``'s binding."""
    module = parse_module(text)
    _check(
        module.grammar == compiled.grammar,
        "GRAMMAR does not equal the compiled canonical AST",
    )
    inline = not module.has_bind
    binding = compute_binding(compiled.codegen_grammar)
    rules = {str(rule.name): rule for rule in compiled.codegen_grammar.rules}
    class_by_rule = {b.rule_name: b.class_name for b in binding}
    _check(
        len(module.classes) == len(binding),
        f"{len(module.classes)} classes for {len(binding)} bindings",
    )
    pre = compiled.tokens.unresolved or compiled.codegen_grammar
    ctx = _VerifyCtx(
        class_by_rule,
        compiled.flavour,
        inline,
        rule_closure(pre),
        {str(rule.name): rule for rule in pre.rules},
    )
    for mclass, bound in zip(module.classes, binding):
        _verify_class(mclass, bound, rules[bound.rule_name], ctx)
    return module
