# Lexic — impartial review (V2)

This is a follow-up to `OPUS_REVIEW.md`. The review below re-reads the tree as it stands today, notes what has been addressed since V1, and focuses on the remaining risks to maintainability and to landing the unshipped functionality (R005 constrained generation, R006 cross-grammar translation).

220 tests pass (`uv run pytest tests/ -q` → `220 passed in 2.98s`), so the foundation is working end to end across all seven ground-truth grammars.

## Addressed since V1

- **Project rename is clean.** `pyproject.toml` now declares `name = "lexic"` with a proper hatch build target. Packaging intent is clearer even if the imports still rely on a `pythonpath = ["src"]` shim (see below).
- **No more stray scratch scripts at the root.** `tst.py`, `quick_tst*.py`, `with_guidance.py` are gone. `MILESTONE-BRIEF.md` and `REQUIREMENTS.md` are now under `saved_context/`.
- **No more contradictory `issues.md`.** The tree is internally consistent: `README.md`, `CLAUDE.md`, and `saved_context/REQUIREMENTS.md` tell the same story.
- **Tooling gates exist.** `tools/run_checks.sh` plus `tools/checks/{10_sanity,20_lint,30_typecheck,40_artifacts}.sh` are wired into a `.pre-commit-config.yaml` hook. This is the right pattern for a repo that generates code on disk — worth preserving.
- **Test suite is auditable.** 220 tests, all passing, with one-to-one mirroring between source modules and test files.

## What still looks solid

- The IR (`RuleSpec` + four atom dataclasses) is still the core of the design and it is still tight: 86 lines in `ir.py`, and the three emitters genuinely depend only on it. That boundary is the single most valuable asset in the repo.
- `GrammarModel.to_text()` (`src/base.py:32-76`) is 40 lines of data-driven walking over `spec.items` and `field_map`. No templating tricks, no grammar-specific branches. This is the contract S04 will lean on.
- `semantic_dump()` (`src/base.py:84-95`) still reads cleanly as S04 prep and doesn't overreach.
- No `exec`/`eval`. Generated files land on disk as importable modules, so you can open `generated/arithmetic.py` and see exactly what the codegen produced.

## Remaining concerns (grouped by SOLID)

### 1. Single Responsibility — `lark_builder.py` is two modules in one

`LarkBuilder` owns two responsibilities: (a) producing a Lark grammar string and (b) producing a `Transformer` subclass that reconstructs Pydantic instances from a Lark parse tree. The second responsibility is implemented by `_build_instance` at `src/codegen/lark_builder.py:291-409`, which is ~120 lines of positional matching over `items`, special-casing `ws`, optional char classes, `origin is list`, `Optional` unwrapping, and stray tokens between siblings.

This is the piece most likely to silently miscorrelate fields as the grammar surface grows. Recommendation: extract a `TransformerFactory` (or simply `transformer.py`) that takes `list[RuleSpec]` + `dict[str, type]` and returns a `Transformer`. `LarkBuilder` should then be a ~70-line module that only emits grammar text. The separation also makes it possible to unit-test the transformer construction in isolation (today you can't, because the instance-building logic is reachable only through `parse()`).

### 2. Interface Segregation — `CharClassAtom` is overloaded into three roles

`CharClassAtom` is meant to represent a character class (e.g. `[a-z]`), but the codebase currently uses it for three distinct kinds of value:

1. A true character class from the grammar: `CharClassAtom("[a-z]", 1, 1)`.
2. A **quoted literal with a quantifier**, because `LiteralAtom` has no quantifier fields: `CharClassAtom('"-"', 0, 1)` for `"-"?`. See `src/codegen/ir_builder.py:286-293` and `:449-458`.
3. A **compiled regex pattern** from inlining a `Group`: `CharClassAtom('("true"|"false"|"null")', 1, 1)`. See `src/codegen/ir_builder.py:314-332` and `_group_to_regex` at `:95-127`.

The three variants share one dataclass but need different handling downstream, which is why every emitter now contains a "what shape is this pattern really?" heuristic:

- `gbnf_emitter.py:12-35` — `_normalize_charclass_pattern_for_gbnf` with the infamous `"|\\\\\\\\("` replacement still in place, comment still admits "this is complex".
- `lark_builder.py:66-97` — `_normalize_charclass_pattern` strips GBNF-style quotes with a regex.
- `lark_builder.py:131-134` — `is_complex_regex = p.startswith("(") and "|" in p and not p.startswith("([")` is a pattern-sniffing heuristic that decides whether to skip normalization.

**Recommendation:** split `CharClassAtom` into three atom types with orthogonal responsibilities:

```python
CharClassAtom(pattern: str, min: int, max: int | None)      # true bracket expression
QuotedLiteralAtom(value: str, min: int, max: int | None)    # literal with a quantifier
InlineRegexAtom(pattern: str, min: int, max: int | None)    # compiled group
```

Each emitter then switches on the atom type (a closed, finite enumeration) rather than sniffing string shape. The `_normalize_charclass_pattern_for_gbnf` backslash hack disappears, because `InlineRegexAtom` can be emitted by `GBNFEmitter` as a parenthesised `(arm1 | arm2 | …)` reconstructed from its original structure — or carry a shadow `gbnf_source` field if round-tripping the shape isn't always possible. This is the single change that would most improve maintainability.

### 3. Open/Closed — `_classify` and `_build_instance` grow by case enumeration

`_classify` at `src/codegen/ir_builder.py:183-214` hasn't changed since V1. It enumerates five paths (`value_str`, `pure_literal_alt`, `named_alt`, `sequence`, fallback) gated by six structural probes: `_is_structurally_complex`, `_is_pure_literal_seq`, `_is_single_ruleref`, `_has_any_ruleref`, `_has_nontrivial_group`, `_has_group_with_alt`. The current shape works for the seven ground-truth grammars, but every new grammar shape is an 80%-chance new branch, and the predicates aren't independent (e.g. `_is_structurally_complex` mixes "has `*`-quantified group containing another group" with "all-no-refs AND any arm has group-with-alt"). This is the code most likely to rot.

`_build_instance` at `lark_builder.py:291-409` shows the same smell on the transformer side: nested `if origin is list / if origin is Optional / else` branches, each with a sub-switch on `atom` shape and child type.

**Recommendation:** introduce a small visitor or strategy layer. For classification, a rule could be represented as a tagged tree and classifiers could be pure functions on that tree. For `_build_instance`, dispatch should be keyed on the atom type (`CharClassAtom` / `RuleRefAtom` / `AlternationAtom`) and the field's resolved type, not on ad-hoc `isinstance` chains. A small table-driven approach — `{(atom_type, field_shape): builder_fn}` — would be both shorter and easier to extend.

### 4. Liskov — `AlternationAtom` has two incompatible contracts

`AlternationAtom` is used in two structurally different ways:

- As the sole entry of an `alternation` rule's `items` list, with `field_map={}` (abstract class, no fields). Example: `Term.__grammar__.items == [AlternationAtom([...])]`, `field_map={}`.
- As a positional entry inside a `sequence` rule, mapped to a field named `"value"`. Example: `Move.__grammar__.field_map == {"value": 0, "first": 1}` where item 0 is `AlternationAtom([...])` and item 1 is a `CharClassAtom`.

Every consumer now has to check `spec.kind` before it knows what to do with an `AlternationAtom`. The docstring on `RuleSpec` (`src/codegen/ir.py:72-74`) even calls this out: *"AlternationAtom items are NEVER in field_map"* — but that's only true for `kind == "alternation"`. The `Move` example contradicts it.

**Recommendation:** either (a) introduce an `InlineAlternationAtom` distinct from the top-level `AlternationAtom`, or (b) always wrap inline alternations in a helper rule so they never show up as a sequence item. Option (b) is simpler and consistent with how quantified groups are already handled (they get a synthetic `*-item` helper rule).

### 5. Single Responsibility — the "field naming by position" pre-commitment

`_assign_field_names` at `src/codegen/ir_builder.py:222-261` still names `CharClassAtom` fields `first`, `second`, `third`, `fourth`, `fifth` by position. This is visible in the generated code:

- `arithmetic.Ident` → `first: str, second: str, ws: Ws` (for `[a-z] [a-z0-9_]* ws`).
- `chess.Move` → `first: str` (for the `[+#]?` check/mate suffix).
- `chess.Pawn` → `first, second, third, fourth` for four distinct semantic positions (capture-file, dest-file, dest-rank, promotion).
- `json_ws.Number` → `first, second, third, fourth, ws` (sign, integer-part, fractional-part, exponent, ws).

R006 (cross-grammar translate) will not be able to map `chess.Pawn.third` onto anything meaningful, because the name carries no semantic information. Two grammars that each happen to have a `first` and `second` char class will look structurally identical even when they mean unrelated things.

**Recommendation options, in order of invasiveness:**

1. **Annotation comments in GBNF.** Allow `# @field=captureFile` comments above a char class and have `IRBuilder` attach them. Non-invasive, grammar-author-controlled.
2. **Derive names from char-class content.** `[a-h]` in a chess context → `file`, `[1-8]` → `rank`. Heuristics are brittle but better than ordinal names.
3. **Make translation structural, not name-based.** Treat `semantic_dump()` as producing an ordered tuple of (atom-shape, value) pairs, and require target rules to line up structurally. This deals with the problem by sidestepping names, but only works if grammar shapes align.

Any of these is better than shipping R006 against `first`/`second`/`third`. I'd combine (1) and (3): allow optional field-name annotations in GBNF and fall back to structural matching.

### 6. Dependency Inversion — the `base ↔ codegen` direction

`src/base.py:14` imports `RuleSpec`, `LiteralAtom`, and `RuleRefAtom` from `codegen.ir`. `src/base.py:80` lazily imports `GBNFEmitter`. Meanwhile `generated/*.py` import both `base.GrammarModel` and `codegen.ir.*`.

This is not wrong, but it means `base.py` (the runtime) depends on the `codegen` package (the build-time tool). Classes live in `generated/`, types they rely on live in `codegen/ir.py`. If the intent is that `codegen/` can eventually be split out (compile ahead, run without it), the shared IR dataclasses should move out of `codegen/` into a neutral module, e.g. `src/ir.py`. `codegen/` would then depend on it, `base.py` would depend on it, and `generated/*.py` would depend on it — with no back-edges from runtime into build-time.

### 7. DRY — escape-sequence decoding is duplicated

`_decode_gbnf_escapes` at `src/codegen/lark_builder.py:40-55` and the inline decoder at `src/base.py:45-55` do the same work, in the same way, with a slightly different sentinel (`\x00BACKSLASH\x00` vs `\x00BS\x00`). They should live in one place — either `codegen/ir.py` (as a utility next to the atoms they operate on) or a new `codegen/escapes.py`. Otherwise a future change to escape handling has to be done in two places and the drift will show up as an obscure round-trip test failure.

### 8. Topological sort still patches root post-hoc

`_topo_sort` at `src/codegen/ir_builder.py:555-582` runs a DFS and then explicitly pops the root rule and inserts it at index 0. As noted in V1, this is a symptom of the traversal starting from the wrong seed. `visit(by_cls["Root"])` first (when the root rule is `root`), then visit remaining specs, would do the right thing without the post-hoc fix. Low urgency, but worth fixing before any downstream code learns to depend on the accidental ordering.

### 9. `_normalize_charclass_pattern_for_gbnf` is still untouched

`src/codegen/gbnf_emitter.py:12-35` still has the `pattern.replace("|\\\\\\\\(", '|"\\\\\\\\\\\\"(')` hack with its comment "this is complex". V1 flagged this; it's still here. This is the clearest visible symptom of issue (2) above — fixing `CharClassAtom`'s overloading removes the need for this function.

### 10. Quantifier loss in `_group_to_regex`

Probably a real bug worth tracking. `json_ws.gbnf` declares:

```
number ::= ("-"? ([0-9] | [1-9] [0-9]{0,15})) ("." [0-9]+)? ([eE] [-+]? [1-9] [0-9]{0,15})? ws
```

`generated/json_ws.py:156` produces `CharClassAtom("([0-9]|[1-9][0-9])", min=1, max=1)` for the integer-part group — the inner `{0,15}` is silent-dropped, and the exponent group becomes `([eE][-+][0-9][1-9])` (sign and digit quantifiers both gone). `_group_to_regex` at `src/codegen/ir_builder.py:95-127` does handle inner `CharClass` quantifiers (line 114) but reconstructs literal + quantifier only in the `Literal` branch via `re.escape`, and the `{0,15}` on `[0-9]{0,15}` is turned into a repeated `[0-9]` without a regex quantifier. Worth adding a direct test: parse `number ::= [1-9] [0-9]{0,15}` and assert the emitted regex preserves `{0,15}`. Also worth a property-based test that throws long numeric strings at `json_ws` and asserts `parse(x).to_text() == x`.

## Testing gaps relative to the risks above

The round-trip tests in `tests/test_parser.py` use simple fixtures: `"x=1\n"`, `"{}"`, `'{"a":1}'`, `"1. e4 e5\n2. d4 d5\n"`. They prove the pipeline works on these cases; they do not exercise:

- Long decimal / exponent numbers in `json_ws` (would catch the quantifier-loss bug above).
- JSON strings containing the escape alternatives (`\"`, `\\`, `\uXXXX`).
- Arithmetic expressions with operator precedence — e.g. `"x=a+b*c\n"`.
- `c.gbnf` round-trip (no parser test exists for `c` at all).
- Malformed input after a valid prefix (parse-position failure modes).

A property-based layer using `hypothesis` to generate strings from a grammar and assert `parse(x).to_text() == x` across all seven grammars would lock in the round-trip guarantee much more tightly and is the single best test investment. The generator can be driven from `RuleSpec` itself, which keeps it grammar-agnostic (and doubles as a prototype for R005's generation loop).

## Alignment with REQUIREMENTS.md

- R001, R002, R003, R004, R007: implemented, tested, passing.
- R005 (LLM constrained generation): still absent from `src/`. No `generate()` entry point, no LLInterpreter integration, no references to llama.cpp or an equivalent. The requirement is listed as `active`; the tree has not moved toward it since V1.
- R006 (cross-grammar translate): explicitly deferred, `semantic_dump()` is the only concrete groundwork. See §5 above for why the current field-naming scheme is a blocker.
- R008 (tests-first): cannot be audited from the tree alone.

## Prioritised recommendations

If you can only do one thing before S04 (R006): **split `CharClassAtom` into three atom types** (§2). It eliminates the shape-sniffing heuristics in all three emitters, removes the backslash hack, and gives translation a cleaner surface to reason about.

If you can do three:

1. Split `CharClassAtom` (§2).
2. Extract the transformer-construction logic out of `LarkBuilder` (§1) and add `hypothesis`-based round-trip tests (§"Testing gaps").
3. Decide on semantic field naming before R006 lands (§5) — even if the answer is "GBNF comments, parsed by `IRBuilder`".

The quantifier-loss bug (§10) is a one-day fix and should land alongside whichever of the above you choose first, because the new round-trip tests will otherwise start catching it as unrelated noise.

## Bottom line

Compared to V1, the repo has done the easy cleanup: rename, drop stale files, wire up checks, confirm the test suite runs green. The structural concerns — IR overloading, two-roles-one-module in `lark_builder`, positional field names — are unchanged and will dominate the cost of landing R005 and R006. The codebase is in a strong enough state that all three fixes are doable one at a time without a rewrite; they just need to happen before translation is attempted in earnest, not during.

