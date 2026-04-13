---
estimated_steps: 62
estimated_files: 3
skills_used: []
---

# T01: Implement src/codegen.py with SOLID Pydantic model generator

Create src/__init__.py (empty package marker) and src/codegen.py which implements build(grammar_path) -> dict[str, type]. This is the full SOLID inheritance pattern generator: AlternativeNode rules → abstract base + typed concrete subclasses; SequenceNode rules → Pydantic models with typed fields; single RuleRefNode rules → subclass or BaseModel with value field.

IMPORTATION NOTE: llguidance.gbnf_to_lark exports: GrammarParser, resolve, ASTNode, AlternativeNode, LiteralNode, RegexNode, RepetitionNode, RuleNode, RuleRefNode, SequenceNode.

PORT THESE UTILITIES VERBATIM from FAILED_ATTEMPT/builder.py (they are correct):
- load_grammar() lines 40-45: read text, GrammarParser().parse(text), resolve(rules), return rules
- to_class_name() lines 53-55: snake_case → PascalCase via split('_') + capitalize join
- to_field_name() lines 58-63: lowercase, replace hyphen with underscore, suffix _ for reserved words (type, class, import, from, with, pass, raise)
- pluralise() lines 66-70: avoid double-s, append _list if ends with s, else append s
- decode_literal() lines 73-96: convert llguidance escape sequences (\n, \t, \r, \\, \") to actual chars
- ast_to_regex() lines 104-140: recursively convert terminal AST to Python regex string
- _node_to_type() lines 148-183: return Python type annotation string for AST node (str for terminals, ClassName for non-terminals, list[X] for repetition, Optional[X] for 0-1 repetition)
- _sequence_fields() lines 186-242: return list of (field_name, type_str, default_suffix) for all non-literal nodes in a SequenceNode; handles deduplication with _2, _3 suffixes; RuleRefNode → to_field_name(node.name); RepetitionNode → pluralise(inner name) or singular if optional; else 'value'

DO NOT PORT generate_models() — replace with _build_class_code() described below.

IMPLEMENT _build_class_code(rules: dict[str, RuleNode], grammar_stem: str) -> str:
  The function returns a Python source code string that when exec'd produces all Pydantic model classes in a namespace. The string MUST start with:
    from __future__ import annotations
    from pydantic import BaseModel, Field
    from typing import Optional, Any

  Emit classes in order of rule.order (sort non-terminal rules by r.order). Skip terminal rules (r.rule_is_terminal == True).

  ROOT RENAME ISSUE: resolve() renames 'root' to 'start' in the dict key AND in rule.name. Before calling resolve(), capture the original root rule name: `original_root = next(iter(parser.parse(text)))`. After resolve(), the rule that was 'root' now has rule.name == 'start'. When generating a class for this rule, use to_class_name(original_root) as the class name (→ 'Root'), NOT to_class_name('start'). To identify the root rule after resolve: it has the smallest rule.order (order == 0) AND its rule.name is now 'start'. Alternative simple approach: in load_grammar, capture the original root name before resolve(), return it alongside rules, or do the reverse rename: after resolve(), if 'start' in rules and rules['start'].order == 0, set rules['root'] = rules.pop('start'); rules['root'].name = 'root' (this reverses the rename so the rest of the code sees 'root' consistently).

  CLASS GENERATION RULES BY RULE TYPE:

  AlternativeNode rule (rule.alternatives is AlternativeNode, len > 1):
    1. Emit: class {ClassName}(BaseModel):\n    pass\n  (abstract base)
    2. For each alternative in rule.alternatives.alternatives (index i):
       - If RuleRefNode and target non-terminal: class {to_class_name(alt.name)}{ClassName}({ClassName}):\n    {field}: {TargetClassName}\n
       - If RuleRefNode and target terminal: class {to_class_name(alt.name)}{ClassName}({ClassName}):\n    value: str\n
       - If SequenceNode or other inline: class {ClassName}Alt{i}({ClassName}):\n    {fields from _sequence_fields() or 'value: str' if no fields}\n

  SequenceNode rule (rule.alternatives is SequenceNode):
    fields = _sequence_fields(rule.alternatives)
    if no fields: class {ClassName}(BaseModel):\n    pass\n
    else: class {ClassName}(BaseModel):\n    {field}: {type}{default}\n  for each field

  Single RuleRefNode rule (rule.alternatives is RuleRefNode):
    target = rule.alternatives.target
    if target is None or target.rule_is_terminal: class {ClassName}(BaseModel):\n    value: str\n
    else: class {ClassName}({to_class_name(target.name)}):\n    pass\n

  RepetitionNode rule (rule.alternatives is RepetitionNode):
    inner_type = _node_to_type(rule.alternatives) → will be list[X] or Optional[X]
    class {ClassName}(BaseModel):\n    items: {inner_type} = Field(default_factory=list)\n

  AlternativeNode rule with single alternative (len == 1):
    treat as SequenceNode — emit class with fields.

  After all class definitions, emit model_rebuild() calls for every class in the same definition order:
    {ClassName}.model_rebuild()\n  for each class defined.

IMPLEMENT build(grammar_path: str | Path) -> dict[str, type]:
  1. path = Path(grammar_path)
  2. grammar_stem = path.stem (e.g. 'json_ws')
  3. text = path.read_text()
  4. parser = GrammarParser(); raw_rules = parser.parse(text)
  5. original_root = next(iter(raw_rules))  # capture before resolve mutates
  6. resolve(raw_rules)  # mutates in place — 'root' becomes 'start'
  7. Reverse the rename: if 'start' in raw_rules: raw_rules['root'] = raw_rules.pop('start'); raw_rules['root'].name = 'root'
  8. code_str = _build_class_code(raw_rules, grammar_stem)
  9. namespace = {}
  10. try: exec(code_str, namespace) except Exception as e: print(code_str); raise
  11. Extract all classes: mods = {k: v for k, v in namespace.items() if isinstance(v, type) and issubclass(v, BaseModel) and not k.startswith('_') and k not in ('BaseModel', 'Field', 'Optional', 'Any')}
  12. Set __module__ on each: for cls in mods.values(): cls.__module__ = f'src.generated.{grammar_stem}'
  13. Return mods

KEY PITFALLS:
- from __future__ import annotations MUST be the first line of code_str (before imports). Without it, forward references in type annotations fail at class definition time for circular deps (json_ws.gbnf: Value refs Object refs Value).
- The exec namespace must contain {'__builtins__': __builtins__} or just {} — Python fills builtins automatically for exec with a plain dict.
- model_rebuild() must be called AFTER all classes are defined, not inline. Emit all class definitions first, then all model_rebuild() calls.
- For json_ws.gbnf, VALUE has 6+ branches. Branches that are inline (not a simple RuleRefNode) get names like ValueAlt4, ValueAlt5.
- Do not emit classes for terminal rules (r.rule_is_terminal == True). Refs to terminals produce str fields.
- The pydantic import in exec namespace needs to work: exec(code_str, {}) will import pydantic from the running environment. This is fine.

## Inputs

- `FAILED_ATTEMPT/builder.py`
- `resources/ground_truth/json_ws.gbnf`
- `resources/ground_truth/arithmetic.gbnf`

## Expected Output

- `src/__init__.py`
- `src/codegen.py`

## Verification

uv run python -c "from src.codegen import build; mods = build('resources/ground_truth/json_ws.gbnf'); assert mods['ObjectValue'].__bases__ == (mods['Value'],), mods['ObjectValue'].__bases__; assert issubclass(mods['Root'], mods['Object']), mods['Root'].__bases__; print('PASS:', sorted(mods.keys()))"
