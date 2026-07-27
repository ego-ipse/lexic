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
from pathlib import Path
from typing import NamedTuple

from lexic import ir
from lexic.compile.artifact import CompiledGrammar
from lexic.compile.notation.emit import black_quoted, ir_doc
from lexic.compile.notation.parse import load_ir
from lexic.compile.pipeline.binding import (
    RuleBinding,
    class_name_for,
    compute_binding,
    non_empty_arms,
)
from lexic.compile.writer import write_module
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import get_flavour
from lexic.ir.base import IrSelf
from lexic.ir.layout import IrCat, IrDoc, IrGroup, IrLine, IrNest, IrText, render
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


def _ws_inl_leak(text: str) -> str:
    """The first value-final token separated from its delimiter by a newline.

    A value-final token (bare name, ``)``, string, int) is followed by its
    delimiter (``,``/``)``) across only space/tab in an exported module — the
    module self-grammar's ``ws-inl`` cannot cross a newline. The layout algebra
    breaks only AFTER ``(``/``,`` (whose ``ws`` DOES cross a newline), so a
    newline before a delimiter never occurs; this finds one if it ever does.

    The word test is ``str.isalnum() or "_"``, which is exactly CPython's
    ``\\w``: both are ``isalpha() or isdecimal() or isdigit() or isnumeric()``,
    plus the underscore.

    :param text: Rendered notation.
    :returns: The offending slice, or ``""`` when the invariant holds.
    """
    at = text.find("\n")
    while at >= 0:
        # A newline at 0 cannot start a match — no preceding character — but it
        # must be SKIPPED, not terminated on. Writing `while at > 0` here
        # returns "" for `"\na\n,"`, where the invariant is violated at 1, and
        # the caller raises on this, so a false negative ships a broken twin in
        # silence (403 of 4 617 859 inputs, adversarial pass 2).
        before = text[at - 1] if at else ""
        if before in (")", "_") or before.isalnum():
            after = at + 1
            while after < len(text) and text[after] == " ":
                after += 1
            if after < len(text) and text[after] in ",)":
                return text[at - 1 : after + 1]
        at = text.find("\n", at + 1)
    return ""


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


def field_type(
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


def value_str_type(rule: IrRule) -> str:
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


def docstring_lines(rule_text: str) -> list[str]:
    """The class docstring: the rule in grammar syntax, escaped and wrapped.

    Backslashes and double quotes escape so the text is safe inside a
    ``\"\"\"…\"\"\"`` literal; an over-width rule wraps at spaces onto
    continuation lines — the fill shape on the layout algebra (each word's
    group decides its own break against the current line), so a single
    over-budget token overflows rather than chopping mid-word.
    """
    doc = rule_text.replace("\\", "\\\\").replace('"', '\\"').strip()
    words = doc.split(" ")
    parts: list[IrDoc] = [IrText('    """``' + words[0])]
    parts.extend(IrGroup(IrCat(IrLine(" "), IrText(word))) for word in words[1:])
    parts.append(IrText('``"""'))
    return render(IrNest(4, IrCat(*parts)), WIDTH).split("\n")


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
        type_str = field_type(ibind.mode, item, class_by_rule, optional=optional)
        default = " = None" if optional and ibind.mode != "models" else ""
        lines.append(f"    {name}: {type_str}{default}")
    return lines


class _Rendered(NamedTuple):
    """A rendered fragment: its lines + every header symbol it spelled.

    The header is the union of these, so each renderer declares its own
    spellings. Nothing reads the finished module back to find out what is in it.
    """

    lines: list[str]
    symbols: frozenset[str]


def _indented_ir(prefix: str, node: IrSelf) -> _Rendered:
    """``prefix`` + the node in notation, rendered as ONE layout document.

    The prefix and the node's doc render together (the prefix's leading
    indent becomes the base ``IrNest``), so column accounting is exact and
    the continuation indents are the formatter's own (a top-level statement
    continues at 4, a class-level one at 8) — a fresh export is a
    ruff-format fixpoint, no post-hoc re-indent pass.
    """
    base = len(prefix) - len(prefix.lstrip(" "))
    notation = ir_doc(node)
    doc = IrCat(IrText(prefix), IrNest(base, notation.doc))
    text = render(doc, WIDTH)
    leak = _ws_inl_leak(text)
    if leak:
        raise UnsupportedConstructError(
            f"export: newline before a delimiter breaks module reparse: {leak!r}"
        )
    return _Rendered(text.split("\n"), notation.symbols)


def _inline_table_lines(bind: RuleBinding, rule: IrRule) -> _Rendered:
    """The ``inline_tables`` ClassVars: ``__grammar__`` and ``__binds__``.

    Strings render double-quoted (:func:`~lexic.compile.notation.black_quoted`)
    so the inline tables are a formatter fixpoint like the rest of the module.
    """
    grammar = _indented_ir("    __grammar__: ClassVar[IrRule] = ", rule)
    lines = list(grammar.lines)
    # The annotations this function writes by hand are spellings too.
    symbols = grammar.symbols | {"ClassVar", "IrRule"}
    if bind.fields:
        lines.append("    __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {")
        symbols |= {"IrBind"}
        for name, ibind in bind.fields.items():
            args = f"{ibind.item}, {black_quoted(ibind.mode)}"
            if not ibind.semantic:
                args += ", False"
            lines.append(
                f"        {ibind.item}: ({black_quoted(name)}, IrBind({args})),"
            )
        lines.append("    }")
    return _Rendered(lines, symbols)


def _class_lines(
    bind: RuleBinding,
    rule: IrRule,
    class_by_rule: dict[str, str],
    rule_text: str,
    *,
    inline_tables: bool,
) -> _Rendered:
    """One class definition's lines, and the header symbols they spell."""
    bases = ", ".join(bind.parent_class_names) or "GrammarModel"
    lines = [f"class {bind.class_name}({bases}):"]
    lines.extend(docstring_lines(rule_text))
    symbols: frozenset[str] = frozenset()
    body: list[str] = []
    if bind.kind == "value_str":
        annotation = value_str_type(rule)
        body.append(f"    value: {annotation}")
        # Asked of the annotation just produced, not of the finished module:
        # ``Literal[…]`` is the one form that needs a typing import.
        if annotation.startswith("Literal["):
            symbols |= {"Literal"}
    elif bind.kind == "sequence":
        body.extend(_sequence_field_lines(bind, rule, class_by_rule))
    if inline_tables:
        tables = _inline_table_lines(bind, rule)
        body.extend(tables.lines)
        symbols |= tables.symbols
    if body:  # formatter fixpoint: blank line between docstring and body
        lines.append("")
        lines.extend(body)
    return _Rendered(lines, symbols)


# ── module assembly ──────────────────────────────────────────────────────


def _import_block(spelled: frozenset[str], *, inline_tables: bool) -> str:
    """The complete header imports for the symbols emission SPELLED — isort-stable.

    ``spelled`` is what the renderers reported, routed to the module each name
    lives on. Nothing is read back out of the rendered text: a scan cannot tell
    a spelling from a mention, and walking the value instead over-imports
    (the notation elides trailing defaults). ``bind_module`` and
    ``GrammarModel`` are the module's fixed frame, not derived. The lexic block
    is emitted in sorted module order (``compile`` < ``ir`` < ``model``) so a
    user's isort/format-on-save pass is a NO-OP on a fresh export —
    regeneration never fights the formatter.

    :param spelled: Header symbols the renderers reported.
    :param inline_tables: Whether the module ends in the bind call.
    :returns: The header source.
    :raises UnsupportedConstructError: When a spelled symbol has no home to
        import it from — silently dropping it would emit a module that cannot
        import.
    """
    ir_names = sorted(name for name in spelled if name in ir.__all__)
    typing_names = [name for name in ("ClassVar", "Literal") if name in spelled]
    homeless = spelled - set(ir_names) - set(typing_names)
    if homeless:
        raise UnsupportedConstructError(
            f"export: emission spelled {sorted(homeless)}, which the header "
            "cannot import from lexic.ir or typing"
        )
    lines = ["from __future__ import annotations", ""]
    if typing_names:
        lines += [f"from typing import {', '.join(typing_names)}", ""]
    if not inline_tables:
        lines.append("from lexic.compile import bind_module")
    joined = f"from lexic.ir import {', '.join(ir_names)}"
    if len(joined) <= WIDTH:
        lines.append(joined)
    else:
        lines.append("from lexic.ir import (")
        lines.extend(f"    {name}," for name in ir_names)
        lines.append(")")
    lines.append("from lexic.model import GrammarModel")
    return "\n".join(lines)


def _grammar_source(source: str, tree: _pyast.Module) -> str:
    """The text of the module's ``GRAMMAR`` assignment, read structurally.

    Not ``source.split("GRAMMAR: IrAst = ")``: the module docstring renders the
    grammar in its own flavour, so a grammar with a terminal spelling that
    phrase put the split in the DOCSTRING and the gate refused a legal grammar.
    Asking the parsed module which statement assigns ``GRAMMAR`` cannot land
    anywhere else.

    :param source: The rendered module.
    :param tree: Its parsed form.
    :returns: The assignment's right-hand side, verbatim.
    :raises UnsupportedConstructError: When the module assigns no ``GRAMMAR``.
    """
    for node in tree.body:
        if not isinstance(node, _pyast.AnnAssign) or node.value is None:
            continue
        target = node.target
        if not isinstance(target, _pyast.Name) or target.id != "GRAMMAR":
            continue
        segment = _pyast.get_source_segment(source, node.value)
        if segment is not None:
            return segment
    raise UnsupportedConstructError(
        "export: the rendered module assigns no GRAMMAR, so there is nothing "
        "to round-trip against the compiled AST"
    )


def _check_export(source: str, canonical: IrAst) -> None:
    """The always-on export gates: valid Python, GRAMMAR round-trips.

    :raises UnsupportedConstructError: When the rendered module does not
        parse as Python or its ``GRAMMAR`` does not reconstruct the compiled
        canonical AST.
    """
    try:
        tree = _pyast.parse(source)
    except SyntaxError as exc:
        raise UnsupportedConstructError(
            f"export: rendered module is not valid Python: {exc}"
        ) from exc
    if load_ir(_grammar_source(source, tree)) != canonical:
        raise UnsupportedConstructError(
            "export: rendered GRAMMAR does not round-trip to the compiled AST"
        )


def _module_body(compiled: CompiledGrammar, *, inline_tables: bool) -> _Rendered:
    """Every top-level block of the module, and the symbols they spell.

    ``lines`` are the blocks (classes, ``GRAMMAR``, the bind call), joined by
    the caller — a block is itself multi-line.
    """
    flavour = get_flavour(compiled.flavour)
    binding = compute_binding(compiled.codegen_grammar)
    rules = {str(rule.name): rule for rule in compiled.codegen_grammar.rules}
    # The DOCSTRING alone renders off the pre-resolution grammar — same rules,
    # same structure, but a token terminal still spelled the way it was written.
    # Resolution bakes ordinals and drops the spellings, so a docstring off
    # ``codegen_grammar`` reads ``<[151667]>`` while ``GRAMMAR`` — which
    # round-trips to the canonical AST — holds ``<think>``: two resolution
    # states in one file. Everything else (the field types, and the
    # ``inline_tables`` ``__grammar__``, which is RUNTIME data the class binds)
    # keeps the resolved rule.
    authored = {
        str(rule.name): rule
        for rule in (compiled.tokens.unresolved or compiled.codegen_grammar).rules
    }
    class_by_rule = {bind.rule_name: bind.class_name for bind in binding}
    blocks: list[str] = []
    spelled: frozenset[str] = frozenset()
    for bind in binding:
        rule = rules[bind.rule_name]
        # Flat emission: docstring_lines owns the wrap (its char-chop moves
        # onto the layout algebra as its own task); width-broken rule text
        # would double-wrap here.
        rendered = _class_lines(
            bind,
            rule,
            class_by_rule,
            str(flavour.apply(authored.get(bind.rule_name, rule), width=None)),
            inline_tables=inline_tables,
        )
        blocks.append("\n".join(rendered.lines))
        spelled |= rendered.symbols
    grammar = _indented_ir("GRAMMAR: IrAst = ", compiled.grammar)
    blocks.append("\n".join(grammar.lines))
    spelled |= grammar.symbols | {"IrAst"}  # the annotation this line writes
    if not inline_tables:
        blocks.append("bind_module(GRAMMAR, globals())")
    return _Rendered(blocks, spelled)


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
    rendered = _module_body(compiled, inline_tables=inline_tables)
    body = "\n\n\n".join(rendered.lines) + "\n"
    doc = (
        f'"""Generated twin module for grammar {stem!r} '
        f"({compiled.flavour}).\n\n"
        "Twin classes of the runtime compile: construct, to_text(), "
        "to_grammar(), dump();\nparsing stays on CompiledGrammar. "
        "Regenerate rather than edit.\n"
        '"""'
    )
    source = doc + "\n\n" + _import_block(rendered.symbols, inline_tables=inline_tables)
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

    Written through :func:`~lexic.compile.writer.write_module`, the same step a
    payload goes out through: validated, staged, and byte-compiled, so a twin
    and its ``.pyc`` land as a matched pair or not at all.
    """
    target = Path(path)
    source = export_source(
        compiled,
        stem=stem if stem is not None else target.stem,
        inline_tables=inline_tables,
    )
    return write_module(target, source)
