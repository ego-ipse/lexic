"""GBNF → Pydantic model generator using the SOLID inheritance pattern.

AlternativeNode rules  →  abstract BaseModel base + typed concrete subclasses
SequenceNode rules     →  Pydantic model with named, typed fields
Single-RuleRefNode     →  subclass of the referenced model (or value: str stub)

Usage:
    from src.codegen import build
    mods = build("resources/ground_truth/json_ws.gbnf")
    # writes src/generated/json_ws.py, returns dict[str, type]
"""

from __future__ import annotations

import re
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
from pydantic import BaseModel


# ── Name helpers ─────────────────────────────────────────────────────────────


def to_class_name(name: str) -> str:
    return "".join(p.capitalize() for p in name.split("_"))


def to_field_name(name: str) -> str:
    n = name.lower().replace("-", "_")
    return n + "_" if n in {"type", "class", "import", "from", "with", "pass", "raise"} else n


def pluralise(name: str) -> str:
    return name + "_list" if name.endswith("s") else name + "s"


def decode_literal(value: str) -> str:
    escapes = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}
    out, i = [], 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            out.append(escapes.get(value[i + 1], value[i + 1]))
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


# ── AST → regex (terminal rules only) ────────────────────────────────────────


def ast_to_regex(node: ASTNode, rules: dict[str, RuleNode]) -> str:
    if isinstance(node, LiteralNode):
        return re.escape(decode_literal(node.value))
    if isinstance(node, RegexNode):
        return node.rx
    if isinstance(node, RuleRefNode):
        if node.target is None or not node.target.rule_is_terminal:
            raise ValueError(f"non-terminal ref '{node.name}' in terminal context")
        return ast_to_regex(node.target.alternatives, rules)
    if isinstance(node, RepetitionNode):
        inner = ast_to_regex(node.node, rules)
        bare = inner if (inner.startswith("[") or (len(inner) == 1 and inner not in r"\.^$*+?{}[]|()" )) else f"(?:{inner})"
        if node.min_times == 0 and node.max_times is None:
            return f"{bare}*"
        if node.min_times == 1 and node.max_times is None:
            return f"{bare}+"
        if node.min_times == 0 and node.max_times == 1:
            return f"{bare}?"
        return f"{bare}{{{node.min_times},{node.max_times if node.max_times is not None else ''}}}"
    if isinstance(node, SequenceNode):
        return "".join(ast_to_regex(n, rules) for n in node.nodes)
    if isinstance(node, AlternativeNode):
        parts = sorted([ast_to_regex(a, rules) for a in node.alternatives], key=lambda p: (p == "", -len(p)))
        return parts[0] if len(parts) == 1 else "(?:" + "|".join(parts) + ")"
    raise ValueError(f"unknown node type: {type(node)}")


# ── Type annotation helpers ───────────────────────────────────────────────────

_WS_NAMES = frozenset({"ws", "whitespace", "space", "spaces", "sp", "opt_ws", "req_ws"})


def _is_ws(node: ASTNode) -> bool:
    return (
        isinstance(node, RuleRefNode)
        and node.target is not None
        and node.target.rule_is_terminal
        and node.name.lower() in _WS_NAMES
    )


def _node_to_type(node: ASTNode) -> str | None:
    if isinstance(node, LiteralNode) or _is_ws(node):
        return None
    if isinstance(node, RegexNode):
        return "str"
    if isinstance(node, RuleRefNode):
        if node.target is None:
            return "Any"
        return "str" if node.target.rule_is_terminal else to_class_name(node.target.name)
    if isinstance(node, RepetitionNode):
        inner = _node_to_type(node.node)
        if inner is None:
            return None
        return f"Optional[{inner}]" if (node.min_times == 0 and node.max_times == 1) else f"list[{inner}]"
    if isinstance(node, SequenceNode):
        types = [t for n in node.nodes if not _is_ws(n) for t in (_node_to_type(n),) if t]
        if not types:
            return None
        return types[0] if len(types) == 1 else f"tuple[{', '.join(types)}]"
    if isinstance(node, AlternativeNode):
        types = list(dict.fromkeys(t for a in node.alternatives for t in (_node_to_type(a),) if t))
        if not types:
            return "str"
        return types[0] if len(types) == 1 else f"Union[{', '.join(types)}]"
    return "Any"


def _sequence_fields(seq: SequenceNode) -> list[tuple[str, str, str]]:
    """(field_name, type_str, default_suffix) for every meaningful node in a sequence."""
    fields: list[tuple[str, str, str]] = []
    seen: dict[str, int] = {}

    for node in seq.nodes:
        if isinstance(node, LiteralNode) or _is_ws(node):
            continue
        typ = _node_to_type(node)
        if typ is None:
            continue

        if isinstance(node, RuleRefNode):
            base = to_field_name(node.name)
        elif isinstance(node, RepetitionNode):
            optional = node.min_times == 0 and node.max_times == 1
            inner = node.node
            if isinstance(inner, RuleRefNode):
                base = to_field_name(inner.name) if optional else pluralise(to_field_name(inner.name))
            elif isinstance(inner, SequenceNode):
                ref = next((n for n in inner.nodes if isinstance(n, RuleRefNode) and not _is_ws(n)), None)
                base = (to_field_name(ref.name) if (optional and ref) else pluralise(to_field_name(ref.name)) if ref else "items")
            else:
                base = "items"
        else:
            base = "value"

        if base in seen:
            seen[base] += 1
            base = f"{base}_{seen[base]}"
        else:
            seen[base] = 0

        default = " = None" if typ.startswith("Optional[") else " = Field(default_factory=list)" if typ.startswith("list[") else ""
        fields.append((base, typ, default))

    return fields


# ── Topological sort: base classes before subclasses ─────────────────────────


def _topo_sort(rules: list[RuleNode]) -> list[RuleNode]:
    by_name = {r.name: r for r in rules}
    visited: set[str] = set()
    out: list[RuleNode] = []

    def visit(r: RuleNode) -> None:
        if r.name in visited:
            return
        visited.add(r.name)
        if isinstance(r.alternatives, RuleRefNode):
            t = r.alternatives.target
            if t and not t.rule_is_terminal and t.name in by_name:
                visit(by_name[t.name])
        out.append(r)

    for r in rules:
        visit(r)
    return out


# ── Code generation ───────────────────────────────────────────────────────────


def _cls(name: str, base: str, fields: list[tuple[str, str, str]]) -> list[str]:
    lines = [f"class {name}({base}):"]
    if fields:
        lines += [f"    {f}: {t}{d}" for f, t, d in fields]
    else:
        lines.append("    pass")
    lines.append("")
    return lines


def _build_source(rules: dict[str, RuleNode], stem: str) -> str:
    non_terminals = _topo_sort(sorted(
        (r for r in rules.values() if not r.rule_is_terminal),
        key=lambda r: r.order,
    ))

    lines: list[str] = [
        "from __future__ import annotations",
        "from typing import Any, Optional, Union",
        "from pydantic import BaseModel, Field",
        "",
    ]
    class_names: list[str] = []

    for rule in non_terminals:
        cname = to_class_name(rule.name)
        body = rule.alternatives

        if isinstance(body, AlternativeNode) and len(body.alternatives) > 1:
            lines += _cls(cname, "BaseModel", [])
            class_names.append(cname)
            for i, alt in enumerate(body.alternatives):
                if isinstance(alt, RuleRefNode):
                    sub = to_class_name(alt.name) + cname
                    if alt.target is None or alt.target.rule_is_terminal:
                        fields = [("value", "str", "")]
                    else:
                        fields = [(to_field_name(alt.name), to_class_name(alt.target.name), "")]
                else:
                    sub = f"{cname}Alt{i}"
                    seq_fields = _sequence_fields(alt) if isinstance(alt, SequenceNode) else []
                    fields = seq_fields or [("value", "str", "")]
                lines += _cls(sub, cname, fields)
                class_names.append(sub)

        elif isinstance(body, AlternativeNode):
            alt = body.alternatives[0]
            fields = _sequence_fields(alt) if isinstance(alt, SequenceNode) else []
            lines += _cls(cname, "BaseModel", fields)
            class_names.append(cname)

        elif isinstance(body, SequenceNode):
            lines += _cls(cname, "BaseModel", _sequence_fields(body))
            class_names.append(cname)

        elif isinstance(body, RuleRefNode):
            t = body.target
            if t is None or t.rule_is_terminal:
                lines += _cls(cname, "BaseModel", [("value", "str", "")])
            else:
                lines += _cls(cname, to_class_name(t.name), [])
            class_names.append(cname)

        elif isinstance(body, RepetitionNode):
            inner_type = _node_to_type(body) or "list[Any]"
            optional = body.min_times == 0 and body.max_times == 1
            default = " = None" if optional else " = Field(default_factory=list)"
            lines += _cls(cname, "BaseModel", [("items", inner_type, default)])
            class_names.append(cname)

        else:
            lines += _cls(cname, "BaseModel", [])
            class_names.append(cname)

    lines.append("")
    for name in class_names:
        lines.append(f"{name}.model_rebuild()")
    lines.append("")

    return "\n".join(lines)


def _load_rules(path: Path) -> dict[str, RuleNode]:
    text = path.read_text()
    raw = GrammarParser().parse(text)
    resolve(raw)
    if "start" in raw:
        raw["root"] = raw.pop("start")
        raw["root"].name = "root"
    return raw


# ── Public API ────────────────────────────────────────────────────────────────


def generate(grammar_path: str | Path) -> str:
    """Return generated Python source for *grammar_path* (no file I/O)."""
    path = Path(grammar_path)
    header = f"# Generated from {path.name} by src/codegen.py — DO NOT EDIT\n"
    return header + "\n" + _build_source(_load_rules(path), path.stem)


def build(
    grammar_path: str | Path,
    output_dir: str | Path = Path("src/generated"),
) -> dict[str, type]:
    """Generate Pydantic models, write *output_dir/<stem>.py*, return live class dict."""
    grammar_path = Path(grammar_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    init = output_dir / "__init__.py"
    if not init.exists():
        init.write_text("")

    code = generate(grammar_path)
    (output_dir / f"{grammar_path.stem}.py").write_text(code)

    ns: dict = {}
    try:
        exec(code, ns)  # noqa: S102
    except Exception:
        for i, line in enumerate(code.splitlines(), 1):
            print(f"{i:4}: {line}")
        raise

    mods = {
        k: v for k, v in ns.items()
        if isinstance(v, type)
        and issubclass(v, BaseModel)
        and not k.startswith("_")
        and k not in ("BaseModel", "Field", "Optional", "Any", "Union")
    }
    for cls in mods.values():
        cls.__module__ = f"src.generated.{grammar_path.stem}"
    return mods


def build_file(
    grammar_path: str | Path,
    output_dir: str | Path = Path("src/generated"),
) -> Path:
    """Write the generated .py file and return its path."""
    grammar_path = Path(grammar_path)
    build(grammar_path, output_dir)
    return Path(output_dir) / f"{grammar_path.stem}.py"


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if not args:
        print("Usage: python -m src.codegen <grammar.gbnf> [output_dir]")
        sys.exit(1)

    gpath = Path(args[0])
    odir = Path(args[1]) if len(args) > 1 else Path("src/generated")
    mods = build(gpath, odir)
    print(f"Wrote {odir / gpath.stem}.py  ({len(mods)} classes: {', '.join(sorted(mods))})")
