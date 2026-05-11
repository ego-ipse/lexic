"""Model emitter — IrItem-shape RuleSpec → Python source string.

Target-shape commitments land incrementally:
  Task 9 (this task): class body skeleton + canonical imports + __grammar__ in class body.
  Task 10: Annotated[str, StringConstraints(...)] for pattern fields.
  Task 11: Literal[...] for pure-literal alternations.
  Task 12: Module-level type aliases hoisted from collect_aliases().
  Task 13: __grammar__ moved to module footer.

Decision CQ #1 (no # FIXME): _repr_iritem produces real Python for every shape.
Decision CQ #4 (fixed imports): emit a canonical import block always.
"""

from __future__ import annotations

from io import StringIO

from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import RuleSpec

CANONICAL_IMPORTS = """\
from __future__ import annotations
from typing import ClassVar, List, Literal, Optional, Union

from pydantic import Field, StringConstraints
from typing_extensions import Annotated

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup, IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import RuleSpec
"""


def _is_required(q: Quantifier) -> bool:
    return q.min == 1 and q.max == 1


def _is_optional(q: Quantifier) -> bool:
    return q.min == 0 and q.max == 1


def _field_type_skeleton(item: IrItem, specs_by_rule: dict[str, RuleSpec]) -> str:
    """Skeleton: pattern fields → str; rule refs → cls / Optional[cls] / List[cls]."""
    atom = item.atom
    q = item.quantifier
    if isinstance(atom, (IrLiteral, IrCharClass)):
        return "str"
    if isinstance(atom, IrRuleRef):
        ref = specs_by_rule.get(atom.name)
        cls = ref.class_name if ref else atom.name.replace("-", "_").title()
        if _is_required(q):
            return cls
        if _is_optional(q):
            return f"Optional[{cls}]"
        return f"List[{cls}]"
    if isinstance(atom, IrGroup):
        # Skeleton stage: treat IrGroup as 'str' if no rulerefs, otherwise Union of arm refs.
        arm_refs = []
        for arm in atom.body.arms:
            if len(arm.items) == 1 and isinstance(arm.items[0].atom, IrRuleRef):
                arm_refs.append(arm.items[0].atom.name)
        if arm_refs:
            cls_names = [
                specs_by_rule[n].class_name for n in arm_refs if n in specs_by_rule
            ] or [n.replace("-", "_").title() for n in arm_refs]
            return f"Union[{', '.join(cls_names)}]"
        return "str"
    return "str"


def _repr_quantifier(q: Quantifier) -> str:
    return f"Quantifier({q.min}, {q.max!r})"


def _repr_atom_value(atom) -> str:
    if isinstance(atom, IrLiteral):
        return f"IrLiteral({atom.value!r})"
    if isinstance(atom, IrCharClass):
        return f"IrCharClass({atom.pattern!r}, negated={atom.negated})"
    if isinstance(atom, IrRuleRef):
        return f"IrRuleRef({atom.name!r})"
    if isinstance(atom, IrGroup):
        return f"IrGroup({_repr_alternation(atom.body)})"
    raise TypeError(f"Cannot serialise atom: {type(atom).__name__}")


def _repr_alternation(alt: IrAlternation) -> str:
    if not alt.arms:
        return "IrAlternation(arms=())"
    arms = ", ".join(_repr_sequence(s) for s in alt.arms)
    return f"IrAlternation(arms=({arms},))"


def _repr_sequence(seq: IrSequence) -> str:
    if not seq.items:
        return "IrSequence(items=())"
    items = ", ".join(_repr_iritem(it) for it in seq.items)
    return f"IrSequence(items=({items},))"


def _repr_iritem(item: IrItem) -> str:
    return f"IrItem({_repr_atom_value(item.atom)}, {_repr_quantifier(item.quantifier)})"


def _repr_items(spec: RuleSpec) -> str:
    parts = []
    for item in spec.items:
        if isinstance(item, IrAlternation):
            parts.append(_repr_alternation(item))
        elif isinstance(item, IrItem):
            parts.append(_repr_iritem(item))
        else:
            raise TypeError(f"Unsupported items entry: {type(item).__name__}")
    return "[" + ", ".join(parts) + "]"


def _repr_field_map(spec: RuleSpec) -> str:
    items = ", ".join(f"{k!r}: {v}" for k, v in spec.field_map.items())
    return "{" + items + "}"


def _repr_rulespec(spec: RuleSpec) -> str:
    return (
        f"RuleSpec(\n"
        f"    rule_name={spec.rule_name!r},\n"
        f"    class_name={spec.class_name!r},\n"
        f"    parent_class_name={spec.parent_class_name!r},\n"
        f"    kind={spec.kind!r},\n"
        f"    items={_repr_items(spec)},\n"
        f"    field_map={_repr_field_map(spec)},\n"
        f"    non_semantic_fields=frozenset({sorted(spec.non_semantic_fields)!r}),\n"
        f")"
    )


def _emit_class(
    spec: RuleSpec, specs_by_rule: dict[str, RuleSpec], out: StringIO
) -> None:
    out.write(f"\n\nclass {spec.class_name}({spec.parent_class_name}):\n")
    inv = {idx: name for name, idx in spec.field_map.items()}
    body_lines: list[str] = []
    body_lines.append(f"    __grammar__: ClassVar[RuleSpec] = {_repr_rulespec(spec)}")
    if spec.kind == "value_str":
        body_lines.append("    value: str")
    elif spec.kind == "alternation":
        # Abstract base — no fields
        pass
    else:  # sequence
        for idx, item in enumerate(spec.items):
            if not isinstance(item, IrItem):
                continue
            if idx not in inv:
                continue
            name = inv[idx]
            ftype = _field_type_skeleton(item, specs_by_rule)
            body_lines.append(f"    {name}: {ftype}")
    if not body_lines or all(line.startswith("    __grammar__") for line in body_lines):
        body_lines.append("    pass")
    for line in body_lines:
        out.write(line + "\n")


def emit_module_source(specs: list[RuleSpec], *, stem: str) -> str:
    """Render specs to a Python module source string."""
    specs_by_rule = {s.rule_name: s for s in specs}
    out = StringIO()
    out.write(
        f'"""Generated module: {stem}. Do not edit; regenerated from grammar."""\n'
    )
    out.write(CANONICAL_IMPORTS)
    for spec in specs:
        _emit_class(spec, specs_by_rule, out)
    return out.getvalue()
