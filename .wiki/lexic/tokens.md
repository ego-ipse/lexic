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
bound to two different encodings is an error. Composing them may bind ONE
tokenizer under two names (its own and the grammar's) — that is still one
tokenizer, so the sole-vocabulary check counts by identity, not by entry.

A vocabulary is per-deployment, not per-grammar: `compiled.bind(tok)` returns
a new artefact against a different vocabulary without recompiling
([[public-api]]).

## The segmentation pipeline

`IrTokenPipeline` is the data around the merge rewrite: `specials` (atomic,
matched first), `remap` (ordinal → working char), `normalize` (ordered
replaces), `pretokens` (ordered `IrPretoken` splits) and `byte_fallback`.

`IrPretoken` is the whole contract — *a spec whose `split` partitions text*
— and it is **open-set**: a new family subclasses it and the pipeline accepts
it with no dispatch-table edit. That is deliberate, and it is where a
format's own split vocabulary belongs: **outside `ir/`**, beside the reader
that names it ([[decisions]]). `lexic.api.pretokens` holds the
`tokenizer.json` families and their byte table; the spine stays neutral about
whose pipeline it is.

A reader **refuses what it cannot honour** rather than reading past it: a
section or flag that changes what gets segmented is an error, not a shorter
answer. The test is whether the setting CHANGES the result, not whether it is
present — a flag whose effect depends on the content (does normalization
alter this token?) must be judged against the content, or it rejects files
that tokenize identically either way. Sections that act on an
already-segmented sequence are out of scope and say so.

Everything in a pipeline is **derived from a document's own sections**, never
fitted to a family. Two traps the readers must handle and the spine must not
know about:

- a byte-level step may declare that it contributes **no split of its own**
  (a family that pre-splits with its own pattern says so); the reader then
  emits no split spec, rather than a flag reaching an IR node;
- the byte **remap follows such a step's presence**, decided separately from
  whether it splits. Composing them may bind ONE
tokenizer under two names (its own and the grammar's) — that is still one
tokenizer, so the sole-vocabulary check counts by identity, not by entry.

A vocabulary is per-deployment, not per-grammar: `compiled.bind(tok)` returns
a new artefact against a different vocabulary without recompiling
([[public-api]]).

### The segmentation model

`IrSegmenter` is the role — `symbols(tok, text)` turns one working-alphabet
piece into the vocabulary symbols covering it. Two ship: `IrLongestMatch`
(merge-free) and `IrRankedMerge` (the reference BPE fixpoint). The BUILDERS
choose: `from_vocab` means longest match, `from_merges` means ranked merge,
so the model is decided where it is already known rather than re-derived per
gap. `with_segmenter` attaches another — Unigram or WordPiece are declarable
outside `ir/` without touching the spine.

Both shipped models are singletons, not empty records: an empty
`IrNamedTuple` compares EQUAL to any other empty one, which would make two
tokenizers differing only in model compare equal — and the compile caches
key on tokenizer equality.

**What a vocabulary cannot carry is skipped at SEEDING**, by `carries`: in
the vocabulary, byte-fallback-able, or covered by the unknown symbol. That
is not a silent drop but the reference behaviour, and it is what lets the
surviving neighbours become adjacent and merge ACROSS the gap. Dropping the
symbol after seeding instead leaves them unmerged — a different token
stream — and refusing rejects input real vocabularies handle (a byte-level
vocabulary may simply have no entry for some byte characters). The raise in
the token resolver is the safety net for a symbol that survives seeding and
still resolves to nothing.

`IrUnknown(spelling, fuse)` is the last resort before that raise: vocab →
byte fallback → unknown → refuse.

`universe` is the **highest ordinal, inclusive**, for every encoding. Reading
it as exclusive refuses the ceiling value itself; reading an exclusive one as
inclusive admits an ordinal past the end.

### The segmentation pipeline

`IrTokenPipeline` carries what turns text into pieces before the merge
rewrite: `specials` (atomic, matched first), `remap` (byte → working char),
`normalize` (ordered replaces), `pretokens` (ordered `IrPretoken` splits) and
`byte_fallback`. `IrPretoken` is open-set — a new family subclasses it and
the pipeline accepts it with no dispatch-table edit.

Every field is **derived from a document's own sections**, never hand-fitted
to a family; `lexic.api.json_tokenizer` reads them. Two rules that are easy
to get wrong:

- a byte-level step's **`use_regex=False`** means *byte mapping only, no
  split of its own* — families that pre-split with their own pattern set it
  that way, and imposing a default pattern on top corrupts their
  segmentation;
- the byte **remap follows a byte-level step's presence**, independent of
  that flag.

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
