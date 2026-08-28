# Prototype 5 — REVIEW_7 mechanisms: regular lowering, interpreted ABI, fold discipline, local meaning, GC

**Phase:** post-`REVIEW_7` ruling support. Source remains unchanged; every
executable lives in `proto/`, passes the repository Pyright environment, ruff
check/format, and pylint 10.00/10 with no suppression of any kind.

**Tree:** branch `targeter`, source baseline `0faa7289`. Witness:
`resources/tokenizers/qwen3.tokenizer.json`, 11,422,654 bytes; the vocab
region alone is 3,596,468 characters / 151,643 entries. All timings on the
Python 3.14.3 free-threading host; sequential rows run with the collector
ENABLED unless stated (the new §0 GC rule).

**Supersession note (2026-08-29):** this report is provenance, not the current
design ruling. `PROTOTYPE_7.md` replaces scanner admission with the stronger
boundary proof and signature × demand region derivation; replaces the
cross-process 0.368907/0.262931 comparison with the in-process controlled
0.351784/0.246319 row; rejects the resolver-based route stand-in; rejects
child-local ambiguity as language-narrowing; and supersedes the odd/fixed-order
GC rows with an even eight-pair run. `PROTOTYPE_8.md` further distinguishes
dirty-cone semantic-operation count from exact persistent meaning comparison
and eager materialization.

## 1 — the regular-region lowering exists; its original identity was bounded

`proto/regular_region_lowering.py` answers REVIEW_7 finding 1's mechanism
question. A `RegionSpec` — opener, entry rule names, demanded item indices,
separator, terminator — is witness-locator *data*. The mechanism is generic:

- **Proof.** The region's rule closure is compiled through the existing
  grammar-derived `build_recognizer` (`parsing/pda/core/scanner.py`); a cyclic
  or non-simple closure returns `None` and the region declines. The witness
  spec containing the recursive `value` rule declines exactly this way.
- **Lowering.** Demanded entry items become positional named capture groups
  (`c0`, `c2`) over the rules' own derived pattern sources; undemanded items
  are non-capturing. Entry and separator+entry transitions compile from the
  same sources. No JSON or tokenizer name appears in the mechanism.
- **Identity.** Over the first 4,000 vocab entries (79,207 chars), the
  captured/decoded product is equal, in order, to (a) the same lowering
  derived from the **GBNF ground-truth formulation**'s canonical rules
  (`resources/ground_truth/json.gbnf` through `canonical_grammar`), (b) the
  stdlib oracle, and (c) the **generic engine product**
  `compile_ast(JSON_GRAMMAR).reduce(slice, JSON_REDUCER, cores=1)`.

`reports/PROTOTYPE_6.md` extends this witness across native, GBNF, ABNF, and
EBNF formulations, 1/2/3 demanded captures, the complete vocab region, empty
valid input, and malformed refusals. The original two-capture/valid-slice result
alone was not a generic production proof.

## 2 — the interpreted completion-op ABI is 1.40x the fused capture, not 16.7x

The same file lowers the same region two more ways and times both over the
full 3.60 M-char vocab region, sequential, GC on, seven rounds:

| execution model | wall median | entries/s | MB/s per core |
|---|---:|---:|---:|
| one capturing match per whole entry (`--mode capture`) | 0.262931 s | 576,741 | 13.7 |
| one C-level match per rule + flat int-op dispatch (`--mode ops`) | 0.368907 s | 411,060 | 9.7 |

The `ops` row is an optimistic lower bound for the §3 flat ABI on this region: one
compiled-recognizer consult per lexical rule completion (string, separator,
int), one `if/elif` int dispatch per op, decode/int/insert as ops — no
per-character loop, no frames, transactions, PDA driver, merge region, or
remaining document. It is **1.40x** the fused whole-entry
recognizer, while the current reduction-variant parse of the same witness is
11.93 s (0.96 MB/s per core).

**Consequence for finding 1:** the 16.7x per-core gap between the current
engine and the prototype carrier is NOT primarily "regex versus interpreter".
It is per-character value-string consumption plus model construction. An
interpreted product ABI whose value-string terminals are consumed by one
compiled-recognizer consult per occurrence reaches ~10 of the needed
~16 MB/s per core on this dominant region; it does not prove the complete
<1.000 s envelope. The whole-entry capturing lowering
buys the remaining 1.40x and is what the ~105x objective needs. Both rows are
published beside the 0.121197 s eight-worker capture/join row as required.

## 3 — the shared-forest fold discipline is interleaving-dependent (finding 7)

`proto/shared_forest_refold.py` parses three tiny grammars through the real
kernel and fast-path tree build, proves the built derivation shares one
subtree **object** (the input-independent zero-width tree), then replicates
`parsing/fold.py`'s walk discipline and counts fold-body executions of the
shared node:

| shape | slots referencing the shared object | fold-body executions |
|---|---:|---:|
| `root ::= a "x" a`, `a ::= "y"?` over `"x"` | 2 | **2** |
| `root ::= a b`, `b ::= a "z"` over `"z"` | 2 | **2** |
| `root ::= b c`, `b ::= a "u"`, `c ::= a "w"` over `"uw"` | 2 | **1** |

The membership guard skips only *finished* folds, so a shared object pushed
while pending refolds (shapes 1–2), while one folded under an earlier sibling
is skipped (shape 3). Neither per-node-once nor per-occurrence semantics
holds; the count is a traversal accident. Under the side-effecting completion
ABI that means duplicated *and* missing effects, nondeterministically. A
fold-entry guard (also exercised) makes the value fold exactly-once per node
in all three shapes; occurrence-owned effects must then ride the parent's slot
consumption, not the child's fold body. Both witnesses become §3 exit gates.

## 4 — rejected child-local ambiguity experiment (finding 8)

This experiment measured a cheap mechanism but its semantic ruling is
**rejected**: the dropping-parent row proves child-local comparison would refuse
two derivations with one complete root value. `proto/local_meaning_fold.py`
compares the current root-rooted
`another_meaning` against folds rooted at each ambiguity family's differing
**child** subtree (building from the packed key itself drags the parent
context back in — measured and rejected inside the prototype's history):

| witness | root verdict | root folds | local verdict | local folds |
|---|---|---:|---|---:|
| kept difference | differs | 6 | differs | 4 |
| dropping parent | **no difference** | 6 | **differs** | 4 |
| same meaning | no difference | 6 | no difference | 4 |
| distant point (601 chars) | differs | 2,414 | differs | 4 |

- The distant-point row is the cost statement: root-rooted comparison refolds
  the whole document per flipped point (n+1 full folds — 2,414 and growing
  linearly with document size), the local fold pays 4 nodes regardless.
- The dropping-parent row refutes the proposed local law. The observable
  product is the complete requested root value; a parent which drops the child
  can erase the distinction. `PROTOTYPE_7.md` replaces this with completed-code
  ancestor replay to the root, and `PROTOTYPE_8.md` supplies exact persistent
  meanings for large built-in accumulators.
- Incidental finding: the engine's `same_value` recurses per nesting level and
  overflows the interpreter stack near depth ~1000 — deep meanings need an
  iterative comparator when §8 lands.

The initial witness covered internal packed-family points only.
`PROTOTYPE_6.md` adds the separate accepting-root-item case: each sibling root
needs one complete fold because no internal ambiguity key contains that choice.

## 5 — the carrier budget with the collector enabled (finding 11)

`proto/carrier_gc_cost.py` re-runs the exact composed carrier
(`composed_native_tokenizer` capture → canonical freeze → record) alternating
collector states round by round in one process, eight retained workers:

| collector | process CPU median | wall median |
|---|---:|---:|
| enabled | 0.801694 s | 0.170211 s |
| disabled | 0.790703 s | 0.153264 s |

This first comparison always ran enabled before disabled, so its
**+0.016948 s wall (~11 %)** delta is order-confounded and rejected.
`PROTOTYPE_6.md` alternates pair order and measures +0.005182 s median wall and
+0.005439 s process CPU. Production runs with GC on; `src` never manipulates
collector state; the §0 protocol records GC state per row.

## 6 — the reducer-free selection morphism (finding 10)

`proto/demand_selection.py` prototypes the kept reducer-free selection
morphism — `select_raw(entry, spec)`, compiled as OCCURRENCE DEMAND the way
the target architecture executes. An earlier draft that pre-passed spans with
the current templating machinery and re-parsed kept text was deleted as
unfaithful to the new architecture; this one executes the new shape:

- **One parse per document, no re-parse.** Binding compiles the selection
  into a single contextual clone grammar: the rule-keyed fold becomes
  occurrence-keyed through cloning (the §6 contextual-clone mechanism), and
  one `parse_model` call recognizes the document while building exactly the
  demanded products in place.
- **Undemanded work is recognition-only.** Every undemanded subtree routes to
  a `-sk` twin with no fold body; kept leaf values route to the ORIGINAL
  model-building rules, so the kept `GrammarModel` is constructed by the same
  parse that recognized it, with its certified absolute span captured off the
  same slot. Retained construction over a 1,000-entry document keeping two
  paths: 2 models, 998 key records (demanded by duplicate refusal), nothing
  else.
- **The extent codomain is statically model-free.** Its variant routes kept
  values to `-sk` too and keeps only spans; a reachability walk over the
  bound grammar proves no model-building rule is reachable from the start —
  zero values materialize, deferred materialization is the caller's slice.
- **Key routing is deterministic, not grammatical.** Selected raw keys become
  literal-routed dispatch arms beside a recognition-only fallback; the
  overlap on selected keys is settled by a deterministic
  specialized-over-poison-over-fallback preference carried through the
  public ambiguity resolver — the RouteOp continuation's stand-in
  (`proto/route_continuation.py` owns the recognition-time mechanism
  production compiles instead).
- **Shape verdicts are syntax-first.** A selected-nested key over a
  non-mapping value derives only the poison arm, which consumes the value
  through recognition-only recovery and defers the refusal until after the
  parse succeeds — the contract's poisoned-state behavior, exercised.
- **Contract edges.** Empty and nested-empty declarations refuse; repeated
  raw keys at a SELECTED level refuse while unselected levels stay
  unchecked; missing paths are absent; results are declaration-ordered;
  `to_text()` equals the certified slice.
- **No reducer, no signature, no formulation privilege.** Binding consumes
  a compiled grammar with the compatible mapping shape and its binding view
  only; the toy `(k=v, ...)`
  grammar has no reducer at all, and the GBNF ground-truth and native JSON
  formulations return identical kept values. Raw keys are declaredly
  distinct from decoded keys (`{"a": 1, "a": 2}` selects the raw
  spelling) — the difference from decoded `select`.
- **Measured tie-in to finding 8.** Retained products are demand-sized, but
  fold-body EXECUTIONS run ~3x retained (6 kept-arm and 2,999 fallback
  executions for 2 + 998 retained) because today's ambiguity/attempt
  machinery re-folds candidate derivations — the same root-refold cost §8's
  local-meaning mechanism removes.

The production §6 implementation lowers this same contract through the
product compiler's demand analysis and runs only through the one `reduce`
morphism channel — no `Template.run` twin — with the toy-grammar templating
assertions ported to it. `PROTOTYPE_6.md` supplies the missing third `reduce`
overload and exact model/extent capture result types.

## Gates retained

The lowering prototype's `RegionSpec` names are witness locators. Production
route compilation must derive equivalent regions from the composed
lower×upper grammar without naming rules, certify entries/exits as §9
requires, and keep the decline-to-sequential path. The ops row prices the
interpreted ABI's per-completion dispatch on one region; it does not measure
frames, transactions, or the PDA driver. Nothing here relaxes the §4 parse
non-regression gate or the §5 differential.
