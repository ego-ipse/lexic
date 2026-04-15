"""Parse text using a GBNF grammar and return typed Pydantic instances.

Uses Lark Earley parser under the hood. Builds the Lark grammar from the
ClassSpec hierarchy (same structure the emitter uses), parses the input,
then transforms the parse tree into Pydantic model instances.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from lark import Lark, Transformer, Token, Tree

# Ensure project root is importable.
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
_src_root = str(Path(__file__).parent)
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)

from codegen.parser import parse_gbnf
from codegen.classify import (
    classify_rule,
    to_pascal,
    strip_ws,
    is_ws_item,
    is_single_ruleref,
    unwrap_group_alt,
    is_inline_literal_alt_group,
)
from codegen.ast import (
    Alternation,
    CharClass,
    Group,
    Item,
    Literal,
    Rule,
    RuleRef,
    Sequence,
)
from codegen.emitter import build_specs, topo_sort, ClassSpec, FieldSpec


def _lark_name(name: str) -> str:
    """Convert a GBNF rule name to a Lark rule name.

    Must match _class_to_lark_name(to_pascal(name)) so references and definitions agree.
    """
    return _class_to_lark_name(to_pascal(name))


def _class_to_lark_name(class_name: str) -> str:
    """PascalCase → snake_case for Lark rule names."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", class_name)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return s.lower()


def _unescape_gbnf_literal(value: str) -> str:
    """Interpret GBNF escape sequences to actual characters."""
    result = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            c = value[i + 1]
            esc_map = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}
            result.append(esc_map.get(c, value[i] + c))
            i += 2
        else:
            result.append(value[i])
            i += 1
    return "".join(result)


def _literal_to_lark(value: str) -> str:
    """Convert a GBNF literal to Lark terminal."""
    actual = _unescape_gbnf_literal(value)
    if any(c in actual for c in "\n\t\r"):
        regex_parts = []
        for c in actual:
            if c == "\n":
                regex_parts.append(r"\n")
            elif c == "\t":
                regex_parts.append(r"\t")
            elif c == "\r":
                regex_parts.append(r"\r")
            elif c in r"\.^$*+?{}[]|()/":
                regex_parts.append("\\" + c)
            else:
                regex_parts.append(c)
        return f"/{''.join(regex_parts)}/"
    escaped = actual.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _charclass_to_lark(
    pattern: str, quantifier: str | None, terminals: dict[str, str]
) -> str:
    """Convert a char class to Lark, using named terminals for quantified patterns."""
    pattern = pattern.replace("/", "\\/")
    if quantifier:
        if quantifier == "*":
            term_name = f"CC{len(terminals)}"
            terminals[term_name] = f"{pattern}+"
            return f"{term_name}?"
        elif quantifier == "?":
            return f"/{pattern}/?"
        else:
            term_name = f"CC{len(terminals)}"
            terminals[term_name] = f"{pattern}{quantifier}"
            return term_name
    return f"/{pattern}/"


# ── Context object for grammar building ──────────────────────────────────────


class _BuildCtx:
    """Shared state for Lark grammar building."""

    def __init__(
        self, rules_dict, classifications, name_map, specs_by_name, terminals, sub_rules
    ):
        self.rules_dict = rules_dict
        self.classifications = classifications
        self.name_map = name_map
        self.specs_by_name = specs_by_name
        self.terminals = terminals
        self.sub_rules = sub_rules
        # Track which helper sub-rules we've already emitted
        self.emitted_helpers: set[str] = set()


# ── Spec-driven rule generation ──────────────────────────────────────────────


def _spec_to_lark_rule(spec: ClassSpec, rule: Rule | None, ctx: _BuildCtx) -> str:
    """Generate a Lark rule line for a ClassSpec."""
    lk_name = _class_to_lark_name(spec.name)

    if spec.is_abstract:
        if rule is None:
            return f"{lk_name} :"
        alt = unwrap_group_alt(rule.body)
        arms = []
        arm_counter = 0
        for seq in alt.seqs:
            stripped = strip_ws(seq)
            if len(stripped.items) == 0:
                continue
            arm_counter += 1
            ref = is_single_ruleref(stripped)
            if ref is not None:
                arms.append(_lark_name(ref))
            else:
                alias = f"{lk_name}__arm{arm_counter}"
                arm_lark = _seq_items_to_lark_simple(seq.items, ctx)
                arms.append(f"{arm_lark} -> {alias}")
        return f"{lk_name} : " + "\n    | ".join(arms)

    if spec.is_value_str:
        if rule is None:
            return f"{lk_name} :"
        alt = unwrap_group_alt(rule.body)
        body = _alt_to_lark_simple(alt, ctx)
        return f"{lk_name} : {body}" if body.strip() else f"{lk_name} :"

    # Sequence class
    parts = []
    if rule is not None:
        alt = unwrap_group_alt(rule.body)
        raw_arms = [s for s in alt.seqs if len(strip_ws(s).items) > 0]
        if raw_arms:
            parts = _fields_to_lark_parts(spec, raw_arms[0], ctx)
    if not parts and spec.fields:
        for f in spec.fields:
            parts.append(_field_type_fallback(f))

    body = " ".join(parts)
    return f"{lk_name} : {body}" if body.strip() else f"{lk_name} :"


def _fields_to_lark_parts(spec: ClassSpec, seq: Sequence, ctx: _BuildCtx) -> list[str]:
    """Walk GBNF items and spec fields together, producing Lark rule parts."""
    parts = []
    field_idx = 0

    for item in seq.items:
        if is_ws_item(item):
            parts.append("ws?")
            continue

        field_idx += 1
        if field_idx > len(spec.fields):
            # More items than fields — emit remaining as simple
            parts.append(_atom_to_lark_simple(item.atom, item.quantifier, ctx))
            continue
        field = spec.fields[field_idx - 1]
        part = _item_to_lark_for_field(item, field, spec, ctx)
        parts.append(part)

    return parts


def _item_to_lark_for_field(
    item: Item, field: FieldSpec, parent_spec: ClassSpec, ctx: _BuildCtx
) -> str:
    """Convert a GBNF item to Lark syntax, guided by field type."""
    if isinstance(item.atom, Literal):
        s = _literal_to_lark(item.atom.value)
        if item.quantifier:
            s += item.quantifier
        return s

    if isinstance(item.atom, CharClass):
        return _charclass_to_lark(item.atom.pattern, item.quantifier, ctx.terminals)

    if isinstance(item.atom, RuleRef):
        if item.atom.name == "ws":
            return "ws?"
        ref = _lark_name(item.atom.name)
        q = item.quantifier or ""
        return f"{ref}{q}"

    if isinstance(item.atom, Group):
        return _group_to_lark_for_field(item, field, parent_spec, ctx)

    return ""


def _group_to_lark_for_field(
    item: Item, field: FieldSpec, parent_spec: ClassSpec, ctx: _BuildCtx
) -> str:
    """Convert a group item to Lark, creating sub-rules for helper classes."""
    q = item.quantifier
    stripped_arms = [
        a for a in (strip_ws(s) for s in item.atom.alt.seqs) if len(a.items) > 0
    ]
    raw_arms = item.atom.alt.seqs

    if is_inline_literal_alt_group(item):
        inner = _alt_to_lark_simple(item.atom.alt, ctx)
        s = f"({inner})"
        if q:
            s += q
        return s

    # Inline union of named rules
    if (
        q is None
        and len(stripped_arms) > 1
        and all(is_single_ruleref(a) is not None for a in stripped_arms)
    ):
        refs = [_lark_name(is_single_ruleref(a)) for a in stripped_arms]
        return "(" + " | ".join(refs) + ")"

    # Repeated group (+, *)
    if q in ("+", "*"):
        if len(stripped_arms) == 1 and len(stripped_arms[0].items) == 1:
            inner_item = stripped_arms[0].items[0]
            inner_lark = _atom_to_lark_simple(
                inner_item.atom, inner_item.quantifier, ctx
            )
            return f"{inner_lark}{q}"
        else:
            helper_name = field.type_str[5:-1]  # List[X] -> X
            return _emit_helper_sub_rule(helper_name, raw_arms[0], ctx) + q

    # Optional group (?)
    if q == "?":
        if len(stripped_arms) == 1 and len(stripped_arms[0].items) == 1:
            inner_item = stripped_arms[0].items[0]
            inner_lark = _atom_to_lark_simple(
                inner_item.atom, inner_item.quantifier, ctx
            )
            return f"{inner_lark}?"
        else:
            helper_name = field.type_str[9:-1]  # Optional[X] -> X
            return _emit_helper_sub_rule(helper_name, raw_arms[0], ctx) + "?"

    # Unquantified single-arm group → inline
    if q is None and len(stripped_arms) == 1:
        return _seq_items_to_lark_simple(raw_arms[0].items, ctx)

    # Fallback
    inner = _alt_to_lark_simple(item.atom.alt, ctx)
    s = f"({inner})"
    if q:
        s += q
    return s


def _emit_helper_sub_rule(helper_name: str, raw_seq: Sequence, ctx: _BuildCtx) -> str:
    """Emit a Lark sub-rule for a helper class, using spec-aware field mapping."""
    helper_lk = _class_to_lark_name(helper_name)
    if helper_lk in ctx.emitted_helpers:
        return helper_lk
    ctx.emitted_helpers.add(helper_lk)

    helper_spec = ctx.specs_by_name.get(helper_name)
    if helper_spec and helper_spec.fields:
        # Spec-aware: walk fields and items together
        parts = _fields_to_lark_parts(helper_spec, raw_seq, ctx)
        inner_lark = " ".join(parts)
    else:
        # Fallback: simple conversion
        inner_lark = _seq_items_to_lark_simple(raw_seq.items, ctx)

    ctx.sub_rules.append(f"{helper_lk} : {inner_lark}")
    return helper_lk


# ── Simple (non-spec-aware) conversion helpers ───────────────────────────────


def _atom_to_lark_simple(atom, quantifier: str | None, ctx: _BuildCtx) -> str:
    """Simple atom→Lark conversion (no field guidance)."""
    if isinstance(atom, Literal):
        s = _literal_to_lark(atom.value)
        if quantifier:
            s += quantifier
        return s
    if isinstance(atom, CharClass):
        return _charclass_to_lark(atom.pattern, quantifier, ctx.terminals)
    if isinstance(atom, RuleRef):
        if atom.name == "ws":
            return "ws?"
        ref = _lark_name(atom.name)
        if quantifier:
            ref += quantifier
        return ref
    if isinstance(atom, Group):
        inner = " | ".join(
            " ".join(
                _atom_to_lark_simple(it.atom, it.quantifier, ctx) for it in s.items
            )
            for s in atom.alt.seqs
        )
        s = f"({inner})"
        if quantifier:
            s += quantifier
        return s
    return ""


def _seq_items_to_lark_simple(items: list[Item], ctx: _BuildCtx) -> str:
    parts = []
    for item in items:
        if is_ws_item(item):
            parts.append("ws?")
            continue
        parts.append(_atom_to_lark_simple(item.atom, item.quantifier, ctx))
    return " ".join(parts)


def _alt_to_lark_simple(alt: Alternation, ctx: _BuildCtx) -> str:
    arms = [_seq_items_to_lark_simple(s.items, ctx) for s in alt.seqs]
    return " | ".join(arms)


def _field_type_fallback(f: FieldSpec) -> str:
    return "/[^\\s]+/"


# ── Grammar builder ──────────────────────────────────────────────────────────


def build_lark_grammar(
    grammar_path: str | Path,
) -> tuple[str, str, list[Rule], list[ClassSpec]]:
    """Build a Lark grammar from a GBNF file, using the ClassSpec hierarchy."""
    grammar_path = Path(grammar_path)
    rules = parse_gbnf(grammar_path.read_text())
    rules_dict = {r.name: r for r in rules}
    classifications = {r.name: classify_rule(r, rules_dict) for r in rules}
    name_map = {r.name: to_pascal(r.name) for r in rules}
    specs = topo_sort(build_specs(rules))
    specs_by_name = {s.name: s for s in specs}

    terminals: dict[str, str] = {}
    sub_rules: list[str] = []

    ctx = _BuildCtx(
        rules_dict, classifications, name_map, specs_by_name, terminals, sub_rules
    )

    cls_to_rule: dict[str, Rule] = {}
    for r in rules:
        cls_to_rule[to_pascal(r.name)] = r

    start_rule = _lark_name(rules[0].name)
    lark_lines: list[str] = []

    has_ws = any(r.name == "ws" for r in rules)

    for spec in specs:
        rule = cls_to_rule.get(spec.name)
        if rule is None:
            # Helper class — will be emitted as sub-rule when needed
            continue
        if rule.name == "ws":
            continue

        line = _spec_to_lark_rule(spec, rule, ctx)
        lark_lines.append(line)

    # Add sub-rules
    lark_lines.extend(sub_rules)

    if has_ws:
        lark_lines.append("ws : /[ \\t\\n]+/")

    for term_name, regex in terminals.items():
        lark_lines.append(f"{term_name} : /{regex}/")

    grammar_str = "\n".join(lark_lines)
    return grammar_str, start_rule, rules, specs


# ── Tree → Pydantic construction ─────────────────────────────────────────────


def _flatten_tokens(tree) -> str:
    if isinstance(tree, Token):
        return str(tree)
    if isinstance(tree, Tree):
        return "".join(_flatten_tokens(c) for c in tree.children)
    return str(tree)


def _is_ws_node(item) -> bool:
    return isinstance(item, Tree) and item.data == "ws"


def _instance_matches_type(instance, type_name: str) -> bool:
    """Check if instance's class name matches type_name or is a subclass of it."""
    cls = type(instance)
    if cls.__name__ == type_name:
        return True
    # Check base classes (for abstract class hierarchies)
    for base in cls.__mro__:
        if base.__name__ == type_name:
            return True
    return False


def _build_transformer_class(
    specs: list[ClassSpec],
    classes: dict[str, type],
    rules: list[Rule],
    rules_dict: dict[str, Rule],
) -> type:
    """Dynamically build a Lark Transformer subclass."""
    spec_by_name = {s.name: s for s in specs}
    classifications = {r.name: classify_rule(r, rules_dict) for r in rules}

    # Build arm alias mapping
    arm_aliases: dict[str, tuple[str, int]] = {}
    for r in rules:
        cls = classifications.get(r.name)
        if cls != "named_alt":
            continue
        alt = unwrap_group_alt(r.body)
        arm_counter = 0
        for seq in alt.seqs:
            stripped = strip_ws(seq)
            if len(stripped.items) == 0:
                continue
            arm_counter += 1
            ref = is_single_ruleref(stripped)
            if ref is None:
                lk_name = _class_to_lark_name(to_pascal(r.name))
                alias = f"{lk_name}__arm{arm_counter}"
                arm_aliases[alias] = (r.name, arm_counter)

    methods = {}

    def ws_method(self, items):
        # Discard ws nodes — they don't correspond to fields
        from lark.visitors import Discard

        return Discard

    methods["ws"] = ws_method

    for s in specs:
        lk = _class_to_lark_name(s.name)
        cls_type = classes.get(s.name)
        if cls_type is None:
            continue
        # Skip Ws — handled specially above (returns plain string, not Pydantic object)
        if s.name == "Ws":
            continue

        if s.is_abstract:

            def make_abstract(cn=s.name):
                def method(self, items):
                    children = [
                        c
                        for c in items
                        if c is not None and not isinstance(c, (Token, str))
                    ]
                    return children[0] if children else (items[0] if items else None)

                return method

            methods[lk] = make_abstract()

        elif s.is_value_str:

            def make_value(ct=cls_type):
                def method(self, items):
                    val = "".join(
                        _flatten_tokens(c) if isinstance(c, Tree) else str(c)
                        for c in items
                    )
                    return ct(value=val)

                return method

            methods[lk] = make_value()

        else:

            def make_seq(ct=cls_type, sp=s):
                def method(self, items):
                    return _build_sequence_instance(ct, sp, items)

                return method

            methods[lk] = make_seq()

    # Arm aliases
    for alias, (parent_rule, arm_idx) in arm_aliases.items():
        parent_cls_name = to_pascal(parent_rule)
        arm_cls_name = f"{parent_cls_name}Arm{arm_idx}"
        arm_cls = classes.get(arm_cls_name)
        arm_spec = spec_by_name.get(arm_cls_name)
        if arm_cls is None or arm_spec is None:
            continue

        if arm_spec.is_value_str:

            def make_arm_val(ct=arm_cls):
                def method(self, items):
                    val = "".join(
                        _flatten_tokens(c) if isinstance(c, Tree) else str(c)
                        for c in items
                    )
                    return ct(value=val)

                return method

            methods[alias] = make_arm_val()
        else:

            def make_arm_seq(ct=arm_cls, sp=arm_spec):
                def method(self, items):
                    return _build_sequence_instance(ct, sp, items)

                return method

            methods[alias] = make_arm_seq()

    return type("GrammarTransformer", (Transformer,), methods)


def _build_sequence_instance(cls_type: type, spec: ClassSpec, items: list) -> object:
    """Build a Pydantic instance from spec fields and Lark tree children.

    Uses a forward-matching strategy: tries to match each field against the
    current child. For Optional fields, uses lookahead to decide whether to
    consume or skip.
    """
    children = [item for item in items if not _is_ws_node(item)]
    kwargs = {}
    child_idx = 0

    for fi, field in enumerate(spec.fields):
        t = field.type_str

        if t.startswith("List["):
            inner_type = t[5:-1]
            collected = []
            if inner_type == "str":
                # Consume str tokens until we hit a non-str or run out
                # But stop if a subsequent field needs a non-str child
                while child_idx < len(children):
                    c = children[child_idx]
                    if isinstance(c, (Token, str)):
                        collected.append(str(c))
                        child_idx += 1
                    else:
                        break
            else:
                while child_idx < len(children):
                    c = children[child_idx]
                    if isinstance(c, (Token, str)):
                        break
                    if _instance_matches_type(c, inner_type):
                        collected.append(c)
                        child_idx += 1
                    else:
                        break
            kwargs[field.name] = collected

        elif t.startswith("Optional["):
            inner_type = t[9:-1]
            if child_idx >= len(children):
                kwargs[field.name] = None
                continue

            c = children[child_idx]
            if inner_type == "str":
                # Lookahead: check if consuming this token would leave enough
                # tokens for subsequent required fields
                remaining_required = _count_remaining_required(spec.fields[fi + 1 :])
                remaining_children = len(children) - child_idx
                if (
                    isinstance(c, (Token, str))
                    and remaining_children > remaining_required
                ):
                    kwargs[field.name] = str(c)
                    child_idx += 1
                else:
                    kwargs[field.name] = None
            else:
                if not isinstance(c, (Token, str)):
                    kwargs[field.name] = c
                    child_idx += 1
                else:
                    kwargs[field.name] = None

        elif t == "str":
            if child_idx < len(children):
                c = children[child_idx]
                kwargs[field.name] = (
                    str(c) if isinstance(c, (Token, str)) else _flatten_tokens(c)
                )
                child_idx += 1
            else:
                kwargs[field.name] = ""

        elif t.startswith("Union["):
            if child_idx < len(children):
                kwargs[field.name] = children[child_idx]
                child_idx += 1

        else:
            if child_idx < len(children):
                kwargs[field.name] = children[child_idx]
                child_idx += 1

    return cls_type(**kwargs)


def _count_remaining_required(fields: list[FieldSpec]) -> int:
    """Count non-optional, non-list fields (they each consume exactly one child)."""
    count = 0
    for f in fields:
        t = f.type_str
        if t.startswith("Optional[") or t.startswith("List["):
            continue
        count += 1
    return count


# ── Public API ────────────────────────────────────────────────────────────────


def parse(text: str, grammar_path: str | Path) -> object:
    """Parse text against a GBNF grammar and return a typed Pydantic instance."""
    from codegen import codegen as run_codegen

    grammar_path = Path(grammar_path)
    classes = run_codegen(grammar_path)

    lark_grammar, start_rule, rules, specs = build_lark_grammar(grammar_path)
    rules_dict = {r.name: r for r in rules}

    parser = Lark(
        lark_grammar,
        parser="earley",
        ambiguity="resolve",
        start=start_rule,
        keep_all_tokens=True,
    )

    tree = parser.parse(text)

    TransformerClass = _build_transformer_class(specs, classes, rules, rules_dict)
    transformer = TransformerClass()
    return transformer.transform(tree)
