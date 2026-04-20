# Lexic — Addendum: Tokeniser Tokens in GBNF

**Status:** addendum to `LEXIC_FLAVOUR_ADDENDUM.md` and the prior
documents.

Scope: the GBNF "Tokens" feature (`<think>`, `<[1000]>`, `!<think>`,
`!<[1001]>`) has implications for the IR, the flavour design, and the
Pydantic generated code. Nothing is being built now — this document
reserves the design space and names the decisions that have to happen
before any implementation work begins.

---

## 1. What GBNF tokens actually are

From the GBNF README:

> Tokens allow grammars to match specific tokenizer tokens rather than
> character sequences. This is useful for constraining outputs based on
> special tokens (like `<think>` or `</think>`).

Syntactically, the outer `<` and `>` are delimiters — not part of the
matched text. The content between them names the token. This is
spelled out unambiguously in the llguidance grammar spec (the syntax
llama.cpp's `<...>` token feature borrows from):

> Special tokens can [be] referenced via `<token_name>` syntax
> (i.e., any string between `<` and `>`), for example `<|ENDOFTEXT|>`.

So:

- `<think>` — match the tokeniser token whose canonical name is
  `think`. Fails to parse if `think` is not exactly one token in the
  active vocabulary.
- `<|ENDOFTEXT|>` — match the token whose canonical name is
  `|ENDOFTEXT|`. (Most modern tokenisers use pipe-bracket-wrapping for
  their special tokens — `|name|` — precisely to keep their canonical
  names from colliding with the outer `<...>` delimiters.)
- `<[1000]>` — match tokeniser token with ID 1000
  (vocabulary-specific).
- `!<think>` / `!<[1001]>` — match *any* token except the named one.
- Often used as quantified atoms: `!</think>*` for "any sequence of
  tokens until you hit the token named `/think`."

The GBNF README's own wording (*"`<think>` will match the token whose
text is exactly `<think>`"*) is misleading. What the author meant is
that reasoning-model tokenisers do commonly register a token whose
canonical name happens to be the string `think` — and in a grammar
*you* write `<think>` to reference it. The outer angles are syntax;
the inner `think` is the name.

The distinguishing property: **these atoms operate at the token level,
not the character level**. Semantically they are specific to the
tokeniser being used at generation time. A grammar using `<think>`
binds to whatever vocabulary is active when llama.cpp evaluates it.

---

## 2. Why this is structurally different from everything else

Every other GBNF construct reduces to "match this character sequence."
Character ranges, literals, quantifiers, alternations — all character-level.
The IR, the Lark runtime, Pydantic validation, `to_text()` round-trip:
all assume character-level semantics.

Tokens break that assumption in four places:

### 2.1 Portability across consumers

A grammar using character ranges parses the same text regardless of which
LLM emitted it. A grammar using `<think>` parses meaningfully only
against the tokeniser that defines `<think>` as a single vocabulary
entry. The same `.gbnf` file could parse differently (or fail to parse)
with a different model's tokeniser.

This is actually consistent with GBNF's role as a constrained-decoding
format. It is **not** consistent with Lexic's role as a text↔Pydantic
round-trip layer, where parsing is expected to be deterministic from
text alone.

### 2.2 Portability across flavours

None of the other flavours Lexic plans to support (ABNF, EBNF, Lark,
PEG) have tokeniser-token constructs. They're all character-level
formalisms. Emitting GBNF-with-tokens to ABNF requires a choice:

- Expand the token to its literal string (`<think>` → `"<think>"` as an
  ABNF literal). Loses the "exactly one vocabulary token" guarantee, but
  the ABNF grammar still describes the same language at the character
  level.
- Refuse emission with a diagnostic. Honest but limits translation.

The choice probably differs per target: expand-and-warn when emitting
character-level flavours, refuse when emitting to another tokeniser-aware
format (none exist today, but the placeholder matters).

### 2.3 Pydantic representation

A Pydantic field of type `Literal["think"]` captures "the value is
exactly the string `think`." It does not capture "this string was
produced as a single token in a specific vocabulary." There is no clean
type-level representation of the tokeniser-token constraint.

This is fine for round-trip: parse produces `"think"` as a string, emit
reproduces `"think"` as a string. But it means Lexic cannot *validate*
at Pydantic-construction time that the user-supplied value would actually
tokenise as a single token — that validation requires the tokeniser, which
Lexic doesn't have in scope.

### 2.4 The `!` negation operator

Character-level negation exists (`[^\n]` is "any character except
newline"). Token-level negation (`!<think>` meaning "any token except
the one named `think`") is structurally different: it requires
iterating the full vocabulary and subtracting. At emission time into a
character-level flavour, `!<think>` roughly corresponds to "any string
of characters that doesn't match the canonical text of the named token,"
which is expressible as a regex but is not the same constraint — the
token-level version excludes precisely one vocabulary entry, while the
character-level version excludes any string that matches.

---

## 3. The three design decisions that have to be made

These don't need to be made today — but when the tokens feature is
implemented, these are the choice points that shape the rest of the
design.

### 3.1 Does the IR have a first-class `TokenAtom`?

**Option A — add `TokenAtom` to the IR.**

```python
@dataclass
class TokenAtom:
    """Match a specific tokeniser token.

    Either `name` or `token_id` is set, never both.
    `name` is the token's canonical name — the string inside the
    outer `<...>` delimiters of the GBNF syntax. For `<|endoftext|>`
    it is `"|endoftext|"`; for `<think>` it is `"think"`.
    `negate=True` means match any token except this one.
    """
    name: str | None
    token_id: int | None
    negate: bool
    min: int
    max: int | None
```

Pros: explicit IR representation, clean dispatch in emitters, consistent
with the existing atom-type pattern.

Cons: adds a sixth atom type to a proposal that just collapsed seven into
five (`LEXIC_GENERATED_CODE_PROPOSAL.md` §5.5). Most Lexic use cases don't
need tokens, so every atom consumer now has to either handle or explicitly
reject `TokenAtom`.

**Option B — represent tokens as a special-form `PatternAtom` with a
source-form annotation.**

```python
PatternAtom(
    regex=r"^think$",                  # what it means at char level
    source_forms={"gbnf": "<think>"},  # the token-reference syntax
    min=1, max=1,
    tags={"gbnf:token"},               # marker so emitters know
)
```

Pros: no new atom type. The regex-level behaviour is correct at the
character level (it matches the string `think`). GBNF emitter reads
the tag and emits the token-reference syntax; other flavours emit the
plain regex form.

Cons: the "one token in the vocabulary" semantics is encoded only as a
tag, not as a type. Easy to lose during transformations. Conflates "this
is a character pattern" with "this is a token reference."

**Option C — reject tokens from the IR entirely. Parsers that encounter
them raise `UnsupportedConstructError`.**

Pros: simplest. Keeps Lexic focused on the character-level use case,
which is what the round-trip story is about.

Cons: Lexic can no longer parse GBNF grammars that llama.cpp users have
written with tokens. Breaks the "Lexic handles any GBNF grammar" promise.

**Leaning:** Option A, but only when tokens are actually implemented.
Until then, parsers should raise a specific error on encountering `<...>`
syntax (Option C as a placeholder), so that ambiguity doesn't accumulate
silently. When Option A lands, the error turns into a working code path.

### 3.2 What's the Pydantic type for a token-constrained field?

A GBNF rule `root ::= <think> body </think>` has three components. In the
Pydantic generated code:

**Proposal:** `TokenAtom` generates `Annotated[str, TokenConstraint(name="think")]`
where `TokenConstraint` is a Lexic-defined Pydantic validator marker.
The `name` parameter is the token's canonical name — the inner content
of the `<...>` delimiters.

```python
from lexic import TokenConstraint

@grammar_rule('think body end_think')
class Thought(GrammarModel):
    think:      Annotated[str, TokenConstraint(name="think")]
    body:       str
    end_think:  Annotated[str, TokenConstraint(name="/think")]
```

At runtime, `instance.think` holds the string `"think"` (the token's
canonical name). Without a tokeniser, `TokenConstraint` validates only
the string-equality part ("value must equal `think`"). Users who want
full token-level validation supply a tokeniser at construction time:

```python
instance = Thought.model_validate(data, context={"tokeniser": my_tokeniser})
```

When a tokeniser is supplied, the constraint also verifies that the value
tokenises to exactly one token (or to the named ID). When none is
supplied, the constraint degrades gracefully to string equality.

This preserves Lexic's no-dependency philosophy — we don't import a
tokeniser — while giving users who have one a hook to opt into stronger
validation.

For the ID form, use `TokenConstraint(token_id=1000)` instead of `name`.
Exactly one of the two must be set. Lexic should also support
`TokenConstraint(name="think", negate=True)` to model `!<think>` — the
field then accepts any token-name string *except* the named one
(validated fully only when a tokeniser is supplied).

### 3.3 What does `to_text()` emit for token atoms?

Three sub-options:

- **Emit the token's canonical name as a bare string.** A `Thought`
  instance with `think="think"`, `body="…"`, `end_think="/think"`
  would round-trip to the string `"think…/think"`. This is the "pure
  character-level" emission and is honest about what the atom carried.
  Without more context, nothing in the emitted string signals that
  those fragments were originally token references.
- **Emit the token in GBNF reference syntax.** `<think>…</think>`.
  This is what a user who parsed a GBNF grammar, built an instance,
  and called `to_text()` typically expects — round-trip fidelity with
  the original grammar's textual form. But it's only meaningful when
  the consumer of the output is also GBNF-aware.
- **Require the caller to supply a tokeniser.** `instance.to_text(tokeniser=...)`
  either returns text (if the tokeniser encodes each named token back
  to its canonical string) or returns a token-ID stream via a separate
  method.

**Leaning:** emit in GBNF reference syntax (`<think>…</think>`) by
default *when the grammar was parsed from GBNF*, preserving textual
round-trip. Expose `to_tokens(tokeniser)` returning `list[int]` as the
separate method for users who need the token-ID form. Lexic's default
round-trip stays string-level; token-level output is a specialisation
for users who need it.

The bare-string option is useful for cross-flavour translation, where
the target flavour doesn't have `<...>` syntax — in that case the
character-level regex is what gets emitted.

### 3.4 The angle-bracket ambiguity, and when the ID form is required

The GBNF string-form syntax `<name>` works cleanly when the token's
canonical name contains no `<` or `>` characters. `<think>`, `<|endoftext|>`,
`<start_header_id>`, and `<|channel|>` are all unambiguous because the
parser can identify the outer `<` and matching `>` and strip them.

**It breaks when a token's canonical name itself contains `<` or `>`.**
Imagine a tokeniser that registers a literal token named `<think>`
(brackets included in the canonical name). To reference it in GBNF
string form, a user would have to write `<<think>>`, and the GBNF
parser has no documented escape mechanism for the inner brackets. The
parse becomes ambiguous:

- Is `<<think>>` a reference to a token named `<think>`?
- Or is it a reference to a token named `<think` followed by a `>`?
- Or a reference to `<` followed by `think>`?

The GBNF spec does not resolve this. llama.cpp's current parser
behaviour in this case is implementation-defined and shouldn't be
relied on.

**The ID form `<[N]>` is the unambiguous escape hatch.** The inner
content is always `[` + integer + `]`, which cannot be confused with a
name containing angle brackets. The llguidance spec extends this with
range and negation syntax (`<[128000-128255]>`, `<[^128000]>`,
`<[*]>`), all of which remain unambiguous because they're integer-only
inside the outer delimiters.

**Lexic's rule for the GBNF parser:**

- Accept string-form `<name>` only when `name` contains no `<` or `>`.
- When the parser encounters a string-form token reference whose inner
  content contains `<` or `>`, raise `TokenAmbiguityError` with a
  message naming the token and recommending the ID form: *"Token
  reference `<<think>>` contains angle brackets in the token name,
  which creates parsing ambiguity. Use the ID form `<[N]>` where N is
  the numeric token ID, which can be looked up with your tokeniser's
  vocabulary API."*
- Accept ID-form `<[N]>` unconditionally. Also accept range syntax
  `<[M-N]>` and the negation forms `<[^...]>` at the parser level; whether
  the IR supports them is a separate decision (see §3.1).

This is a limitation of the GBNF specification, not of Lexic. Real-world
grammars sidestep the issue by convention — tokenisers pipe-bracket-wrap
their special-token names (`|endoftext|`, `|channel|`, `|message|`)
precisely so the names don't collide with the outer `<>` delimiters.
For the rare case where a token's canonical name does contain angle
brackets, the ID form is the correct and only reliable way to reference
it.

---

## 4. Overrides to prior documents

### 4.1 Override to `LEXIC_GENERATED_CODE_PROPOSAL.md` §5.5

The IR atom collapse now leaves open the possibility of a **sixth atom
type** (`TokenAtom`), deferred. The collapse still produces five atom
types for all non-token grammars. Atom consumers must be written to
dispatch on atom type via a dictionary (as already recommended in
`OPUS_REVIEW_V3.md` §1) so that adding `TokenAtom` later is additive, not
a refactor.

### 4.2 Override to `LEXIC_FLAVOUR_ADDENDUM.md` §4.1

The flavour adapter contract implicitly assumed all flavours produce the
same five-atom IR. **Extend:** the `RuleSpec` IR must be capable of
carrying atom types that not all flavours can emit. Specifically,
`TokenAtom` is GBNF-only. Other flavours' emitters must either:

- lower `TokenAtom` to an approximate character-level pattern at
  emission time (with a documented loss of the "exactly one token"
  guarantee), or
- raise `UnsupportedConstructError` when asked to emit a grammar
  containing `TokenAtom` entries.

Per-flavour adapter documentation must state which strategy it takes for
each IR atom type it cannot express natively. The default for ABNF, EBNF,
and Lark is lower-with-warning; users can request strict-refusal mode via
a parameter.

### 4.3 Override to `LEXIC_FLAVOUR_ADDENDUM.md` §4.2

The regex-dialect boundary (§4.2 of the flavour addendum) does not apply
to `TokenAtom`. Tokens are not regex patterns. When the tokens feature
ships, the adapter layer needs a second dialect-translation track for
token representations specifically. GBNF has two token syntaxes (`<text>`
and `<[id]>`); if another tokeniser-aware flavour ever gets added, each
will have its own. Keep the design open.

### 4.4 Override to `LEXIC_FLAVOUR_ADDENDUM.md` §4.3

Cross-flavour round-trip properties (§4.4) gain an asterisk: property
**1 (semantic round-trip)** and property **3 (data round-trip across
flavours)** assume all atoms involved can be expressed in both source and
target flavours. Grammars containing `TokenAtom` break this assumption
when translated to non-GBNF flavours. The test harness must either:

- exclude token-bearing grammars from cross-flavour round-trip tests, or
- assert the weaker property "cross-flavour translation succeeds up to
  the token-level loss documented in §4.2 of this addendum."

Either is acceptable; pick and document.

### 4.5 Override to `LEXIC_ECOSYSTEM_RECOMMENDATIONS.md` §3.1

The ecosystem doc said R005 (constrained generation) should be treated as
"emit GBNF, consume text," with Lexic not owning the token loop. Tokens
in GBNF strengthen this recommendation: **the tokens feature is precisely
where Lexic would otherwise need to own tokeniser integration**, which
would pull Lexic into model-specific territory that's the domain of
guidance, llguidance, XGrammar, and llama.cpp.

Stay out of it. `<think>` atoms parse through Lexic as string-level
literals; the token-level semantics are the responsibility of the
constrained-decoding engine downstream.

---

## 5. Things to do now, even without implementation

Four small decisions that keep the design open:

1. **Reserve the `<...>` syntax in the GBNF parser.** Today, encountering
   `<think>`, `<|endoftext|>`, `<[1000]>`, or their negated forms
   should raise a specific `UnsupportedConstructError` naming the
   feature and pointing at this addendum. Don't silently pass through
   or fall into a generic parse error — either makes the feature
   harder to add later. When the feature is implemented, the same
   parser must also detect the angle-bracket-ambiguity case (§3.4)
   and raise `TokenAmbiguityError` pointing at the ID-form workaround.

2. **Reserve an atom-type slot in the IR.** The atom union (five types
   post-collapse) should be documented as "closed but versioned": adding a
   sixth atom type is a minor version bump, breaking nothing that consumes
   the existing five. Every dispatch table (emitters, generator,
   transformer) should have an explicit `default` branch that raises
   with "unsupported atom type" rather than silently skipping.

3. **Document the non-support in user-facing docs.** "GBNF token
   constructs (`<name>`, `<[1000]>`, `!<name>`, `!<[1000]>`) are not
   yet supported; Lexic raises on grammars containing them." Users
   deserve to know, especially users bringing grammars from llama.cpp
   that might use this feature.

4. **Don't add a tokeniser dependency.** No `pip install tokenizers` or
   `pip install transformers`. When tokens ship, the design is "supply a
   tokeniser via validation context." Lexic never imports one.

---

## 6. What's out of scope even when tokens are implemented

- **Token-aware constrained generation.** Lexic's role stops at parsing
  and emitting grammars. The engine that enforces "token must be one of
  N" during generation is llama.cpp / llguidance / guidance / XGrammar.
  Lexic never masks logits, never hooks into a sampler.
- **Tokeniser-specific test fixtures in the core library.** Vocabulary
  files are large and licensing-complicated. Any tokeniser-dependent
  tests live in a separate `lexic-tokens-test` package that users opt
  into; the core library's test suite never imports a tokeniser.
- **Converting text to tokens in `to_text()`.** `to_text()` returns
  strings; `to_tokens(tokeniser)` returns integer lists. Two methods, two
  contracts, no conflation.

---

## 7. Summary

The GBNF tokens feature is not trivially bolted onto a character-level
grammar tool, and it's not portable across the flavours the previous
addendum opens the door to. The right move is:

- **Recognise tokens as a separate axis** from character-level grammar —
  they're tokeniser-bound, not flavour-bound.
- **Read the syntax correctly.** The outer `<` and `>` in `<n>` are
  delimiters; the inner text is the token's canonical name. The same
  applies to the ID form `<[N]>`. The GBNF README example wording is
  misleading; the llguidance spec is the authoritative reference.
- **Reserve the IR slot and parser syntax now** (raising on unsupported
  input), implement the atom type later when there's demand.
- **Require the ID form for tokens whose canonical name contains `<`
  or `>`.** This is the only reliable way to reference such tokens;
  the string form is genuinely ambiguous and Lexic raises rather than
  guess.
- **Keep the tokeniser dependency out of Lexic's core.** Users who need
  full token-level validation supply one via Pydantic validation
  context.
- **Make non-GBNF emitters either lower-with-warning or refuse** when
  they encounter tokens in the IR. Configurable per adapter.

Deferring implementation is correct. Not naming the design surface is
not — the choices above need to be made before the IR atom collapse
lands, so that the atom-type enum is extensible-in-one-direction rather
than frozen-at-five.
