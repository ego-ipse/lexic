# Knowledge Base

<!-- Append-only. Patterns, gotchas, and lessons learned during development. -->

## llguidance: resolve() renames 'root' to 'start' — must be reversed

`resolve(raw_rules)` mutates the rules dict in-place, renaming the 'root' key to 'start' and setting `rule.name = 'start'`. Any code that expects the root rule to be named 'root' must reverse this immediately after calling resolve():

```python
if 'start' in raw_rules:
    raw_rules['root'] = raw_rules.pop('start')
    raw_rules['root'].name = 'root'
```

Without this reversal, the generated Root class is emitted as `class Start(BaseModel)` and `mods['Root']` raises KeyError. Discovered in M001/S01/T01.

## exec'd code strings: `from __future__ import annotations` must be first line

When using `exec()` to define Pydantic classes that reference each other (e.g., json_ws where `Value` refs `Object` which refs `Value`), `from __future__ import annotations` MUST be the very first line of the code string — before any imports. Without it, forward references in type annotations fail at class definition time with `NameError` because Python resolves annotations eagerly in exec context.

```python
code = "from __future__ import annotations\nfrom pydantic import BaseModel\n..."
exec(code, {})
```

Discovered in M001/S01/T01.

## Pydantic v2: model_rebuild() must be called after ALL classes are defined

In generated code strings, `model_rebuild()` calls must be emitted as a separate block after all class definitions — not inline after each class. Pydantic v2 needs all forward-referenced classes to exist in the namespace before it can resolve them.

Pattern: emit all class bodies first, then emit one `ClassName.model_rebuild()` line per class in the same definition order. Discovered in M001/S01/T01.

## resources/ground_truth has 6 grammars, not 7 — json_arr.gbnbf is absent

The plan and slice spec reference 7 ground-truth grammars, but `resources/ground_truth/` contains only 6 `.gbnf` files. `json_arr.gbnbf` (note typo: `.gbnbf`) is referenced in task descriptions but does not exist on disk. Use `glob('*.gbnf*')` to collect whatever is present rather than hardcoding 7. Discovered in M001/S01/T02.

## _sem_name Case 4: parent_cname + to_class_name(node.name), not reversed

The task plan described Case 4 fallback as `to_class_name(node.name) + parent_cname` (rule-ref first), but the test expectations require the reverse: `parent_cname + to_class_name(node.name)`. For example, `term` arm 2 has first non-ws ref `expr` → `TermExpr` (parent `Term` + `Expr`), not `ExprTerm`. Similarly `statement` arm 0 has first non-ws ref `dataType` → `StatementDataType`. Always use `parent_cname + to_class_name(node.name)` in Case 4. Discovered in M001/S05/T02.

## SequenceNode attribute is .nodes, not .items

The llguidance AST `SequenceNode` stores its children in `.nodes`, not `.items`. Code that iterates over sequence arms via `arm.items` silently sees an empty/absent attribute. All internal iteration over SequenceNode children must use `arm.nodes`. Discovered in M001/S05/T02.

## parse() always returns Root — ObjectValue is a nested type, not the top-level result

`parse(text, grammar_path)` always returns an instance of `Root` for any input, because the grammar's root rule (`root ::= object` for json_ws) maps to `Root`. `ObjectValue` is the concrete subtype of `Value` for when a JSON value is itself an object — it appears as a nested field, not as the parse result. Any demo, test, or doc that says "parse returns ObjectValue" is wrong. The authoritative check is `type(result).__name__ == 'Root'`. Discovered in M001/S02/T01.
