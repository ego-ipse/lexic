"""``export_source`` — a reader-first ``.py`` view of a compiled grammar.

Renders every rule's binding in the record spine's own syntax: a
``GrammarModel`` subclass carrying its ``__grammar__: ClassVar[IrRule]`` and
(for a ``sequence``-kind rule) its ``__binds__`` table, matching what
:func:`~lexic.compile.synthesis.synthesize` builds directly at runtime via
``type(...)``. Field annotations are readable approximations (``str``,
``list[Foo]``, ``Foo | Bar | None``) rather than the runtime's neutral
``object`` placeholder — this view is for a HUMAN inspecting a compiled
grammar's shape, not for the import machinery: nothing in the runtime reads
or imports the rendered source.

``export_source`` only reprs :class:`~lexic.ir.nodes.IrAst` /
:class:`~lexic.ir.nodes.IrRule` / :class:`~lexic.ir.bind.IrBind` — pure
grammar-AST records with no action-algebra content. It never reprs a
:class:`~lexic.parsing.Reducer` or a flavour's noise map: those carry
:class:`~lexic.ir.base.IrLambda` bodies, whose ``__repr__`` can raise on an
unlocatable callable (a module-level function is fine; a closure is not).

``ruff`` is invoked here, and only here in :mod:`lexic.compile`, to format
the rendered source — imported lazily so the dev-tool dependency never
touches the runtime import path.
"""

from __future__ import annotations

import subprocess
import sys

from lexic.compile import CompiledGrammar
from lexic.compile.binding import (
    RuleBinding,
    class_name_for,
    compute_binding,
    non_empty_arms,
)
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
)

_HEADER = '''"""Reader view of compiled grammar {stem!r}.

Renders every synthesized model class in the record spine's own syntax
(GrammarModel subclass, ``__grammar__``, ``__binds__``). NOT imported by the
runtime and not meant to be reimported — a human-readable snapshot of a
compiled grammar's shape.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from lexic.base import GrammarModel
from lexic.ir import IrAst, IrBind, IrRule
'''

_UNIT = IrQuantifier(1, 1)


def _ref_class_name(ref: IrRuleRef, class_by_rule: dict[str, str]) -> str:
    """Class name for a rule ref — the binding's own name, or a folded fallback."""
    return class_by_rule.get(str(ref), class_name_for(str(ref)))


def _group_model_type(atom: IrAlternation, class_by_rule: dict[str, str]) -> str:
    """Readable union type for a model-mode inline group: each unit-ref arm's class.

    Model mode is only reached for an all-unit-ref group, so every arm
    contributes exactly one class name; duplicates collapse (first occurrence
    wins order). Falls back to the base class when, unexpectedly, no arm
    yields a class name — kept permissive since this view is read-only.
    """
    names: list[str] = []
    for arm in atom:
        if len(arm) == 1 and isinstance(arm[0].atom, IrRuleRef):
            name = _ref_class_name(arm[0].atom, class_by_rule)
            if name not in names:
                names.append(name)
    return " | ".join(names) if names else "GrammarModel"


def _model_base_type(item: IrItem, class_by_rule: dict[str, str]) -> str:
    """The base (unwrapped) type for a model/models-mode field's item."""
    atom = item.atom
    if isinstance(atom, IrRuleRef):
        return _ref_class_name(atom, class_by_rule)
    if isinstance(atom, IrAlternation):
        return _group_model_type(atom, class_by_rule)
    return "GrammarModel"


def _field_type(
    mode: str, item: IrItem, class_by_rule: dict[str, str], *, optional: bool
) -> str:
    """Readable annotation for one bound field — mode-driven, optionality-wrapped.

    ``models`` fields are always a ``list[...]`` (never optional themselves —
    an absent repetition is an empty list); ``model``/``text``/``gtext``
    fields wrap in ``| None`` when the field may be unset.
    """
    if mode == "models":
        return f"list[{_model_base_type(item, class_by_rule)}]"
    base = _model_base_type(item, class_by_rule) if mode == "model" else "str"
    return f"{base} | None" if optional else base


def _is_pure_literal_alt(body: IrAlternation) -> bool:
    """True when every non-empty arm is a single unquantified literal."""
    arms = non_empty_arms(body)
    return bool(arms) and all(
        len(arm) == 1
        and isinstance(arm[0].atom, IrLiteral)
        and arm[0].quantifier == _UNIT
        for arm in arms
    )


def _value_str_type(rule: IrRule) -> str:
    """Readable annotation for a ``value_str`` rule's implicit ``value`` field.

    A single-item single-arm body (one pattern atom) is a pass-through —
    plain ``str``, matching the base-spine's own ``_value_str_literals`` shape
    (`lexic/base.py`): a lone literal is not membership-checked either. A
    multi-arm pure-literal alternation types as ``Literal[...]`` (mirroring
    the permitted-value set); every other shape (a ref-free mixed body) types
    as plain ``str`` — this view never derives a constraining regex, unlike
    the retired pydantic-era emitter.
    """
    arms = non_empty_arms(rule.body)
    if len(arms) == 1 and len(arms[0]) == 1:
        return "str"
    if _is_pure_literal_alt(rule.body):
        literals = ", ".join(
            f"{str(arm[0].atom)!r}" for arm in non_empty_arms(rule.body)
        )
        return f"Literal[{literals}]"
    return "str"


def _binds_repr(bind: RuleBinding) -> str:
    """The ``__binds__`` classvar's literal — item slot to ``(field, IrBind)``."""
    entries = ", ".join(
        f"{ibind.item}: ({name!r}, {ibind!r})" for name, ibind in bind.fields.items()
    )
    return "{" + entries + "}"


def _sequence_field_lines(
    bind: RuleBinding, rule: IrRule, class_by_rule: dict[str, str]
) -> list[str]:
    """Field lines for a ``sequence``-kind class, in item order."""
    arm = non_empty_arms(rule.body)[0]
    empty_arm = any(not a for a in rule.body)
    lines: list[str] = []
    for name, ibind in bind.fields.items():
        item = arm[ibind.item]
        optional = empty_arm or (ibind.mode != "models" and item.quantifier.lo == 0)
        type_str = _field_type(ibind.mode, item, class_by_rule, optional=optional)
        default = " = None" if optional and ibind.mode != "models" else ""
        lines.append(f"    {name}: {type_str}{default}")
    return lines


def _class_body_lines(
    bind: RuleBinding, rule: IrRule, class_by_rule: dict[str, str]
) -> list[str]:
    """Every body line for one class: fields (kind-specific), then the footers."""
    if bind.kind == "value_str":
        lines = [f"    value: {_value_str_type(rule)}"]
    elif bind.kind == "alternation":
        lines = []
    else:
        lines = _sequence_field_lines(bind, rule, class_by_rule)
    lines.append(f"    __grammar__: ClassVar[IrRule] = {rule!r}")
    if bind.fields:
        lines.append(
            f"    __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {_binds_repr(bind)}"
        )
    return lines


def _class_source(
    bind: RuleBinding, rule: IrRule, class_by_rule: dict[str, str]
) -> str:
    """One class definition, blank-line separated from its neighbours."""
    bases = ", ".join(bind.parent_class_names) or "GrammarModel"
    lines = [f"class {bind.class_name}({bases}):"]
    lines.extend(_class_body_lines(bind, rule, class_by_rule))
    return "\n".join(lines)


def export_module_source(
    canonical: IrAst, codegen_grammar: IrAst, binding: list[RuleBinding], *, stem: str
) -> str:
    """Render a codegen grammar + its binding view to a reader-first ``.py`` string.

    :param canonical: The canonical (pre-pass) grammar — rendered as the
        module-level ``GRAMMAR``.
    :param codegen_grammar: The post-pass grammar — each class's ``__grammar__``.
    :param binding: The binding view (:func:`~lexic.compile.binding.compute_binding`).
    :param stem: Grammar stem, named in the module docstring.
    :returns: The rendered (unformatted) module source.
    """
    rules = {str(rule.name): rule for rule in codegen_grammar.rules}
    class_by_rule = {bind.rule_name: bind.class_name for bind in binding}
    parts = [_HEADER.format(stem=stem)]
    for bind in binding:
        parts.append(_class_source(bind, rules[bind.rule_name], class_by_rule))
    parts.append(f"GRAMMAR: IrAst = {canonical!r}")
    parts.append(f"START: str = {canonical.start!r}")
    return "\n\n\n".join(parts) + "\n"


def _ruff_format(source: str) -> str:
    """Best-effort ``ruff format`` over ``source``; returns it unchanged on failure.

    Imported/invoked lazily and only from this function, so ``ruff`` (a
    dev-group tool) never becomes a runtime import of :mod:`lexic.compile`.
    An unavailable or failing formatter is not fatal — the unformatted source
    is already valid Python.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "format", "-"],
            input=source,
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError, subprocess.CalledProcessError:
        return source
    return result.stdout


def export_source(compiled: CompiledGrammar, *, stem: str = "grammar") -> str:
    """The public entry: a compiled grammar's reader-first ``.py`` view.

    Recomputes the binding view from ``compiled.codegen_grammar`` (the
    :class:`~lexic.compile.CompiledGrammar` artefact carries the grammars and
    the fold, not the binding view itself) and renders it alongside
    ``compiled.grammar`` (the canonical AST — the module-level ``GRAMMAR``),
    then formats the result with ``ruff``.

    :param compiled: The compiled grammar to render.
    :param stem: Grammar stem named in the module docstring; callers that
        compiled from a path or a keyed text should pass their own stem.
    :returns: The formatted module source string.
    """
    binding = compute_binding(compiled.codegen_grammar)
    source = export_module_source(
        compiled.grammar, compiled.codegen_grammar, binding, stem=stem
    )
    return _ruff_format(source)
