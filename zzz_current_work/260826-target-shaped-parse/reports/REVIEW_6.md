# Plan review — target-shaped parsing, pass 6

**Reviewed:** 2026-08-28  
**Scope:** the current coherent plan in `context.md`, `goal.md`, `DESIGN.md`,
`TODO.md`, and `LEDGER.md`; reports through `PROTOTYPE_3.md` and `REVIEW_5.md`;
the latest feasibility prototypes; and the cited production seams.  This was a
static review only.  No benchmark was run.

## Verdict

**NO-GO for the stated source-start/performance-feasibility gate.**  The
semantic-signature/lower×upper-state product is still a credible generic
architecture, and the plan correctly avoids a model bridge and a privileged
parser.  The claimed approximately `0.166 s` *ready tokenizer* result is not,
however, an end-to-end measured product yet, and its boundary conflicts with
the named `read_from_path` outcome.  There are also two representation and
certification decisions which must be fixed before the direct finalisation
path is implemented.

These are not requests to restore the old whole-document reduction.  They are
requirements that the new one-product path account for all of the work it
claims to replace, and that its externally observable IR behaviour be defined
once.

## Blockers

### 1 — The `0.113811 + 0.001864 + 0.008423` account omits construction of the final IR product

**Severity:** blocker — performance feasibility.

`PROTOTYPE_3.md` combines the high-volume capture median, the shell-control
median, and the `IrTokenIndex` freeze median into an approximately `42 ms`
remainder below the target.  Those readings do not compose into a ready
`IrTokenizer`:

- `proto/anchored_tokenizer_regions.py:77-81` declares the completed product
  as native `Tables` and `Ranks`; `_measure` only anchors, captures, joins, and
  returns those dictionaries (`192-240`).  Its anchors are also literal
  `"vocab"`/`"merges"` JSON spellings (`84-99`), rather than the planned
  derived target route.
- `proto/tokenizer_index_shape.py:33-43` freezes an already-owned
  `dict[IrStr, IrChr]`, `dict[IrChr, IrStr]`, and `dict[IrTuple, IrInt]` by
  updating the index's table.  `_measure` times only that operation
  (`61-67`, `91-102`).  The fixture/population phase has already obtained all
  IR leaves before the clock starts.
- The actual final record needs those leaves and all three mappings.  Today
  `IrTokenizer` contains `encode`, `decode`, and `ranks` map fields
  (`src/lexic/ir/text/tokenizer.py:271-317`) and `_build` derives the inverse,
  validates specials, chooses the segmenter, and constructs the record
  (`371-400`).  Qwen has 151,669 vocabulary entries and 151,387 ranks
  (`tests/integration/lexic/tokens/test_real_tokenizer_qwen.py:92-98`).

Thus no timing currently charges conversion/reuse policy for the primitive
capture values into final `IrStr`/`IrChr`/`IrTuple`/`IrInt`, inverse-table
ownership, or the real `from_indexes` validation/record tail.  Reusing leaves
is a valid design, but it must be created by the direct parser on the measured
path; it cannot arrive through a pre-reduced tokenizer or an untimed fixture.

**Required change and proof gate.**  Before source implementation is allowed
to rely on the `0.166 s` number, add a serial, no-prebuilt-data feasibility
witness that starts with resident Qwen source text and finishes a real
`IrTokenizer.from_indexes` result.  It must separately attribute:

1. target proposal and typed-hole certification;
2. small-field lower/upper recognition and decoding;
3. high-volume direct capture into the final IR leaves (including any
   interning/ownership transfer);
4. ordered joins, duplicate checks, inverse construction, and rank assignment;
5. each index freeze; and
6. `from_indexes` pipeline/root validation and record construction.

The witness must compare exact tables, segmentation behaviour, and the chosen
equality semantics to the current semantic reference; exercise duplicate
vocabulary/rank and cross-fragment duplicate refusals; and report allocation
or RSS as well as wall/process time.  It must contain no reduced document,
`IrMap`, dyad list, existing tokenizer, or pre-created IR table.  Only that
composed measurement may be used as the ready-tokenizer feasibility claim.

### 2 — `read_from_path` cannot share the `0.166 s` acceptance boundary unless source I/O is excluded by contract

**Severity:** blocker — contradictory acceptance metric.

The requested outcome names `json_tokenizer.read_from_path`, which necessarily
performs `Path.read_text()` before it calls `read`
(`src/lexic/api/json_tokenizer.py:99-121`).  The prior clean attribution measured
the Qwen source read alone at `0.192904 s` and `0.233518 s`, median
`0.213211 s` (`260821-one-path/reports/i23_report.md:66-103`).  In contrast,
`PROTOTYPE_3.md` explicitly budgets no source-file I/O.  The historic
`17.416359 s` comparison also combines more than the direct parse/build path
(`i23_report.md:103-121`).

Consequently, an end-to-end cold `read_from_path` result cannot plausibly be
under `0.166 s` on the evidence already retained.  This is a measurement
contract problem, not an excuse to hide file read time or to make JSON special.

**Required change and proof gate.**  Amend the goal/design/TODO acceptance
tables before implementation to name two metrics:

- a resident-text `read(text, ...)` direct-product budget, for which the
  composed witness in blocker 1 is relevant; and
- a separately reported cold and warm `read_from_path` budget which includes
  source I/O.

Both should retain exact semantic and failure witnesses.  The public path may
still return a ready tokenizer, but it must not be advertised as meeting a
resident-text budget when its measured boundary is a cold file read.

### 3 — `IrTokenIndex` makes insertion order observable without defining whether it is part of value identity

**Severity:** blocker for the new IR/finalisation ABI.

The proposed index preserves builder/source order:
`proto/tokenizer_index_shape.py:33-43`, and its validation treats the key order
as required output (`70-83`).  The inherited `IrMapping` equality and hash are
order-insensitive (`src/lexic/ir/action/mapping.py:169-187`), while its repr
iterates insertion order (`189-196`).  This differs deliberately from `IrMap`,
which canonicalises by key repr (`199-235`).

That discrepancy crosses real artifact seams.  The payload codec serialises
mapping entries in iteration order (`src/lexic/compile/payload/codec.py:95-97,
129`), the reader reconstructs via `from_table` (`payload/reader.py:120-127`),
and notation emission iterates the mapping's dyads
(`src/lexic/compile/notation/emit.py:217-220`).  Two indexes with the same
lookups but different source orders would currently compare and hash equal, yet
emit different notation/payload byte sequences and preserve their different
orders on load.

**Required change and proof gate.**  Choose and document one of these contracts
before adding `IrTokenIndex`:

- If source order is semantic/observable, override equality, inequality, and
  hash for ordered items; or
- if it is representation-only, define and enforce the one public construction
  order which makes emission/payload canonical (without reintroducing the
  expensive `IrMap` sort on the hot path).

Then place the class in `ir/text/tokenizer.py`, expose only the final three
index fields and one `from_indexes` final tail, and make `from_vocab` and
`from_merges` converge to it.  Add notation, repr, payload export/read
fixpoint, deterministic emission, equality/hash, duplicate, bijection, rank,
and special-membership tests.  `from_owned` may bypass duplicate scanning only
behind a single validated internal builder; public `from_table` must retain the
base duplicate refusal (`mapping.py:99-120`).

## Required proof gates before claiming parallel/direct completion

### 4 — The measured shell control is not typed-hole certification through the composed product

**Severity:** high missing implementation proof gate; not a new architecture
blocker.

`proto/schema_shell_cost.py` uses literal field anchors, replaces contents, and
uses a Python JSON load/dictionary lookup.  It does not execute the planned
lower × upper product, carry lower/upper entry-exit states, preserve a parent
accumulator, or run deferred semantic verdict ordering.  Its `0.001864 s`
therefore cannot be charged as the cost of actual pre-submission
certification.

The plan's requirement in `DESIGN.md` §9 and `TODO.md` §9 is the right one:
only the same compiled product may certify and later resume a typed hole.  Make
that an executable gate before submitting work: certification must run exact
production lower decoding and target routing over the prefix, interstitial
shell, and suffix; record concrete product states and parent handles; then
resume/validate the same product after the fragment result attaches.  It must
not construct the full JSON map, call `json.loads`, or treat a replaced `vocab`
as an absent/empty field.

The witness needs valid Qwen, nested false anchor, reordered fields, escaped
spelling, duplicate, and malformed inputs.  In particular, a later syntax
failure must beat a previously recorded semantic refusal, and multiple semantic
refusals must use the stated source/phase ordering.  The final result/refusal
must equal the sequential direct product.  This both proves no duplicate
recognition/discovery/finalisation and covers the intended syntax → ambiguity →
deferred-semantics ordering.

### 5 — Generic derivation and physical recognizer ownership require production-shaped evidence

**Severity:** high missing proof gates.

The high-volume prototype hard-codes JSON keys and container markers
(`anchored_tokenizer_regions.py:84-99`), so it cannot establish the plan's
claim that a `SemanticSignature`/reducer declaration derives target routes for
every equivalent grammar formulation.  The non-JSON prototype rows establish
only regex ownership for synthetic lexical closures, not target extraction over
GBNF, ABNF, and EBNF formulations.

Before source work claims formulation independence, compile one small target
schema through native JSON plus the repository's JSON GBNF, ABNF, and EBNF
formulations (including a renamed/reordered equivalent where the format permits
it).  Assert that the generic declaration produces equivalent target products,
results, ambiguity/refusal ordering, and no parser/compile rule-name special
case.  JSON remains a witness, never an input-specific branch.

Likewise, the cache-distinguishing pattern comment in
`anchored_tokenizer_regions.py:134-152` is a promising feasibility technique,
but it is not yet an ownership proof for the actual product.  The current
worker replicas own table/memo state, not necessarily cache-distinct compiled
recognizers (`src/lexic/parsing/parallel/replicas.py:94-127`); direct scanner
compilation goes through `re.compile`
(`src/lexic/parsing/pda/core/scanner.py:129-157`).  The production gate must
assert distinct identities for every hot recognizer/pattern in every actual
fragment-product worker (including capture and continuation recognizers), equal
language/results, a negative shared-cache guard, and an engaged-split guard.
Bind those replicas before timing; no worker-id lookup or source rewrite may
enter the paid loop.

## Retained positive constraints

`DESIGN.md`'s product-state proposal, its typed-hole intent, and the
no-regression isolation in `TODO.md` §§4, 7, 9, and 12 remain the correct
direction.  Keep the existing static opcode/no-model-bridge gate, the
fresh-state fallback/ambiguity checks, exact integer range ownership, and the
parallel eligibility/2 KiB-floor control rows.  The changes above add the
missing composed evidence; they do not authorize a second recognition path, a
JSON-only parser, or a second finalisation API.

## Re-entry condition

Update the active plan/ledger with the two acceptance-boundary decisions and
the five gates above.  A new review may clear the source-start gate after the
resident-text composed witness, ABI contract tests, and typed-hole/formulation/
ownership witnesses exist and pass.  Until then, the reported component
medians are useful budgets only, not a feasibility proof of a ready tokenizer.
