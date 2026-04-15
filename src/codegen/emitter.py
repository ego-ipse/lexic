"""Python source emitter for GBNF codegen.

Converts classified rules into ClassSpec objects and renders them as an
importable Python module with Pydantic models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .ast import (
    Alternation,
    CharClass,
    Group,
    Item,
    Literal,
    Rule,
    RuleRef,
    Sequence,
)
from .classify import (
    classify_rule,
    is_inline_literal_alt_group,
    is_pure_literal_seq,
    is_single_ruleref,
    is_ws_item,
    strip_ws,
    to_pascal,
    unwrap_group_alt,
)


# ── Specs ───────────────────────────────────────────────────────────────────

@dataclass
class FieldSpec:
    """A single field in a generated Pydantic model."""
    name: str
    type_str: str
    annotation: Any


@dataclass
class ClassSpec:
    """Blueprint for a generated Pydantic model class."""
    name: str
    base: str  # "BaseModel" or a parent class name
    is_abstract: bool
    fields: list[FieldSpec] = field(default_factory=list)
    is_value_str: bool = False
    docstring: str = ""


# ── Field extraction (from a single sequence) ──────────────────────────────

def _field_from_literal(fname: str, q: str | None) -> FieldSpec:
    if q == "?":
        return FieldSpec(fname, "Optional[str]", (Optional[str], ...))
    return FieldSpec(fname, "str", (str, ...))


def _field_from_ruleref(fname: str, ref_name: str, q: str | None, name_map: dict[str, str]) -> FieldSpec:
    ref_cls = name_map.get(ref_name, to_pascal(ref_name))
    if q is None:
        return FieldSpec(fname, ref_cls, (ref_cls, ...))
    if q == "?":
        return FieldSpec(fname, f"Optional[{ref_cls}]", (Optional[str], ...))
    return FieldSpec(fname, f"List[{ref_cls}]", (list, ...))


def _field_from_inline_union(fname: str, inner_arms: list[Sequence], name_map: dict[str, str]) -> FieldSpec:
    """D4: inline alternation of named rules → Union[A, B, ...]."""
    ref_names = [
        name_map.get(is_single_ruleref(a), to_pascal(is_single_ruleref(a)))
        for a in inner_arms
    ]
    return FieldSpec(fname, f"Union[{', '.join(ref_names)}]", (str, ...))


def _field_from_repeated_group(
    fname: str, inner_arms: list[Sequence], class_name: str, name_map: dict[str, str],
) -> tuple[FieldSpec, list[ClassSpec]]:
    """Repeated group (+ or *) → List[T] or List[HelperItem]."""
    helpers: list[ClassSpec] = []
    if len(inner_arms) == 1 and len(inner_arms[0].items) == 1:
        inner_it = inner_arms[0].items[0]
        if isinstance(inner_it.atom, RuleRef):
            ref_cls = name_map.get(inner_it.atom.name, to_pascal(inner_it.atom.name))
            return FieldSpec(fname, f"List[{ref_cls}]", (list, ...)), helpers
        return FieldSpec(fname, "List[str]", (list, ...)), helpers

    helper_name = f"{class_name}Item"
    h_fields, h_helpers = seq_to_fields(
        inner_arms[0], helper_name, name_map,
    )
    helpers.extend(h_helpers)
    helpers.append(ClassSpec(helper_name, "BaseModel", False, h_fields))
    return FieldSpec(fname, f"List[{helper_name}]", (list, ...)), helpers


def _field_from_optional_group(
    fname: str, inner_arms: list[Sequence], class_name: str, name_map: dict[str, str],
    opt_idx: int, opt_count: int,
) -> tuple[FieldSpec, list[ClassSpec]]:
    """Optional group → Optional[T] or Optional[HelperOpt]."""
    helpers: list[ClassSpec] = []
    if len(inner_arms) == 1 and len(inner_arms[0].items) == 1:
        inner_it = inner_arms[0].items[0]
        if isinstance(inner_it.atom, (Literal, CharClass)):
            return FieldSpec(fname, "Optional[str]", (Optional[str], ...)), helpers
        if isinstance(inner_it.atom, RuleRef):
            ref_cls = name_map.get(inner_it.atom.name, to_pascal(inner_it.atom.name))
            return FieldSpec(fname, f"Optional[{ref_cls}]", (Optional[str], ...)), helpers
        return FieldSpec(fname, "Optional[str]", (Optional[str], ...)), helpers

    helper_name = f"{class_name}Opt{opt_idx}" if opt_count > 1 else f"{class_name}Opt"
    h_fields, h_helpers = seq_to_fields(inner_arms[0], helper_name, name_map)
    helpers.extend(h_helpers)
    helpers.append(ClassSpec(helper_name, "BaseModel", False, h_fields))
    return FieldSpec(fname, f"Optional[{helper_name}]", (Optional[str], ...)), helpers


def _count_opt_groups(seq: Sequence) -> int:
    count = 0
    for it in seq.items:
        if is_ws_item(it):
            continue
        if it.quantifier == "?" and isinstance(it.atom, Group):
            inner = it.atom.alt.seqs[0] if len(it.atom.alt.seqs) == 1 else it.atom.alt.seqs[0]
            if len(strip_ws(inner).items) > 1:
                count += 1
    return count


def seq_to_fields(
    seq: Sequence, class_name: str, name_map: dict[str, str],
) -> tuple[list[FieldSpec], list[ClassSpec]]:
    """Convert a sequence of items into a list of fields and any helper classes."""
    fields: list[FieldSpec] = []
    helpers: list[ClassSpec] = []
    field_idx = 0
    opt_count = _count_opt_groups(seq)
    opt_idx = 0

    for it in seq.items:
        if is_ws_item(it):
            continue

        field_idx += 1
        fname = f"field{field_idx}"

        # Literal / CharClass → str
        if isinstance(it.atom, (Literal, CharClass)):
            fields.append(_field_from_literal(fname, it.quantifier))

        # RuleRef → typed reference
        elif isinstance(it.atom, RuleRef):
            fields.append(_field_from_ruleref(fname, it.atom.name, it.quantifier, name_map))

        # Group → dispatch by shape
        elif isinstance(it.atom, Group):
            f, h, field_idx, opt_idx = _process_group_item(
                it, fname, field_idx, class_name, name_map, opt_idx, opt_count,
            )
            fields.extend(f)
            helpers.extend(h)

    return fields, helpers


def _process_group_item(
    it: Item, fname: str, field_idx: int, class_name: str,
    name_map: dict[str, str], opt_idx: int, opt_count: int,
) -> tuple[list[FieldSpec], list[ClassSpec], int, int]:
    """Handle a group item, returning fields, helpers, and updated counters."""
    fields: list[FieldSpec] = []
    helpers: list[ClassSpec] = []
    q = it.quantifier

    inner_arms = [a for a in (strip_ws(s) for s in it.atom.alt.seqs) if len(a.items) > 0]

    # Inline literal alternation → str
    if is_inline_literal_alt_group(it):
        fields.append(_field_from_literal(fname, q))

    # D4: inline union of named rules
    elif q is None and len(inner_arms) > 1 and all(is_single_ruleref(a) is not None for a in inner_arms):
        fields.append(_field_from_inline_union(fname, inner_arms, name_map))

    # Repeated group
    elif q in ("+", "*"):
        f, h = _field_from_repeated_group(fname, inner_arms, class_name, name_map)
        fields.append(f)
        helpers.extend(h)

    # Optional group
    elif q == "?":
        opt_idx += 1
        f, h = _field_from_optional_group(fname, inner_arms, class_name, name_map, opt_idx, opt_count)
        fields.append(f)
        helpers.extend(h)

    # Unquantified single-arm group → inline its contents
    elif q is None and len(inner_arms) == 1:
        field_idx -= 1  # undo outer increment; re-count inline items
        for inner_it in inner_arms[0].items:
            if is_ws_item(inner_it):
                continue
            sub_fields, sub_helpers = seq_to_fields(Sequence([inner_it]), class_name, name_map)
            for sf in sub_fields:
                field_idx += 1
                sf.name = f"field{field_idx}"
                fields.append(sf)
            helpers.extend(sub_helpers)

    else:
        fields.append(FieldSpec(fname, "str", (str, ...)))

    return fields, helpers, field_idx, opt_idx


# ── Spec construction ───────────────────────────────────────────────────────

def _rule_text(rule: Rule) -> str:
    """Reconstruct a compact one-line representation of the rule for docstrings."""
    def _alt_text(alt: Alternation) -> str:
        return " | ".join(_seq_text(s) for s in alt.seqs)

    def _seq_text(seq: Sequence) -> str:
        return " ".join(_item_text(it) for it in seq.items)

    def _item_text(it: Item) -> str:
        txt = _atom_text(it.atom)
        if it.quantifier:
            txt += it.quantifier
        return txt

    def _atom_text(atom) -> str:
        if isinstance(atom, Literal):
            return f'"{atom.value}"'
        if isinstance(atom, CharClass):
            return atom.pattern
        if isinstance(atom, RuleRef):
            return atom.name
        if isinstance(atom, Group):
            return f"({_alt_text(atom.alt)})"
        return "?"

    return f"{rule.name} ::= {_alt_text(rule.body)}"


def _build_value_str_spec(name: str, base: str, docstring: str) -> ClassSpec:
    return ClassSpec(
        name, base, False,
        [FieldSpec("value", "str", (str, ...))],
        is_value_str=True, docstring=docstring,
    )


def build_specs(rules: list[Rule]) -> list[ClassSpec]:
    """Build the full list of ClassSpec objects from parsed rules."""
    rules_dict = {r.name: r for r in rules}
    name_map = {r.name: to_pascal(r.name) for r in rules}
    classifications = {r.name: classify_rule(r, rules_dict) for r in rules}

    # Parent map for named alternations.
    parent_of: dict[str, str] = {}
    arm_anon: dict[str, list[tuple[int, Sequence]]] = {}

    for r in rules:
        if classifications[r.name] != "named_alt":
            continue
        alt = unwrap_group_alt(r.body)
        arms = [strip_ws(seq) for seq in alt.seqs]
        anon_arms = []
        counter = 0
        for arm in arms:
            if len(arm.items) == 0:
                continue
            counter += 1
            ref = is_single_ruleref(arm)
            if ref is not None:
                parent_of[ref] = name_map[r.name]
            else:
                anon_arms.append((counter, arm))
        arm_anon[r.name] = anon_arms

    # Build specs per rule.
    all_specs: list[ClassSpec] = []
    rule_texts = {r.name: _rule_text(r) for r in rules}

    for r in rules:
        cls_name = name_map[r.name]
        cls = classifications[r.name]
        base = parent_of.get(r.name, "BaseModel")
        docstring = rule_texts[r.name]

        if cls in ("semantic_terminal", "pure_literal_alt"):
            all_specs.append(_build_value_str_spec(cls_name, base, docstring))

        elif cls == "named_alt":
            all_specs.append(ClassSpec(cls_name, base, True, docstring=docstring))
            for arm_idx, arm_seq in arm_anon.get(r.name, []):
                arm_name = f"{cls_name}Arm{arm_idx}"
                fields, h = seq_to_fields(arm_seq, arm_name, name_map)
                all_specs.extend(h)
                all_specs.append(ClassSpec(arm_name, cls_name, False, fields, docstring=f"Anonymous arm {arm_idx} of {r.name}"))

        elif cls == "sequence":
            alt = unwrap_group_alt(r.body)
            arms = [a for a in (strip_ws(s) for s in alt.seqs) if len(a.items) > 0]
            if len(arms) == 0:
                all_specs.append(_build_value_str_spec(cls_name, base, docstring))
            else:
                fields, h = seq_to_fields(arms[0], cls_name, name_map)
                all_specs.extend(h)
                all_specs.append(ClassSpec(cls_name, base, False, fields, docstring=docstring))

    return all_specs


# ── Topological ordering ───────────────────────────────────────────────────

def topo_sort(specs: list[ClassSpec]) -> list[ClassSpec]:
    """Order specs so base classes appear before subclasses."""
    by_name = {s.name: s for s in specs}
    ordered: list[ClassSpec] = []
    visited: set[str] = set()

    def visit(name: str):
        if name in visited:
            return
        visited.add(name)
        spec = by_name.get(name)
        if spec is None:
            return
        if spec.base not in ("BaseModel",) and spec.base in by_name:
            visit(spec.base)
        ordered.append(spec)

    for s in specs:
        visit(s.name)
    return ordered


# ── to_text() rendering ────────────────────────────────────────────────────

def _to_text_expr(f: FieldSpec) -> str:
    """Build the to_text() expression for a single field."""
    t = f.type_str
    name = f"self.{f.name}"

    # str types
    if t == "str":
        return name
    if t == "Optional[str]":
        return f"({name} or \"\")"
    if t == "List[str]":
        return f'"".join({name})'

    # Union[X, Y, ...] → .to_text()
    if t.startswith("Union["):
        return f"{name}.to_text()"

    # List[X] where X is not str
    if t.startswith("List["):
        return f'"".join(i.to_text() for i in {name})'

    # Optional[X] where X is not str
    if t.startswith("Optional["):
        return f'({name}.to_text() if {name} else "")'

    # Bare named type
    return f"{name}.to_text()"


def _render_to_text(spec: ClassSpec) -> list[str]:
    """Generate to_text() method lines for a ClassSpec."""
    if spec.is_abstract:
        return [
            "    def to_text(self) -> str:",
            "        raise NotImplementedError",
        ]
    if spec.is_value_str:
        return [
            "    def to_text(self) -> str:",
            "        return self.value",
        ]
    if not spec.fields:
        return [
            "    def to_text(self) -> str:",
            '        return ""',
        ]
    exprs = [_to_text_expr(f) for f in spec.fields]
    body = " + ".join(exprs)
    return [
        "    def to_text(self) -> str:",
        f"        return {body}",
    ]


# ── Source rendering ────────────────────────────────────────────────────────

def render_source(specs: list[ClassSpec], grammar_path: str) -> str:
    """Render an importable Python source string from ordered ClassSpecs."""
    needs_abc = any(s.is_abstract for s in specs)
    needs_list = any(f.type_str.startswith("List[") for s in specs for f in s.fields)
    needs_optional = any(f.type_str.startswith("Optional[") for s in specs for f in s.fields)
    needs_union = any(f.type_str.startswith("Union[") for s in specs for f in s.fields)

    typing_parts = []
    if needs_list:
        typing_parts.append("List")
    if needs_optional:
        typing_parts.append("Optional")
    if needs_union:
        typing_parts.append("Union")

    lines = [
        f'"""Auto-generated Pydantic models from {grammar_path}."""',
        "from __future__ import annotations",
        "",
    ]
    if needs_abc:
        lines.append("from abc import ABC")
    if typing_parts:
        lines.append(f"from typing import {', '.join(typing_parts)}")
    if needs_abc or typing_parts:
        lines.append("")
    lines += ["from pydantic import BaseModel", "", ""]

    for spec in specs:
        bases = [spec.base] if spec.base != "BaseModel" else ["BaseModel"]
        if spec.is_abstract:
            bases.append("ABC")

        lines.append(f"class {spec.name}({', '.join(bases)}):")
        if spec.docstring:
            safe_doc = spec.docstring.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'    """{safe_doc}"""')
        if spec.is_abstract:
            lines.append("    pass")
        elif spec.is_value_str:
            lines.append("    value: str")
        elif spec.fields:
            for f in spec.fields:
                lines.append(f"    {f.name}: {f.type_str}")
        else:
            lines.append("    pass")
        lines.extend(_render_to_text(spec))
        lines += ["", ""]

    lines.append("# Resolve forward references")
    lines.append("_ns = {k: v for k, v in globals().items() if isinstance(v, type)}")
    for spec in specs:
        lines.append(f"{spec.name}.model_rebuild(_types_namespace=_ns)")
    lines.append("")

    return "\n".join(lines)
