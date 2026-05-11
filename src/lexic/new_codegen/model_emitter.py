"""Model emitter — IrItem-shape NewRuleSpec → Python source string.

Target-shape commitments land incrementally:
  Task 9 (this task): class body skeleton + canonical imports.
  Task 10: Annotated[str, StringConstraints(...)] for pattern fields.
  Task 11: Literal[...] for pure-literal alternations.
  Task 12: Module-level type aliases hoisted from collect_aliases().
  Task 13: __grammar__ moved to module footer.

Decision CQ #1 (no # FIXME): _REPR_ACTION covers every IR shape.
Decision CQ #4 (fixed imports): emit a canonical import block always.
"""

from __future__ import annotations

from io import StringIO
from typing import Callable

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrNode,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import NewRuleSpec
from lexic.ir.walk import IrDispatch

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
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import NewRuleSpec
"""


def _is_required(q: Quantifier) -> bool:
    return q.min == 1 and q.max == 1


def _is_optional(q: Quantifier) -> bool:
    return q.min == 0 and q.max == 1


# ── IR repr emission ──────────────────────────────────────────────────────────
#
# _IrRepr folds an IR item subtree to a Python-repr string suitable for
# embedding in __grammar__ = NewRuleSpec(...) assignments in emitted source.
#
# The dispatch table maps each node type to a (node, old_children, new_children)
# → str callable.  new_children carries already-visited child strings, so
# IrGroup, IrAlternation, IrSequence, and IrItem just interpolate nc[i].

_REPR_ACTION: dict[type, Callable[..., str]] = {
    IrLiteral: lambda n, oc, nc: f"IrLiteral({n.value!r})",
    IrCharClass: lambda n, oc, nc: f"IrCharClass({n.pattern!r}, negated={n.negated})",
    IrRuleRef: lambda n, oc, nc: f"IrRuleRef({n.name!r})",
    IrGroup: lambda n, oc, nc: f"IrGroup({nc[0]})",
    IrAlternation: lambda n, oc, nc: (
        "IrAlternation(arms=())"
        if not nc
        else f"IrAlternation(arms=({', '.join(nc)},))"
    ),
    IrSequence: lambda n, oc, nc: (
        "IrSequence(items=())" if not nc else f"IrSequence(items=({', '.join(nc)},))"
    ),
    IrItem: lambda n, oc, nc: (
        f"IrItem({nc[0]}, Quantifier({n.quantifier.min}, {n.quantifier.max!r}))"
    ),
}


class _IrRepr(IrDispatch[IrNode, str]):
    """Fold an IR item subtree to a Python-repr string."""

    action = _REPR_ACTION

    def _combine(self, node: IrNode, old_children: tuple, new_children: tuple) -> str:
        try:
            return self.action[type(node)](node, old_children, new_children)
        except KeyError as exc:
            raise UnsupportedConstructError(
                f"_IrRepr: no repr handler for {type(node).__name__!r}",
            ) from exc


# ── Field type emission ───────────────────────────────────────────────────────
#
# _field_type maps an IrItem to a Python type annotation string via a
# module-level dispatch table keyed on item.atom type.
# Quantifier context stays on the IrItem; atom helpers receive it explicitly.
# Skeleton stage: IrCharClass and pure-pattern IrGroup both emit 'str'.
# Task 10 replaces those entries with Annotated[str, StringConstraints(...)].


def _ruleref_type(name: str, q: Quantifier, specs: dict[str, NewRuleSpec]) -> str:
    ref = specs.get(name)
    cls = ref.class_name if ref else name.replace("-", "_").title()
    if _is_required(q):
        return cls
    if _is_optional(q):
        return f"Optional[{cls}]"
    return f"List[{cls}]"


def _group_type(atom: IrGroup, specs: dict[str, NewRuleSpec]) -> str:
    arm_refs = [
        arm.items[0].atom.name
        for arm in atom.body.arms
        if len(arm.items) == 1 and isinstance(arm.items[0].atom, IrRuleRef)
    ]
    if arm_refs:
        cls_names = [
            specs[n].class_name if n in specs else n.replace("-", "_").title()
            for n in arm_refs
        ]
        return f"Union[{', '.join(cls_names)}]"
    return "str"


_ATOM_FIELD_TYPE: dict[type, Callable] = {
    IrLiteral: lambda a, q, s: "str",
    IrCharClass: lambda a, q, s: "str",
    IrRuleRef: lambda a, q, s: _ruleref_type(a.name, q, s),
    IrGroup: lambda a, q, s: _group_type(a, s),
}


def _field_type(item: IrItem, specs: dict[str, NewRuleSpec]) -> str:
    """Return the Python type annotation string for an IrItem."""
    handler = _ATOM_FIELD_TYPE.get(type(item.atom))
    if handler is None:
        raise UnsupportedConstructError(
            f"_field_type: no handler for atom type {type(item.atom).__name__!r}"
        )
    return handler(item.atom, item.quantifier, specs)


# ── ModuleEmitter ─────────────────────────────────────────────────────────────


class ModuleEmitter:
    """Render a list of NewRuleSpecs to a Python module source string.

    Owns the _IrRepr instance and the specs index so all emission helpers
    share state without threading it through every call.
    """

    def __init__(self, specs: list[NewRuleSpec]) -> None:
        self._specs = specs
        self._by_rule: dict[str, NewRuleSpec] = {s.rule_name: s for s in specs}
        self._repr = _IrRepr()

    def emit(self, *, stem: str) -> str:
        """Render all specs to a module source string."""
        out = StringIO()
        out.write(
            f'"""Generated module: {stem}. Do not edit; regenerated from grammar."""\n'
        )
        out.write(CANONICAL_IMPORTS)
        for spec in self._specs:
            out.write(self.emit_class(spec))
        return out.getvalue()

    def emit_class(self, spec: NewRuleSpec) -> str:
        """Render one spec to a class definition string (no module header)."""
        out = StringIO()
        self._write_class(spec, out)
        return out.getvalue()

    def _write_class(self, spec: NewRuleSpec, out: StringIO) -> None:
        out.write(f"\n\nclass {spec.class_name}({spec.parent_class_name}):\n")
        inv = {idx: name for name, idx in spec.field_map.items()}
        body_lines: list[str] = []
        body_lines.append(
            f"    __grammar__: ClassVar[NewRuleSpec] = {self._repr_rulespec(spec)}"
        )
        if spec.kind == "value_str":
            body_lines.append("    value: str")
        elif spec.kind == "alternation":
            pass
        else:
            for idx, item in enumerate(spec.items):
                if not isinstance(item, IrItem) or idx not in inv:
                    continue
                body_lines.append(f"    {inv[idx]}: {_field_type(item, self._by_rule)}")
        if all(line.startswith("    __grammar__") for line in body_lines):
            body_lines.append("    pass")
        for line in body_lines:
            out.write(line + "\n")

    def _repr_rulespec(self, spec: NewRuleSpec) -> str:
        return (
            f"NewRuleSpec(\n"
            f"        rule_name={spec.rule_name!r},\n"
            f"        class_name={spec.class_name!r},\n"
            f"        parent_class_name={spec.parent_class_name!r},\n"
            f"        kind={spec.kind!r},\n"
            f"        items={self._repr_items(spec)},\n"
            f"        field_map={self._repr_field_map(spec)},\n"
            f"        non_semantic_fields=frozenset({sorted(spec.non_semantic_fields)!r}),\n"
            f"    )"
        )

    def _repr_items(self, spec: NewRuleSpec) -> str:
        return "[" + ", ".join(self._repr.visit(item) for item in spec.items) + "]"

    def _repr_field_map(self, spec: NewRuleSpec) -> str:
        pairs = ", ".join(f"{k!r}: {v}" for k, v in spec.field_map.items())
        return "{" + pairs + "}"


def emit_module_source(specs: list[NewRuleSpec], *, stem: str) -> str:
    """Render specs to a Python module source string."""
    return ModuleEmitter(specs).emit(stem=stem)
