# `lexic.parsing_2` — IR-native Earley parsing

`parsing_2` is the Lark replacement: a scannerless [Earley](https://en.wikipedia.org/wiki/Earley_parser)
parser that runs **directly over an `IrAst`**. No meta-grammar string, no Lark
grammar generation, no external parser. The premise is that **an `IrAst` already
*is* a grammar** — a set of named rules, each an alternation of sequences of
atoms — so it can drive a parser as-is.

The self-hosting fixpoint is the proof: take the ABNF-of-ABNF grammar expressed
as IR (`grammars/abnf_2.py`'s `ABNF_GRAMMAR`), emit its own source text, parse
that text back with itself, reduce, and recover the identical `IrAst`.

**On the product metric (text → `IrAst`) this engine beats Lark ~2×** — see §12.

```
grammar (IrAst) ──► normalize() ──► compile_tables() ──► ParserTables   (once per grammar)
                                                              │
text (str) ─────────────────────────────► Kernel(tables, text).run()    (per parse)
                                                              │
                             ┌────────────────────────────────┼─────────────────────┐
                             ▼                                ▼                     ▼
                     FastTree → ParseTree        FusedReduce → IrAst        to_chart() → Chart
                     (single derivation)         (the product path)         (forest readers:
                             │                                              derivations,
                     Reducer → IrAst                                        is_ambiguous, …)
```

---

## 1. Public API

Six functions in `__init__.py`. Each is a thin wrapper that boxes the input and
drives exactly one `IrSelf` orchestration node in `engine.py`. Per the IR's
no-`IrBool` rule, a truth value is an `IrInt ∈ {0, 1}`.

| Function | Returns | Meaning |
|---|---|---|
| `recognize(grammar, text)` | `IrInt` 0/1 | Does `text` derive from the start rule? (No forest built.) |
| `parse(grammar, text)` | `ParseTree` | The single derivation. **Raises** on no-parse *or* ambiguity. |
| `parse_reduced(grammar, text, reducer)` | `IrSelf` | **The product path**: text → reduced IR in one fused pass. Raises like `parse`. |
| `parse_forest(grammar, text)` | `SppfNode` \| `IrNone` | The shared packed parse forest root, or `IrNone` on no-parse. |
| `derivations(grammar, text)` | `IrSeq[ParseTree]` | *Every* derivation, nothing silently dropped. |
| `is_ambiguous(grammar, text)` | `IrInt` 0/1 | Does the input have more than one derivation? (Short-circuits at 2.) |

```python
from lexic.parsing_2 import parse, parse_reduced, recognize
from lexic.parsing_2.normalize import normalize

g = normalize(MY_GRAMMAR)            # desugar to classical Earley shape first
assert recognize(g, "input text")    # IrInt(1)
tree = parse(g, "input text")        # a ParseTree
ir = parse_reduced(g, "input text", MY_REDUCER)   # straight to IR — fastest
```

> **The grammar must be normalised first** (§6). The parser assumes classical
> Earley shape: every quantifier is `(1, 1)` and every group is a named rule.
> Multi-char literals stay atomic (§5). `normalize()` is the caller's
> responsibility — kept separate so the desugaring stays isolated.

---

## 2. The design in one sentence

**The grammar compiles once; the paid loop runs over the compiled form.**
`compile_tables()` is the parser's "codegen moment": exactly as `codegen/`
emits Python classes from a `RuleSpec` (grammar stays ground truth, the classes
are its compiled representation), `tables.py` compiles an `IrAst` into flat
int-coded tables, and `kernel.py` runs Earley over them with no per-item IR
dispatch, no IR object as a hot-path key, and no tuple allocation per advance.

The IR seams sit at the edges, all IR-native:

- **in:** `compile_tables(IrAst) → ParserTables` walks the grammar (memoised
  per grammar object, like constructing a `lark.Lark`);
- **out (product):** `FusedReduce` folds the packed forest to IR against the
  flavour's `Reducer` policy tables (`IrMap`s of IR bodies);
- **out (general):** `Kernel.to_chart()` decodes the packed SPPF into the
  IR-native `Chart` for the trampolined forest readers.

State objects (`ParserTables`, `Kernel`, `KernelState`) ARE-AN `IrLeaf`; logic
lives on classes and per-parse state on cursors — but inside the kernel the
per-item work is list indexing and int arithmetic, deliberately: this is the
package's compiled-form zone, the scoped relaxation of per-item IR dispatch
that the measured ~2× IrSelf-purity floor demanded.

## 3. The compiled tables (`tables.py`)

Every dotted position of every arm gets one int `code`, laid out so
consecutive dots are consecutive ints — **advancing an item's dot is `+ 1`**.
One flat list discriminates the classic Earley trichotomy with a single index:

| `next_sym[code]` | meaning |
|---|---|
| `rule_id + 1` (> 0) | dot faces that non-terminal — predict |
| `-(term_id + 1)` (< 0) | dot faces that terminal atom — scan |
| `0` | dot past the arm's end — complete |

An **Earley item** is the single int `code << 20 | origin` (a single-digit
CPython int for realistic grammars — set/dict operations at the primitive
floor); an **SPPF handle** `(item, end)` packs the same way again. Value-equal
arms of one rule intern to a single arm (the IR node IS its value), matching
the legacy item tuples' value semantics.

`ParserTables` splits along consumers: `CodeTables` (the code-space half the
loop indexes per item), `DecodeTables` (the IR-space half used only when
results decode back to IR), plus the terminal atoms, per-terminal scan kinds
(`term_lens`), and two per-grammar lazy caches (char → accepting terminals,
char → interned `IrLiteral`). `nullable_completes` precomputes the
Aycock-Horspool advance set per nullable rule.

## 4. The kernel (`kernel.py`)

`Kernel(tables, text, record_links).run()` is the whole Earley loop: close
each column to a fixpoint (predict / complete, dispatched by one `next_sym`
index), scan between columns. Per-column indexes are position-indexed lists of
small containers keyed by bare `rule_id`/`term_id` ints — `seen` (dedup),
`waiting` (completer), `scannable` (scanner), `predicted`, and the Leo memo.

- **SPPF (Scott 2008), preserved in full.** `st.links[handle]` records packed
  families `(predecessor, pred_end, child)`; a key reached two ways files an
  additional family; identical families dedup; ≥ 2 families ⇒ ambiguity
  point. `child` is a packed handle or the consumed text itself.
- **Aycock-Horspool nullable advance**, recording the completer's own
  empty-completion handle so the two provenances collapse into one family.
- **Leo right recursion (Leo 1991).** A deterministic right-recursive
  completion jumps to the chain's topmost item; the skipped completions are
  deferred in `st.leo_links` (a *bucket* per top — converging ambiguous
  chains each file their bottom) and rebuilt lazily by `expand_leo`, O(chain),
  only when a derivation actually walks them. The climb rejects
  **same-column (empty-span) steps** — they are cycle- and ambiguity-prone
  and carry no asymptotic benefit, so the normal completer (which records
  every family) handles them; columns then strictly decrease up the climb and
  no cycle guard is needed. (This also fixes a legacy bug where a second
  chain converging on an already-deferred top silently lost its family.)
- **Recognition skips the forest** (`record_links=False`) — no links, no
  allocation beyond the chart itself.

`FastTree` is the unambiguous fast path: an explicit-stack walk of the packed
links building the single `ParseTree` (memoised per handle); any key packing
more than one family aborts to the trampolined enumeration over the decoded
chart. Depth lives in lists, never the C stack (N = 60,000 verified).

## 5. Scanning: chars, literals, runs

The scanner resolves which terminals a character can begin once per distinct
char (cached on the tables), then reads each column's `scannable` bucket:

- a **char class** advances one column;
- a **multi-char literal** is atomic — one C-level `text.startswith` and the
  advance lands k columns ahead (`normalize` no longer splits literals);
- a **run terminal** (§7) consumes its maximal run in one step and lands at
  the run's end.

## 6. Normalisation (`normalize.py`)

Two canonicalisations precede Earley, both `IrTransformer`s:

1. **Flatten inline groups** — an `IrAlternation` used as an atom is hoisted
   to a fresh synthetic rule (prefix `__`), keeping its quantifier.
2. **Desugar quantifiers** — a non-`(1, 1)` quantifier becomes a synthetic
   right-recursive rule (`*` → `X = "" / elem X`; `+` → `X = elem / elem X`;
   `?` → `X = "" / elem`; bounded counts unrolled). The `*`/`?` rules are
   *nullable*; Leo (§4) keeps the right recursion linear where it survives.

Large *bounded* counts (`{lo, hi}`) still unroll `hi`-deep at desugar time —
the one remaining rough edge.

## 7. Run terminals (`lexruns.py`) — the derived lexer

Lark's decisive constant-factor advantage was never a C parser (it has no C
extensions): its *dynamic lexer* matches hand-declared tokens with compiled
regexes, so its Earley loop steps over **tokens** (~5 chars each on the ABNF
workload) while a scannerless engine steps over **chars**. `lexruns.py`
closes that gap by *deriving* the token layer from the grammar — and unlike
Lark's silently-incomplete maximal munch, the collapse is **proved** safe:

A synthetic star/plus rule collapses into a single maximal-munch `RunTerm`
when:

1. **Fixed charset** — the unit resolves to a set of single chars (a terminal,
   or transitively a rule whose every arm is one such atom);
2. **Derivation uniqueness** — charset-rule alternatives are pairwise
   disjoint, so the collapse cannot hide ambiguity from the SPPF;
3. **Follow disjointness** — `FOLLOW(rule) ∩ charset = ∅` (classic
   FIRST/FOLLOW over the compiled tables), so no continuation can ever
   require a shorter-than-maximal match.

A char class too large to expand poisons the sets it touches and the affected
rules simply stay per-char. The reducer-side half of the decision lives in
`reduce.collapsed_tables(reducer, grammar)`: a run may only collapse when its
per-char reduction contributions are reconstructible from the run text — the
unit's leaf rules are DROP noise (`RUN_DROP`: contribute nothing) or YIELD
text rules (`RUN_STR`: one `IrStr` per char), or a bare terminal under the
literal policy (`RUN_LEAF`). Anything else stays per-char for that reducer.
Collapsed tables are therefore **per (reducer, grammar)** and memoised; only
`parse_reduced` uses them — `parse`/`recognize`/forest readers keep the plain
tables and their exact `ParseTree` shapes.

On the ABNF self-host workload all six repetition rules collapse (wsp runs,
rulename tails, digit/hex runs, char-val bodies), which is most of the input.

## 8. Reduction (`reduce.py`) — the meta-notation seam

A flavour's "meta notation" is unchanged: `reductions` (an `IrMap` from a
rule's `IrRuleRef` to a body folding the rule's matched children into IR) and
a cleaning policy (`noise` per child rule: `DROP`/`KEEP_REDUCED`/…;
`literal` for terminal leaves). `YIELD` recovers a subtree's source text.

Two folds implement it:

- **`FusedReduce` — the product path.** One explicit-stack pass folds the
  packed SPPF straight to IR: no intermediate `ParseTree`. A `ReducePlan`
  (cached per reducer × tables) compiles the policies against the rule
  numbering; synthetic nodes splice; run children reconstruct per §7; and a
  rule whose body IS `YIELD` reduces to its **source span** —
  `text[origin:end]`, O(1) — whenever no DROP-noise rule is reachable
  beneath it (`can_drop` reachability), skipping the whole subtree. Bodies
  receive the matched span text as `n` (computed only when the body mentions
  `YIELD`) and the cleaned children on `nc`. Any shape the plan can't
  compile (ambiguity, KEEP_RAW/custom noise) returns a miss and the caller
  falls back to a fresh plain-tables parse + the legacy fold — behaviour
  identical, just slower.
- **`Reducer` over a `ParseTree`** — the general fold, driven by the
  iterative `_FastReduce` (explicit stack) with the trampolined
  `ReduceSource`/`ResolveSource` as its lineage. Feeds on `parse()` output.

## 9. Forest & ambiguity (`forest.py`, `chart.py`)

Ambiguity is never silently resolved: `parse`/`parse_reduced` raise on it;
`parse_forest`/`derivations`/`is_ambiguous` expose every reading. The general
readers work over the IR-native decoded `Chart` (`Kernel.to_chart()` expands
all deferred Leo chains first): `SppfNode` handles, the lazy replayable
`IrStream`, and the depth-safe trampolined enumeration cogens (`NodeDerivs`,
`PrefixSource`, `ChildDerivs`) are unchanged from the pre-kernel engine.
`BuildTree` is the strict single-derivation façade over that path.

## 10. Module map

| Module | Responsibility |
|---|---|
| `tables.py` | `ParserTables`/`CodeTables`/`DecodeTables`, `RunTerm`, `compile_tables` (memoised) / `build_tables` (variants). |
| `kernel.py` | `Kernel` — the flat Earley loop (predict/scan/complete, Leo, packed SPPF), `FastTree`, decode to `Chart`. |
| `lexruns.py` | Run-terminal derivation: charset resolution, FIRST/FOLLOW, the three collapse proofs. |
| `normalize.py` | Desugar IR into classical Earley shape (groups, quantifiers). |
| `reduce.py` | `Reducer` + policies, `FusedReduce`, `ReducePlan`, `collapsed_tables`. |
| `engine.py` | The `IrSelf` orchestration nodes the public API drives. |
| `forest.py` | `ParseTree`/`SppfNode`, trampolined enumeration, `IrStream`, `BuildTree`. |
| `chart.py` | The decoded IR-native SPPF (`Chart`/`Links`). |
| `item.py` | `EarleyItem` — the decoded dotted-arm tuple. |
| `trampoline.py` | Depth-safe generator driver for the forest/reduce walks. |

## 11. Invariants

- **Grammar is canonical.** The parser never mutates the grammar; the tables
  are its compiled representation, rebuilt from it alone.
- **Full SPPF.** Nullable completion (Aycock-Horspool), sharing and packed
  families (Scott 2008), exact ambiguity — including under Leo and under run
  collapse (both proved, §4/§7).
- **Depth-safe.** No tree walk recurses through the C stack (explicit
  stacks + trampoline; N = 60,000 verified).
- **One way per task.** One parse function, one fused product entry, one
  emit method.
- **The compiled-form zone is scoped.** Per-item IR dispatch is compiled away
  *inside* `kernel.py`/`tables.py` only; every seam in and out of the zone is
  IR-native, and orchestration, normalisation and reduction policy stay
  `IrSelf` end to end.

## 12. Benchmark results

Measured with `zzz_current_work/bench_parsing.py` (2026-07-01), a
stage-for-stage race against **Lark 1.3.1** (`parser='earley'`, pure Python —
it ships no compiled extensions) on the ABNF self-host workload. Interleaved
medians; the `parse+reduce` row is the product: text → `IrAst`.
Fixpoint holds on every path.

### ABNF self-host (920 chars/copy)

| input | stage | Lark | `parsing_2` | ratio |
|---|---|---|---|---|
| x1 (920 ch) | recognize | 18.7 ms | **8.0 ms** | **0.42×** |
| | parse | 26.6 ms | 34.1 ms | 1.28× |
| | **parse+reduce** | 27.0 ms | **15.0 ms** | **0.55×** |
| x2 (1840 ch) | recognize | 36.9 ms | **15.2 ms** | **0.41×** |
| | parse | 52.4 ms | 64.3 ms | 1.23× |
| | **parse+reduce** | 53.7 ms | **28.9 ms** | **0.54×** |
| x4 (3680 ch) | recognize | 74.9 ms | **32.3 ms** | **0.43×** |
| | parse | 108.7 ms | 137.1 ms | 1.26× |
| | **parse+reduce** | 109.9 ms | **62.1 ms** | **0.56×** |

**The product beats Lark ~2× (44-48% faster) and recognition ~2.4×, stable
across sizes.** The rows are independent races, not an additive ladder — each
entry runs its own optimal pipeline: `recognize` on maximally collapsed
tables with no forest; `parse` on plain per-char tables (its contract is the
exact reducer-agnostic `ParseTree` — the one row still above Lark);
`parse_reduced` on reducer-collapsed tables plus the fused fold. The product
comparison is honest: Lark's row is likewise its one-call parse + transform
riding on its token-collapsed lexer.

### Deep right-recursion — `S = "a"*`

Linear (µs/N flat), no stack overflow, and 2.5–3× **faster** than Lark:

| N | parse→tree | µs/N | Lark | ratio | | recognize | µs/N | Lark | ratio |
|---|---|---|---|---|---|---|---|---|---|
| 400 | 3.50 ms | 8.8 | 10.75 ms | 0.3× | | (1600) 6.91 ms | 4.3 | 16.17 ms | 0.4× |
| 1600 | 14.10 ms | 8.8 | 40.49 ms | 0.3× | | (6400) 28.40 ms | 4.4 | 71.95 ms | 0.4× |

### Lineage

The pre-kernel, per-item-IrSelf engine's history (3.33× → 2.22× on the
product through OPT1–OPT-REDUCE) is recorded in
`zzz_current_work/postleo/HANDOVER_postleo.md`; the compile/kernel/runs
rework plan and its measured phase gates are in
`zzz_current_work/postleo/PLAN_obliterate_lark.md`. Phase results:
kernel (A) 2.22× → 1.45×; fused reduce (B) → 1.07×; derived runs (C) →
**0.52×**.

## References

- J. Earley (1970), *An Efficient Context-Free Parsing Algorithm*.
- J. Aycock & R. N. Horspool (2002), *Practical Earley Parsing* — nullable completion.
- J. M. I. M. Leo (1991), *A general context-free parsing algorithm running in
  linear time on every LR(k) grammar without using lookahead* — right-recursion.
- E. Scott (2008), *SPPF-Style Parsing From Earley Recognisers* — the shared packed
  parse forest via provenance links.
