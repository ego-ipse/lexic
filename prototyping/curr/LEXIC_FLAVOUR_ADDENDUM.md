# Lexic — Addendum: Grammar Flavour as a Choice

**Status:** addendum to `OPUS_REVIEW_V3.md`,
`LEXIC_GENERATED_CODE_PROPOSAL.md`, and
`LEXIC_ECOSYSTEM_RECOMMENDATIONS.md`.

Scope: contains only what this addendum **overrides or adds**. Everything
in the prior documents stands unless contradicted here.

---

## 1. The change in scope

Lexic should treat the grammar notation as a **parameter of the pipeline**,
not as a hardcoded assumption. The target flavours, in likely order of
usefulness:

- **GBNF** (llama.cpp) — current, stays the default.
- **ABNF** (RFC 5234) — used by every IETF RFC grammar.
- **EBNF** (ISO 14977) — academic standard; closest to GBNF syntactically.
- **Lark** — Lexic already uses Lark internally at parse time; exposing it
  as a choice is near-free.
- **PEG** — ordered-choice semantics differ from CFG, so this one is
  non-trivial and should be deferred until real demand exists.

The value proposition the prior ecosystem document understated: **no
library in the structured-output or grammar-tooling space does cross-flavour
round-trip**. An RFC author who wants to run their ABNF grammar against
llama.cpp currently hand-translates. A llama.cpp grammar author who wants
to cite a spec in a paper hand-translates the other way. Lexic can make
that one command.

This is depth, not just breadth — the combination of Pydantic-first
authoring + multi-flavour emission is a capability no other library
offers, and it's independently useful even if the Pydantic round-trip
layer weren't there.

---

## 2. Overrides to `LEXIC_GENERATED_CODE_PROPOSAL.md`

### 2.1 Override §5.5 — IR pattern representation

The proposal said `PatternAtom` has fields `pattern: str` (regex) and
`gbnf: str` (shadow). **Replace with:**

```python
@dataclass
class PatternAtom:
    regex: str                         # canonical, Python `re` dialect
    source_forms: dict[str, str]       # flavour-shadow map; see §4.1
    min: int
    max: int | None
```

Rationale: the shadow needs to be per-flavour, not GBNF-locked.
`source_forms` is populated by whichever parser consumed the grammar
(e.g. the ABNF parser writes `source_forms["abnf"] = "0*15DIGIT"`), and
read by whichever emitter is producing output (e.g. `to_grammar("gbnf")`
reads `source_forms["gbnf"]` if present, falls back to reconstructing
from `regex` if not).

This field is the atom's only concession to flavour-specific detail.
Everything else on the atom is dialect-neutral.

### 2.2 Override §4.3 — the `grammar_rule` decorator DSL

The proposal described the decorator's mini-DSL (`'expr "=" ws result "\\n"'`)
as "a strict subset of GBNF." **Rephrase as:**

> The mini-DSL is **Lexic's internal grammar syntax**, inspired by GBNF.
> It is not literal GBNF and is not literal ABNF or EBNF. It is the one
> string format a grammar author writes inside `@grammar_rule(...)`,
> regardless of what target flavour they want to emit to.

This is critical. The decorator DSL must **not** multiply into flavour
dialects; `@grammar_rule('EXPR = expr "=" result')` with ABNF syntax is
explicitly out of scope. A user who wants ABNF output writes the same
decorator and calls `instance.to_grammar("abnf")`.

The internal DSL happens to resemble GBNF because that's the closest
notation to what Python grammar authors will recognise. This is a
stylistic choice, not a semantic coupling.

### 2.3 Override §12 — implementation order

The proposal's step 1 was "Merge char-class atom types into `PatternAtom`."
**Revise to:**

> **Step 1: Design the canonical pattern representation.** Before collapsing
> `CharClassAtom`, `QuantifiedLiteralAtom`, and `InlineRegexAtom`, pick
> the regex dialect for `PatternAtom.regex` (Python `re`, with a documented
> subset that maps cleanly to GBNF, ABNF, EBNF, and Lark). Commit to
> `source_forms: dict[str, str]` as the shadow shape, not a single `gbnf`
> field.

This is the single decision that, if taken wrong now, will be expensive
to reverse when flavour-switching lands. Get it right once; the rest of
the proposal's sequence is unchanged.

### 2.4 Override §11 — non-goals

The proposal's non-goals list says "Parsing GBNF in the decorator." **Extend to:**

> Parsing any flavour-specific syntax inside `@grammar_rule(...)`. The
> decorator accepts Lexic's mini-DSL only. Flavour translation happens
> at the module level via `codegen(path, flavour=...)` and
> `instance.to_grammar(flavour)`.

---

## 3. Overrides to `LEXIC_ECOSYSTEM_RECOMMENDATIONS.md`

### 3.1 Override §3.2 — R006 framing

The recommendations doc said: *"No library in the survey does this. It's
Lexic's unique contribution."* **Add:**

> Cross-flavour grammar translation (GBNF ↔ ABNF ↔ EBNF ↔ Lark) is a
> second unique contribution, disjoint from cross-grammar data translation
> (R006). Flavour translation is easier, cheaper, has a clearer scope, and
> has an identifiable audience (RFC authors, llama.cpp users writing specs,
> academic grammar tooling). Ship it as a parallel track to R006, not as
> a sub-feature of it.

The practical implication: a new method `Grammar.translate_flavour("abnf")`
(class-level, not instance-level) that takes the `RuleSpec` list plus a
target flavour and emits text. Orthogonal to `translate(instance, target_cls)`.

### 3.2 Override §4 — features to explicitly reject

The recommendations doc said to reject "Cross-language client codegen."
**Clarify:**

> Cross-programming-language codegen (Python + TypeScript + Go + Ruby,
> à la BAML) is out of scope.
>
> **Cross-grammar-flavour codegen (GBNF ↔ ABNF ↔ EBNF) is in scope** as a
> deferred feature. These are not the same axis: flavour switching keeps
> the entire pipeline in Python and swaps only the frontmost parser and
> the rearmost emitter. Language switching would require a runtime for
> each target language.

### 3.3 Override §5 — priority ordering

Add a **Tier 2.5** between "required before public release" and "enables
R006":

> **Tier 2.5 — preserves the flavour-switching option.**
>
> - `PatternAtom.source_forms: dict[str, str]` instead of
>   `PatternAtom.gbnf: str`.
> - `codegen(path, flavour: str = "gbnf")` parameter in the signature,
>   even if it only accepts `"gbnf"` today.
> - Module rename: `codegen/parser.py` → `codegen/gbnf/parser.py`, with
>   a `GbnfAdapter` at `codegen/gbnf/__init__.py`.
> - `instance.to_grammar(flavour="gbnf")` method as the forward-facing
>   entry point, with `to_gbnf()` kept as an alias.
>
> None of these do anything today beyond renaming and adding a parameter
> that only accepts one value. All of them preserve the option to add
> flavours later without breaking the 1.0 API.

Tier 2.5 is cheap (roughly a day of work) and its cost grows linearly
with time if deferred, because each new user of the 1.0 API is another
caller whose calls would break if the signatures changed.

### 3.4 Override §4 — "A builder-pattern grammar DSL" rejection

The recommendations doc rejected a pygbnf-style builder DSL. **This rejection
still holds**, but add:

> Cross-flavour translation is a different axis. The rejected thing was
> *a third authoring surface* competing with GBNF text and Pydantic-first.
> Flavour translation doesn't add an authoring surface — users still
> author in one of the two existing ways (text file or Pydantic decorator),
> and the choice of *what to emit* is independent. ABNF input becomes a
> fourth authoring *input* (alongside GBNF text, EBNF text, Pydantic
> classes), but there's no new syntax to learn per flavour — each is
> already a well-defined standard.

---

## 4. New design points not covered in prior documents

These are additions, not overrides.

### 4.1 The flavour adapter contract

Every supported flavour is implemented as a **flavour adapter** package
under `lexic/codegen/<flavour>/`:

```
lexic/codegen/<flavour>/
  __init__.py        FlavourAdapter (parser + ir_builder + emitter)
  parser.py          text → flavour-specific AST
  ast.py             flavour-specific AST nodes
  ir_builder.py      flavour AST → RuleSpec IR
  emitter.py         RuleSpec IR → flavour text
  patterns.py        regex-dialect translation for this flavour
```

The adapter's public interface is:

```python
class FlavourAdapter(Protocol):
    name: str                                      # e.g. "gbnf", "abnf"
    extensions: tuple[str, ...]                    # e.g. (".gbnf",)

    def parse(self, text: str) -> list[RuleSpec]: ...
    def emit(self, specs: list[RuleSpec]) -> str: ...
```

Everything else (validation, naming, class generation, Lark building,
Pydantic emission) is flavour-agnostic and lives in `lexic.ir` +
`lexic.codegen` without sub-packages. The adapters are the only code that
knows any flavour's specifics.

### 4.2 The regex dialect boundary

`PatternAtom.regex` is **Python `re` syntax**, but restricted to a subset
that every target flavour's pattern syntax can express:

- Character classes `[abc]`, `[a-z]`, `[^abc]`.
- Standard escapes `\n`, `\t`, `\r`, `\\`, `\"`.
- Unicode escapes `\xXX`, `\uXXXX`, `\UXXXXXXXX`.
- Quantifiers `?`, `+`, `*`, `{n}`, `{n,m}`, `{n,}`.
- Alternation `|` inside groups.
- Non-capturing groups `(?:...)` (for nesting without capture side-effects).

Excluded: backreferences, lookahead/lookbehind, named captures,
possessive quantifiers, `\b` word boundaries, `\d`/`\w`/`\s`
(write these as explicit char classes for portability).

A `patterns.py` module per flavour handles the dialect-specific
translation. `GbnfPatternEmitter.emit("[a-z]+")` → `"[a-z]+"`.
`AbnfPatternEmitter.emit("[a-z]+")` → `"1*ALPHA"` where `ALPHA` is an
ABNF core rule. `BnfPatternEmitter.emit("[a-z]+")` → expansion into
recursive productions, with a fresh rule name inserted.

This module is the single place dialect knowledge lives. If a user writes
a pattern using a feature outside the portable subset, codegen raises with
a specific diagnostic naming the unsupported construct and suggesting an
alternative.

### 4.3 Whitespace conventions across flavours

Different flavours handle whitespace differently:

| Flavour | Convention |
|---|---|
| GBNF | Explicit `ws` rule, referenced where allowed. |
| ABNF | Implicit `*c-wsp` between most productions; core rules like `SP`, `HTAB`, `CRLF`. |
| EBNF | Usually explicit, sometimes implicit via lexer level. |
| Lark | `%ignore` directive at grammar header. |

On **parsing**: each flavour's adapter is responsible for producing a
`RuleSpec` list that captures whitespace faithfully as explicit
`RuleRefAtom("ws", ...)` entries (current Lexic convention). This lets the
rest of the pipeline remain flavour-agnostic. If ABNF implicit whitespace
is used, the ABNF `IRBuilder` inserts `ws` refs at every legal position
and generates a `ws` rule matching ABNF's `c-wsp` semantics.

On **emission**: each flavour's emitter decides how to render those `ws`
references in the target dialect. GBNF emitter emits them as literal `ws`
rule references. ABNF emitter strips them and lets ABNF's implicit
whitespace do the work. EBNF emitter picks the convention per user
configuration.

This means a **round-trip is guaranteed semantically but not textually**
when the source and target flavours disagree on whitespace convention.
`to_grammar("abnf")` on a grammar originally parsed from GBNF will
produce an ABNF grammar that parses the same language, but the ABNF text
won't contain explicit `ws` tokens. This should be documented upfront
and tested against the round-trip property "parse the emitted grammar
with its own parser, run text through both, assert identical parse trees."

### 4.4 Round-trip properties across flavours

Three properties the cross-flavour test suite must assert, for every pair
`(src, dst)` of supported flavours:

1. **Semantic round-trip.** `parse(emit_dst(parse_src(g)))` produces the
   same `list[RuleSpec]` as `parse_src(g)`, up to canonical rule
   ordering. That is, converting a grammar from `src` to `dst` and
   parsing it back yields the same IR.

2. **Text round-trip within a flavour.** `emit_src(parse_src(g)) == g`
   up to normalisation (canonical whitespace, canonical rule order).
   This is the current GBNF round-trip property, extended to each
   flavour's emitter.

3. **Data round-trip across flavours.** For a text `t` valid in grammar
   `g_src`, and grammars `g_src` and `g_dst` expressing the same
   language (i.e. `g_dst = convert(g_src, src → dst)`), parsing `t`
   with Lexic against either grammar produces the same Pydantic
   instance. This is the property that validates the cross-flavour
   feature is actually useful.

Property 3 is the hardest to hold and is where subtle bugs will surface.
It has to be tested with hypothesis-generated grammars as well as the
seven ground-truth ones, because hand-crafted grammars tend to exercise
similar feature combinations.

### 4.5 Scope of the initial flavour-switching milestone

If and when flavour-switching lands, the realistic 1.0 scope is:

- **In:** GBNF (existing), ABNF, EBNF.
- **Out:** PEG (semantic mismatch; ordered choice vs CFG), ANTLR (too
  big), W3C EBNF variant (differs from ISO, user-hostile to support both).

ABNF and EBNF share the CFG model with GBNF, so their adapters are
structural translations of what the GBNF adapter already does. Rough
sizing: ~500 LoC per adapter (parser + IR builder + emitter + patterns),
plus ~200 LoC of cross-flavour test harness.

PEG is a legitimate future addition — lots of modern grammars are PEG —
but it requires the IR to grow a new atom variant (`OrderedChoiceAtom`)
and a Parser choice (Lark Earley doesn't model PEG semantics
faithfully). Defer until asked.

### 4.6 CLI implication

The `lexic init` / `lexic codegen` CLI (mentioned in the recommendations
doc as the "60 seconds to first parse" surface) needs a `--flavour` flag:

```
lexic codegen grammar.gbnf                          # auto-detected
lexic codegen grammar.abnf                          # auto-detected
lexic codegen spec.txt --flavour abnf               # explicit
lexic convert grammar.gbnf --to abnf > grammar.abnf # flavour translation
```

The `convert` subcommand is the flavour-translation entry point. It's
trivially implementable on top of adapters and shows the feature working
without requiring users to write any Python.

### 4.7 Sidecar flavour handling

The sidecar YAML from `LEXIC_GENERATED_CODE_PROPOSAL.md` §6.4 is
flavour-neutral by design — it references class names and field names, not
grammar syntax. This is correct and doesn't need changing.

One small addition: the sidecar may specify a `default_emission_flavour`
per project, so users of a third-party GBNF grammar who want their emitted
output to be ABNF can configure it once:

```yaml
# my_project.lexic.yaml
emission:
  default_flavour: abnf
classes:
  # ... existing rename entries
```

This is optional and has zero effect today (no non-GBNF flavours exist).
It exists to keep the sidecar semantics consistent once flavours arrive.

---

## 5. What this addendum does not decide

Three questions that are genuinely open and worth deferring:

- **Regex dialect escape hatch.** If a user absolutely needs `\b` or a
  lookahead, do we let them put raw regex into the pattern and lose
  cross-flavour portability? Probably yes, via an opt-in
  `StringConstraints(pattern=..., portable=False)` flag — but not today.
- **Whitespace-convention preference per user.** Some users will want ABNF
  output that uses explicit `SP` rules instead of implicit `c-wsp`. Not
  deciding this until there's a user with a real preference.
- **Handling of flavour-specific directives.** Lark's `%ignore`, ABNF's
  core rule imports, EBNF's comment syntax — each flavour has metadata
  that doesn't map to `RuleSpec`. Drop on parse, add on emit with defaults,
  document the loss. Not designing a metadata IR field today.

---

## 6. Prioritised summary

Things to do **now**, as part of the current refactor cycle, to preserve
the flavour-switching option:

1. Design `PatternAtom` with `source_forms: dict[str, str]` (§2.1, §4.1).
2. Add `flavour: str = "gbnf"` parameter to `codegen()` signature (accepts
   only `"gbnf"` today) (§3.3).
3. Rename `codegen/parser.py` → `codegen/gbnf/parser.py`, create
   `codegen/gbnf/__init__.py` with a `GbnfAdapter` bundling the existing
   parser + ir_builder + emitter (§3.3, §4.1).
4. Add `instance.to_grammar(flavour="gbnf")` method, keep `to_gbnf()` as
   an alias (§3.3).
5. Document the decorator DSL as "Lexic's internal grammar syntax, not
   literal GBNF" (§2.2).

Things to explicitly **not do now** but plan for:

- Implement ABNF or EBNF adapters.
- Add a regex-dialect translator.
- Ship a `lexic convert` CLI.
- Test cross-flavour round-trip properties.

Things to **commit to** about the feature when it does land:

- Three flavours at 1.0 (GBNF, ABNF, EBNF). PEG deferred.
- Flavour adapters are the only code that knows dialect specifics.
- Round-trip is semantic, not textual, when source and target flavours
  disagree on a convention (documented explicitly).
- The `@grammar_rule` decorator DSL never multiplies into dialect
  variants.

The cost of the "now" list is roughly a day. The cost of not doing it
grows every time a caller consumes the current `codegen()` or
`to_gbnf()` APIs.
