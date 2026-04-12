"""
codegen.py — GBNF-to-Pydantic-model generator using the SOLID inheritance pattern.

AlternativeNode rules → abstract base class + typed concrete subclasses
SequenceNode rules    → Pydantic models with typed fields
RuleRefNode rules     → subclass of the referenced model (or BaseModel with value field)
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


# ---------------------------------------------------------------------------
# Name utilities (ported verbatim from FAILED_ATTEMPT/builder.py)
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
        parts.sort(key=lambda p: (p == "", -len(p)))
        return "(?:" + "|".join(parts) + ")"
    raise ValueError(f"Unknown AST node type: {type(node)}")


# ---------------------------------------------------------------------------
# Type annotation helpers (ported verbatim from FAILED_ATTEMPT/builder.py)
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


# ---------------------------------------------------------------------------
# Topological sort: ensure base classes are emitted before subclasses
# ---------------------------------------------------------------------------


def _topo_sort_rules(non_terminals: list[RuleNode]) -> list[RuleNode]:
    """Sort rules so inheritance base classes are defined before their subclasses.

    Only top-level RuleRefNode rules (class X(Y): pass) create an ordering
    constraint — everything else only inherits from BaseModel or from a class
    defined within the same rule's block.
    """
    rule_map = {r.name: r for r in non_terminals}

    def inheritance_dep(rule: RuleNode) -> str | None:
        """Return the rule name this class MUST inherit after, or None."""
        body = rule.alternatives
        if isinstance(body, RuleRefNode):
            if (
                body.target is not None
                and not body.target.rule_is_terminal
                and body.target.name in rule_map
            ):
                return body.target.name
        return None

    visited: set[str] = set()
    result: list[RuleNode] = []

    def visit(rule: RuleNode) -> None:
        if rule.name in visited:
            return
        visited.add(rule.name)
        dep = inheritance_dep(rule)
        if dep:
            visit(rule_map[dep])
        result.append(rule)

    for rule in non_terminals:  # non_terminals already sorted by order
        visit(rule)

    return result


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------


def _build_class_code(rules: dict[str, RuleNode], grammar_stem: str) -> str:
    """Return Python source that when exec'd defines all Pydantic model classes."""
    non_terminals = sorted(
        [r for r in rules.values() if not r.rule_is_terminal],
        key=lambda r: r.order,
    )

    # Topological sort so base classes are emitted before subclasses
    ordered = _topo_sort_rules(non_terminals)

    lines: list[str] = [
        "from __future__ import annotations",
        "from pydantic import BaseModel, Field",
        "from typing import Optional, Any, Union",
        "",
    ]

    all_class_names: list[str] = []  # ordered list of every class emitted

    for rule in ordered:
        cname = to_class_name(rule.name)
        body = rule.alternatives

        if isinstance(body, AlternativeNode) and len(body.alternatives) > 1:
            # ── Abstract base ──────────────────────────────────────────────
            lines += [f"class {cname}(BaseModel):", "    pass", ""]
            all_class_names.append(cname)

            for i, alt in enumerate(body.alternatives):
                if isinstance(alt, RuleRefNode):
                    sub_name = to_class_name(alt.name) + cname
                    if alt.target is None or alt.target.rule_is_terminal:
                        # Terminal ref → value: str
                        lines += [f"class {sub_name}({cname}):", "    value: str", ""]
                    else:
                        # Non-terminal ref → typed field
                        field_name = to_field_name(alt.name)
                        target_cname = to_class_name(alt.target.name)
                        lines += [
                            f"class {sub_name}({cname}):",
                            f"    {field_name}: {target_cname}",
                            "",
                        ]
                else:
                    # Inline SequenceNode or other
                    sub_name = f"{cname}Alt{i}"
                    if isinstance(alt, SequenceNode):
                        fields = _sequence_fields(alt)
                    else:
                        fields = []
                    lines.append(f"class {sub_name}({cname}):")
                    if fields:
                        for fname, ftype, fdefault in fields:
                            lines.append(f"    {fname}: {ftype}{fdefault}")
                    else:
                        lines.append("    value: str")
                    lines.append("")
                all_class_names.append(sub_name)

        elif isinstance(body, AlternativeNode) and len(body.alternatives) == 1:
            # ── Single-alternative — treat as SequenceNode ─────────────────
            alt = body.alternatives[0]
            if isinstance(alt, SequenceNode):
                fields = _sequence_fields(alt)
            else:
                fields = []
            lines.append(f"class {cname}(BaseModel):")
            if fields:
                for fname, ftype, fdefault in fields:
                    lines.append(f"    {fname}: {ftype}{fdefault}")
            else:
                lines.append("    pass")
            lines.append("")
            all_class_names.append(cname)

        elif isinstance(body, SequenceNode):
            # ── Typed fields model ─────────────────────────────────────────
            fields = _sequence_fields(body)
            lines.append(f"class {cname}(BaseModel):")
            if fields:
                for fname, ftype, fdefault in fields:
                    lines.append(f"    {fname}: {ftype}{fdefault}")
            else:
                lines.append("    pass")
            lines.append("")
            all_class_names.append(cname)

        elif isinstance(body, RuleRefNode):
            # ── Single-ref rule ────────────────────────────────────────────
            target = body.target
            if target is None or target.rule_is_terminal:
                lines += [f"class {cname}(BaseModel):", "    value: str", ""]
            else:
                parent_cname = to_class_name(target.name)
                lines += [f"class {cname}({parent_cname}):", "    pass", ""]
            all_class_names.append(cname)

        elif isinstance(body, RepetitionNode):
            # ── Top-level repetition ───────────────────────────────────────
            inner_type = _node_to_type(body)
            is_optional_rep = body.min_times == 0 and body.max_times == 1
            if inner_type is None:
                inner_type = "list[Any]"
            if is_optional_rep:
                lines += [
                    f"class {cname}(BaseModel):",
                    f"    items: {inner_type} = None",
                    "",
                ]
            else:
                lines += [
                    f"class {cname}(BaseModel):",
                    f"    items: {inner_type} = Field(default_factory=list)",
                    "",
                ]
            all_class_names.append(cname)

        else:
            # ── Fallback ───────────────────────────────────────────────────
            lines += [f"class {cname}(BaseModel):", "    pass", ""]
            all_class_names.append(cname)

    # model_rebuild() must be called after ALL classes are defined
    lines.append("# Resolve forward references")
    for cname in all_class_names:
        lines.append(f"{cname}.model_rebuild()")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _parse_grammar(grammar_path: str | Path) -> tuple[dict, str]:
    """Parse a GBNF grammar file and return (rules_dict, grammar_stem)."""
    path = Path(grammar_path)
    grammar_stem = path.stem
    text = path.read_text()

    parser_obj = GrammarParser()
    raw_rules = parser_obj.parse(text)

    # Capture original root name before resolve() mutates the dict
    next(iter(raw_rules))  # noqa: F841 — side-effect-free peek

    resolve(raw_rules)  # mutates in-place; 'root' → 'start', terminals → UPPER

    # Reverse the 'root' → 'start' rename so the rest of the code sees 'root'
    if "start" in raw_rules:
        raw_rules["root"] = raw_rules.pop("start")
        raw_rules["root"].name = "root"

    return raw_rules, grammar_stem


def generate(grammar_path: str | Path) -> str:
    """Parse a GBNF grammar and return the generated Python source code as a string.

    The returned string is valid Python that, when executed, defines a set of
    Pydantic model classes following the SOLID inheritance pattern.  It does
    *not* execute anything — use :func:`build` to both generate and load the
    classes into a live dict.
    """
    raw_rules, grammar_stem = _parse_grammar(grammar_path)
    return _build_class_code(raw_rules, grammar_stem)


def build(grammar_path: str | Path) -> dict[str, type]:
    """Parse a GBNF grammar, generate Pydantic model source, and return live classes.

    Calls :func:`generate` to produce the Python source then ``exec``s it,
    returning a mapping of PascalCase class name → class object for every
    non-terminal rule.

    Classes use SOLID inheritance: AlternativeNode rules produce abstract bases
    with concrete typed subclasses; SequenceNode rules produce field models;
    single-ref rules produce subclasses.
    """
    raw_rules, grammar_stem = _parse_grammar(grammar_path)
    code_str = _build_class_code(raw_rules, grammar_stem)

    namespace: dict = {}
    try:
        exec(code_str, namespace)  # noqa: S102
    except Exception:
        print("=== generated code ===")
        for lineno, line in enumerate(code_str.splitlines(), 1):
            print(f"{lineno:4d}: {line}")
        print("=== end generated code ===")
        raise

    mods = {
        k: v
        for k, v in namespace.items()
        if isinstance(v, type)
        and issubclass(v, BaseModel)
        and not k.startswith("_")
        and k not in ("BaseModel", "Field", "Optional", "Any")
    }

    for cls in mods.values():
        cls.__module__ = f"src.generated.{grammar_stem}"

    return mods
