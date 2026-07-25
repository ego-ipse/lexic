# Tokens

**When to load:** working on `ir/encoding.py`, `ir/concretize.py`,
`parsing/earley/tokenscan.py` or `parsing/earley/resume.py`; adding a token
terminal to a flavour; wiring a tokenizer into compile; reasoning about
generation masks or the char-column boundary.

## The shape

An **encoding** gives a character class's ordinals their meaning:
`universe` / `resolve` / `spell` / `boundaries` / `ids`, plus a derived
`tokenize`. That surface is the whole engine coupling and **must not grow**.

Three concrete encodings, all peers on `IrEncoding`:

| Encoding | Ordinals are | Notes |
|---|---|---|
| `IrUnicode` | code points | the default; singleton. The degenerate tokenizer — one span per char |
| `IrUtf` | UTF-16 code units | the unit-level transform child; owns surrogate-pair combining, and is the reduce-side unit decode the JSON reducer pipes through |
| `IrTokenizer` | vocab ids | record; `ranks` stored, ordered merges derived at emission |

A tokenizer is **not** a special case in the engine — it is another encoding.
Everything UTF-specific (the `MAX_CODEPOINT` ceiling, `chr`/`ord`) is an
`IrUnicode` property, never an assumption in the set-math.

## Grammar surface

A token terminal is an `IrAlphabet(encoding_name, inner)` — no token-specific
leaf type exists; the inner reuses `IrLiteral` / `IrCharClass` / `IrNot`.
Negation lives **inside** the alphabet (`!<…>` → `IrAlphabet(enc,
IrNot(inner))`), so the encoding governs the complement's universe.

GBNF spells them `<token>`, `<[id]>`, `<[lo-hi]>`, `!<…>`, `.`; ABNF and EBNF
refuse them declaratively. `concretize(ast, registry)` resolves each
alphabet's spelling to an ordinal against a registry (`IrMap[IrStr,
IrEncoding]`) — a language-level rewrite, so a token grammar is
tokenizer-specific once concretized.

`<think>` names the token whose spelling IS `<think>`, brackets included —
`<hi>` denotes a token literally spelled `<hi>`, and refuses at concretize
time if the vocab has no such token. That is llama.cpp's GBNF semantics, and
lexic mirrors it: **grammar is the ground truth, so we describe the format,
we do not prescribe to it.** Content is expressed with negation
(`!</think>*`) rather than by naming a bare word.

## Three capabilities

1. **Read / emit** — no tokenizer needed; token terminals parse and round-trip.
2. **Parse instances** — `compile_text(..., tokenizer=)`; `TokenKernel` scans
   token terminals id-granular at boundary columns.
3. **Constrain generation** — `compiled.constrain()` → a `TokenMaskCursor`.

`tokenizer=` and `registry=` **compose** over a default `unicode`; only a name
bound to two different encodings is an error.

## Engine constraints worth knowing

- **Token terminals island the PDA by construction.** The char-driven
  predictive runtime never matches tokens, so a token grammar's rules island
  and the Earley `TokenKernel` is the single token-matching engine. Char
  grammars never build one, so their hot path is untouched.
- **Run-collapsed tables cannot be resumed.** A run terminal takes the
  *maximal* run, whose extent depends on input not yet appended, so a
  committed run can never grow — maximal munch and incremental extension are
  incompatible. `ResumableKernel.extend` refuses them loudly.
- **A fresh empty parse under-reports viability.** Its seeds are FIRST-gated
  on the absent next char, so `frontier_viable(Kernel(t, "").run())` is
  `False` even when every word extends `""`. A chart that has been extended
  and rolled back reports the truth. Do not use the empty fresh parse as a
  viability oracle.

## The mask cursor

`TokenMaskCursor` is an ABC over two concrete cursors, picked by `.of()`:

- `TokenTermCursor` — token grammar; the mask is frontier set algebra over the
  live token-terms, no exploration.
- `CharTrieCursor` — char grammar; a trie DFS over vocab spellings on a
  char-granular recognizer (`split_literals`), with mark/extend/rollback per
  branch and empty-column pruning.

Both hold **one live chart**: `push(id)` extends it, so the committed prefix
is parsed once per generation rather than once per candidate token. `ids` is
public and assignable — every read syncs the chart by common-prefix rollback
plus extension.

The oracle for either is `viable_prefix(tables, text)`, the stateless
recompute; differentials hold the two equal.

## The char-column boundary

Token spans are char-aligned. Under a byte-level pipeline a token may end
mid-code-point: `tokenize()` still returns its id, but `boundaries()` yields
no span for it, so token-granular *parsing* covers char-aligned segmentations.
This is the documented limit — a byte-column engine is a separate, unmade
decision, not a gap to route around.

## Related

[[lexic/ir-shapes]] · [[lexic/architecture]] · [[lexic/decisions]] ·
[[lexic/public-api]]
