"""Model emitter — codegen grammar + binding view → Python source string.

Consumes the codegen grammar and its binding view directly (no ``RuleSpec``).
Fields carry their binding as ``Annotated[..., IrBind(...)]`` metadata; each
class footers a ``__grammar__: ClassVar[IrRule]`` from the codegen grammar and
the module footers ``GRAMMAR: IrAst`` (the canonical, pre-pass grammar) +
``START``. Pattern fields resolve to hoisted module-level type aliases; a
canonical import block is always emitted.
"""

from __future__ import annotations

from io import StringIO

from lexic.codegen.aliases import (
    PatternAlias,
    collect_aliases,
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

CANONICAL_IMPORTS = """\
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


def _is_optional(q: IrQuantifier) -> bool:
    return q.lo == 0 and q.hi == 1


def _r_string(pattern: str) -> str:
    quote = "'" if '"' in pattern else '"'
    return f"r{quote}{pattern}{quote}"


def _pattern_type(regex: str, aliases: dict[str, str]) -> str:
    """Alias name if the regex is registered, otherwise an inline Annotated."""
    if regex in aliases:
        return aliases[regex]
    return f"Annotated[str, StringConstraints(pattern={_r_string(regex)})]"


def _is_pure_literal_alt(alt: IrAlternation) -> bool:
    """True when every arm is a single unquantified IrLiteral."""
    return all(
        len(arm) == 1
        and isinstance(arm[0].atom, IrLiteral)
        and arm[0].quantifier == IrQuantifier(1, 1)
        for arm in alt
    )


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


class ModuleEmitter:
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
            a for a in collect_aliases(codegen_grammar) if a.name not in class_names
        ]
        self._alias_decls: list[PatternAlias] = alias_list
        self._aliases: dict[str, str] = {a.regex: a.name for a in alias_list}

    def emit(self, *, stem: str) -> str:
        """Render the whole module to source."""
        out = StringIO()
        out.write(
            f'"""Generated module: {stem}. Do not edit; regenerated from grammar."""\n'
        )
        out.write(CANONICAL_IMPORTS)
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


def emit_module_source(
    canonical: IrAst, codegen_grammar: IrAst, binding: list[RuleBinding], *, stem: str
) -> str:
    """Render a codegen grammar + binding view to a Python module source string.

    :param canonical: The canonical (pre-pass) grammar — the module ``GRAMMAR``.
    :param codegen_grammar: The post-pass grammar — each class's ``__grammar__``.
    :param binding: The binding view (:func:`~lexic.codegen.binding.compute_binding`).
    :param stem: Module stem for the docstring header.
    :returns: The module source string.
    """
    return ModuleEmitter(canonical, codegen_grammar, binding).emit(stem=stem)
