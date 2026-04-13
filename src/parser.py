"""
parser.py — GBNF text → Pydantic model parser using Lark Earley.

Public API:
    parse(text, grammar_path) -> BaseModel instance of the root class
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Union, get_args, get_origin
import inspect

from lark import Lark, Tree, Token
from llguidance.gbnf_to_lark import (
    GrammarParser,
    AlternativeNode,
    LiteralNode,
    RepetitionNode,
    RuleNode,
    RuleRefNode,
    SequenceNode,
    resolve,
)
from pydantic import BaseModel

from src.codegen import build, to_class_name


# ---------------------------------------------------------------------------
# Grammar conversion helpers
# ---------------------------------------------------------------------------


def _gbnf_to_earley_lark(gbnf_text: str) -> str:
    """Convert GBNF grammar text to a Lark Earley grammar string.

    Copies the same logic as with_guidance._gbnf_to_earley_lark, but lives
    in src/ so importing it never triggers model loading.
    """
    parser = GrammarParser()
    rules = parser.parse(gbnf_text)
    resolve(rules)
    for r in rules.values():
        r.name = r.name.lower()
    rlist = sorted(rules.values(), key=lambda r: r.order)
    return "\n".join(str(r) for r in rlist)


def _nullable_rule_names(gbnf_text: str) -> set[str]:
    """Return names of rules that have an empty-string alternative.

    Detects SequenceNode([]) (empty sequence) or LiteralNode('') as
    an alternative — both represent the empty string in the GBNF AST.
    Must run after resolve(); names are lowercased to match Lark output.
    """
    parser = GrammarParser()
    rules = parser.parse(gbnf_text)
    resolve(rules)
    nullable: set[str] = set()
    for rule in rules.values():
        body = rule.alternatives
        if isinstance(body, AlternativeNode):
            for alt in body.alternatives:
                if (isinstance(alt, LiteralNode) and alt.value == "") or (
                    isinstance(alt, SequenceNode) and not alt.nodes
                ):
                    nullable.add(rule.name.lower())
                    break
    return nullable


def _merge_adjacent_regexes(lark_g: str) -> str:
    """Merge consecutive /pat_a/ /pat_b/ into /pat_a pat_b/.

    Only merges when the second regex is NOT followed by a Lark quantifier
    (* + ? ~), so that /[a-z]/ /[a-z0-9_]/* is preserved (the * applies
    to the second regex alone).
    """
    pattern = re.compile(r"/([^/]+)/ /([^/]+)/(?![*+?~])")
    prev = None
    while prev != lark_g:
        prev = lark_g
        lark_g = pattern.sub(r"/\1\2/", lark_g)
    return lark_g


def _fix_lark_grammar(lark_g: str, gbnf_text: str) -> str:
    """Fix the Lark grammar produced by _gbnf_to_earley_lark for Earley parsing.

    Three fixes applied in order:
    1. Move {n} / {n,m} repetitions inside their preceding inline regex so
       Lark sees /pattern{n}/ rather than a zero-width anonymous terminal.
    2. Merge adjacent inline regexes (not when second has a quantifier after).
    3. For rules with empty-string alternatives (e.g. ws): replace the whole
       rule block with a non-empty whitespace regex and make all rule
       references optional (rule → rule?).
    """
    nullable = _nullable_rule_names(gbnf_text)

    # Fix 1 — move {n,m} inside preceding regex
    lark_g = re.sub(
        r"(/[^/]+/)\{(\d+(?:,\d*)?)\}",
        lambda m: m.group(1)[:-1] + "{" + m.group(2) + "}/",
        lark_g,
    )

    # Fix 2 — merge adjacent regexes (guards against zero-width split terminals)
    lark_g = _merge_adjacent_regexes(lark_g)

    # Fix 3 — replace nullable rule blocks, make refs optional
    for rule in nullable:
        lark_g = re.sub(
            rf"^{rule}:.*(?:\n[ \t]+\|.*)*",
            # Use lambda so the replacement string is returned verbatim
            # (re.sub doesn't process escape sequences in callable results)
            lambda m, r=rule: f"{r}: /[ \\t\\n]+/",
            lark_g,
            flags=re.MULTILINE,
        )

    if nullable:
        out_lines: list[str] = []
        for line in lark_g.split("\n"):
            m = re.match(r"^(\w+):", line)
            if m and m.group(1) in nullable:
                out_lines.append(line)  # keep rule definition as-is
            else:
                for rule in nullable:
                    line = re.sub(rf"\b{rule}\b(?!\?)", f"{rule}?", line)
                out_lines.append(line)
        lark_g = "\n".join(out_lines)

    return lark_g


# ---------------------------------------------------------------------------
# Tree → Pydantic transformer
# ---------------------------------------------------------------------------


_WS_NAMES: frozenset[str] = frozenset(
    {"ws", "whitespace", "space", "opt_space", "opt_ws"}
)


def _seq_rule_refs(seq: SequenceNode) -> list[str]:
    """Return the non-ws, non-literal rule names expected by a SequenceNode.

    Used to match actual parse-tree children against a candidate alternative.
    RepetitionNode children are included (using the inner rule name) because
    they may produce zero or more items but their rule name is still present
    in the tree when they match at least once.
    """
    names: list[str] = []
    for node in seq.nodes:
        if isinstance(node, LiteralNode):
            continue
        if isinstance(node, RuleRefNode):
            if node.name.lower() not in _WS_NAMES:
                names.append(node.name.lower())
        elif isinstance(node, RepetitionNode):
            inner = node.node
            if isinstance(inner, RuleRefNode) and inner.name.lower() not in _WS_NAMES:
                names.append(inner.name.lower())
            elif isinstance(inner, SequenceNode):
                for sub in inner.nodes:
                    if isinstance(sub, RuleRefNode) and sub.name.lower() not in _WS_NAMES:
                        names.append(sub.name.lower())
    return names


def _seq_matches(actual: list[str], expected: list[str]) -> bool:
    """Check if actual child rule names match expected (allowing extras for repetitions)."""
    if not expected:
        return not actual
    # Greedy prefix match: actual must start with all required expected names
    # but may have extras (from repetitions producing multiple children)
    ai, ei = 0, 0
    while ei < len(expected) and ai < len(actual):
        if actual[ai] == expected[ei]:
            ai += 1
            ei += 1
        else:
            # Allow consuming more of same rule (repetition) or skip mismatch
            break
    # All expected names must be covered
    return ei >= len(expected)


def _collect_tokens(tree: Tree | Token) -> list[str]:
    """Recursively collect all Token strings from a tree, skipping ws nodes."""
    if isinstance(tree, Token):
        return [str(tree)]
    if isinstance(tree, Tree) and tree.data == "ws":
        return []
    result: list[str] = []
    for child in tree.children:
        result.extend(_collect_tokens(child))
    return result


def _can_consume(annotation: Any, queue: list) -> bool:
    """Return True if annotation can be satisfied by queue[0]."""
    if not queue:
        return False
    origin = get_origin(annotation)

    if annotation is str or annotation == str:
        return isinstance(queue[0], str)
    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        return isinstance(queue[0], annotation)

    if origin is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        return bool(args) and _can_consume(args[0], queue)

    if origin is list:
        return True  # empty list always OK

    if origin is tuple:
        # Count only non-list args as required (list args can produce [])
        args = get_args(annotation)
        required = sum(1 for a in args if get_origin(a) is not list)
        return len(queue) >= required

    return False


def _build_for_annotation(annotation: Any, queue: list) -> Any:
    """Pop from queue to construct a value matching annotation."""
    origin = get_origin(annotation)

    if annotation is str or annotation == str:
        return queue.pop(0) if queue else None

    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        return queue.pop(0) if queue else None

    if origin is Union:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if not non_none:
            return None
        inner = non_none[0]
        if not queue or not _can_consume(inner, queue):
            return None
        return _build_for_annotation(inner, queue)

    if origin is list:
        inner = get_args(annotation)[0]
        result = []
        while queue and _can_consume(inner, queue):
            result.append(_build_for_annotation(inner, queue))
        return result

    if origin is tuple:
        return tuple(_build_for_annotation(a, queue) for a in get_args(annotation))

    # Unknown — pop whatever's next
    return queue.pop(0) if queue else None


def _set_raw(instance: Any, text: str, node: Tree | Token) -> Any:
    """If instance is a BaseModel and node has position info, store the raw text span."""
    if not isinstance(instance, BaseModel):
        return instance
    if not (isinstance(node, Tree) and hasattr(node, "meta")):
        return instance
    meta = node.meta
    if hasattr(meta, "start_pos") and hasattr(meta, "end_pos"):
        raw = text[meta.start_pos : meta.end_pos]
        instance.__dict__["_raw"] = raw
    return instance


def _transform(
    node: Tree | Token,
    mods: dict[str, type],
    gbnf_rules: dict[str, RuleNode],
    text: str,
) -> Any:
    """Public entry: delegates to _transform_impl and stamps _raw on the result."""
    result = _transform_impl(node, mods, gbnf_rules, text)
    return _set_raw(result, text, node)


def _transform_impl(
    node: Tree | Token,
    mods: dict[str, type],
    gbnf_rules: dict[str, RuleNode],
    text: str,
) -> Any:
    """Recursively transform a Lark parse tree into Pydantic model instances.

    Returns:
        A Pydantic BaseModel instance for non-terminal rules,
        a str for terminal rules,
        or None for ws / ignored nodes.
    """
    # Bare token — return as string (used when collecting terminal chars)
    if isinstance(node, Token):
        return str(node)

    rule_name: str = node.data

    # Always skip ws nodes — they carry no semantic content
    if rule_name == "ws":
        return None

    # Determine what this rule produces in codegen
    gbnf_rule = gbnf_rules.get(rule_name)

    # Lark rule that maps to 'root' Pydantic class (resolve renamed root→start)
    pydantic_name = to_class_name("root" if rule_name == "start" else rule_name)
    cls = mods.get(pydantic_name)

    # ── Terminal rule ─────────────────────────────────────────────────────────
    if gbnf_rule and gbnf_rule.rule_is_terminal:
        tokens = _collect_tokens(node)
        if tokens:
            # Regex-based terminal: join char tokens (excludes surrounding literals)
            return "".join(tokens)
        # Literal-only terminal (e.g. "int" ws): extract from original text span
        if hasattr(node, "meta") and hasattr(node.meta, "start_pos"):
            return text[node.meta.start_pos : node.meta.end_pos].rstrip()
        return ""

    # ── No class registered for this rule (skip to children / join) ──────────
    if cls is None:
        # For anonymous intermediary nodes: recurse and collect
        items = []
        for child in node.children:
            val = _transform(child, mods, gbnf_rules, text)
            if val is not None:
                items.append(val)
        if len(items) == 1:
            return items[0]
        return items or None

    # ── Collect non-ws children (keeping as Tree for name inspection) ─────────
    non_ws = [
        c for c in node.children
        if not (isinstance(c, Tree) and c.data == "ws")
    ]

    body = gbnf_rule.alternatives if gbnf_rule else None

    # ── AlternativeNode with multiple alternatives → abstract base ────────────
    if isinstance(body, AlternativeNode) and len(body.alternatives) > 1:
        alts = body.alternatives

        # No non-ws Tree children → matched a literal-only alternative (e.g. true/false/null)
        subtrees = [c for c in non_ws if isinstance(c, Tree)]
        if not subtrees:
            # Extract matched text via propagate_positions
            matched = ""
            if hasattr(node, "meta") and hasattr(node.meta, "start_pos"):
                matched = text[node.meta.start_pos : node.meta.end_pos].strip()
            # Find the literal-only alternative and its concrete subclass
            for alt_i, alt in enumerate(alts):
                if not isinstance(alt, RuleRefNode):
                    sub_name = f"{pydantic_name}Alt{alt_i}"
                    sub_cls = mods.get(sub_name)
                    if sub_cls:
                        return sub_cls.model_construct(value=matched)
            # Fallback
            return cls.model_construct(value=matched)

        # Has one subtree child — identify which alternative it is
        child_tree = subtrees[0]
        child_rule = child_tree.data  # e.g. 'object', 'string', 'number'

        for alt_i, alt in enumerate(alts):
            if not isinstance(alt, RuleRefNode):
                continue
            if alt.name != child_rule:
                continue
            # Found the matching alternative
            child_val = _transform(child_tree, mods, gbnf_rules, text)
            target = alt.target
            if target and not target.rule_is_terminal:
                # Non-terminal ref → subclass has `child_name: ChildClass`
                sub_name = f"{to_class_name(child_rule)}{pydantic_name}"
                sub_cls = mods.get(sub_name)
                if sub_cls and sub_cls.model_fields:
                    field_name = next(iter(sub_cls.model_fields))
                    return sub_cls.model_construct(**{field_name: child_val})
                return sub_cls.model_construct() if sub_cls else child_val
            else:
                # Terminal ref → subclass has `value: str`
                sub_name = f"{to_class_name(child_rule)}{pydantic_name}"
                sub_cls = mods.get(sub_name)
                if sub_cls:
                    return sub_cls.model_construct(value=child_val)
                return cls.model_construct(value=child_val)

        # No RuleRefNode alternative matched — try SequenceNode alternatives
        # by comparing the actual child rule names to expected non-ws rule refs
        actual_names = [c.data for c in non_ws if isinstance(c, Tree)]
        best_alt_i: int | None = None
        best_score = -1
        for alt_i, alt in enumerate(alts):
            if not isinstance(alt, SequenceNode):
                continue
            expected = _seq_rule_refs(alt)
            if _seq_matches(actual_names, expected):
                score = len(expected)  # prefer more specific matches
                if score > best_score:
                    best_score = score
                    best_alt_i = alt_i

        if best_alt_i is not None:
            sub_name = f"{pydantic_name}Alt{best_alt_i}"
            sub_cls = mods.get(sub_name)
            if sub_cls:
                child_vals = [
                    _transform(c, mods, gbnf_rules, text)
                    for c in non_ws
                ]
                child_vals = [v for v in child_vals if v is not None]
                queue = child_vals[:]
                kwargs: dict[str, Any] = {}
                for field_name, field_info in sub_cls.model_fields.items():
                    kwargs[field_name] = _build_for_annotation(field_info.annotation, queue)
                return sub_cls.model_construct(**kwargs)

        # Final fallback: try to transform single child or return empty class
        if subtrees:
            child_val = _transform(subtrees[0], mods, gbnf_rules, text)
            return cls.model_construct(value=child_val) if cls.model_fields else cls.model_construct()
        return cls.model_construct()

    # ── RuleRefNode body → subclass or single-value wrapper ──────────────────
    if isinstance(body, RuleRefNode):
        target = body.target
        child_trees = [c for c in non_ws if isinstance(c, Tree)]
        child_val = _transform(child_trees[0], mods, gbnf_rules, text) if child_trees else None

        if target is None or target.rule_is_terminal:
            # Wraps a terminal → value: str
            val = child_val if isinstance(child_val, str) else str(child_val or "")
            if cls.model_fields:
                return cls.model_construct(value=val)
            return cls.model_construct()
        else:
            # Inherits from child's class → copy fields
            if child_val is not None and isinstance(child_val, BaseModel):
                return cls.model_construct(
                    **{f: getattr(child_val, f, None) for f in cls.model_fields}
                )
            return cls.model_construct()

    # ── SequenceNode / RepetitionNode / default → assign children to fields ──
    # Transform all non-ws children in order
    child_vals: list[Any] = []
    for child in non_ws:
        val = _transform(child, mods, gbnf_rules, text)
        if val is not None:
            child_vals.append(val)

    if not cls.model_fields:
        return cls.model_construct()

    # Assign children to declared fields using annotation-based queue consumption
    queue = child_vals[:]
    kwargs: dict[str, Any] = {}
    for field_name, field_info in cls.model_fields.items():
        annotation = field_info.annotation
        val = _build_for_annotation(annotation, queue)
        kwargs[field_name] = val

    return cls.model_construct(**kwargs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _build_gbnf_rules(gbnf_text: str) -> dict[str, RuleNode]:
    """Parse GBNF and return lowercase rule dict (names match Lark grammar).

    Importantly: does NOT reverse resolve()'s root→start rename.
    The Lark grammar uses 'start'; the transformer maps it to the Root class.
    """
    parser = GrammarParser()
    rules = parser.parse(gbnf_text)
    resolve(rules)
    lowered: dict[str, RuleNode] = {}
    for rule in rules.values():
        rule.name = rule.name.lower()
        lowered[rule.name] = rule
    return lowered


def parse(text: str, grammar_path: str | Path) -> BaseModel:
    """Parse grammar-valid text into a typed Pydantic model instance.

    Args:
        text:         Input text valid under the grammar.
        grammar_path: Path to a .gbnf grammar file.

    Returns:
        An instance of the Root (or equivalent top-level) Pydantic class
        generated by ``build(grammar_path)``.

    Raises:
        lark.exceptions.UnexpectedInput: if text does not match the grammar.
    """
    grammar_path = Path(grammar_path)
    gbnf_text = grammar_path.read_text()

    # Build Pydantic model classes
    mods = build(grammar_path)

    # Build Lark parser
    lark_g = _gbnf_to_earley_lark(gbnf_text)
    lark_g = _fix_lark_grammar(lark_g, gbnf_text)
    lark_parser = Lark(
        lark_g,
        start="start",
        parser="earley",
        ambiguity="resolve",
        propagate_positions=True,
    )

    # Parse and transform
    gbnf_rules = _build_gbnf_rules(gbnf_text)
    tree = lark_parser.parse(text)
    result = _transform(tree, mods, gbnf_rules, text)

    if result is None:
        raise ValueError(f"Parser produced no result for input: {text!r}")
    return result

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse text using a GBNF grammar into a Pydantic model.")
    parser.add_argument("text", help="Input text to parse")
    parser.add_argument("grammar", help="Path to the .gbnf grammar file")
    args = parser.parse_args()

    try:
        result = parse(args.text, args.grammar)
        print(result.model_dump_json(indent=2))
    except Exception as e:
        print(f"Error parsing input: {e}")