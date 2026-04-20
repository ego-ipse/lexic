# Lexic — Recommendations from the Structured-Output Landscape

Status: companion to `LEXIC_GENERATED_CODE_PROPOSAL.md`.

This document looks at what the major libraries in the structured-LLM-output
space have done well and badly, and distils the lessons for Lexic. The
libraries surveyed:

- **guidance** (Microsoft-backed, 21.4k stars) — interleaved Python + LLM
  control, grammar-level constraints.
- **llguidance** — guidance's Rust grammar backend, now the default in
  llama.cpp and SGLang.
- **Outlines** — type-driven constrained generation, Rust core (outlines-core).
- **Instructor** — Pydantic + automatic retries. ~3M monthly downloads,
  ~11k stars.
- **BAML** — DSL with Schema-Aligned Parsing, cross-language client codegen.
- **XGrammar** — default constrained-decoding backend for vLLM and SGLang.
- **pygbnf** — Python DSL for authoring GBNF grammars (tiny, single-author).
- **Lark** — the Python parser Lexic already uses for runtime parsing.
- **Pydantic** — the type/validation layer everything else is built on.

The goal isn't to clone any of them. It's to understand what works, what
hurts, and what Lexic should borrow, avoid, or deliberately invert.

---

## 1. Things to borrow

### 1.1 Instructor's "make it work in ten lines" DX

Instructor's appeal is that the first example is trivial: define a Pydantic
model, patch the client, get a typed object. Three million monthly downloads
happened because the learning curve starts at zero. The cost is pure
runtime (no static guarantees, no compile-time schema checking) and it
can't recover from markdown-wrapped JSON without a retry — but **the
ergonomic bar is real**.

**Apply to Lexic:** the top of the README must show a working parse in
~10 lines. "Write this Pydantic class, parse this text, call `to_text()`."
No mention of GBNF until the user actively wants to author a grammar. The
Pydantic-first path must be the first path.

### 1.2 BAML's Schema-Aligned Parsing as a philosophy

BAML's core insight is that LLMs emit messy output — markdown fences,
chain-of-thought preambles, trailing commas — and strict parsers choke.
Schema-Aligned Parsing recovers structured data even when the output is
syntactically wrong relative to the strict grammar. This is a different
problem from Lexic's (Lexic parses grammar-constrained output, not raw
LLM output), but the **philosophy of recovery-first parsing** transfers.

**Apply to Lexic:** when `parse()` fails, the error should not be "Lark
Earley failed at position 42." It should name the rule that didn't match,
the expected atoms, and the actual text fragment — in that order, in one
sentence. `parse()` should also accept a `strict=False` option that skips
leading whitespace and trailing garbage, because real inputs have both.

### 1.3 Outlines' type-driven surface

Outlines gets the API right at the top level: **the type IS the constraint**.
`Literal[...]`, Pydantic models, regexes — each of these is both "what I
want" and "how it's validated." No second language, no JSON schema to
hand-author. This is the pattern Lexic's proposal already leans on.

**Apply to Lexic:** double down. Every constraint a user can express with
`Annotated[str, StringConstraints(pattern=...)]`, `Literal[...]`,
`Discriminator(...)`, or a nested `GrammarModel` should be sufficient to
generate the grammar. A user should never need to open a `.gbnf` file
unless they want to. This is already the proposal's position; the lesson
is to resist every feature request that would break it.

### 1.4 llguidance's on-the-fly mask computation

Outlines pre-computes token masks for every automaton state, which is fast
at sampling time but incurs significant startup cost and memory. llguidance
computes masks on the fly, lazily builds lexer automata, and has
essentially zero startup cost. For interactive use — the developer
iterating on a grammar — startup cost dominates. This is why llguidance
became the backend for both llama.cpp and SGLang.

**Apply to Lexic:** R005, when it lands, should follow llguidance's
pattern, not Outlines' original pattern. Lazy state construction, on-the-fly
masking. The `CompiledGrammar` object from STRUCTURE.md goes in this
direction; the grammar-state oracle should inherit the same laziness.

### 1.5 BAML's "contract is a file" model

BAML's `.baml` files sit next to the code. They are the source of truth,
generated clients consume them. The upside: the contract is version-controlled,
reviewable, and language-independent. The downside: a build step.

**Apply to Lexic:** the sidecar YAML (§6.4 of the proposal) is this pattern
in miniature. Own it — a Lexic project has a `grammar.gbnf` and optionally
a `grammar.lexic.yaml` for naming. Both are version-controlled, both are
reviewable, neither is magic that lives in a decorator the reader can't see.

### 1.6 Outlines' Rust core, Python bindings

`outlines-core` separated the performance-critical algorithms from the
integration layer. The benefits: lighter dependency weight, better
performance for users who don't need the batteries-included bits,
potential bindings to other languages.

**Apply to Lexic (long-term):** the IR + emitters are pure Python and should
stay that way for now. But when/if Lexic gets a constraint oracle, that
piece is performance-critical and a natural candidate for Rust later. Write
it in Python first, measure, then port only the hot path. Do not rewrite
the codegen in Rust — that's where Python's introspection is genuinely
cheaper than the Rust alternative.

### 1.7 guidance's immutable model objects

guidance makes `Model` objects immutable. `lm += "foo"` returns a new model.
This is counterintuitive at first and extremely useful in practice —
branching generation, swapping contexts, undoing a step all become trivial.

**Apply to Lexic:** `GrammarModel` instances already benefit from Pydantic's
immutability-by-default behaviour. Lean on it. `instance.model_copy(update=...)`
should be the documented way to produce a modified version for round-trip
editing. Never add in-place mutation APIs.

### 1.8 Pydantic's discriminated union design

Pydantic's `Annotated[X | Y | Z, Discriminator(fn)]` pattern is exactly
what union-valued fields need. The discriminator is a function that
returns a string tag, and the tag maps to an arm. Clean, validated, no
guessing.

**Apply to Lexic:** mandatory for every union (proposal §7.6). Never emit a
bare `Union[A, B, C]` field. Users who construct from dicts will thank
the library when it raises a clear error instead of picking the first arm
that happens to validate.

### 1.9 Lark's tree-shaping philosophy

Lark's `?` rule prefix removes the rule from the tree if it has only one
child. Arrows (`-> alias_name`) rename parts of a rule. These are small
features with large ergonomic payoff: the user declares what shape they
want, Lark produces it. Filtering happens at declaration time, not in
post-processing visitor code.

**Apply to Lexic:** the sidecar's rename operations are the analogue, but
Lexic can go further. Add a sidecar directive that marks a rule as
"transparent" (its contents are promoted into the parent). This
eliminates most remaining synthetic helper classes without breaking
round-trip (the sidecar remembers the elision and re-inserts the
intermediate on emission).

---

## 2. Things to avoid

### 2.1 guidance's maintenance signal

guidance has 21.4k stars but a real community complaint: regressions in
new releases, slow bug fixes on core functionality, users pinning old
versions to avoid new bugs. A public GitHub discussion from users includes
the line *"I stopped using Guidance a while ago. Turns out, the number of
stars on GH doesn't mean much."* And from another: *"Sad but I'll stop
using it as well, I'm still using an even older version because of
'newly' introduced bugs."*

**Lesson for Lexic:** the community doesn't forgive regressions on core
operations. `parse`, `to_text`, `codegen` for the seven ground-truth
grammars must have property-based tests pinned hard and a commitment
that *nothing* ships if any of them regresses. Better to delay a release
than to ship a broken parse. The 312-tests-passing claim is worth
defending fiercely.

### 2.2 guidance's "monkeypatching the OpenAI SDK" critique

A blog post complains about Instructor: *"it's default behavior is to
monkey-patch the official OpenAI Python SDK... it can sometimes be
difficult to understand what it's doing under the hood — in some modes
it will even silently modify your prompts before passing it to the LLM."*
The same class of complaint applies to any library that does invisible
work.

**Lesson for Lexic:** no monkeypatching, ever. No modification of user
input strings before parsing. No implicit retries. No silent regeneration
of helper classes that the user deleted from their module. Every action
Lexic takes should be traceable to a line in the user's code or a line in
the user's sidecar. When in doubt, prefer a library that does less.

### 2.3 Outlines' hidden compilation cost

The original Outlines compiled the index with Numba, which JIT-compiled on
first run, *"adding a source of latency during the first run, which was a
source of frustration for many users."* This cost was low in production
(amortised across a deployment) but brutal during experimentation (felt
every time a user iterated on a grammar). The fix was `outlines-core` in
Rust, ahead-of-time compiled.

**Lesson for Lexic:** `parse()` currently regenerates the module on every
call (V3 §8). Fix this before users notice. Iteration tempo is the single
strongest predictor of whether a library gets adopted. A 200ms delay per
parse call during notebook exploration is the quiet killer. The
`CompiledGrammar` refactor in STRUCTURE.md addresses this; it's higher
priority than it looks.

### 2.4 Instructor's retry-and-hope

Instructor's automatic retries on validation failure are celebrated in
its docs and recognised as a weakness in critical reviews: *"The library
also can't fix fundamentally broken LLM outputs — if the model returns
markdown-wrapped JSON or chain-of-thought reasoning before the structured
response, Instructor's strict JSON parser will choke."* Retry papers over
missing constraint-level enforcement. It costs tokens. It hides bugs in
schema design. And it's fundamentally probabilistic — the retry might
succeed or it might not.

**Lesson for Lexic:** no retry loop in `parse()`. If parse fails, it
fails, and the error tells the user why. Retry is a policy that belongs
at the LLM-calling layer (if it belongs anywhere), not inside the parser.
The library's value proposition is deterministic round-trip; retries
undermine that.

### 2.5 BAML's build-step friction

BAML users report that getting started with the DSL and codegen pipeline
"adds a day" compared to Instructor's "under an hour." The DSL is
elegant, the cross-language codegen is genuinely valuable, but the
startup friction is real. Every user who abandons at install-time is a
user the library never gets.

**Lesson for Lexic:** offer both paths but keep the default on the fast
path. The Pydantic-first path (`pip install lexic && from lexic import ...`)
should require no build step, no sidecar, no codegen. The GBNF-first path
(existing grammars, `codegen arithmetic.gbnf`) is for users who already
know they want it. A user should be able to evaluate Lexic's core promise
inside a Jupyter notebook in 30 seconds.

### 2.6 guidance's "everything must interleave with Python" paradigm

guidance's core paradigm — prompts, constraints, and Python all braided
together — is genuinely novel and hard to give up once you're used to it.
But it's also the hardest thing to explain, the hardest thing to debug
(what's a `Model` object, why does `+=` work, why does `with user():`
have a context manager?), and the reason guidance has "interleaved control
flow" problems that show up as cryptic errors deep in its call stack.

**Lesson for Lexic:** do not invent a new programming model. `parse()`
takes a string and returns an instance. `instance.to_text()` returns a
string. `Cls(...)` constructs an instance. There is no DSL, no context
manager, no `with` block, no custom `__add__`. The library's surface is
boring Python functions and boring Pydantic classes. Boring is the
feature.

### 2.7 Lark's auto-filtering default

Lark automatically filters out string literals from the parse tree unless
named with an arrow. This is convenient until it isn't — you lose `"true"`
and `"false"` from your JSON parse tree and have to add arrows to recover
them. The documentation admits this: *"Unfortunately, this means that it
will also filter out literals like 'true' and 'false', and we will lose
that information."*

**Lesson for Lexic:** no invisible filtering. If a literal exists in the
grammar, it exists in the parsed instance's `_raw`. If it doesn't, the
user can see why by looking at `__grammar__.items`. The proposal's `_raw`
mechanism (§9) does this honestly. Resist every temptation to "clean up"
the parse output behind the user's back — it will bite someone on a
grammar the library didn't anticipate.

### 2.8 pygbnf's single-author fragility

pygbnf is nice, focused, and has exactly one contributor and two stars.
It will work today and may be unmaintained in a year. Every library in
this space that doesn't get community traction ends up in this state.

**Lesson for Lexic:** be realistic. Lexic is a single-owner project
today. Two things protect against the pygbnf outcome: (a) keep the
surface small so it can be maintained part-time, (b) make the IR and
generated code so clean that users who want to fork or contribute can do
so without understanding the whole system. STYLE.md is pointing the right
direction; STRUCTURE.md's "each module <200 lines" discipline is what
keeps the bus factor above 1.

### 2.9 Pydantic's recursive-forward-ref edge cases

Pydantic has genuine bugs and rough edges around recursive forward
references — infinite recursion on creation, `update_forward_refs()` /
`model_rebuild()` timing issues, cases that only work "slightly by
accident." Users hit these constantly. The generated code from Lexic
currently has 12 lines of forward-ref resolution per module; each of
those is a possible failure point.

**Lesson for Lexic:** the decorator-based class construction in the
proposal owns forward-ref resolution exactly once, in `grammar_rule`.
Use `model_rebuild` with `_types_namespace` explicitly and test
round-trip on all seven ground-truth grammars plus a pathological
synthetic one with mutually-recursive rules. Document the Pydantic
versions known to work; pin the minimum. Forward refs will be the #1
source of "Lexic is broken on my grammar" reports from strangers.

### 2.10 The "too many ways to do it" trap

The LLM structured-output ecosystem has at least 8–10 overlapping
libraries, each with its own idioms and cargo-cult best practices.
Users are tired. A TechSy comparison opens with the observation that
Instructor's biggest asset is *"fastest time-to-working-code"* —
not any feature, but the lack of competing options.

**Lesson for Lexic:** one way to do it, for each task. One decorator
(`@grammar_rule`), one parse function (`parse`), one emit method
(`to_text`), one grammar-reconstruction method (`to_gbnf`), one
translation entry point (`translate`). No alternate APIs, no legacy
shims, no "simpler subset" wrappers. If a user asks "should I use
`generate()` or `parse_and_generate()`", the library has already failed.

---

## 3. Category-specific recommendations

### 3.1 What to do about R005 (constrained generation)

The research makes it clear: **Lexic should not build its own
constrained-decoding engine**. guidance, llguidance, Outlines, XGrammar,
and llama.cpp's native GBNF all already do this, competing on μs-per-token.
Lexic will lose that race by several orders of magnitude.

The defensible play: **Lexic's grammar compiles to the formats those
engines already consume**. The `to_gbnf()` path is the interface. Users
feed the emitted GBNF to llama.cpp / llguidance / guidance's backend, get
text back, feed it to `parse()`. Lexic contributes the typed Pydantic
layer and the round-trip; the engines contribute token masking.

Treat R005 as "emit GBNF, consume text," not "own the token loop."

A later extension could add an `outlines` or `llguidance` adapter in a
separate `lexic-constrain` package, kept strictly optional.

### 3.2 What to do about R006 (cross-grammar translation)

No library in the survey does this. It's Lexic's unique contribution.
But: **the closest prior art is BAML's cross-language codegen**, which
is an emission problem, not a translation problem. BAML emits the same
schema as Python, TypeScript, Go, Ruby — no runtime data translation
involved.

Lexic's R006 is harder: runtime translation of *data* between grammars.
The honest scope limits:

- **Translation works when grammars agree on semantics.** Two JSON dialects
  → trivial. A Markdown list ↔ a JSON array → feasible with annotations.
  A chess game ↔ a SQL query → not a thing. The library should refuse
  translations that don't structurally align, with clear diagnostics.
- **Annotations are the alignment mechanism.** Without per-field
  `# @semantic=kind` or sidecar `translation:` entries, the library has
  only structural shape to go on. Structural-shape matching works for
  JSON dialects; it fails the moment field orders differ meaningfully.
- **Round-trip only, not lossy conversion.** Translating `{"name":"x"}`
  to YAML and back must produce `{"name":"x"}`. If this is violated, the
  library is worse than regex-and-print. This is the acceptance test.

### 3.3 What to do about error messages

Every library in the space loses users to bad errors. guidance's
interleaved control flow produces errors deep in stack frames. Outlines'
early versions produced opaque "compilation failed" errors. Pydantic's
recursive-ref errors are famous for being unhelpful. Lark's parser errors
mention positions but not rules.

**Lexic's error surface must treat errors as a product feature.** Three
concrete rules:

- **Parse errors name the rule, not the position first.** "Expected
  `expression` after `=` at line 3" beats "UnexpectedToken at col 42."
- **Validation errors name the field path plus the constraint.**
  "`Number.integer_part`: pattern `^(0|[1-9][0-9]{0,15})$` did not match
  input `'007'`" beats "ValidationError on Number."
- **Grammar-authoring errors quote the `@grammar_rule` fragment that failed.**
  "In `@grammar_rule('expr "=" missing_field')`: 'missing_field' does not
  appear in class Assignment's fields. Did you mean 'result'?"

Error quality is where small libraries can beat 21k-star libraries.
Invest early.

### 3.4 What to do about documentation

Instructor's DX win is largely documentation. BAML's adoption story
turned on a working browser-based playground. Outlines ships with
notebooks. guidance's README has Jupyter widget screenshots.

Lexic's documentation strategy:

- **First page is a 10-line example of the Pydantic-first path.** Not
  "here's what GBNF is." That's page five.
- **Seven ground-truth grammars become seven documented examples** — parse a
  chess game, parse JSON, parse a markdown list. Each with round-trip
  demonstrated, each with a CLI invocation.
- **A `lexic init arithmetic` command scaffolds a starter project** with the
  grammar, the generated module, the sidecar, and a test file. Time from
  `pip install` to "I see something parse" should be under 60 seconds.
- **The sidecar format is documented as first-class**, not a footnote.
  Include a cookbook of common sidecar operations (rename, flatten,
  opt-into-Literal, mark-transparent).

---

## 4. Features to explicitly reject

These are things other libraries do that Lexic should *not* do:

- **Custom prompt DSLs embedded in the library.** BAML does this well
  because it's BAML's whole product. Lexic is not a prompting library.
  Users bring their own prompts.
- **Automatic LLM retry loops.** Instructor's signature feature; a leaky
  abstraction and a token-cost trap. If users want retries, they can
  wrap `parse()` themselves.
- **Visual playgrounds / notebook widgets.** BAML and guidance both have
  these; they are substantial maintenance burden and they don't help
  Lexic's differentiated use cases (parsing and round-trip, not
  generation).
- **Cross-language client codegen.** BAML's headline feature; it requires
  Lexic to own a TypeScript/Go/Ruby runtime each, which is not feasible
  for a single-maintainer project. Stay Python-only.
- **Schema-Aligned Parsing (recovering from messy LLM output).** Lexic
  parses grammar-valid text, not garbage. Users who need SAP use BAML
  before Lexic, then feed the cleaned output to Lexic for round-trip.
- **A builder-pattern grammar DSL.** pygbnf's `select([...]) + one_or_more(...)`
  style is elegant but it's a competing surface to the Pydantic-first
  path and to the GBNF text path. Two paths are enough.
- **Function-calling / tool-use primitives.** pygbnf ships a `Toolkit`
  class; guidance has tool use baked in. Lexic is downstream of whatever
  produced the text — tool-calling belongs with the LLM client.
- **Streaming as a first-class API.** BAML's semantic streaming is a
  genuine innovation for LLM UX. Lexic parses finished strings. When
  streaming lands as a requirement, it should be a separate package that
  produces Lexic instances at end-of-stream.

---

## 5. Priority ordering

Against the proposal in `LEXIC_GENERATED_CODE_PROPOSAL.md` and STRUCTURE.md,
the research suggests this ranking:

**Tier 1 — ship before anything else.**

- **IR atom collapse** (proposal §5.5). The single refactor that most
  simplifies everything downstream.
- **`CompiledGrammar` / memoised parse** (STRUCTURE.md §4, V3 §8). The
  startup-cost issue Outlines learned about the hard way.
- **Error messages** (§3.3 above). Addresses the most common adoption
  blocker in this space.

**Tier 2 — required before public release.**

- **Pydantic-first decorator + single-file generated modules**
  (proposal §2–§4). Without this, Lexic's DX is behind Instructor's.
- **Four-tier naming cascade** (proposal §6). Without this, generated
  code is unreadable on real grammars.
- **Sidecar parser** (proposal §6.4). The escape hatch that makes Lexic
  useful on third-party grammars.
- **Discriminator synthesis** (proposal §7.6). Needed for translation and
  for Pydantic-first construction.

**Tier 3 — enables R006.**

- **Semantic annotations + structural fallback for `translate()`**.
  Structural shape matching for easy cases, annotations for semantic
  alignment, refusal-with-diagnostic for incompatible grammars.

**Tier 4 — deliberately deferred.**

- **R005 constraint oracle.** Ship the `to_gbnf()` path first and let
  users wire up llguidance / llama.cpp themselves. Revisit when there's
  a concrete user need the existing engines don't serve.
- **Rust core.** Only after profiling reveals a real bottleneck on real
  grammars at real scale. Python-first.

---

## 6. One-sentence heuristics

Summarising:

- **Make the Pydantic-first path zero-friction; make the GBNF path
  opt-in.**
- **Never do invisible work on behalf of the user.**
- **Errors are a product feature; invest early.**
- **Compose with existing constraint engines, don't replace them.**
- **Regressions on the seven ground-truth grammars are release-blocking.**
- **One way to do each task.**
- **Boring Python, not a custom programming model.**
- **Round-trip fidelity is the product; retries and SAP aren't.**
