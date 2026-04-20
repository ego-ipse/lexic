# Lexic — impartial review (V3)

This is a follow-up to `OPUS_REVIEW_V2.md`. Since V2, the repository has been
restructured into a proper `src/lexic/` package, the IR has been split into a
neutral `lexic.ir` module, `CharClassAtom` has been broken into the three atom
types V2 recommended, the transformer has been pulled out of `lark_builder.py`,
semantic field naming has landed, and a grammar-agnostic `generate()` function
plus `hypothesis` round-trip tests have been added. **312 tests pass**
(`uv run pytest tests/ -q` → `312 passed in 12.18s`).

A lot of V2's top-line recommendations have been executed. The remaining
concerns are deeper, shifted slightly by the refactor, and largely sit around
(a) the complexity of the transformer reconstruction logic, (b) the semantic
quality of derived field names, and (c) the gap between the current random
generator and the R005 constrained-generation requirement.

## Addressed since V2

The green box is substantial:

- **`CharClassAtom` has been split.** `lexic/ir/atoms.py` now defines
  `CharClassAtom` (true bracket expression), `QuantifiedLiteralAtom`
  (quoted literal with a quantifier), and `InlineRegexAtom`
  (compiled group, with both `regex` and `gbnf` shadow fields). The V2 §2
  recommendation landed exactly as described. Every emitter now dispatches on
  atom type rather than sniffing pattern shape.
- **The `_normalize_charclass_pattern_for_gbnf` backslash hack is gone.**
  `gbnf_emitter.py` is now 90 lines with no `"|\\\\\\\\("` replacement and no
  "this is complex" comment.
- **`LarkBuilder` no longer owns transformer construction.**
  `lexic/codegen/lark_builder.py` is down to 141 lines and only produces the
  Lark grammar string; `lexic/codegen/transformer.py` holds the 267-line
  transformer logic behind a `build_transformer(specs, classes)` entry point.
  This is the V2 §1 split.
- **`AlternationAtom` no longer has two contracts.** The inline case has its
  own `InlineAlternationAtom` type. `AlternationAtom` is only ever the sole
  entry of a `kind='alternation'` spec; `InlineAlternationAtom` only ever
  appears inside a `kind='sequence'` spec and always carries a field_map entry.
  The V2 §4 fix.
- **IR lives in a neutral package.** `lexic/ir/` is a separate subpackage;
  `codegen/` depends on it, `base.py` depends on it, and `generated/*.py`
  depends on it. No back-edge from `base.py` into `codegen/` except the
  lazy `GBNFEmitter` import inside `to_gbnf()`. This is the V2 §6 fix.
- **Escape decoding is centralised.** `lexic/utils/escapes.py::decode_gbnf_escapes`
  is the single implementation, used by `base.py`, `transformer.py`, and
  `generate.py`. V2 §7 resolved.
- **Semantic field naming has replaced ordinal positional names.**
  `_CHARCLASS_NAMES` + `_sanitize_pattern` + `_LITERAL_NAMES` +
  `_inline_regex_field_name` mean `chess.RootItem` now has
  `digit, digit2, move, move2` (was `first, second, third, fourth`),
  `arithmetic.Ident` has `lower, alnum, ws` (was `first, second, ws`),
  and `chess.Move` has `value, annotation` (was `value, first`). V2 §5 —
  see caveat in §3 below, the win is partial.
- **Quantifier loss in inline groups is fixed.** `_to_regex` now preserves
  quantifiers on `Literal`, `CharClass`, and `Group` children; the emitted
  `generated/json_ws.py::Number` carries
  `InlineRegexAtom("([0-9]|[1-9][0-9]{0,15})", ...)` and
  `InlineRegexAtom("[eE][-+]?[0-9][1-9]{0,15}", ...)` with the inner
  `{0,15}` and `?` quantifiers intact. V2 §10 resolved.
- **Topological sort is seeded from `root` up front** (`_topo_sort` at
  `ir_builder.py:652-668`). The post-hoc pop/insert hack is gone. V2 §8 resolved.
- **Tests restructured** into `tests/unit/`, `tests/integration/`,
  `tests/property/`, mirroring `src/lexic/` one-to-one. Property tests drive
  `hypothesis` seeds through `generate → parse → to_text` round-trips for six
  of the seven grammars.
- **A grammar-agnostic generator exists.** `lexic/generate.py::generate()` is
  groundwork for R005 — see §7 for the gap between this and what R005 actually
  asks for.

## What looks solid

- The IR (`lexic/ir/atoms.py` + `lexic/ir/spec.py`) is now 136 lines total and
  is the contract the rest of the pipeline depends on. Every atom type is a
  small frozen-shape dataclass with explicit fields. This is the healthiest
  module in the repo.
- The codegen pipeline is genuinely linear: `parser → ir_builder → emitters`,
  each ~90-230 lines, and each emitter reads well in isolation.
- `GrammarModel.to_text()` (`base.py:33-70`) is still 40 lines of
  data-driven iteration over `spec.items`. No templating, no grammar-specific
  branches. It is the one piece R006 translation will hang from, and it has
  stayed tight.
- No `exec` or `eval`; generated modules are importable Python on disk.
- The `pyproject.toml` declares `packages = ["src/lexic"]` and tests drive via
  `pythonpath = ["src"]`. Packaging is cleaner than V2.

## Remaining concerns (grouped by SOLID)

### 1. Single Responsibility — `transformer.py::_build_instance` is still load-bearing imperative code

Moving 267 lines into its own module is real progress, but the complexity did
not shrink — it was relocated. `_build_instance` (`transformer.py:43-184`) is
a single function that interleaves at least five orthogonal policies:

1. **Literal-regex token filtering** (lines 57-67): the
   `non_field_regex_values` set strips Lark `/regex/` tokens that correspond
   to control-char literals so they don't displace field positions. This is
   compensating for Lark's `keep_all_tokens=False` behaviour on `/regex/` vs
   `"quoted"` literals.
2. **List collection** (lines 89-110): pattern-matches `origin is list` and
   handles the "stray string tokens between model children" case.
3. **Optional handling** (lines 112-128): pattern-matches `Optional[X]` via
   `type(None) in args`.
4. **Non-optional non-list dispatch** (lines 130-183): the largest branch,
   which further dispatches on whether `hint is str`, whether the atom is a
   `CharClassAtom` with `max != 1` (multi-char coalescing), whether the atom
   is a `_is_ws_ref`, or whether the atom is an `_is_optional_char`.
5. **Pydantic default supplying** when children run out (lines 174-182).

Every policy has its own edge-case. The "coalesce consecutive string tokens
when `CharClassAtom.max != 1`" rule (lines 142-149) is the subtle kind that
passes on today's grammars and silently mis-correlates the moment a new
grammar introduces, say, two adjacent `*`-quantified char classes with
different patterns.

**The concern is not length — it's that this function is the single untyped,
imperative bridge between the Lark parse tree and the generated Pydantic
classes, and it grows by special-case.** A new grammar shape is very likely a
new branch here rather than a new atom type in `lexic.ir`.

**Recommendation.** Make the transformer table-driven:

```python
BUILDER_BY_ATOM: dict[type[Atom], FieldBuilder] = {
    LiteralAtom: LiteralFieldBuilder(),
    CharClassAtom: CharClassFieldBuilder(),
    RuleRefAtom: RuleRefFieldBuilder(),
    ...
}
```

Each `FieldBuilder` knows: given `(atom, hint, children_cursor)`, return
`(field_value, new_cursor)`. `Optional[X]` and `List[X]` are handled by
wrapping builders (`OptionalFieldBuilder`, `ListFieldBuilder`) rather than
forked branches in the main function. Test each builder in isolation.

This is the single change most likely to keep the pipeline correct as the
grammar surface grows past seven.

### 2. Open/Closed — `_classify` is still a disjunctive predicate cascade

`_classify` at `ir_builder.py:202-233` still enumerates five outcomes
(`value_str`, `pure_literal_alt`, `named_alt`, `sequence`, fallback) gated by
six structural probes (`_is_structurally_complex`,
`_is_pure_literal_seq`, `_is_single_ruleref`, `_has_any_ruleref`,
`_has_nontrivial_group`, `_has_group_with_alt`). The predicates are not
independent — `_is_structurally_complex` in particular ORs together "has `*`
group containing another group" with "all-no-refs AND any arm has
group-with-alt", which reads as "tuned against the training set of seven
grammars".

No grammar in `resources/ground_truth/` currently breaks it, but the eighth
grammar is likely a new branch. This module is the hardest to extend without
regressions, and it carries zero unit tests of its own decision surface
(only end-to-end tests of emitted classes).

**Recommendation.** Either:

- Represent each predicate as a method on a `GbnfRuleTree` wrapper and unit-test
  each predicate on a focused fixture set (decoupled from what the whole pipeline
  emits), or
- Replace the cascade with a visitor that walks the GBNF AST once and returns
  a classification record (kind + arm shapes + helper requirements) in a
  single pass, making the decision surface auditable in one place.

Either way, the decision logic should be visible and testable, not distributed
across six helpers.

### 3. Single Responsibility — semantic field naming solved the ordinal problem but still produces non-semantic names

The naming system is a clear improvement. Obvious cases map well: `[0-9]` →
`digit`, `[a-z]` → `lower`, `[+#]` → `annotation`, `[a-zA-Z0-9_]` → `alnum`,
`-` → `sign`. But two residual failure modes show up in the generated files:

1. **Pattern-sanitised names aren't semantic — only lexical.** `chess.Pawn`
   has fields `a_h_x: str, a_h: str, cc_1_8: str, nbkqr: str`. Those are
   derived from the patterns `[a-h]x` inlined, `[a-h]`, `[1-8]`, and
   `[NBKQR]` — but grammar-author intent (capture-file, dest-file, dest-rank,
   promotion-piece) is nowhere visible. `chess.Nonpawn` is even worse: it's a
   `value_str` rule, so the six char-class atoms never become field names and
   the translation layer sees only an opaque `value: str`.
2. **`InlineRegexAtom` names derive from the first arm.** `json_ws.Number` now
   has `sign, val_0_9, val_0_92, ee_0_9_1_9_0, ws`. `val_0_9` and `val_0_92`
   are disambiguated positionally; `ee_0_9_1_9_0` is not meaningfully
   different from the pattern itself. The names are identifier-safe, stable,
   and completely opaque.

**R006 cross-grammar translation** cannot lean on these names. Two grammars
that each have an `[a-h]` will both produce an `a_h` field even if one means
"chess file" and the other means "hex digit subset". The README
(`README.md:48-49`) acknowledges this with a "planned" inline-comment
annotation mechanism (`# @field=captureFile`) — but the hook does not exist in
`IRBuilder` or `parser.py` yet, and without it the semantic layer is purely
syntactic.

**Recommendation.** Two complementary moves:

1. Add the `# @field=<name>` annotation support to `parser.py` (attach a
   post-comment or pre-comment to the GBNF AST `Item`) and honour it in
   `_assign_field_names`. Non-invasive, author-controlled, and the only way to
   get truly semantic names for pattern-only rules.
2. For rules without annotations, treat `semantic_dump()` as producing a
   **structural tuple** `[(atom_shape, value), ...]` rather than a named dict,
   so R006 can match by position+shape. This is a fallback that skips the name
   problem entirely when two grammars have structurally compatible rules.

Ship R006 against annotations-first + structural-fallback. Do not ship R006
against `a_h_x` / `val_0_92`.

### 4. Single Responsibility — `value_str` round-tripping leaks Lark internals into the transformer

`transformer.py:231-255` reconstructs the text for a `value_str` rule by:

1. collecting all non-`None` children into `token_text`,
2. iterating `spec.items` and emitting filtered-quoted literals at their
   positions,
3. placing `token_text` "at the first non-filtered-literal position".

This works because printable-only `LiteralAtom`s are emitted to Lark as
`"quoted"` (filtered by `keep_all_tokens=False`) while control-char
`LiteralAtom`s are emitted as `/regex/` (kept as tokens). The reconstruction
quietly depends on both behaviours and on the fact that no real `value_str`
rule has the kept-token and filtered-literal interleaved in a way that breaks
"first non-filtered-literal position".

**This is the same family of fragility as §1.** The rule for when a value_str
reconstruction is correct is not written down — it's an emergent consequence
of Lark's tokeniser config plus atom-to-lark emission plus this function.

**Recommendation.** Emit *all* literals as `/regex/` (keep tokens uniformly)
and reconstruct value_str by concatenation in spec order. Trade some Lark
friendliness for an explicit, position-independent reconstruction rule. The
extra tokens are a performance concern, not a correctness one.

### 5. Open/Closed — `generate.py` duplicates structure walking that belongs on the IR

`generate.py` is 274 lines of structural dispatch:

- `_parse_escape` (lines 44-63) and `_parse_charclass_chars` (66-93) re-implement
  GBNF bracket-expression semantics, in parallel to the actual regex used at
  parse time. Two parsers of the same source shape exist now.
- `_gen_inline_regex` (123-142) parses `InlineRegexAtom.gbnf` by splitting on
  `|` — a fourth pass at the same information that `InlineRegexAtom.gbnf` and
  `InlineRegexAtom.regex` already hold.
- `generate()` itself (179-274) dispatches on atom type with a long
  `isinstance`-ladder that duplicates `transformer.py`'s dispatch.

The root cause is that atoms are pure data — every consumer has to build its
own visitor. This isn't inherently wrong, but right now we have at least three
consumers (`ModelEmitter`, `GBNFEmitter`, `LarkBuilder` + `transformer`, plus
the new `generate`) each with its own `isinstance` cascade.

**Recommendation, medium-term.** Give each Atom a minimal protocol —
e.g. `to_gbnf()`, `to_lark()`, `generate(rng)` — and let emitters dispatch via
`atom.to_gbnf()` instead of `_atom_to_gbnf(atom)`. This would trade static
`isinstance` cascades for polymorphic methods; each atom owns its own
rendering in one place, and new atoms don't require changes in four emitters.
The trade-off is that atoms then know about Lark/GBNF — which couples the IR
to its consumers. Reasonable people disagree on this; flag it, don't rush it.

A smaller, cheaper move: extract `_parse_charclass_chars` into
`lexic/utils/charclass.py` so at least the bracket-expression parsing is in one
place. Right now the bracket-expression semantics live in `generate.py` but
*also* (via `InlineRegexAtom.regex`) get handed to Lark's regex engine, so drift
between them would only be caught by property tests.

### 6. Liskov / honest typing — `Union[Pawn, Nonpawn, Castle]` discrimination is implicit

`ModelEmitter._field_type` (`model_emitter.py:20-74`) collapses
`InlineAlternationAtom` and `AlternationAtom` to the common parent class if all
arms share one, otherwise emits `Union[A, B, C]`. `generated/chess.py::Move.value`
is typed `Union[Pawn, Nonpawn, Castle]`. At parse time the transformer's
abstract-arm handler picks "the first non-None, non-Token child" — the Lark
tree decides which arm, and Pydantic is never asked to discriminate.

This works because the transformer produces already-typed instances. It breaks
if someone ever constructs a `Move` by hand from a JSON payload, because
Pydantic has no tag to pick between three shape-similar classes. For R006
translation this becomes a concern: if translate produces a dict that goes
through `Move(**data)`, Pydantic will need a discriminator.

**Recommendation.** When emitting Union fields, attach a Pydantic
`discriminator` annotation or a `model_validator(mode='before')` that picks the
arm by structural shape. Today's code doesn't need this; the moment R006 goes
to code, it will.

### 7. Missing — R005 constrained generation is still absent

`REQUIREMENTS.md` marks R005 as active. The tree has moved slightly: there is
now a `generate()` that can produce random strings conforming to a grammar.
But R005 is not "random string generator" — it is **LLM-guided token-level
generation** that biases sampling so the output remains grammar-valid. That
requires:

- A tokeniser-aware mask function (`logits → allowed-token-mask`) over the
  grammar state.
- A driver that steps per-token, updates state, and returns the allowed set.
- Integration with llama.cpp's sampler or an equivalent hook.

None of these exist. `generate()` is a useful testing tool (it powers the
hypothesis round-trips) but it does not discharge R005.

**Recommendation.** Treat `generate()` as what it is — the property-test
generator — and scope R005 separately. The natural next step is a
`lexic/grammar_state.py` that, given a list of RuleSpecs plus a "current
partial string", answers "which next characters (or tokens, if passed a
tokeniser vocab) keep the string on a valid parse path?". That's the contract
R005 needs and it's a finite, testable surface independent of llama.cpp.

### 8. `parse.py` regenerates the module on every call

`parse()` at `src/lexic/parse.py:20-42` calls `codegen(grammar_path)` every time,
which parses the GBNF, builds IR, writes `generated/<stem>.py`, invalidates
the module in `sys.modules`, and re-execs it. The property-test `conftest.py`
notes this cost as "~20ms each". For a production API it's a disk write per
parse.

This is not a correctness issue but it is an architectural leak: `codegen` is a
build-time tool that `parse()` uses at runtime. The V2 §6 fix got us *most* of
the way — IR is in a neutral package — but `parse()` itself has not been split
between "compile once" and "parse N times".

**Recommendation.** Memoise by grammar-path (or mtime) so the disk write and
module import happen once, not per call. Longer-term: let `parse()` accept
either a path (compile then parse) or a dict of classes (use these, skip
compile). The latter is what R005 and any hot loop will need.

### 9. `to_gbnf()` is the last runtime → codegen back-edge

`base.py:72-76`:

```python
def to_gbnf(self) -> str:
    from lexic.codegen.gbnf_emitter import GBNFEmitter
    return GBNFEmitter([self.__grammar__]).emit_rule(self.__grammar__)
```

This lazy import is cosmetically fine but it's the only remaining reason a
pure-runtime deploy can't drop `lexic/codegen/` entirely. `gbnf_emitter.py`
doesn't depend on `parser.py` or `ir_builder.py`, so it could move to
`lexic/gbnf/` (alongside `lexic/ir/`) and `base.py` could import eagerly
without pulling in the build-time surface.

Low priority, easy cleanup.

### 10. Helper-rule name collision is handled locally but not globally

`ir_builder.py:449-457` dedupes helper rule names within a single
`_seq_to_atoms` call:

```python
existing = {s.rule_name for s in helper_specs}
suffix = 2
candidate = helper_rule_name
while candidate in existing:
    candidate = f"{helper_rule_name}{suffix}"
    suffix += 1
```

But `_seq_to_atoms` is called per rule — `helper_specs` is a fresh list every
time. Two different rules could both produce `foo-item` if a grammar author
used `foo` as a class name twice through different paths. `_assign_field_names`
produces `digit` / `digit2` disambiguation per-rule as well. Cross-rule
collision is prevented today only because `{parent_class_name.lower()}-item`
is unique per parent rule — but that invariant isn't written down.

**Recommendation.** Have `IRBuilder.build()` hold a single `helper_name_set`
passed to `_seq_to_atoms`, so dedup is globally consistent and the invariant
is explicit.

## New concerns introduced by the refactor

### A. `generate.py` is fragile in ways property tests won't catch

Two defaults bias the generator:

- `_pick_count` returns 0 for any optional element (`if min_ == 0: return 0`),
  which means hypothesis round-trips *never exercise any `?`-quantified
  branch*. Every `Optional[X]` in a generated class is only ever `None`
  during property testing.
- `max_depth` starts at 4-5 and alternation arms are picked uniformly, with a
  depth-0 fallback that picks the first arm that produces non-empty output.
  For recursive grammars (arithmetic `term → expr → term`) this produces
  heavily left-biased trees.

The hypothesis test skips `c.gbnf` entirely (only six of seven grammars are
parameterised in `tests/property/test_roundtrip.py`), because `c`'s root is
`(declaration)*` and the generator returns `""` for optional roots.

**Recommendation.** Fix `_pick_count` to actually explore `[0, max]` when
generation is in a "random" mode, with an explicit `minimal=True` mode for
non-exploratory uses. Add a `c.gbnf` round-trip that either asserts on a
hand-picked non-empty seed, or drives the generator from `declaration`
directly.

### B. `generate.py` has its own GBNF decoder paralleling `escapes.py`

`_parse_escape` / `_parse_charclass_chars` re-implement bracket-expression
parsing. `decode_gbnf_escapes` handles literal-string escapes. These are
different concerns (bracket interior vs. quoted-string), but the knowledge of
*which escapes GBNF supports* is now encoded in two places. If the grammar
grows `\N{...}` or similar, both need to change.

Move bracket-expression parsing into `lexic/utils/charclass.py` alongside
`escapes.py` so the set of supported escapes lives in one file.

### C. Transformer references `to_lark_name` via a cross-module import

`transformer.py:19` imports `to_lark_name` from `lark_builder.py`. After the
V2 §1 split these two files depend on each other at the module level
(`lark_builder.py` also does `from lexic.codegen.transformer import build_transformer`
inside `build_transformer`). The cycle is broken only by the lazy import. It
would be cleaner to have `to_lark_name` live in a small shared module (or in
`lexic/utils/`) so neither file has to reach into the other.

## Testing gaps

The property layer is a big upgrade over V2. It still has two blind spots:

1. **Coverage asymmetry.** Six grammars are hypothesis-tested; `c.gbnf` is not,
   and the `arithmetic`/`chess` generators mostly emit minimal (literal-only,
   no-optional) shapes, so the optional branches of the transformer are
   exercised only by hand-written tests in `tests/integration/test_parse.py`.
2. **The `_build_instance` dispatch surface is not unit-tested.** There is
   `tests/unit/lexic/codegen/test_transformer.py`; if it asserts on individual
   `FieldBuilder`-equivalents rather than end-to-end transformer calls, it
   would directly catch the §1 class of bugs. (The file exists; a closer look
   would confirm what shape the tests take.)
3. **No failure-mode tests.** Ill-formed text after a valid prefix, unclosed
   brackets, trailing garbage — none are asserted on. `parse(text, path)` may
   raise a Lark exception or silently accept; there is no contract.
4. **GBNF round-trip is structural but not textual.**
   `test_gbnf_roundtrip.py` asserts rule-name preservation and rule-count
   equality but not that `emit(parse(text)) == text`. For a tool whose selling
   point is "exact-fidelity reconstruction", textual round-trip on emitted
   GBNF is worth locking in.

## Alignment with REQUIREMENTS.md

- **R001, R002, R003, R004, R007**: implemented, tested, passing.
- **R005 (LLM constrained generation)**: `generate()` exists but is a random
  generator, not a constrained-decoding layer. See §7.
- **R006 (cross-grammar translate)**: still explicitly deferred. Groundwork is
  stronger (semantic_dump + atom split + naming) but the naming is still too
  weak to translate against. See §3.
- **R008 (tests-first)**: cannot be audited from the tree alone.

## Prioritised recommendations

If you can only do one thing before S04 (R006):
**ship the `# @field=<name>` annotation parser** (§3) so R006 has something
semantic to translate against. Without it R006 will hit `a_h_x` / `val_0_92`
collisions the moment two grammars overlap.

If you can do three:

1. GBNF annotations → `_assign_field_names` (§3).
2. Table-driven transformer (§1) — or at minimum, add unit tests to
   `test_transformer.py` that exercise each atom-kind × field-shape cell of
   `_build_instance` independently. This makes the §A generator bias visible
   and reduces the blast radius of the `CharClassAtom.max != 1` coalescing
   rule.
3. Textual GBNF round-trip test (`emit(parse(text)) == text`, modulo
   normalisation) for all seven grammars — the single cheapest way to catch
   regressions in the emitter/IR pair as it evolves.

Medium-term, before R005:

- Split `parse()` into "compile once" (returns a `CompiledGrammar` object with
  classes, specs, and a parser) and "parse N times" (takes the compiled
  object). The R005 loop can't afford a per-call disk write.
- Introduce `lexic/grammar_state.py` with a `GrammarState.allowed_next_chars()`
  method driven by the RuleSpec IR. This is the contract R005 needs and it's
  testable without any LLM integration.

## Bottom line

V2 identified eight concrete refactors. **Most of them are in.** The IR split,
the atom-type split, the transformer extraction, the escape-decoder
unification, the IR-package relocation, the semantic-naming first pass, the
quantifier-loss fix, and the `_topo_sort` fix are all shipped. The test suite
has grown from 220 → 312 tests and gained a property layer. This is a real
consolidation, not cosmetic churn.

The remaining risks have shifted but not gone away. The two biggest
maintainability threats now are:

1. **`_build_instance` as the untyped imperative bridge** — it is where new
   grammar shapes will silently mis-correlate fields.
2. **Field naming that is identifier-safe but not semantic** — it is the
   ceiling on R006.

Both are fixable inside the current architecture. Neither requires a rewrite.
Ship them before R006, not during.
