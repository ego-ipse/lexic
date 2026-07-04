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
    collect_aliases_grammar,
    regex_for_charclass,
    regex_for_group,
)
from lexic.codegen.binding import (
    RuleBinding,
    class_name_for,
    non_empty_arms,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.bind import BIND_MODES, IrBind
from lexic.ir.derive import has_ruleref
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
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


# ══ IR-native emit path (Task 4) ══════════════════════════════════════════════
#
# Consumes the codegen grammar + binding view directly — no RuleSpec. Fields
# carry their binding as ``Annotated[..., IrBind(...)]`` metadata; each class
# footers a ``__grammar__: ClassVar[IrRule]`` from the codegen grammar and the
# module footers ``GRAMMAR: IrAst`` (the canonical, pre-pass grammar) + ``START``.

CANONICAL_IMPORTS_IR = """\
from __future__ import annotations
from typing import Annotated, ClassVar, List, Literal, Optional, Union

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrBind,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNone,
    IrNot,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)
"""


def _has_empty_arm(rule: IrRule) -> bool:
    """True when the rule's body carries an empty (epsilon) arm."""
    return any(not arm for arm in rule.body)


def _ref_class(name: str, class_by_rule: dict[str, str]) -> str:
    """Class name for a rule ref — the binding's name, or a folded fallback."""
    return class_by_rule.get(name, class_name_for(name))


def _group_union_type(alt: IrAlternation, class_by_rule: dict[str, str]) -> str:
    """Type for a ref-bearing inline group: its single class or a ``Union``.

    Only single unit-ref arms contribute; a group with mixed/multi-item arms
    (no clean ref arm) has no sub-model type and folds to ``str``.
    """
    arm_refs = [
        arm[0].atom
        for arm in alt
        if len(arm) == 1 and isinstance(arm[0].atom, IrRuleRef)
    ]
    if not arm_refs:
        return "str"
    names = [_ref_class(str(ref), class_by_rule) for ref in arm_refs]
    return names[0] if len(names) == 1 else f"Union[{', '.join(names)}]"


def _base_field_type(
    item: IrItem, mode: str, class_by_rule: dict[str, str], aliases: dict[str, str]
) -> str:
    """Base Python type for a bound item, before Optional/List wrapping.

    Dispatch is on the fold ``mode`` (one of :data:`BIND_MODES`) crossed with the
    atom kind, matching the binding view's mode derivation.
    """
    atom, q = item.atom, item.quantifier
    if mode in ("model", "models"):
        if isinstance(atom, IrRuleRef):
            return _ref_class(str(atom), class_by_rule)
        if isinstance(atom, IrAlternation):
            return _group_union_type(atom, class_by_rule)
    elif mode == "gtext":
        if isinstance(atom, IrAlternation):
            return _pattern_type(regex_for_group(atom, q), aliases)
    elif mode == "text":
        if isinstance(atom, IrLiteral):
            return "str"
        if isinstance(atom, IrCharClass):
            return _pattern_type(regex_for_charclass(atom, q), aliases)
    raise UnsupportedConstructError(
        f"_base_field_type: no rule for mode {mode!r} / atom "
        f"{type(atom).__name__!r} (modes: {BIND_MODES})"
    )


def _wrap_field_type(base: str, bind: IrBind, item: IrItem, empty_arm: bool) -> str:
    """Wrap a base type in ``List``/``Optional`` per the bind and arm shape.

    ``empty_arm`` forces every field Optional (the rule has an epsilon arm, so
    each field may be absent); ``models`` fields become ``List[...]`` and only
    turn Optional under that force.
    """
    inner = f"List[{base}]" if bind.mode == "models" else base
    optional = empty_arm or (bind.mode != "models" and _is_optional(item.quantifier))
    if not optional:
        return inner
    return inner if inner.startswith("Optional[") else f"Optional[{inner}]"


def _value_str_type(rule: IrRule, aliases: dict[str, str]) -> str:
    """Type for a value_str rule's implicit ``value`` field.

    A lone single-item arm takes that atom's pattern; a pure-literal alternation
    becomes a ``Literal[...]``; anything else folds to flat ``str``.
    """
    arms = non_empty_arms(rule.body)
    if len(arms) == 1 and len(arms[0]) == 1:
        item = arms[0][0]
        atom, q = item.atom, item.quantifier
        if isinstance(atom, IrLiteral):
            return "str"
        if isinstance(atom, IrCharClass):
            return _pattern_type(regex_for_charclass(atom, q), aliases)
        if isinstance(atom, IrAlternation):
            return _pattern_type(regex_for_group(atom, q), aliases)
        raise UnsupportedConstructError(
            f"_value_str_type: unexpected atom {type(atom).__name__!r}"
        )
    if _is_pure_literal_alt(rule.body):
        literals = ", ".join(f'"{arm[0].atom}"' for arm in non_empty_arms(rule.body))
        return f"Literal[{literals}]"
    return "str"


class IrModuleEmitter:
    """Render a codegen grammar + binding view to a Python module source string.

    Holds the codegen grammar (per-class ``__grammar__`` rules and field items),
    the canonical grammar (module-level ``GRAMMAR``) and the binding list
    (class identity, kinds, parents, field binds) so every helper shares state.
    """

    def __init__(
        self, canonical: IrAst, codegen_grammar: IrAst, binding: list[RuleBinding]
    ) -> None:
        self._canonical = canonical
        self._binding = binding
        self._rules: dict[str, IrRule] = {r.name: r for r in codegen_grammar.rules}
        self._class_by_rule: dict[str, str] = {
            b.rule_name: b.class_name for b in binding
        }
        class_names = frozenset(b.class_name for b in binding)
        alias_list = [
            a
            for a in collect_aliases_grammar(codegen_grammar)
            if a.name not in class_names
        ]
        self._alias_decls = alias_list
        self._aliases: dict[str, str] = {a.regex: a.name for a in alias_list}

    def emit(self, *, stem: str) -> str:
        """Render the whole module to source."""
        out = StringIO()
        out.write(
            f'"""Generated module: {stem}. Do not edit; regenerated from grammar."""\n'
        )
        out.write(CANONICAL_IMPORTS_IR)
        for alias in self._alias_decls:
            out.write(
                f"\n{alias.name} = Annotated[str, "
                f"StringConstraints(pattern={_r_string(alias.regex)})]\n"
            )
        for bind in self._binding:
            out.write(self.emit_class(bind))
        self._write_footer(out)
        return out.getvalue()

    def emit_class(self, bind: RuleBinding) -> str:
        """Render one class definition (fields + ``__grammar__`` footer)."""
        out = StringIO()
        rule = self._rules[bind.rule_name]
        out.write(f"\n\nclass {bind.class_name}({bind.parent_class_name}):\n")
        self._write_fields(bind, rule, out)
        out.write(f"    __grammar__: ClassVar[IrRule] = {rule!r}\n")
        return out.getvalue()

    def _write_fields(self, bind: RuleBinding, rule: IrRule, out: StringIO) -> None:
        """Write a class body's fields (kind-specific), before the footer."""
        if bind.kind == "value_str":
            out.write(f"    value: {_value_str_type(rule, self._aliases)}\n")
            return
        if bind.kind == "alternation":
            return
        arm = non_empty_arms(rule.body)[0]
        empty_arm = _has_empty_arm(rule)
        for name, ibind in bind.fields.items():
            out.write(self._field_line(name, ibind, arm[ibind.item], empty_arm))

    def _field_line(
        self, name: str, bind: IrBind, item: IrItem, empty_arm: bool
    ) -> str:
        """Render one ``name: Annotated[<type>, IrBind(...)]`` field line."""
        base = _base_field_type(item, bind.mode, self._class_by_rule, self._aliases)
        type_str = _wrap_field_type(base, bind, item, empty_arm)
        default = " = None" if type_str.startswith("Optional[") else ""
        return f"    {name}: Annotated[{type_str}, {bind!r}]{default}\n"

    def _write_footer(self, out: StringIO) -> None:
        """Write the module-level ``GRAMMAR`` (canonical ast) and ``START``."""
        out.write(f"\n\nGRAMMAR: IrAst = {self._canonical!r}\n")
        out.write(f"\nSTART: str = {self._canonical.start!r}\n")


def emit_module_source_ir(
    canonical: IrAst, codegen_grammar: IrAst, binding: list[RuleBinding], *, stem: str
) -> str:
    """Render a codegen grammar + binding view to a Python module source string.

    :param canonical: The canonical (pre-pass) grammar — the module ``GRAMMAR``.
    :param codegen_grammar: The post-pass grammar — each class's ``__grammar__``.
    :param binding: The binding view (:func:`~lexic.codegen.binding.compute_binding`).
    :param stem: Module stem for the docstring header.
    :returns: The module source string.
    """
    return IrModuleEmitter(canonical, codegen_grammar, binding).emit(stem=stem)
