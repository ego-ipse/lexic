"""``export_source`` / ``export_module`` — the importable ``.py`` twin.

Renders a compiled grammar as an importable module: one typed
:class:`~lexic.model.GrammarModel` subclass per rule (docstring = the rule in
the source flavour's syntax; fields in the binding view's defaults-last
declaration order), the canonical ``GRAMMAR`` in IR-constructor notation, and
a module-end :func:`~lexic.compile.bind_module` call that attaches
``__grammar__``/``__binds__`` at import time. ``export_module(compiled,
path, ...)`` is the sole write site (ruling 2: files are written only on an
explicit output path); ``inline_tables=True`` writes the tables as ClassVars
instead of the bind call (self-contained, ~2× faster first import, busier
classes).

The classes in the written module are *twins* of the runtime ``type()``
classes — equivalent but distinct objects; they construct, ``to_text()``,
``to_grammar()`` and ``dump()``, while parsing stays on
:class:`~lexic.compile.CompiledGrammar`.

Formatting is IR-native: the grammar renders through the notation emit half
(:func:`~lexic.compile.notation.emit_ir`, width-solved by the
:mod:`~lexic.ir.layout` algebra) — no external formatter. Every export is
validated in-process: the module must ``ast.parse`` and the rendered
``GRAMMAR`` must :func:`~lexic.compile.notation.load_ir` back to an AST equal
to the compiled one.
"""

from __future__ import annotations

import ast as _pyast
import re
from pathlib import Path

from lexic import ir
from lexic.compile.artifact import CompiledGrammar
from lexic.compile.binding import (
    RuleBinding,
    class_name_for,
    compute_binding,
    non_empty_arms,
)
from lexic.compile.notation import emit_ir, load_ir
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import get_flavour
from lexic.ir.base import IrSelf
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)

WIDTH = 88

_UNIT = IrQuantifier(1, 1)

_IR_NAME = re.compile(r"\bIr[A-Za-z0-9]*\b|\bIR_DEFAULT\b")


# ── field annotations (readable view — the runtime never reads them) ─────


def _ref_class_name(ref: IrRuleRef, class_by_rule: dict[str, str]) -> str:
    """Class name for a rule ref — the binding's own name, or a folded fallback."""
    return class_by_rule.get(str(ref), class_name_for(str(ref)))


def _group_model_type(atom: IrAlternation, class_by_rule: dict[str, str]) -> str:
    """Union type for a model-mode inline group: each unit-ref arm's class.

    Model mode is only reached for an all-unit-ref group, so every arm
    contributes exactly one class name; duplicates collapse (first occurrence
    wins order). Falls back to the base class when, unexpectedly, no arm
    yields a class name.
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
    """Annotation for one bound field — mode-driven, optionality-wrapped.

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
    """Annotation for a ``value_str`` rule's implicit ``value`` field.

    A single-item single-arm body is a pass-through — plain ``str`` (a lone
    literal is not membership-checked by the base spine either). A multi-arm
    pure-literal alternation types as ``Literal[...]`` (the permitted-value
    set); every other ref-free body types as plain ``str``.
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


# ── class rendering ──────────────────────────────────────────────────────


def _docstring_lines(rule_text: str) -> list[str]:
    """The class docstring: the rule in grammar syntax, escaped and wrapped.

    Backslashes and double quotes escape so the text is safe inside a
    ``\"\"\"…\"\"\"`` literal; an over-width rule wraps at spaces onto
    continuation lines.
    """
    doc = rule_text.replace("\\", "\\\\").replace('"', '\\"').strip()
    single = f'    """``{doc}``"""'
    if len(single) <= WIDTH:
        return [single]
    lines: list[str] = ['    """``' + doc[: WIDTH - 11]]
    rest = doc[WIDTH - 11 :]
    while rest:
        lines.append("    " + rest[: WIDTH - 4])
        rest = rest[WIDTH - 4 :]
    lines[-1] += '``"""'
    return lines


def _sequence_field_lines(
    bind: RuleBinding, rule: IrRule, class_by_rule: dict[str, str]
) -> list[str]:
    """Field lines for a ``sequence``-kind class, in declaration order."""
    arm = next((a for a in rule.body if a), IrSequence())
    empty_arm = any(not a for a in rule.body)
    lines: list[str] = []
    for name, ibind in bind.fields.items():
        item = arm[ibind.item]
        optional = empty_arm or (ibind.mode != "models" and item.quantifier.lo == 0)
        type_str = _field_type(ibind.mode, item, class_by_rule, optional=optional)
        default = " = None" if optional and ibind.mode != "models" else ""
        lines.append(f"    {name}: {type_str}{default}")
    return lines


def _indented_ir(prefix: str, node: IrSelf) -> list[str]:
    """``prefix`` + the node in notation, continuation lines re-indented by 4.

    The prefix rides the first emitted line, so when the glued first line
    would overflow, the node re-emits at the prefix-reduced width — the top
    group then breaks and the first line is just the opening call. (No
    parenthesized-assignment fallback: the text must stay pure notation so
    ``load_ir`` can read it back.)
    """
    text = emit_ir(node, WIDTH - 4)
    first, *rest = text.split("\n")
    if len(prefix) + len(first) > WIDTH:
        text = emit_ir(node, WIDTH - len(prefix))
        first, *rest = text.split("\n")
    return [prefix + first] + ["    " + line for line in rest]


def _inline_table_lines(bind: RuleBinding, rule: IrRule) -> list[str]:
    """The ``inline_tables`` ClassVars: ``__grammar__`` and ``__binds__``."""
    lines = _indented_ir("    __grammar__: ClassVar[IrRule] = ", rule)
    if bind.fields:
        lines.append("    __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {")
        for name, ibind in bind.fields.items():
            lines.append(f"        {ibind.item}: ({name!r}, {ibind!r}),")
        lines.append("    }")
    return lines


def _class_lines(
    bind: RuleBinding,
    rule: IrRule,
    class_by_rule: dict[str, str],
    rule_text: str,
    *,
    inline_tables: bool,
) -> list[str]:
    """One class definition's lines."""
    bases = ", ".join(bind.parent_class_names) or "GrammarModel"
    lines = [f"class {bind.class_name}({bases}):"]
    lines.extend(_docstring_lines(rule_text))
    if bind.kind == "value_str":
        lines.append(f"    value: {_value_str_type(rule)}")
    elif bind.kind == "sequence":
        lines.extend(_sequence_field_lines(bind, rule, class_by_rule))
    if inline_tables:
        lines.extend(_inline_table_lines(bind, rule))
    return lines


# ── module assembly ──────────────────────────────────────────────────────


def _import_block(body: str, *, inline_tables: bool) -> str:
    """The complete header imports for a rendered module body.

    ``lexic.ir`` names come from what the body actually references (every
    referenced name is verified against the real ``lexic.ir`` surface);
    ``Literal`` only when a ``Literal[...]`` annotation rendered; ``ClassVar``
    only in ``inline_tables`` mode; ``bind_module`` only when the module ends
    in the bind call.
    """
    ir_names = sorted({n for n in _IR_NAME.findall(body) if hasattr(ir, n)})
    lines = ["from __future__ import annotations", ""]
    typing_names = [
        name
        for name, used in (("ClassVar", inline_tables), ("Literal", "Literal[" in body))
        if used
    ]
    if typing_names:
        lines += [f"from typing import {', '.join(typing_names)}", ""]
    lines.append("from lexic.model import GrammarModel")
    if not inline_tables:
        lines.append("from lexic.compile import bind_module")
    joined = f"from lexic.ir import {', '.join(ir_names)}"
    if len(joined) <= WIDTH:
        lines.append(joined)
    else:
        lines.append("from lexic.ir import (")
        lines.extend(f"    {name}," for name in ir_names)
        lines.append(")")
    return "\n".join(lines)


def _check_export(source: str, canonical: IrAst) -> None:
    """The always-on export gates: valid Python, GRAMMAR round-trips.

    :raises UnsupportedConstructError: When the rendered module does not
        parse as Python or its ``GRAMMAR`` does not reconstruct the compiled
        canonical AST.
    """
    try:
        _pyast.parse(source)
    except SyntaxError as exc:
        raise UnsupportedConstructError(
            f"export: rendered module is not valid Python: {exc}"
        ) from exc
    grammar_text = source.split("GRAMMAR: IrAst = ", 1)[1]
    grammar_text = grammar_text.split("\n\nbind_module(", 1)[0]
    if load_ir(grammar_text) != canonical:
        raise UnsupportedConstructError(
            "export: rendered GRAMMAR does not round-trip to the compiled AST"
        )


def export_source(
    compiled: CompiledGrammar, *, stem: str | None = None, inline_tables: bool = False
) -> str:
    """Render a compiled grammar as importable module source.

    :param compiled: The compiled grammar.
    :param stem: Overrides the module's named stem (default:
        ``compiled.stem``).
    :param inline_tables: Write ``__grammar__``/``__binds__`` as ClassVars in
        each class body instead of the module-end bind call.
    :returns: The module source (validated: parses, GRAMMAR round-trips).
    :raises UnsupportedConstructError: When a validation gate fails.
    """
    stem = stem if stem is not None else compiled.stem
    flavour = get_flavour(compiled.flavour)
    binding = compute_binding(compiled.codegen_grammar)
    rules = {str(rule.name): rule for rule in compiled.codegen_grammar.rules}
    class_by_rule = {bind.rule_name: bind.class_name for bind in binding}
    parts: list[str] = []
    for bind in binding:
        rule = rules[bind.rule_name]
        rule_text = str(flavour.apply(rule))
        parts.append(
            "\n".join(
                _class_lines(
                    bind, rule, class_by_rule, rule_text, inline_tables=inline_tables
                )
            )
        )
    parts.append("\n".join(_indented_ir("GRAMMAR: IrAst = ", compiled.grammar)))
    if not inline_tables:
        parts.append("bind_module(GRAMMAR, globals())")
    body = "\n\n\n".join(parts) + "\n"
    doc = (
        f'"""Generated twin module for grammar {stem!r} '
        f"({compiled.flavour}).\n\n"
        "Twin classes of the runtime compile: construct, to_text(), "
        "to_grammar(), dump();\nparsing stays on CompiledGrammar. "
        "Regenerate rather than edit.\n"
        '"""'
    )
    source = doc + "\n\n" + _import_block(body, inline_tables=inline_tables)
    source += "\n\n\n" + body
    _check_export(source, compiled.grammar)
    return source


def export_module(
    compiled: CompiledGrammar,
    path: str | Path,
    *,
    stem: str | None = None,
    inline_tables: bool = False,
) -> Path:
    """Write the importable twin module — the sole write site (ruling 2).

    :param compiled: The compiled grammar.
    :param path: The output ``.py`` file path (parent directories created).
    :param stem: Overrides the module's named stem (default: the output
        file's stem).
    :param inline_tables: See :func:`export_source`.
    :returns: The written path.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    source = export_source(
        compiled,
        stem=stem if stem is not None else target.stem,
        inline_tables=inline_tables,
    )
    target.write_text(source, encoding="utf-8")
    return target
