# Token support

Grammars can match tokenizer **tokens** instead of characters — the README
§Tokens surface: `<think>` (text-form), `<[1000]>` (id-form), `!<…>` (negation),
`.` (any). Token support is **additive**: a grammar with no token terminal
parses and emits byte-identically to before, and the engine coupling to a
tokenizer is exactly three calls — `boundaries` + `spell` + `decode.keys()`.

## The encoding model (`ir/encoding.py`)

A char class is a set of **ordinals**; an `IrEncoding` is what those ordinals
mean — `universe` (the `.`/complement ceiling), `resolve` (a spelling → an
ordinal), `spell` (an ordinal → its spelling). The universe-relative complement
algebra is shared on the role marker; concrete encodings supply the codec.

- **`IrUnicode`** (singleton, the default) — ordinals ARE Unicode code points;
  codec is `ord`/`chr`. Escape spelling is layered on at emit by the flavour, not
  the encoding.
- **`IrTokenizer(name, encode, decode, merges, specials)`** — ordinals are vocab
  ids. `encode` is spelling→id, `decode` the derived inverse (O(1) `spell`).
  `merges` is the ordered rewrite model: an `IrTuple` of `IrTuple(left, right)`
  dyads whose **position is the merge rank** (an `IrMap` would reorder by repr).
  `specials` is the atomic-match set (HF's `added_tokens`): an `IrTuple` of `IrStr`
  spellings matched **whole**, before the rewrite, so a special like `<think>` is
  one token even amid BPE content. Empty `merges`/`specials` (elided from repr) ⇒
  a vocab-only tokenizer; merges ⇒ merge-based. Built from a Mapping via
  `from_vocab` / `from_merges` (each takes optional `specials`), both funnelling
  through one `_build` (coerces `name`, derives `decode`, validates specials ⊆
  vocab). No custom `__new__` — the record is the plain positional constructor.

`IrUnicode` and `IrTokenizer` are **peers** — everything UTF-specific is an
`IrUnicode` property, never hard-coded in the set-math. A registry is just an
`IrMap[IrStr, IrEncoding]`; no bespoke class.

### Segmentation is intrinsic and data-driven

`IrTokenizer.boundaries(text) -> [(char_start, char_end, id)]` picks its
algorithm from its own data (the `IrCharClass.complement` precedent). `specials`
(if any) are matched atomically first (longest-first), then each gap runs the
vocab model:

- **no merges** → deterministic **longest-match** over the vocab;
- **merges present** → the **ranked-merge rewrite** — the reference BPE
  algorithm, exact: from single-char symbols, repeatedly apply the lowest-rank
  adjacent merge (leftmost) to fixpoint, over the derived `ranks: IrMap`, with no
  hard-coded tables. Char-offset spans are tracked through the merges.

A position covered by no vocab token yields no token-match point (the
unsegmentable / mid-multibyte case). `tokenize` is the id sequence of the spans.

**Byte-level is deferred.** A complete byte-level model segments at byte
granularity (a codepoint can split across tokens), so `boundaries` would return
byte offsets — conflicting with the fixed char-column engine coupling. It is a
byte-column engine effort (expressed IR-natively as a remap `IrMap` when built),
not a char-level fake. The merge model already IS a real BPE tokenizer.

## The binding atom — `IrAlphabet` (`ir/nodes.py`)

`IrAlphabet(encoding_name, inner_atom)` scopes a pure inner atom to an encoding
by **name**: `IrAlphabet("tokens", IrLiteral("<think>"))` is the token whose text
is `<think>`; `IrAlphabet("tokens", IrCharClass(IrChr(1000)))` is id 1000.
Negation lives **inside** the alphabet — `IrAlphabet(enc, IrNot(inner))` — reusing
the ordinary `IrLiteral`/`IrCharClass`/`IrNot` leaves, so there is **no
token-specific leaf**. `canonicalize` fences `IrAlphabet` from the UTF passes.

`concretize(ast, registry)` resolves each alphabet's spelling to an ordinal at
compile — `IrLiteral("<think>")` → `IrCharClass(IrChr(id))` via the named
encoding's `resolve`; the id-form is validated in-universe; negation composes.

## The compile surface (`compile/__init__.py`)

`compile_text(text, *, tokenizer=None, registry=None)`:

- `registry: IrMap[IrStr, IrEncoding]` binds the grammar's encoding **names** to
  encodings (`unicode` always present) — the general form. The registry key is the
  name the grammar uses, decoupled from the tokenizer's own `.name`.
- `tokenizer=` is **sugar** for a one-entry registry (the tokenizer under its own
  `name`). Passing both refuses (ambiguous).
- The instance-**segmentation** tokenizer is derived as the registry's sole
  `IrTokenizer` (`unicode` never segments); zero or multiple ⇒ no auto
  segmentation (a char grammar, or a compile-only multi-encoding binding).

`CompiledGrammar.tokenizer` is that segmentation tokenizer. `.parse(text)` routes
a token grammar through `token_model` (lexic segments with its own tokenizer,
each token terminal matches id-granular); a char grammar goes through
`parse_model`. `.constrain()` returns the mask cursor (below).

## The engines (`parsing/earley/`)

- **`TokenKernel`** (`tokenscan.py`) — the single token-matching engine: a Kernel
  subclass parsing a token grammar against text lexic has segmented, via a bounds
  map (char pos → (id, len)) + per-term id-sets read off the `IrAlphabet` terms
  (negation read from the `IrNot` inside) and one atomic-token `_scan` branch. The
  base char Kernel is untouched; **token rules island the PDA** — the Earley token
  product is the whole parse (the char PDA never matches tokens).
- **`TokenMaskCursor`** (`tokenscan.py`) — capability C, the generation cursor:
  `constrain()` → `mask()` / `push(id)` / `accepts()`. Two modes, by grammar kind:
  - **token grammar** (`IrAlphabet` terms): the mask reads the admissible ids off
    the frontier column's live token-terms (token-frontier set algebra).
  - **char grammar** (no token terms): the **char-heavy** mask — a token is
    admissible iff `prefix+spell(token)` stays a **viable prefix** of the
    char grammar (`viable_prefix`: `accept ≥ 0`, or a frontier item still faces a
    symbol). The recognizer runs char-granular (`split_literals` splits merged
    multi-char literals so a mid-literal prefix advances). Complete **and** sound —
    a differential test pins it to a brute-force oracle. It reparses per candidate
    token, pruned by prefix-monotone first-char viability (a dead first char skips
    the full reparse, memoised per char); a resumable recognizer is the deeper
    perf follow-up.

  Mask soundness holds in both modes: it never admits a token a live item would
  reject.

## Format is the caller's concern

A tokenizer is built from a **Mapping** (`encode` + ordered `merges`). *How* that
Mapping was produced — parsed from any format (HF `tokenizer.json`, GPT-2 vocab +
merges, CSV, …) via a lexic `(grammar, reduction)`, or handed in pre-parsed — is
the **caller's** concern. **No file format lives in `src`.** Formats are templates
on top of json: the same grammar with a value-yielding reduction reads the format
into `IrMap`/`IrTuple`, dogfooding the engine's own `parse_model` (the
`compile/notation` precedent). A specific format is at most a test fixture.

## Invariants

- Char grammars byte-identical; every token change is an added dispatch entry.
- Token rules island the PDA; `TokenKernel` is the single token engine.
- Engine↔tokenizer coupling is exactly `boundaries` + `spell` + `decode.keys()` —
  a real tokenizer drops in without touching the engine. Do not grow it.
- Mask soundness (never admit an invalid token).
- Everything an `IrSelf` on the spine; maps are `IrMap`, never `dict`.
