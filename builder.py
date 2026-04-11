#!/usr/bin/env python3
"""
builder.py — Generate built/<name>/models.py, parser.py, and __init__.py from a GBNF grammar.

Usage:
    uv run builder.py [grammar_file] [name]

    grammar_file  Path to .gbnf file (default: grammar.gbnf)
    name          Package name for output (default: stem of grammar_file)

Output is written to built/<name>/.
"""

from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

from llguidance.gbnf_to_lark import (
    ASTNode,
    AlternativeNode,
    GrammarParser,
    LiteralNode,
    RegexNode,
    RepetitionNode,
    RuleNode,
    RuleRefNode,
    SequenceNode,
    resolve,
)


# ---------------------------------------------------------------------------
# Grammar loading
# ---------------------------------------------------------------------------


def load_grammar(grammar_path: Path) -> dict[str, RuleNode]:
    text = grammar_path.read_text()
    parser = GrammarParser()
    rules = parser.parse(text)
    resolve(rules)
    return rules


# ---------------------------------------------------------------------------
# Name utilities
# ---------------------------------------------------------------------------


def to_class_name(rule_name: str) -> str:
    """snake_case → PascalCase."""
    return "".join(part.capitalize() for part in rule_name.split("_"))


def to_field_name(rule_name: str) -> str:
    """Normalise a rule name to a safe Python identifier."""
    name = rule_name.lower().replace("-", "_")
    if name in {"type", "class", "import", "from", "with", "pass", "raise"}:
        name += "_"
    return name


def pluralise(name: str) -> str:
    """Simple pluralisation — avoid double-s."""
    if name.endswith("s"):
        return name + "_list"
    return name + "s"


def decode_literal(value: str) -> str:
    """Convert llguidance escape sequences in LiteralNode.value to actual chars."""
    result = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            c = value[i + 1]
            if c == "n":
                result.append("\n")
            elif c == "t":
                result.append("\t")
            elif c == "r":
                result.append("\r")
            elif c == "\\":
                result.append("\\")
            elif c == '"':
                result.append('"')
            else:
                result.append(c)
            i += 2
        else:
            result.append(value[i])
            i += 1
    return "".join(result)


# ---------------------------------------------------------------------------
# AST → regex (for terminal rules only)
# ---------------------------------------------------------------------------


def ast_to_regex(node: ASTNode, rules: dict[str, RuleNode]) -> str:
    """Recursively convert a terminal-only AST subtree to a Python regex string."""
    if isinstance(node, LiteralNode):
        return re.escape(decode_literal(node.value))
    if isinstance(node, RegexNode):
        return node.rx  # already a character class like [a-z] or [^\n]
    if isinstance(node, RuleRefNode):
        if node.target is None or not node.target.rule_is_terminal:
            raise ValueError(f"Non-terminal ref '{node.name}' in terminal context")
        return ast_to_regex(node.target.alternatives, rules)
    if isinstance(node, RepetitionNode):
        inner = ast_to_regex(node.node, rules)
        # Character classes don't need grouping for quantifiers
        needs_group = not (
            inner.startswith("[")
            or (len(inner) == 1 and inner not in r"\.^$*+?{}[]|()")
        )
        bare = f"(?:{inner})" if needs_group else inner
        if node.min_times == 0 and node.max_times is None:
            return f"{bare}*"
        if node.min_times == 1 and node.max_times is None:
            return f"{bare}+"
        if node.min_times == 0 and node.max_times == 1:
            return f"{bare}?"
        max_s = str(node.max_times) if node.max_times is not None else ""
        return f"{bare}{{{node.min_times},{max_s}}}"
    if isinstance(node, SequenceNode):
        return "".join(ast_to_regex(n, rules) for n in node.nodes)
    if isinstance(node, AlternativeNode):
        parts = [ast_to_regex(a, rules) for a in node.alternatives]
        if len(parts) == 1:
            return parts[0]
        # Put empty-matching alternatives last so Python's left-to-right regex
        # engine doesn't short-circuit on the empty match before trying longer ones.
        parts.sort(key=lambda p: (p == "", -len(p)))
        return "(?:" + "|".join(parts) + ")"
    raise ValueError(f"Unknown AST node type: {type(node)}")


# ---------------------------------------------------------------------------
# Model generation
# ---------------------------------------------------------------------------


def _node_to_type(node: ASTNode) -> str | None:
    """Return a Python type annotation string for an AST node, or None to skip."""
    if isinstance(node, LiteralNode):
        return None  # structural separator — not a field
    if isinstance(node, RegexNode):
        return "str"
    if isinstance(node, RuleRefNode):
        if node.target is None:
            return "Any"
        if node.target.rule_is_terminal:
            return "str"
        return to_class_name(node.target.name)
    if isinstance(node, RepetitionNode):
        inner = _node_to_type(node.node)
        if inner is None:
            return None
        if node.min_times == 0 and node.max_times == 1:
            return f"Optional[{inner}]"
        return f"list[{inner}]"
    if isinstance(node, SequenceNode):
        types = [t for t in (_node_to_type(n) for n in node.nodes) if t is not None]
        if not types:
            return None
        return types[0] if len(types) == 1 else f"tuple[{', '.join(types)}]"
    if isinstance(node, AlternativeNode):
        types = list(
            dict.fromkeys(
                t
                for t in (_node_to_type(a) for a in node.alternatives)
                if t is not None
            )
        )
        if not types:
            return "str"
        return types[0] if len(types) == 1 else f"Union[{', '.join(types)}]"
    return "Any"


def _sequence_fields(seq: SequenceNode) -> list[tuple[str, str, str]]:
    """Return list of (field_name, type_str, default_suffix) from a sequence node."""
    fields: list[tuple[str, str, str]] = []
    seen: dict[str, int] = {}

    for node in seq.nodes:
        if isinstance(node, LiteralNode):
            continue

        typ = _node_to_type(node)
        if typ is None:
            continue

        # Pick a field name
        if isinstance(node, RuleRefNode):
            base = to_field_name(node.name)
        elif isinstance(node, RepetitionNode):
            inner = node.node
            is_optional = node.min_times == 0 and node.max_times == 1
            if isinstance(inner, RuleRefNode):
                base = (
                    to_field_name(inner.name)
                    if is_optional
                    else pluralise(to_field_name(inner.name))
                )
            elif isinstance(inner, SequenceNode):
                # e.g. (" " kv-pair)* — name after the non-literal part
                for n in inner.nodes:
                    if not isinstance(n, LiteralNode):
                        if isinstance(n, RuleRefNode):
                            base = pluralise(to_field_name(n.name))
                        else:
                            base = "items"
                        break
                else:
                    base = "items"
            else:
                base = "items"
        else:
            base = "value"

        # Deduplicate
        if base in seen:
            seen[base] += 1
            base = f"{base}_{seen[base]}"
        else:
            seen[base] = 0

        default = ""
        if typ.startswith("Optional["):
            default = " = None"
        elif typ.startswith("list["):
            default = " = Field(default_factory=list)"

        fields.append((base, typ, default))

    return fields


def generate_models(rules: dict[str, RuleNode], grammar_name: str) -> str:
    """Return the full content of models.py."""
    non_terminals = sorted(
        [r for r in rules.values() if not r.rule_is_terminal],
        key=lambda r: r.order,
    )

    lines = [
        f"# GENERATED by builder.py from {grammar_name}.gbnf — DO NOT EDIT",
        f"# Run: uv run builder.py {grammar_name}.gbnf",
        "from __future__ import annotations",
        "from typing import Any, Optional, Union",
        "from pydantic import BaseModel, Field",
        "",
        "",
    ]

    for rule in non_terminals:
        cname = to_class_name(rule.name)
        body = rule.alternatives

        if isinstance(body, SequenceNode):
            fields = _sequence_fields(body)
        elif isinstance(body, RuleRefNode):
            # Single reference (e.g. start → packet)
            if body.target and body.target.rule_is_terminal:
                fields = [("value", "str", "")]
            else:
                fields = [("root", to_class_name(body.name), "")]
        elif isinstance(body, AlternativeNode):
            # Top-level alternation → single `root` field of Union type
            types = list(
                dict.fromkeys(
                    t
                    for t in (_node_to_type(a) for a in body.alternatives)
                    if t is not None
                )
            )
            if not types:
                types = ["str"]
            union = types[0] if len(types) == 1 else f"Union[{', '.join(types)}]"
            fields = [("root", union, "")]
        else:
            typ = _node_to_type(body) or "str"
            fields = [("value", typ, "")]

        lines.append(f"class {cname}(BaseModel):")
        if not fields:
            lines.append("    pass")
        else:
            for fname, ftype, fdefault in fields:
                lines.append(f"    {fname}: {ftype}{fdefault}")
        lines += ["", ""]

    # Resolve forward references
    lines.append("# Resolve forward references")
    for rule in non_terminals:
        lines.append(f"{to_class_name(rule.name)}.model_rebuild()")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parser generation
# ---------------------------------------------------------------------------


def _gen_terminal_parser(rule: RuleNode, rules: dict[str, RuleNode]) -> str:
    """Generate a _parse_TERMINAL(text, pos) function."""
    try:
        pattern = ast_to_regex(rule.alternatives, rules)
    except ValueError as e:
        pattern = r"[^\n]*"
        comment = f"  # fallback: {e}"
    else:
        comment = ""
    name = rule.name  # UPPERCASE
    return (
        f"def _parse_{name}(text: str, pos: int) -> tuple[str, int]:\n"
        f"    m = _re_match({pattern!r}, text, pos){comment}\n"
        f"    if m is None:\n"
        f"        raise ParseError({name!r}, pos, text)\n"
        f"    return m\n"
    )


def _gen_nonterminal_parser(rule: RuleNode, rules: dict[str, RuleNode]) -> str:
    """Generate a parse_X(text, pos) function for a non-terminal rule."""
    cname = to_class_name(rule.name)
    fname = rule.name  # snake_case
    body = rule.alternatives
    lines: list[str] = [
        f"def parse_{fname}(text: str, pos: int) -> tuple[{cname}, int]:"
    ]

    if isinstance(body, RuleRefNode):
        if body.target and body.target.rule_is_terminal:
            lines.append(f"    val, pos = _parse_{body.target.name}(text, pos)")
            lines.append(f"    return {cname}(value=val), pos")
        elif body.target:
            lines.append(f"    inner, pos = parse_{body.target.name}(text, pos)")
            lines.append(f"    return {cname}(root=inner), pos")
        else:
            lines.append(
                f"    raise ParseError({fname!r}, pos, text)  # unresolved ref"
            )

    elif isinstance(body, AlternativeNode):
        lines.append("    _start = pos")
        for alt in body.alternatives:
            lines.append("    try:")
            if isinstance(alt, RuleRefNode) and alt.target:
                if alt.target.rule_is_terminal:
                    lines.append(
                        f"        val, pos = _parse_{alt.target.name}(text, pos)"
                    )
                    lines.append(f"        return {cname}(root=val), pos")
                else:
                    lines.append(
                        f"        inner, pos = parse_{alt.target.name}(text, pos)"
                    )
                    lines.append(f"        return {cname}(root=inner), pos")
            else:
                lines.append("        pass")
            lines.append("    except ParseError:")
            lines.append("        pos = _start")
        lines.append(f"    raise ParseError({fname!r}, pos, text)")

    elif isinstance(body, RepetitionNode):
        # Top-level repetition: e.g. body-content ::= (body-line "\n")*
        # Model field is always named "value" (from _node_to_type fallback path)
        field_defs = [("value", _node_to_type(body) or "str", "")]
        inner = body.node
        is_optional = body.min_times == 0 and body.max_times == 1
        is_list = body.max_times is None

        if is_list:
            lines.append("    value: list = []")
            if isinstance(inner, SequenceNode):
                lines.append("    while True:")
                lines.append("        _loop_pos = pos")
                lines.append("        try:")
                collected: list[str] = []
                _emit_sequence_body(
                    inner, lines, fname, "            ", rules, collected
                )
                # Append the meaningful item
                for n in inner.nodes:
                    if isinstance(n, RuleRefNode) and n.target:
                        item_var = to_field_name(n.target.name)
                        lines.append(f"            value.append({item_var})")
                        break
                lines.append("        except ParseError:")
                lines.append("            pos = _loop_pos")
                lines.append("            break")
            elif isinstance(inner, RuleRefNode) and inner.target:
                if inner.target.rule_is_terminal:
                    lines.append("    while True:")
                    lines.append("        try:")
                    lines.append(
                        f"            _item, pos = _parse_{inner.target.name}(text, pos)"
                    )
                    lines.append("            value.append(_item)")
                    lines.append("        except ParseError: break")
                else:
                    lines.append("    while True:")
                    lines.append("        try:")
                    lines.append(
                        f"            _item, pos = parse_{inner.target.name}(text, pos)"
                    )
                    lines.append("            value.append(_item)")
                    lines.append("        except ParseError: break")
            lines.append(f"    return {cname}(value=value), pos")
        else:
            lines.append(
                f"    raise ParseError({fname!r}, pos, text)  # unhandled repetition"
            )

    elif isinstance(body, SequenceNode):
        field_defs = _sequence_fields(body)
        field_names = {f[0] for f in field_defs}
        field_vars: list[str] = []
        seen_vars: dict[str, int] = {}  # mirrors _sequence_fields deduplication

        def _var(base: str) -> str:
            """Return the deduplicated field name, matching _sequence_fields."""
            if base in seen_vars:
                seen_vars[base] += 1
                return f"{base}_{seen_vars[base]}"
            seen_vars[base] = 0
            return base

        # Emit default initialisations for optional/list fields
        for fname_f, ftype, fdefault in field_defs:
            if fdefault == " = None":
                lines.append(f"    {fname_f} = None")
            elif "list" in ftype:
                lines.append(f"    {fname_f}: list = []")

        for node in body.nodes:
            if isinstance(node, LiteralNode):
                actual = decode_literal(node.value)
                escaped = repr(actual)
                lines.append(f"    if not text[pos:].startswith({escaped}):")
                lines.append(f"        raise ParseError({fname!r}, pos, text)")
                lines.append(f"    pos += {len(actual)}")

            elif isinstance(node, RepetitionNode):
                inner = node.node
                is_optional = node.min_times == 0 and node.max_times == 1
                is_list = node.max_times is None

                if is_optional:
                    if isinstance(inner, RuleRefNode) and inner.target:
                        var = _var(to_field_name(inner.name))
                        lines.append("    try:")
                        if inner.target.rule_is_terminal:
                            lines.append(
                                f"        {var}, pos = _parse_{inner.target.name}(text, pos)"
                            )
                        else:
                            lines.append(
                                f"        {var}, pos = parse_{inner.target.name}(text, pos)"
                            )
                        lines.append("    except ParseError: pass")
                        if var not in field_vars:
                            field_vars.append(var)
                    elif isinstance(inner, SequenceNode):
                        lines.append("    _opt_pos = pos")
                        lines.append("    try:")
                        _emit_sequence_body(
                            inner, lines, fname, "        ", rules, field_vars
                        )
                        lines.append("    except ParseError: pos = _opt_pos")

                elif is_list:
                    if isinstance(inner, RuleRefNode) and inner.target:
                        var = _var(pluralise(to_field_name(inner.name)))
                        lines.append("    while True:")
                        lines.append("        try:")
                        if inner.target.rule_is_terminal:
                            lines.append(
                                f"            _item, pos = _parse_{inner.target.name}(text, pos)"
                            )
                        else:
                            lines.append(
                                f"            _item, pos = parse_{inner.target.name}(text, pos)"
                            )
                        lines.append(f"            {var}.append(_item)")
                        lines.append("        except ParseError: break")
                        if var not in field_vars:
                            field_vars.append(var)
                    elif isinstance(inner, SequenceNode):
                        # name from first non-literal ref inside inner seq
                        base_list = next(
                            (pluralise(to_field_name(n.name)) for n in inner.nodes
                             if isinstance(n, RuleRefNode) and n.target),
                            "items"
                        )
                        list_var = _var(base_list)
                        lines.append("    while True:")
                        lines.append("        _loop_pos = pos")
                        lines.append("        try:")
                        tmp: list[str] = []
                        _emit_sequence_body(
                            inner, lines, fname, "            ", rules, tmp
                        )
                        for n in inner.nodes:
                            if isinstance(n, RuleRefNode) and n.target:
                                item_var = to_field_name(n.target.name)
                                lines.append(
                                    f"            {list_var}.append({item_var})"
                                )
                                break
                        lines.append("        except ParseError:")
                        lines.append("            pos = _loop_pos")
                        lines.append("            break")
                        if list_var not in field_vars:
                            field_vars.append(list_var)

            elif isinstance(node, RuleRefNode) and node.target:
                var = _var(to_field_name(node.name))
                if node.target.rule_is_terminal:
                    lines.append(
                        f"    {var}, pos = _parse_{node.target.name}(text, pos)"
                    )
                else:
                    lines.append(
                        f"    {var}, pos = parse_{node.target.name}(text, pos)"
                    )
                if var not in field_vars:
                    field_vars.append(var)

        all_vars = list(dict.fromkeys(field_vars))
        valid_vars = [v for v in all_vars if v in field_names]
        if valid_vars:
            kwargs = ", ".join(f"{v}={v}" for v in valid_vars)
            lines.append(f"    return {cname}({kwargs}), pos")
        else:
            lines.append(f"    return {cname}(), pos")

    else:
        lines.append(f"    raise ParseError({fname!r}, pos, text)  # unhandled")

    return "\n".join(lines) + "\n"


def _emit_sequence_body(
    seq: SequenceNode,
    lines: list[str],
    rule_name: str,
    indent: str,
    rules: dict[str, RuleNode],
    collected_vars: list[str],
) -> None:
    """Emit parser code for a SequenceNode inline (used inside try/loop blocks)."""
    for node in seq.nodes:
        if isinstance(node, LiteralNode):
            actual = decode_literal(node.value)
            escaped = repr(actual)
            lines.append(f"{indent}if not text[pos:].startswith({escaped}):")
            lines.append(f"{indent}    raise ParseError({rule_name!r}, pos, text)")
            lines.append(f"{indent}pos += {len(actual)}")
        elif isinstance(node, RuleRefNode) and node.target:
            var = to_field_name(node.target.name)
            if node.target.rule_is_terminal:
                lines.append(
                    f"{indent}{var}, pos = _parse_{node.target.name}(text, pos)"
                )
            else:
                lines.append(
                    f"{indent}{var}, pos = parse_{node.target.name}(text, pos)"
                )
            if var not in collected_vars:
                collected_vars.append(var)


def generate_init(rules: dict[str, RuleNode], grammar_name: str) -> str:
    """Return the full content of __init__.py for the built package."""
    non_terminals = sorted(
        [r for r in rules.values() if not r.rule_is_terminal],
        key=lambda r: r.order,
    )
    class_names = [to_class_name(r.name) for r in non_terminals]
    import_list = ", ".join(class_names)
    all_list = ", ".join(f'"{n}"' for n in class_names + ["parse", "ParseError"])

    return textwrap.dedent(f"""\
        # GENERATED by builder.py from {grammar_name}.gbnf — DO NOT EDIT
        # Run: uv run builder.py {grammar_name}.gbnf
        from .models import ({import_list})
        from .parser import parse, ParseError

        __all__ = [{all_list}]
        """)


def generate_parser(rules: dict[str, RuleNode], grammar_name: str) -> str:
    """Return the full content of parser.py."""
    terminals = sorted(
        [r for r in rules.values() if r.rule_is_terminal],
        key=lambda r: r.order,
    )
    non_terminals = sorted(
        [r for r in rules.values() if not r.rule_is_terminal],
        key=lambda r: r.order,
    )

    class_names = [to_class_name(r.name) for r in non_terminals]
    import_list = ", ".join(class_names)

    header = textwrap.dedent(f"""\
        # GENERATED by builder.py from {grammar_name}.gbnf — DO NOT EDIT
        # Run: uv run builder.py {grammar_name}.gbnf
        from __future__ import annotations
        import re
        from typing import Optional
        from .models import {import_list}


        class ParseError(Exception):
            def __init__(self, rule: str, pos: int, text: str):
                ctx = text[max(0, pos - 20) : pos + 20]
                super().__init__(f"Parse error in {{rule!r}} at pos {{pos}}: ...{{ctx!r}}...")


        def _re_match(pattern: str, text: str, pos: int) -> Optional[tuple[str, int]]:
            m = re.match(pattern, text[pos:], re.DOTALL)
            if m:
                return m.group(0), pos + len(m.group(0))
            return None


        def parse(text: str, start: str = "packet") -> object:
            \"\"\"Parse Vyx text. start must be a non-terminal rule name (snake_case).\"\"\"
            fn = globals().get(f"parse_{{start}}")
            if fn is None:
                raise ValueError(f"Unknown start rule: {{start!r}}")
            result, pos = fn(text, 0)
            while pos < len(text) and text[pos] in " \\t\\n\\r":
                pos += 1
            if pos != len(text):
                raise ParseError(start, pos, text)
            return result


        """)

    parts = [header]
    parts.append("# --- Terminal parsers ---\n\n")
    for rule in terminals:
        parts.append(_gen_terminal_parser(rule, rules))
        parts.append("\n")

    parts.append("# --- Non-terminal parsers ---\n\n")
    for rule in non_terminals:
        parts.append(_gen_nonterminal_parser(rule, rules))
        parts.append("\n")

    return "".join(parts)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    args = sys.argv[1:]
    grammar_path = Path(args[0]) if args else Path("grammar.gbnf")
    grammar_name = args[1] if len(args) > 1 else grammar_path.stem

    out_dir = Path("built") / grammar_name
    out_dir.mkdir(parents=True, exist_ok=True)

    rules = load_grammar(grammar_path)
    n_term = sum(1 for r in rules.values() if r.rule_is_terminal)
    n_nonterm = sum(1 for r in rules.values() if not r.rule_is_terminal)
    print(f"Loaded {len(rules)} rules ({n_term} terminals, {n_nonterm} non-terminals)")

    models_out = out_dir / "models.py"
    models_src = generate_models(rules, grammar_name)
    models_out.write_text(models_src)
    print(f"Wrote {models_out} ({len(models_src)} bytes)")

    parser_out = out_dir / "parser.py"
    parser_src = generate_parser(rules, grammar_name)
    parser_out.write_text(parser_src)
    print(f"Wrote {parser_out} ({len(parser_src)} bytes)")

    init_out = out_dir / "__init__.py"
    init_src = generate_init(rules, grammar_name)
    init_out.write_text(init_src)
    print(f"Wrote {init_out} ({len(init_src)} bytes)")


if __name__ == "__main__":
    main()
