"""
codegen.py — GBNF → Pydantic model generator.

Usage:
    build("path/to/grammar.gbnf")
        → writes src/generated/<stem>.py
        → returns dict[str, type] of live Pydantic classes

SOLID inheritance pattern:
    AlternativeNode rule  → abstract BaseModel base + typed concrete subclasses
    SequenceNode rule     → BaseModel with typed fields
    RuleRefNode rule      → subclass (non-terminal target) or value: str (terminal)
    RepetitionNode rule   → BaseModel with items field
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

# ── Whitespace rule names to suppress from generated fields ──────────────────

_WS_NAMES = {"ws", "whitespace", "space", "opt_space", "opt_ws"}


# ── Name utilities ────────────────────────────────────────────────────────────


def to_class_name(name: str) -> str:
    """snake_case / kebab-case / camelCase → PascalCase."""
    name = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
    return "".join(p.capitalize() for p in re.split(r"[_\-]", name))


def to_field_name(name: str) -> str:
    """Normalise a rule name to a safe Python identifier."""
    name = name.lower().replace("-", "_")
    if name in {"type", "class", "import", "from", "with", "pass", "raise"}:
        name += "_"
    return name


def pluralise(name: str) -> str:
    if name.endswith("s"):
        return name + "_list"
    return name + "s"


def decode_literal(value: str) -> str:
    """Convert llguidance escape sequences to actual characters."""
    ESC = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}
    result, i = [], 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            result.append(ESC.get(value[i + 1], value[i + 1]))
            i += 2
        else:
            result.append(value[i])
            i += 1
    return "".join(result)


# ── AST → regex (terminal rules only) ────────────────────────────────────────


def ast_to_regex(node: ASTNode, rules: dict[str, RuleNode]) -> str:
    """Recursively convert a terminal-only AST subtree to a Python regex string."""
    if isinstance(node, LiteralNode):
        return re.escape(decode_literal(node.value))
    if isinstance(node, RegexNode):
        return node.rx
    if isinstance(node, RuleRefNode):
        if node.target is None or not node.target.rule_is_terminal:
            raise ValueError(f"Non-terminal ref {node.name!r} in terminal context")
        return ast_to_regex(node.target.alternatives, rules)
    if isinstance(node, RepetitionNode):
        inner = ast_to_regex(node.node, rules)
        bare = f"(?:{inner})" if (inner.startswith("(") or len(inner) > 1) else inner
        if node.min_times == 0 and node.max_times is None:
            return f"{bare}*"
        if node.min_times == 1 and node.max_times is None:
            return f"{bare}+"
        if node.min_times == 0 and node.max_times == 1:
            return f"{bare}?"
        hi = str(node.max_times) if node.max_times is not None else ""
        return f"{bare}{{{node.min_times},{hi}}}"
    if isinstance(node, SequenceNode):
        return "".join(ast_to_regex(n, rules) for n in node.nodes)
    if isinstance(node, AlternativeNode):
        parts = sorted(
            [ast_to_regex(a, rules) for a in node.alternatives],
            key=lambda p: (p == "", -len(p)),
        )
        return parts[0] if len(parts) == 1 else "(?:" + "|".join(parts) + ")"
    raise ValueError(f"Unknown AST node type: {type(node)}")


# ── Type annotation helpers ───────────────────────────────────────────────────


def _is_ws(node: ASTNode) -> bool:
    return isinstance(node, RuleRefNode) and node.name in _WS_NAMES


def _node_to_type(node: ASTNode) -> str | None:
    """Return a Python type annotation string for node, or None to skip."""
    if isinstance(node, LiteralNode) or _is_ws(node):
        return None
    if isinstance(node, RegexNode):
        return "str"
    if isinstance(node, RuleRefNode):
        if node.target is None:
            return "Any"
        return "str" if node.target.rule_is_terminal else to_class_name(node.target.name)
    if isinstance(node, RepetitionNode):
        if _is_ws(node.node):
            return None
        inner = _node_to_type(node.node)
        if inner is None:
            return None
        if node.min_times == 0 and node.max_times == 1:
            return f"Optional[{inner}]"
        return f"list[{inner}]"
    if isinstance(node, SequenceNode):
        types = [t for n in node.nodes if not _is_ws(n) for t in [_node_to_type(n)] if t]
        if not types:
            return None
        return types[0] if len(types) == 1 else f"tuple[{', '.join(types)}]"
    if isinstance(node, AlternativeNode):
        types = list(
            dict.fromkeys(t for a in node.alternatives for t in [_node_to_type(a)] if t)
        )
        if not types:
            return "str"
        return types[0] if len(types) == 1 else f"Union[{', '.join(types)}]"
    return "Any"


def _sequence_fields(seq: SequenceNode) -> list[tuple[str, str, str]]:
    """Return [(field_name, type_str, default_suffix)] for a SequenceNode."""
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
            inner, is_opt = node.node, node.min_times == 0 and node.max_times == 1
            if isinstance(inner, RuleRefNode):
                base = to_field_name(inner.name) if is_opt else pluralise(to_field_name(inner.name))
            elif isinstance(inner, SequenceNode):
                base = next(
                    (
                        pluralise(to_field_name(n.name))
                        for n in inner.nodes
                        if isinstance(n, RuleRefNode) and not _is_ws(n)
                    ),
                    "items",
                )
            else:
                base = "items"
        else:
            base = "value"

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


# ── Code generation ───────────────────────────────────────────────────────────


class _ClassDef:
    """Collected class definition before emission."""

    __slots__ = ("name", "parent", "body")

    def __init__(self, name: str, parent: str, body: list[str]) -> None:
        self.name = name
        self.parent = parent  # "BaseModel" or name of another generated class
        self.body = body      # indented lines (no "class X(Y):" header)


def _sequence_body(seq: SequenceNode) -> list[str]:
    fields = _sequence_fields(seq)
    if not fields:
        return ["    pass"]
    return [f"    {fname}: {ftype}{fdefault}" for fname, ftype, fdefault in fields]


def _collect(defs: list[_ClassDef], rules: dict[str, RuleNode]) -> None:
    """Populate defs in rule.order, before topological sort."""
    non_terminals = sorted(
        (r for r in rules.values() if not r.rule_is_terminal),
        key=lambda r: r.order,
    )

    for rule in non_terminals:
        cname = to_class_name(rule.name)
        body = rule.alternatives

        if isinstance(body, AlternativeNode) and len(body.alternatives) > 1:
            # Abstract base
            defs.append(_ClassDef(cname, "BaseModel", ["    pass"]))
            # Typed subclasses
            for i, alt in enumerate(body.alternatives):
                if isinstance(alt, RuleRefNode):
                    sub = f"{to_class_name(alt.name)}{cname}"
                    if alt.target is None or alt.target.rule_is_terminal:
                        defs.append(_ClassDef(sub, cname, ["    value: str"]))
                    else:
                        field = to_field_name(alt.name)
                        target_cls = to_class_name(alt.target.name)
                        defs.append(_ClassDef(sub, cname, [f"    {field}: {target_cls}"]))
                elif isinstance(alt, SequenceNode):
                    defs.append(_ClassDef(f"{cname}Alt{i}", cname, _sequence_body(alt)))
                else:
                    typ = _node_to_type(alt) or "str"
                    defs.append(_ClassDef(f"{cname}Alt{i}", cname, [f"    value: {typ}"]))

        elif isinstance(body, AlternativeNode):
            # Single alternative — treat as sequence
            inner = body.alternatives[0]
            b = _sequence_body(inner) if isinstance(inner, SequenceNode) else [f"    value: {_node_to_type(inner) or 'str'}"]
            defs.append(_ClassDef(cname, "BaseModel", b))

        elif isinstance(body, SequenceNode):
            defs.append(_ClassDef(cname, "BaseModel", _sequence_body(body)))

        elif isinstance(body, RuleRefNode):
            if body.target is None or body.target.rule_is_terminal:
                defs.append(_ClassDef(cname, "BaseModel", ["    value: str"]))
            else:
                defs.append(_ClassDef(cname, to_class_name(body.target.name), ["    pass"]))

        elif isinstance(body, RepetitionNode):
            inner_type = _node_to_type(body) or "list[Any]"
            defs.append(_ClassDef(cname, "BaseModel", [f"    items: {inner_type} = Field(default_factory=list)"]))

        else:
            typ = _node_to_type(body) or "str"
            defs.append(_ClassDef(cname, "BaseModel", [f"    value: {typ}"]))


def _topo_sort(defs: list[_ClassDef]) -> list[_ClassDef]:
    """Sort so each class is emitted after its parent class."""
    by_name = {d.name: d for d in defs}
    result: list[_ClassDef] = []
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited or name not in by_name:
            return
        visited.add(name)
        visit(by_name[name].parent)  # emit parent first
        result.append(by_name[name])

    for d in defs:
        visit(d.name)

    return result


def _build_class_code(rules: dict[str, RuleNode]) -> str:
    defs: list[_ClassDef] = []
    _collect(defs, rules)
    ordered = _topo_sort(defs)

    lines: list[str] = [
        "from __future__ import annotations",
        "from pydantic import BaseModel, Field",
        "from typing import Any, Optional, Union",
        "from src.base import GrammarNode",
        "",
    ]

    for cd in ordered:
        # Top-level classes inherit GrammarNode (which inherits BaseModel).
        # Subclasses inherit their parent generated class, which eventually
        # reaches GrammarNode through the hierarchy.
        parent = "GrammarNode" if cd.parent == "BaseModel" else cd.parent
        lines.append(f"class {cd.name}({parent}):")
        lines.extend(cd.body)
        lines.append("")

    lines.append("")
    for cd in ordered:
        lines.append(f"{cd.name}.model_rebuild()")

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

_BUILD_CACHE: dict[Path, dict[str, type]] = {}


def build(grammar_path: str | Path) -> dict[str, type]:
    """
    Build Pydantic model classes from a GBNF grammar file.

    Writes src/generated/<stem>.py and returns a dict mapping class name →
    live class object.
    """
    path = Path(grammar_path).resolve()
    if path in _BUILD_CACHE:
        return _BUILD_CACHE[path]

    stem = path.stem
    text = path.read_text()

    parser = GrammarParser()
    raw_rules = parser.parse(text)
    resolve(raw_rules)

    # resolve() renames the root rule 'root' → 'start'; reverse it.
    if "start" in raw_rules and raw_rules["start"].order == 0:
        raw_rules["root"] = raw_rules.pop("start")
        raw_rules["root"].name = "root"

    code_str = _build_class_code(raw_rules)

    # Write generated file.
    out_dir = Path("src/generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "__init__.py").touch(exist_ok=True)
    header = f"# Generated from {path.name} — DO NOT EDIT\n"
    (out_dir / f"{stem}.py").write_text(header + "\n" + code_str + "\n")

    # Execute and extract classes.
    namespace: dict = {}
    try:
        exec(code_str, namespace)
    except Exception:
        print(code_str)
        raise

    from pydantic import BaseModel

    _skip = {"BaseModel", "GrammarNode", "Field", "Optional", "Any", "Union"}
    mods = {
        k: v
        for k, v in namespace.items()
        if isinstance(v, type)
        and issubclass(v, BaseModel)
        and not k.startswith("_")
        and k not in _skip
    }
    for cls in mods.values():
        cls.__module__ = f"src.generated.{stem}"

    _BUILD_CACHE[path] = mods
    return mods
