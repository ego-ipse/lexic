# S06: Parser Rewrite + to_text() — Research

**Date:** 2026-04-13
**Status:** Ready for planning

## Summary

S06 has two interlocking deliverables: (1) a clean `src/parser.py` rewrite that populates correctly-typed Pydantic instances from grammar text, and (2) a `GrammarNode` base class in `src/base.py` whose `to_text()` reconstructs canonical text by walking the AST, not replaying raw spans. Both must be proven across all 6 ground-truth grammars by a tests-first `tests/test_parser.py`.

The current `src/parser.py` already works for 5 of 6 grammars with simple inputs (json_ws, list, chess, japanese, json_arr, c all parse). It fails for arithmetic expressions with operators (`x=1+2\n` fails because `ws ::= [ \t\n]*` is a Kleene-star nullable rule that `_nullable_rule_names()` doesn't detect). The bigger issue is architectural: the current parser uses `_raw` text span storage for `to_text()`-like retrieval — which the slice explicitly removes. There is no `src/base.py` and no `to_text()` method anywhere.

The hardest part of this slice is `to_text()` design. Generated class fields don't capture literal grammar tokens (braces, colons, commas, newlines). `to_text()` must know the grammar rule's AST to emit literals in the right places — this requires storing the GBNF rule AST on each class as a class variable (`__gbnf_rule_body__`) set by `build()` after class creation.

## Recommendation

**Four-task build order: tests → base.py → codegen update → parser rewrite.**

1. **T01**: Write `tests/test_parser.py` complete and failing. Cover all 6 grammars, type hierarchy, canonical `to_text()` round-trips, and rejection cases.
2. **T02**: Create `src/base.py` with `GrammarNode(BaseModel)` and `to_text()` via `__gbnf_rule_body__` class variable + `_emit_with_rule()` recursive walker.
3. **T03**: Update `src/codegen.py` to (a) import `GrammarNode`, (b) use `GrammarNode` as parent for top-level generated classes, (c) set `__gbnf_rule_body__` on each class in `build()` after `exec()`.
4. **T04**: Rewrite `src/parser.py`: remove all `_raw` code, fix nullable detection to include Kleene-star rules, fix transformer to use semantic names (not `AltN`), use full text span for terminal rules.

## Implementation Landscape

### Key Files

- `src/parser.py` — Full rewrite target. The `_nullable_rule_names()` function misses `ws ::= [ \t\n]*` (RepetitionNode, min_times=0). The transformer at line 414 still uses `f"{pydantic_name}Alt{best_alt_i}"` for SequenceNode arms — these names don't exist after S05. The `_set_raw()` function (line 264) and all `_raw` storage must be removed.
- `src/codegen.py` — Needs `build()` extended to set `__gbnf_rule_body__` on each class. `_ClassDef` needs an `ast_body: ASTNode` slot to carry the arm node through to `build()`. The generated code header must import `GrammarNode` from `src.base` and use it as the root parent.
- `src/base.py` — Does NOT exist. Create with `GrammarNode(BaseModel)`, `to_text() -> str`, and the `_emit_with_rule(node, queue)` helper that walks the GBNF AST emitting literals and consuming field values.
- `tests/test_parser.py` — Does NOT exist. Create with parametrized tests covering all 6 grammars.
- `tests/test_codegen.py` — Exists and passes 27 tests. Do not break it.

### Current Parser Status (what works, what doesn't)

| Grammar | Simple parse | With operators/complexity |
|---------|-------------|--------------------------|
| json_ws | ✅ `Root` with correct field values | ✅ nested objects/arrays |
| list | ✅ `Root(items=['hello'])` | items strips `"- "` prefix — bug for to_text |
| chess/japanese | ✅ (same structure as json_ws) | — |
| json_arr | ✅ | — |
| c | ✅ `int main(){}` | not tested |
| arithmetic | ✅ `x=1\n` (simple) | ❌ `x=1+2\n` fails (nullable ws bug) |

**The list bug**: `item ::= "- " [content]+ "\n"` is a terminal rule. The current parser joins char tokens → `items=['hello']` loses the `"- "` prefix and `"\n"` suffix. For `to_text()` to reconstruct `"- hello\n"`, the transformer must return the FULL text span for terminal rules: `text[node.meta.start_pos:node.meta.end_pos]`. This gives `items=['- hello\n']`, and `Root.to_text()` just concatenates them.

### The `to_text()` Architecture

**Problem**: `Object(BaseModel)` has field `strings: Optional[tuple[str, Value, list[tuple[str, Value]]]]`. The braces `{}`, colons `:`, commas `,` are grammar literals not stored in any field. `to_text()` must emit them.

**Solution**: Store the GBNF rule's AST body node on each class as `__gbnf_rule_body__: ClassVar[ASTNode]` set by `build()`. `GrammarNode.to_text()` calls `_emit_with_rule(self.__class__.__gbnf_rule_body__, list(field_values))`.

**`__gbnf_rule_body__` assignment** (set in `build()` after `exec()`):
- For rules with SequenceNode/RuleRef/Repetition body → set `__gbnf_rule_body__ = rule.alternatives` on the class
- For AlternativeNode rules → abstract base gets `None` (it delegates to subclass via `self.__class__`); each concrete subclass gets its ARM node (the specific `RuleRefNode`, `SequenceNode`, or `LiteralNode` for that arm)
- Requires `_ClassDef` to carry `ast_body: ASTNode | None` and a new `_BODY_MAP: dict[str, ASTNode]` to be built alongside `defs` in `_collect()`

**`_emit_with_rule(node, queue: list)` logic**:
- `LiteralNode` → emit `decode_literal(node.value)`, don't consume queue
- `RuleRefNode(ws_name)` → skip (ws names: `{"ws", "whitespace", "space", "opt_ws", "opt_space"}`)
- `RuleRefNode(terminal)` → emit `str(queue.pop(0))`
- `RuleRefNode(non-terminal)` → call `queue.pop(0).to_text()`
- `SequenceNode` → iterate children, recurse for each
- `RepetitionNode(min=0, max=1)` → Optional field: if `queue[0] is None`, pop and skip; else pop, unpack tuple if needed, recurse into inner node
- `RepetitionNode(list)` → pop list field; for each item, recurse into inner node (unpack tuple if needed)
- `AlternativeNode([all LiteralNodes])` → emit `str(queue.pop(0))` (stored matched literal)
- `AlternativeNode([mixed])` → consume one value; if GrammarNode, call `.to_text()`; else `str()`
- `RegexNode` → emit `str(queue.pop(0))`

**Canonical output examples**:
- `json_ws` `{"city":"Porto"}` → `to_text()` → `'{"city":"Porto"}'` (no spaces, ws not emitted)
- `list` `"- hello\n"` stored as terminal string → `to_text()` → `'- hello\n'`
- `arithmetic` `x=1\n` → `to_text()` → `'x=1\n'`
- `c` `int main(){}` → `to_text()` → `'int main(){}'`

### Nullable WS Fix

**Bug**: `_nullable_rule_names()` only detects `LiteralNode('')` or `SequenceNode([])` as nullable. It misses `ws: /[ \t\n]/*` (a `RepetitionNode` with `min_times=0`).

**Fix**: Also mark rules whose `alternatives` is a `RepetitionNode` with `min_times == 0` as nullable. This fixes arithmetic parsing.

### Transformer Fix: Semantic Names for SequenceNode Arms

**Bug**: In `_transform_impl` line 414: `sub_name = f"{pydantic_name}Alt{best_alt_i}"`. These `AltN` names no longer exist after S05.

**Fix**: Replace with `_sem_name(alt, pydantic_name, {})` to derive the semantic name — same logic used in `_collect()`. Import `_sem_name` from codegen or duplicate the logic in parser.

### Build Order

1. **T01 (tests-first)**: Write all tests before touching implementation. Tests must FAIL on current code. Confirm failure before proceeding.
2. **T02 (src/base.py)**: Standalone — no codegen changes needed yet. `GrammarNode.to_text()` can be implemented and unit-tested in isolation.
3. **T03 (codegen update)**: Modify `_ClassDef` to carry `ast_body`, update `_collect()` and `_build_class_code()` to use `GrammarNode` as root parent, update `build()` to set `__gbnf_rule_body__`. Run `pytest tests/test_codegen.py -v` — must still pass 27 tests.
4. **T04 (parser rewrite)**: With base.py and codegen both updated, rewrite parser.py: remove `_raw`, fix nullable detection, fix transformer. Run `pytest tests/test_parser.py -v` until all pass.

### Verification Approach

```
uv run pytest tests/test_parser.py -v     # primary gate
uv run pytest tests/test_codegen.py -v    # regression gate (27 tests must still pass)
```

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| GBNF → Lark grammar | `_gbnf_to_earley_lark()` in `src/parser.py` (copied from `with_guidance.py`) | Already works for 5/6 grammars; keep it |
| GBNF AST parsing | `llguidance.gbnf_to_lark.GrammarParser` + `resolve()` | Already in use; exposes all AST node types needed |
| Earley parsing | `lark.Lark(parser="earley")` | Already configured with `propagate_positions=True` |

## Constraints

- `to_text()` must be on `GrammarNode` base class, NOT in per-class generated code
- No `_raw` field anywhere — `to_text()` must use AST field traversal
- `tests/test_parser.py` must be complete and failing BEFORE any implementation changes
- `uv run` is the execution environment; all imports assume `src/` package
- `json_arr.gbnbf` has a typo in the filename (`.gbnbf` not `.gbnf`) — reference it by exact filename in tests

## Common Pitfalls

- **`AltN` names in transformer**: The transformer currently looks up `{pydantic_name}Alt{i}` for SequenceNode arms (line 414). These classes don't exist after S05. Must use `_sem_name()` logic.
- **Terminal rule text**: Current transformer joins individual char tokens, losing literal prefix/suffix. For terminal rules, use the full text span `text[meta.start_pos:meta.end_pos]` instead.
- **Nullable ws detection**: `ws ::= [ \t\n]*` is nullable via RepetitionNode, not via empty alternative. Extend `_nullable_rule_names()` to check `isinstance(rule.alternatives, RepetitionNode) and rule.alternatives.min_times == 0`.
- **`__gbnf_rule_body__` on abstract bases**: Abstract base classes (like `Value`) have `AlternativeNode` body with multiple arms. Setting their `__gbnf_rule_body__` to the full AlternativeNode is harmless since `to_text()` is always called on concrete subclass instances (which have their own body). Abstract bases can have `__gbnf_rule_body__ = None` and `to_text()` should assert or raise if called directly.
- **tuple field unpacking in `_emit_with_rule`**: When a `RepetitionNode` body contains a SequenceNode, the corresponding field is `list[tuple[...]]`. Each item in the list is a tuple that must be unpacked as a queue before recursing into the SequenceNode.
- **`test_codegen.py` regression**: Any change to `_build_class_code()` (to import `GrammarNode`) must be careful not to break the 27 existing tests. The parent class change (`BaseModel` → `GrammarNode` for root-level classes) affects the test `test_solid_hierarchy` assertions — update them to expect `GrammarNode` as the ultimate base.
- **`json_arr.gbnbf` filename**: Note the `.gbnbf` extension (typo in filename). Use `Path('resources/ground_truth/json_arr.gbnbf')` in tests.

## Open Risks

- **`_emit_with_rule` tuple/Optional edge cases**: The field type for `Object.strings` is `Optional[tuple[str, Value, list[tuple[str, Value]]]]` — deeply nested. The recursive emitter must correctly unpack the outer Optional, then the outer tuple, then the inner list, then the inner tuples. Getting this right for all 6 grammars (some with `Number` having 3 separate Optional/list fields) requires careful implementation.
- **Abstract base `to_text()` guard**: If `to_text()` is called on a pure abstract base instance (Value, Term, Factor, etc.) it has no fields and no meaningful `__gbnf_rule_body__`. Add a guard: if `not cls.model_fields`, raise `NotImplementedError` with a message indicating this is an abstract base.
- **c.gbnf Statement arms with operator-only sequences**: Some `statement` arms contain `SequenceNode` with operator literals (`"="`, `"("`, `")"`, `";"`) that appear in `to_text()` output. These are straightforward if the emitter handles `LiteralNode` correctly.
