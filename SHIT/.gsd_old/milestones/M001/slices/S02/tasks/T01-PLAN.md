---
estimated_steps: 31
estimated_files: 2
skills_used: []
---

# T01: Implement src/parser.py — GBNF-to-Lark grammar converter and Pydantic tree transformer

Implement src/parser.py with the full Grammar-Aware Parser. This file may already exist from a research phase — read it first. If it exists and uv run pytest tests/test_parser.py -v passes 21/21, verify the demo command and mark done without changes.

If the file needs to be written or fixed, implement these four components:

**1. _gbnf_to_earley_lark(gbnf_text: str) -> str**
Copied from with_guidance.py lines 255-269 (no model loading). Uses GrammarParser + resolve() from llguidance.gbnf_to_lark. After resolve(), root is renamed to 'start' — do NOT reverse this (unlike build() which does reverse it). The transformer maps tree.data == 'start' to mods.get('Root').

**2. _fix_lark_grammar(lark_g: str, gbnf_text: str) -> str**
Three sequential fixes:
- Fix 1 — quantifier outside regex: regex `r'/([^/]+)/{(\d+,\d+)}'` → replace with `/\1{\2}/` (move quantifier inside regex)
- Fix 2 — adjacent regex merge: regex `r'/([^/]+)/ /([^/]+)/(?![*+?~])'` → merge into `/\1\2/` (negative lookahead prevents merging when second regex is followed by Lark quantifier)
- Fix 3 — nullable rule detection: scan gbnf_text for rules with empty-string alternatives (SequenceNode with no children after resolve()). Replace entire rule with `/[ \t\n]+/?` and add `?` to all references to that rule name in lark_g.

**3. _transform(tree, mods, gbnf_rules, text) -> Any**
Recursive tree walker (NOT Lark Transformer class) mapping Lark Tree nodes to Pydantic instances via model_construct().

Four rule body types:
- Terminal rules (r.rule_is_terminal == True): if Tree has Token children, join them → str. If no Tokens (literal-only rule), use text[tree.meta.start_pos:tree.meta.end_pos].rstrip() — requires propagate_positions=True in Lark.
- AlternativeNode rules (abstract bases like Value): if no non-ws subtrees → literal match (true/false/null) → text span → find XAltN subclass. If has subtree → check child rule name against RuleRefNode alternatives → find XY concrete subclass. If no RuleRefNode match → compare child rule names against _seq_rule_refs(alt) for each SequenceNode alternative → instantiate XAltN subclass.
- RuleRefNode body (subclass rules like Root(Object)): if terminal ref → value: str field. If non-terminal → copy fields from child instance.
- SequenceNode / default (Object, Declaration etc): transform all non-ws children → flat list. Consume using _build_for_annotation(annotation, queue) for each field.

**4. _build_for_annotation(annotation, queue: deque) -> Any**
Consumes from child value queue to satisfy a Pydantic field annotation:
- str → pop one str
- BaseModel subclass → pop one instance
- Optional[T] → if _can_consume(T, queue), recurse; else None
- list[T] → consume while _can_consume(T, queue) → collect
- tuple[A, B, C] → consume one per type arg

_can_consume for tuples: count only non-list args as required (list args can produce []). Without this, Optional[tuple[str, Value, list[...]]] with 2 items would fail because 2 < 3.

**5. parse(text: str, grammar_path: Path) -> BaseModel**
Public API: reads grammar_path, calls _gbnf_to_earley_lark, _fix_lark_grammar, builds Lark(grammar, parser='earley', propagate_positions=True), calls build(grammar_path) to get mods, parses text, calls _transform on root tree.

**Critical constraints:**
- Use model_construct() everywhere (bypasses Pydantic validation — required for complex field types like Optional[tuple[str, Value, list[...]]])
- Import from src.codegen: build, to_class_name, _sequence_fields
- Do NOT import with_guidance.py — triggers model load
- Use deque (collections.deque) for the queue in _build_for_annotation

## Inputs

- `src/codegen.py`
- `resources/ground_truth/json_ws.gbnf`
- `resources/ground_truth/arithmetic.gbnf`
- `resources/ground_truth/c.gbnf`
- `resources/ground_truth/chess.gbnf`
- `resources/ground_truth/japanese.gbnf`
- `resources/ground_truth/list.gbnf`

## Expected Output

- `src/parser.py`

## Verification

uv run python -c "from src.parser import parse; from pathlib import Path; obj = parse('{\"city\": \"Porto\"}', Path('resources/ground_truth/json_ws.gbnf')); print(type(obj).__name__)" | grep -q ObjectValue && echo PASS
