"""Model emitter — IrItem-shape RuleSpec → Python source string.

Target-shape commitments land incrementally:
  Task 9: class body skeleton + canonical imports.
  Task 10: Annotated[str, StringConstraints(...)] for pattern fields.
  Task 11: Literal[...] for pure-literal alternations.
  Task 12: Module-level type aliases hoisted from collect_aliases().
  Task 13: __grammar__ moved to module footer.

Decision CQ #4 (fixed imports): emit a canonical import block always.
"""

from __future__ import annotations

from io import StringIO
from typing import Callable, cast

from lexic.codegen.aliases import (
    PatternAlias,
    collect_aliases,
    regex_for_charclass,
    regex_for_group,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.derive import has_ruleref
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRuleRef,
)
from lexic.ir.operators import IrNot
from lexic.ir.spec import RuleSpec

CANONICAL_IMPORTS = """\
from __future__ import annotations
from typing import Annotated, ClassVar, List, Literal, Optional, Union

from pydantic import Field, StringConstraints

from lexic.base import GrammarModel
from lexic.ir.base import IrNone, IrStr
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
    IrQuantifier,
)
from lexic.ir.operators import IrNot
from lexic.ir.spec import RuleSpec
"""


def _is_required(q: IrQuantifier) -> bool:
    return q.lo == 1 and q.hi == 1


def _is_optional(q: IrQuantifier) -> bool:
    return q.lo == 0 and q.hi == 1


# ── Field type emission ───────────────────────────────────────────────────────
#
# _field_type maps an IrItem to a Python type annotation string.
# Pattern atoms consult the alias map first; if the regex is registered there,
# the alias name is returned instead of an inline Annotated[...] expression.


def _ruleref_type(name: str, q: IrQuantifier, specs: dict[str, RuleSpec]) -> str:
    ref = specs.get(name)
    cls = ref.class_name if ref else name.replace("-", "_").title()
    if _is_required(q):
        return cls
    if _is_optional(q):
        return f"Optional[{cls}]"
    return f"List[{cls}]"


def _group_type(atom: IrAlternation, specs: dict[str, RuleSpec]) -> str:
    arm_refs = [
        arm[0].atom
        for arm in atom
        if len(arm) == 1 and isinstance(arm[0].atom, IrRuleRef)
    ]
    if arm_refs:
        cls_names = [
            specs[n].class_name if n in specs else n.replace("-", "_").title()
            for n in arm_refs
        ]
        if len(cls_names) == 1:
            return cls_names[0]
        return f"Union[{', '.join(cls_names)}]"
    return "str"


def _r_string(pattern: str) -> str:
    quote = "'" if '"' in pattern else '"'
    return f"r{quote}{pattern}{quote}"


def _pattern_type(regex: str, aliases: dict[str, str]) -> str:
    """Return the alias name if registered, otherwise an inline Annotated[...] string."""
    if regex in aliases:
        return aliases[regex]
    return f"Annotated[str, StringConstraints(pattern={_r_string(regex)})]"


_ATOM_FIELD_TYPE: dict[type, Callable] = {
    IrLiteral: lambda a, q, s, al: "str",
    IrCharClass: lambda a, q, s, al: _pattern_type(regex_for_charclass(a, q), al),
    IrNot: lambda a, q, s, al: (
        _pattern_type(regex_for_charclass(a[0], q, negated=True), al)
        if isinstance(a[0], IrCharClass)
        else "str"
    ),
    IrRuleRef: lambda a, q, s, al: _ruleref_type(a, q, s),
    IrAlternation: lambda a, q, s, al: (
        _pattern_type(regex_for_group(a, q), al)
        if not has_ruleref(a)
        else _group_type(a, s)
    ),
}


def _field_type(
    item: IrItem, specs: dict[str, RuleSpec], aliases: dict[str, str]
) -> str:
    """Return the Python type annotation string for an IrItem."""
    handler = _ATOM_FIELD_TYPE.get(type(item.atom))
    if handler is None:
        raise UnsupportedConstructError(
            f"_field_type: no handler for atom type {type(item.atom).__name__!r}"
        )
    return handler(item.atom, item.quantifier, specs, aliases)


def _is_pure_literal_alt(alt: IrAlternation) -> bool:
    """True when every arm is a single unquantified IrLiteral."""
    return all(
        len(arm) == 1
        and isinstance(arm[0].atom, IrLiteral)
        and arm[0].quantifier == IrQuantifier(1, 1)
        for arm in alt
    )


def _value_str_field_type(
    spec: RuleSpec, by_rule: dict[str, RuleSpec], aliases: dict[str, str]
) -> str:
    """Return the field type annotation for a value_str spec."""
    if len(spec.items) != 1:
        return "str"
    item = spec.items[0]
    if isinstance(item, IrAlternation):
        if _is_pure_literal_alt(item):
            literals = ", ".join(f'"{cast(IrLiteral, arm[0].atom)}"' for arm in item)
            return f"Literal[{literals}]"
        return "str"
    if isinstance(item, IrItem):
        return _field_type(item, by_rule, aliases)
    raise UnsupportedConstructError(
        f"_value_str_field_type: unexpected item type {type(item).__name__!r}"
    )


# ── ModuleEmitter ─────────────────────────────────────────────────────────────


class ModuleEmitter:
    """Render a list of NewRuleSpecs to a Python module source string.

    Owns the specs index so all emission helpers share state without
    threading it through every call.
    """

    def __init__(self, specs: list[RuleSpec]) -> None:
        self._specs = specs
        self._by_rule: dict[str, RuleSpec] = {s.rule_name: s for s in specs}
        class_names: frozenset[str] = frozenset(s.class_name for s in specs)
        alias_list: list[PatternAlias] = [
            a for a in collect_aliases(specs) if a.name not in class_names
        ]
        self._alias_decls = alias_list
        self._aliases: dict[str, str] = {a.regex: a.name for a in alias_list}

    def emit(self, *, stem: str) -> str:
        """Render all specs to a module source string."""
        out = StringIO()
        out.write(
            f'"""Generated module: {stem}. Do not edit; regenerated from grammar."""\n'
        )
        out.write(CANONICAL_IMPORTS)
        for alias in self._alias_decls:
            quote = chr(39) if chr(34) in alias.regex else chr(34)
            pattern = f"r{quote}{alias.regex}{quote}"
            out.write(
                f"\n{alias.name} = Annotated[str, StringConstraints(pattern={pattern})]\n"
            )
        for spec in self._specs:
            out.write(self.emit_class(spec))
        self._write_footer(out)
        return out.getvalue()

    def emit_class(self, spec: RuleSpec) -> str:
        """Render one spec to a class definition string (no module header or footer)."""
        out = StringIO()
        self._write_class(spec, out)
        return out.getvalue()

    def _write_class(self, spec: RuleSpec, out: StringIO) -> None:
        out.write(f"\n\nclass {spec.class_name}({spec.parent_class_name}):\n")
        inv = {idx: name for name, idx in spec.field_map.items()}
        body_lines: list[str] = []
        if spec.kind == "value_str":
            body_lines.append(
                f"    value: {_value_str_field_type(spec, self._by_rule, self._aliases)}"
            )
        elif spec.kind == "alternation":
            pass
        else:
            for idx, item in enumerate(spec.items):
                if not isinstance(item, IrItem) or idx not in inv:
                    continue
                type_str = _field_type(item, self._by_rule, self._aliases)
                if _is_optional(item.quantifier) and not type_str.startswith(
                    "Optional["
                ):
                    type_str = f"Optional[{type_str}]"
                default = " = None" if _is_optional(item.quantifier) else ""
                body_lines.append(f"    {inv[idx]}: {type_str}{default}")
        if not body_lines:
            body_lines.append("    pass")
        for line in body_lines:
            out.write(line + "\n")

    def _write_footer(self, out: StringIO) -> None:
        for spec in self._specs:
            out.write(
                f"\n\n{spec.class_name}.__grammar__ = {self._repr_rulespec(spec)}\n"
            )

    def _repr_rulespec(self, spec: RuleSpec) -> str:
        return (
            f"RuleSpec(\n"
            f"        rule_name={spec.rule_name!r},\n"
            f"        class_name={spec.class_name!r},\n"
            f"        parent_class_name={spec.parent_class_name!r},\n"
            f"        kind={spec.kind!r},\n"
            f"        items={self._repr_items(spec)},\n"
            f"        field_map={self._repr_field_map(spec)},\n"
            f"        non_semantic_fields=frozenset({sorted(spec.non_semantic_fields)!r}),\n"
            f"    )"
        )

    def _repr_items(self, spec: RuleSpec) -> str:
        return "[" + ", ".join(repr(item) for item in spec.items) + "]"

    def _repr_field_map(self, spec: RuleSpec) -> str:
        pairs = ", ".join(f"{k!r}: {v}" for k, v in spec.field_map.items())
        return "{" + pairs + "}"


def emit_module_source(specs: list[RuleSpec], *, stem: str) -> str:
    """Render specs to a Python module source string."""
    return ModuleEmitter(specs).emit(stem=stem)
