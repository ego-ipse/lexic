"""ModelEmitter: renders list[RuleSpec] into an importable Python source file.

Single responsibility: knows Python/Pydantic syntax. Knows nothing about Lark or GBNF text.
"""
from __future__ import annotations

from .ir import AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec


def _field_type(atom, specs_by_rule: dict[str, RuleSpec]) -> str:
    """Return the Pydantic field type string for a non-literal atom."""
    if isinstance(atom, CharClassAtom):
        return "str"
    if isinstance(atom, RuleRefAtom):
        ref = specs_by_rule.get(atom.rule_name)
        cls_name = ref.class_name if ref else atom.rule_name.replace("-", "_").title()
        if atom.min == 1 and atom.max == 1:
            return cls_name
        if atom.min == 0 and atom.max == 1:
            return f"Optional[{cls_name}]"
        return f"List[{cls_name}]"
    return "str"


def _repr_atom(atom) -> str:
    """Render an atom as a Python constructor call for the __grammar__ literal."""
    if isinstance(atom, LiteralAtom):
        escaped = atom.value.replace("\\", "\\\\").replace('"', '\\"')
        return f'LiteralAtom("{escaped}")'
    if isinstance(atom, CharClassAtom):
        escaped = atom.pattern.replace("\\", "\\\\").replace('"', '\\"')
        max_repr = "None" if atom.max is None else str(atom.max)
        return f'CharClassAtom("{escaped}", min={atom.min}, max={max_repr})'
    if isinstance(atom, RuleRefAtom):
        max_repr = "None" if atom.max is None else str(atom.max)
        return f'RuleRefAtom("{atom.rule_name}", min={atom.min}, max={max_repr})'
    if isinstance(atom, AlternationAtom):
        names = ", ".join(f'"{n}"' for n in atom.arm_rule_names)
        return f"AlternationAtom([{names}])"
    return "None"


class ModelEmitter:
    """Renders a list of RuleSpec objects into an importable Python source string."""

    def __init__(self, specs: list[RuleSpec], grammar_path: str):
        self._specs = specs
        self._grammar_path = grammar_path
        self._by_rule = {s.rule_name: s for s in specs}

    def render(self) -> str:
        needs_list = any(
            "List[" in _field_type(a, self._by_rule)
            for s in self._specs
            for fname, idx in s.field_map.items()
            for a in [s.items[idx]]
        )
        needs_optional = any(
            "Optional[" in _field_type(a, self._by_rule)
            for s in self._specs
            for fname, idx in s.field_map.items()
            for a in [s.items[idx]]
        )
        needs_abc = any(s.kind == "alternation" for s in self._specs)

        typing_parts = ["ClassVar"]
        if needs_list:
            typing_parts.append("List")
        if needs_optional:
            typing_parts.append("Optional")

        lines = [
            f'"""Auto-generated Pydantic models from {self._grammar_path}."""',
            "from __future__ import annotations",
            "",
        ]
        if needs_abc:
            lines.append("from abc import ABC")
        lines.append(f"from typing import {', '.join(sorted(typing_parts))}")
        lines.append("")
        lines.append("from base import GrammarModel")
        lines.append(
            "from codegen.ir import ("
            "AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec"
            ")"
        )
        lines.append("")
        lines.append("")

        for spec in self._specs:
            lines.extend(self._render_class(spec))
            lines.append("")
            lines.append("")

        lines.append("# Resolve forward references")
        lines.append("_ns = {k: v for k, v in globals().items() if isinstance(v, type)}")
        for spec in self._specs:
            lines.append(f"{spec.class_name}.model_rebuild(_types_namespace=_ns)")
        lines.append("")
        return "\n".join(lines)

    def _render_class(self, spec: RuleSpec) -> list[str]:
        if spec.kind == "alternation":
            bases = (
                f"{spec.parent_class_name}, ABC"
                if spec.parent_class_name != "GrammarModel"
                else "GrammarModel, ABC"
            )
        else:
            bases = spec.parent_class_name

        lines = [f"class {spec.class_name}({bases}):"]
        lines.append(f'    """{spec.rule_name} ::= (see __grammar__)"""')
        lines.extend(self._render_grammar_attr(spec))

        if spec.kind == "alternation":
            lines.append("    pass")
        elif spec.kind == "value_str":
            lines.append("    value: str")
        else:
            # sequence fields
            ordered = sorted(spec.field_map.items(), key=lambda x: x[1])
            if ordered:
                for fname, idx in ordered:
                    atom = spec.items[idx]
                    ftype = _field_type(atom, self._by_rule)
                    if ftype.startswith("Optional["):
                        lines.append(f"    {fname}: {ftype} = None")
                    else:
                        lines.append(f"    {fname}: {ftype}")
            else:
                lines.append("    pass")

        return lines

    def _render_grammar_attr(self, spec: RuleSpec) -> list[str]:
        items_repr = "[" + ", ".join(_repr_atom(a) for a in spec.items) + "]"
        fm_repr = "{" + ", ".join(f'"{k}": {v}' for k, v in spec.field_map.items()) + "}"
        lines = [
            "    __grammar__: ClassVar[RuleSpec] = RuleSpec(",
            f'        rule_name="{spec.rule_name}",',
            f'        class_name="{spec.class_name}",',
            f'        parent_class_name="{spec.parent_class_name}",',
            f'        kind="{spec.kind}",',
            f"        items={items_repr},",
            f"        field_map={fm_repr},",
            "    )",
        ]
        return lines
