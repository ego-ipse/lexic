# `lexic.parsing_2` — IR-native Earley parsing

`parsing_2` is the Lark replacement: a scannerless [Earley](https://en.wikipedia.org/wiki/Earley_parser)
parser that runs **directly over an `IrAst`**. No meta-grammar string, no Lark
grammar generation, no external parser. The premise is that **an `IrAst` already
*is* a grammar** — a set of named rules, each an alternation of sequences of
atoms — so it can drive a parser as-is.

The endgame is self-hosting. Take the ABNF-of-ABNF grammar expressed as IR
(`grammars/abnf_2.py`'s `ABNF_GRAMMAR`), emit its own source text, parse that text
back with itself, reduce the forest, and recover the identical `IrAst`. That
fixpoint — *parse the ABNF source of ABNF with the ABNF grammar and recover the
ABNF grammar* — is the proof that retires the hand-written meta-grammars.

```
                    ┌───────────────────────────────────────────────┐
   grammar (IrAst)  │  normalize()   →  Earley-shaped IrAst           │
        │           │      │                                          │
        │           │      ▼                                          │
        └──────────►│  EarleyParser  ──build──►  Chart (SPPF links)   │
   text (str)  ─────►│      │                        │                │
                    │      ▼                        ▼                 │
                    │  recognize / parse / parse_forest / derivations │
                    │                               │                 │
                    │                        ParseTree(s)             │
                    │                               │                 │
                    │      Reducer (flavour meta-notation)            │
                    │                               ▼                 │
                    │                          IrAst (recovered)      │
                    └───────────────────────────────────────────────┘
```

---

## 1. Public API

Everything hangs off five functions in `__init__.py`. Each is a thin wrapper that
boxes the input text and drives exactly one `IrSelf` orchestration node in
`engine.py`; the node owns all the logic and the wrapper returns its result
verbatim. Per the IR's no-`IrBool` rule, a truth value is an `IrInt ∈ {0, 1}`.

| Function | Returns | Meaning |
|---|---|---|
| `recognize(grammar, text)` | `IrInt` 0/1 | Does `text` derive from the start rule? (No forest built.) |
| `parse(grammar, text)` | `ParseTree` | The single derivation. **Raises** on no-parse *or* ambiguity. |
| `parse_forest(grammar, text)` | `SppfNode` \| `IrNone` | The shared packed parse forest root, or `IrNone` on no-parse. |
| `derivations(grammar, text)` | `IrSeq[ParseTree]` | *Every* derivation, nothing silently dropped. |
| `is_ambiguous(grammar, text)` | `IrInt` 0/1 | Does the input have more than one derivation? (Short-circuits at 2.) |

```python
from lexic.parsing_2 import parse, recognize
from lexic.parsing_2.normalize import normalize

g = normalize(MY_GRAMMAR)          # desugar to classical Earley shape first
assert recognize(g, "input text")  # IrInt(1)
tree = parse(g, "input text")      # a ParseTree
```

> **The grammar must be normalised first** (§7). The parser assumes classical
> Earley shape: every quantifier is `(1, 1)`, every group is a named rule, every
> literal is a single character. `normalize()` is the caller's responsibility, not
> the parser's — kept separate so the desugaring stays isolated from the parse loop.

---

## 2. The design in one sentence

**Every state object and every engine operation IS-AN `IrSelf`.** The chart, the
columns, the parse cursor, the forest nodes, the three Earley operations, the
driver loop, the reduction fold — all are IR nodes carrying the standard
`eval(d, n, nc) -> Ir_co` protocol. The parser is not "code that manipulates IR";
it is IR, dispatched on itself.

Concretely, the choice of Earley operation IS a **type dispatch on the symbol
after the dot**, run over the *same* `IrTypeMap` substrate the emit flavours use —
just pointed the other direction:

| symbol after the dot | meaning | operation |
|---|---|---|
| `IrRuleRef` | non-terminal | `Predict` |
| `IrLiteral` / `IrCharClass` / `IrRange` | terminal | `Scan` |
| `IrNoneType` (dot past the end) | arm complete | `Complete` |

`EARLEY_OPS` (in `ops.py`) is that dispatch table; `EarleyParser` (in `engine.py`)
IS-AN `IrDispatch` whose `actions` table is `EARLEY_OPS`. Resolving the next
operation is the inherited, memoised, concrete-first MRO dispatch. `IrRuleRef`
resolves to `Predict` ahead of the `IrStr` it subclasses — exactly the
concrete-first property the flavours rely on.

---

## 3. The Earley algorithm

### 3.1 Items and columns

An **Earley item** (`item.py`) is a dotted arm as a plain tuple:

```python
EarleyItem = tuple[IrRuleRef, IrSequence, int, int]
#                  rule_name   arm          dot  origin
```

`dot` is how far into the arm we've matched; `origin` is the input column where
this arm started. A plain tuple (not an IR node) is a deliberate perf choice: it's
engine state, never walked/emitted/reduced, and native tuple equality gives free
O(1) dedup and hashing.

The **chart** (`chart.py`) is a list of **columns**, one per input position. A
`Column` is an append-only, insertion-ordered, de-duplicated set of items. The
parser closes column *i* to a fixpoint, then scans one character to seed column
*i+1*, for *i* in `0 .. len(text)`.

### 3.2 The three operations

**Predict** (`Predict` in `ops.py`) — the dot faces non-terminal `ref`. For every
arm of `ref`, add a fresh dot-0 item originating at the current column. Each rule
is seeded at most once per column (the `column.predicted` set-of-names guard).

**Scan** (`Scan`) — the dot faces a terminal. This body is a **deliberate no-op**.
Terminals need no close-time action; the actual character match happens *between*
columns in the driver (`ScanColumn`), which reads the column's `scannable_by_atom`
index. `Scan` exists only to give terminals a (do-nothing) dispatch target — the
"deferral half" of scanning.

**Complete** (`Complete`) — the dot has reached the end of an arm; the item
recognised `rule_name` over `origin .. col`. Every item in column `origin` whose
dot faces that rule advances by one dot into the current column.

The driver closes a column by iterating it and dispatching each item's next
symbol. Predict/Complete *append to the column while it is being iterated* — this
is the Earley fixpoint, and it's why the column is one of the package's two
deliberate mutable leaves (see §9).

### 3.3 The mutable-chart exception

Everything in `lexic.ir` is otherwise immutable. The chart, columns, `ParseCtx`,
and `ForestCtx` are the documented exceptions: the predictor/completer add to a
column *while iterating it*, so a frozen tuple would be rebuilt on every insert
(quadratic). The mutation surface is kept to **dunders only** — `item in column`
(membership), `column += item` (insert) — so the leaves stay `eval` + dunders,
never named mutator methods.

---

## 4. The chart as a shared packed parse forest (SPPF)

Recognition alone only needs a yes/no. To recover *derivations*, the chart also
records **provenance links**, following Scott (2008, *SPPF-Style Parsing From
Earley Recognisers*).

`chart.links[(item, end)]` records **how** an advanced item was built: a set of
**packed families**, each a triple

```python
Link = tuple[EarleyItem, int, IrSelf]
#            predecessor  pred_end  consumed_child
```

- `predecessor` — the item one dot to the left.
- `consumed_child` — the node consumed to advance the dot: an `IrLiteral` terminal
  leaf (from a scan), or a **shared `SppfNode`** `(done, col)` referencing a
  completed sub-derivation (from a completion). Sub-derivations are *referenced,
  never flattened*, so the forest stays polynomial under ambiguity.

The key rule (Scott 2008): an `(item, end)` reached **more than one way** records
an *additional* family rather than dropping it. Identical families dedup. A key
with ≥ 2 distinct families is an **ambiguity point**. The link table is therefore
a shared, packed, binarised parse forest — and `forest.py` walks it as a DAG.

`Links` (in `chart.py`) IS-AN `IrMultiMap` overriding only `__iadd__` to add the
SPPF dedup on top of the inherited append.

---

## 5. Nullable rules (Aycock–Horspool)

A rule that can derive the empty string needs special care: a nullable `ref`
predicted *after* its own empty completion already fired in the current column
would otherwise never advance its waiter.

`NullableRules` (`engine.py`) computes the nullable set by least-fixpoint (a rule
is nullable if any arm is nullable; an arm is nullable if every item is a ruleref
to a nullable rule — the empty arm vacuously). It returns not just the names but,
per nullable ref, its **empty-deriving arms** — precomputed once.

When `Predict` faces a nullable ref, it advances the predicting item *immediately*
(Aycock–Horspool). Crucially, the consumed child it records for that advance is the
**same** `SppfNode` the completer would record for the empty completion. Recording
identical node identity lets `Links` dedup collapse the AH advance and the matching
empty completion into **one** family — so an unambiguous nullable derivation is
recorded once, while a rule with two genuinely distinct empty-deriving arms still
records both families (real ambiguity preserved).

---

## 6. Leo optimisation (right recursion)

A naïve Earley completer is Θ(n²) on right-recursive grammars: completing a
right-recursion chain re-walks the whole chain at every column. [Leo
(1991)](https://doi.org/10.1016/0304-3975(91)90180-A) fixes this: a **deterministic**
right-recursive reduction may jump straight to the chain's *topmost* item.

- `LeoItem` (`ops.py`) resolves the transitive (topmost) item by climbing the
  chain. A Leo candidate is the **unique** last-symbol waiter `[B → α • ref]` in
  the column (read from the small `waiting[ref]` bucket). Any second waiter — or
  one where `ref` isn't last — makes it non-deterministic and the normal completer
  runs. Nullable cycles are guarded with a lazily-allocated `seen` set (needed only
  on same-column empty-span steps; ordinary cross-column right-recursion never
  cycles). Closed columns memoise the result in `column.leo`.

- `Complete._try_leo` engages only for chains of length ≥ 2, so grammars of many
  *shallow* right-recursions stay on the normal completer.

The forest cost is deferred too. A Leo jump would otherwise elide the intermediate
completions the forest reader needs. So it files, under `(top_item, end)` in
`chart.leo_links`, the single **bottom** triple needed to rebuild the skipped
chain. `LeoExpand` (`forest.py`) materialises that chain into `chart.links`
**lazily** — only the first prefix request that actually reaches a deferred top
rebuilds it, bottom-up, O(chain) once. So only chains a derivation actually walks
are ever built: Θ(n) for one right-recursive parse instead of the eager Θ(n²).

---

## 7. Normalisation (`normalize.py`)

The IR is richer than textbook BNF, so three canonicalisations precede Earley. Run
in order, each assuming its predecessors (via `normalize()`):

1. **Flatten inline groups** (`FlattenGroups`) — an `IrAlternation` used as an atom
   (a parenthesised group) is hoisted to a fresh synthetic rule, so every atom
   after the dot is a ruleref or a terminal. The hoisted item keeps its quantifier.

2. **Desugar quantifiers** (`DesugarQuantifiers`) — a non-`(1, 1)` quantifier
   becomes a ref to a synthetic right-recursive rule:
   - `*` → `X = "" / elem X`   (nullable)
   - `+` → `X = elem / elem X`
   - `?` → `X = "" / elem`      (nullable)
   - bounded counts `{lo,hi}` unrolled into an optional chain.

3. **Split multi-char literals** (`SplitLiterals`) — scannerless Earley scans one
   character per column, so `IrLiteral("false")` becomes five single-char items.
   Run last, after a quantified literal has been moved into a synthetic rule.

Each transform is an `IrTransformer`: the generic `IrRebuild` default walks and
rebuilds the tree, so a transform only declares the node types where it *deviates*
— no hand-rolled `rules → arms → items` recursion. Synthetic rules carry the
`SYNTHETIC_PREFIX` (`"__"`) so the reduction step can recognise and collapse them.
A per-run `Minter` leaf mints collision-free names and collects the new rules; a
`memo` interns identical expansions so repeated quantifiers share one synthetic
rule (fewer rules → fewer Earley items).

> **Scaling.** The `*`/`+` desugaring produces *deterministic right recursion*
> (`X = "" / elem X`), which the Leo optimisation (§6) parses in **linear** time —
> `recognize`/`parse` of `[a-z]*` over N chars is flat at ~7.9 / ~13.0 µs/char. The
> one rough edge is **bounded counts**: `{lo, hi}` unrolls into `hi` nested
> synthetic rules and recurses `hi`-deep at desugar time, so a very large `hi`
> (≳ 1000) overflows the Python recursion limit. Unbounded/optional quantifiers are
> unaffected.

---

## 8. Forest & derivation extraction (`forest.py`)

Two node shapes sit over the chart's link table:

- **`SppfNode(item, end)`** — a shared, packed, *pure-data* handle for a dotted
  item over a span. Its families are `chart.links[(item, end)]`, read on demand.
  The same handle always exposes the same families (sharing); `> 1` family ⇒
  ambiguous. Intrinsically **binary** (one predecessor + one child per family), so
  the forest is binarised by construction.

- **`ParseTree(symbol, kids)`** — ONE derivation: a rule symbol over its children
  (sub-`ParseTree`s and consumed `IrLiteral` leaves, in source order). This is the
  reducible output. (The field is `kids`, not `children`, to avoid shadowing the
  `IrNamedTuple.children()` protocol.)

### 8.1 Depth-safety: the trampoline

A node's derivations are a lazy product over its families × predecessor prefixes ×
consumed-child derivations. Right-recursive grammars make that product *arbitrarily
deep* — a native nested-generator walk overflows the C stack at ~300 levels.

`trampoline.py` fixes this. A **cogen** is a generator (an IR node's `__iter__`)
that, rather than iterating a child directly, yields commands to the `Trampoline`
driver:

- `(ADVANCE, child)` — resume `child` to its next value; the driver sends it back,
  or `EXHAUSTED` when done.
- `(EMIT, value)` — `value` is one of my outputs.

Suspended cogens live as locals in their parent's frame, so the driver's explicit
Python list holds only the live spine — **depth lives in a list, never the C
stack**. The behaviour stays on `__iter__` (an allowed dunder). The three
enumeration cogens are:

- `NodeDerivs` — a completed handle → one `ParseTree` per prefix.
- `PrefixSource` — a handle → its kid-sequence prefixes (the lazy product; dot-0 is
  the single empty prefix; expands a deferred Leo top on first touch).
- `ChildDerivs` — one family's consumed child → its derivations (a terminal is its
  own sole derivation; a sub-`SppfNode` recurses via the trampoline).

A `ForestCtx` cursor carries the chart plus the set of **open** handles (prefixes
mid-production); a re-entrant request on an open handle is a genuine nullable cycle
and emits the single empty prefix to terminate it.

### 8.2 Lazy, replayable streams

`IrStream[T]` drives its source **once**, buffering each element so later consumers
replay without re-driving. `is_ambiguous` and `parse` exploit this: they take only
the first one or two derivations from the lazy `DERIVATION_STREAM` and never force
the (potentially exponential) full enumeration.

Public readers: `DERIVATION_STREAM` (lazy stream), `DERIVATIONS` (eager `IrSeq`),
`BUILD_TREE` (strict single derivation, **raises** on a second).

### 8.3 The iterative fast path

For the common unambiguous case, `BuildTree` first tries `_FastTree` — an iterative
walk of the binarised SPPF using an explicit work stack (frames
`(node, dest, slot, resolved)`) and a memo, bypassing the coroutine trampoline
entirely. It returns `IrNone` on a fast-path miss (ambiguity, or more than one link
on a key), and only then does `BuildTree` fall back to the trampolined stream.

---

## 9. Reduction: the meta-notation seam (`reduce.py`)

Recognition proves a derivation exists; **reduction** turns it into the target
`IrAst`. This is where a flavour's *meaning* attaches. A flavour's "meta notation"
is two tables:

- **`reductions`** — an `IrMap` from a rule's `IrRuleRef` to a body that folds the
  rule's matched children (arriving on the argument channel `nc`) into an IR node.
- **`noise` / `literal`** — a *cleaning policy*: which children are noise
  (whitespace, delimiters) and dropped before a body sees them.

`Reducer` IS-AN `IrDispatch` that folds a `ParseTree` bottom-up, dispatching on
`tree.symbol` (a *value*, hence it overrides `eval` rather than using the type-keyed
table). Each child contributes:

- `DROP` — nothing (non-semantic rule / inline terminal).
- `KEEP_RAW` — the terminal leaf unchanged.
- `KEEP_REDUCED` — the reduced child IR (default for semantic sub-rules).
- a spliced synthetic sub-tree — flattened in place (quantifier groups).
- `YIELD` — recover a subtree's *source text*, skipping non-semantic spans (for
  rules that yield text rather than build).

The fold is depth-safe. `_FastReduce` is an iterative explicit-stack walk (the
default path); `ReduceSource`/`ResolveSource` are the trampolined equivalents. A
`ReduceCtx` cursor memoises each node's reduction by `id`, so a `KEEP_REDUCED`
re-entry reads the memo rather than re-folding. Unlike `_FastTree`, a `ParseTree` is
already disambiguated by construction, so `_FastReduce` has no ambiguity fallback —
it always completes.

### Example: the ABNF reducer (`grammars/abnf_2.py`)

```python
ABNF_NOISE = IrMap(
    *(IrTuple(IrRuleRef(name), DROP) for name in
      ("wsp", "SP", "HTAB", "c-nl", "CR", "LF", "DQUOTE")),   # whitespace/delimiters
    IrTuple(IR_DEFAULT, KEEP_REDUCED),                        # everything else kept
)

ABNF_REDUCTIONS = IrMap(
    IrTuple(IrRuleRef("rule"),        IrBuild(IrRule)),
    IrTuple(IrRuleRef("alternation"), IrBuild(IrAlternation)),
    IrTuple(IrRuleRef("concatenation"), IrBuild(IrSequence)),
    IrTuple(IrRuleRef("rulename"),    IrBuild(IrRuleRef, IrTuple(YIELD))),
    # … num-val decodes hex/decimal digit-runs via IrUnradix, etc.
    IrTuple(IR_DEFAULT, YIELD),
)

ABNF_REDUCER = Reducer(reductions=ABNF_REDUCTIONS, noise=ABNF_NOISE, literal=DROP)
```

Feed a `ParseTree` from `parse(normalize(ABNF_GRAMMAR), abnf_source)` to
`ABNF_REDUCER.apply(...)` and you get back the `IrAst` — the self-hosting fixpoint.

---

## 10. Module map

| Module | Responsibility |
|---|---|
| `item.py` | `EarleyItem` — the dotted-arm tuple `(rule, arm, dot, origin)`. |
| `chart.py` | `Column` / `Chart` (mutable Earley sets) + `Links` (the SPPF provenance table) + deferred `leo_links`. |
| `ops.py` | `Predict` / `Scan` / `Complete` operation bodies, `LeoItem`, `ParseCtx` cursor, and the `EARLEY_OPS` dispatch table. |
| `engine.py` | `EarleyParser` (the `IrDispatch`), the `BuildChart` driver loop, `CloseColumn`/`ScanColumn`, grammar-derived index nodes (`RuleIndex`, `NullableRules`, `CharAccepts`), and the per-API orchestration nodes. |
| `forest.py` | `SppfNode` / `ParseTree`, trampolined enumeration cogens, `IrStream`, `_FastTree`, `LeoExpand`. |
| `reduce.py` | `Reducer` (forest → `IrAst`), the contribution policies (`DROP`/`KEEP_RAW`/`KEEP_REDUCED`/`YIELD`), `_FastReduce`. |
| `normalize.py` | Desugar IR into classical Earley shape (groups, quantifiers, literals). |
| `trampoline.py` | Depth-safe generator driver for the forest/reduce walks. |

---

## 11. Performance notes

The parser has been through several optimisation rounds. The load-bearing ideas:

- **Per-item indices.** On insert, a `Column` files each item under the symbol its
  dot faces: `waiting[ref]` (for the completer) and `scannable_by_atom[atom]` (for
  the scanner). So the completer reads only predecessors awaiting the finished rule,
  and the char-indexed scanner touches only items facing an atom that accepts the
  current char — never rescanning the whole column.

- **One `ParseCtx` per parse.** A single mutable cursor is reused across every
  dispatch (only `ctx.item`/`ctx.column` advance), eliminating the per-item
  `ParseCtx` + `IrTuple` allocation the dispatch protocol would otherwise pay
  (~67 K/parse gone).

- **`str`-keyed rule/nullable tables (OPT5).** `ParseCtx` mirrors the grammar
  indices as plain `str`-keyed dicts, because the table-key `IrRuleRef` and the
  grammar-atom `IrRuleRef` are distinct objects with equal hash but different
  identity — keying by `str` avoids an `IrScalar.__eq__` on every predictor probe.

- **Recognition skips the forest.** `recognize` flips `ctx.record_links = False`, so
  no SPPF links are recorded — recognition never reads the forest, so building it is
  wasted work.

- **Char-acceptance resolved once per char.** `char_accepts` is filled lazily: the
  first time a character is scanned, the grammar's terminal-atom set is filtered
  once; subsequent columns read the cached bucket.

- **Inlined hot-path dispatch.** `CloseColumn` inlines the two active operations
  behind an `isinstance` guard rather than paying the generic `IrDispatch` dict
  lookup + call per item (terminals are a no-op).

- **Leo (§6)** and the **iterative fast paths** (`_FastTree`, `_FastReduce`) keep
  right-recursive parses linear and off the C stack.

---

## 12. Invariants

- **Grammar is canonical.** The parser never mutates the grammar; it reads IR and
  produces IR.
- **IR-native.** Every state object and operation IS-AN `IrSelf`; logic lives on
  nodes, per-parse state lives on the mutable cursors (`ParseCtx`/`ForestCtx`), never
  in free functions.
- **Full SPPF.** Ambiguity is never silently resolved — `parse` raises on it;
  `parse_forest`/`derivations`/`is_ambiguous` expose every reading. Nullable-rule
  completion (Aycock–Horspool) and sharing (Scott 2008) are handled.
- **Depth-safe.** No tree walk recurses through the C stack; deep right-recursive
  derivations run on explicit lists/stacks (trampoline, `_FastTree`, `_FastReduce`).
- **Mutation is dunders-only.** The mutable-chart exception is confined to
  `Column`/`Chart`/`ParseCtx`/`ForestCtx`, and their mutation surface is `+=`, `in`,
  indexing, iteration — never named mutator methods.

## 13. Benchmark results

Measured with `zzz_current_work/bench_parsing.py` (2026-07-01). The benchmark is a
true stage-for-stage race against **Lark** (`parser='earley'`) on the ABNF
self-host workload — parse ABNF's own source text and recover its `IrAst`. Each
cell is the median ± stdev over interleaved samples (one of every variant per
round, so machine drift hits all variants alike). The `parse+reduce` row is the
headline product: text → `IrAst`, the object you actually ship.

**Fixpoint holds:** `earley IrAst == lark IrAst` — both paths recover the identical
grammar.

### ABNF self-host (920 chars/copy)

| input | stage | Lark | Earley (`parsing_2`) | earley / lark |
|---|---|---|---|---|
| x1 (920 ch) | recognize | 18.8 ± 0.3 ms | 30.6 ± 0.8 ms | 1.63× |
| | parse | 26.7 ± 0.4 ms | 47.5 ± 1.5 ms | 1.78× |
| | **parse+reduce** | 27.1 ± 0.4 ms | 56.3 ± 1.2 ms | **2.07×** |
| x2 (1840 ch) | recognize | 37.3 ± 0.5 ms | 59.4 ± 1.5 ms | 1.59× |
| | parse | 52.9 ± 0.7 ms | 94.4 ± 2.0 ms | 1.79× |
| | **parse+reduce** | 54.1 ± 0.6 ms | 112.6 ± 2.0 ms | **2.08×** |
| x4 (3680 ch) | recognize | 74.7 ± 1.9 ms | 121.7 ± 2.1 ms | 1.63× |
| | parse | 104.7 ± 1.2 ms | 193.5 ± 6.1 ms | 1.85× |
| | **parse+reduce** | 107.4 ± 0.7 ms | 232.0 ± 7.7 ms | **2.16×** |

At x4: **63.0 µs/char** (Earley) vs **29.2 µs/char** (Lark). The ratio is stable
across input sizes — the constant factor, not the asymptotics, is the gap. Lark's
transformer is compiled C-backed machinery; the `parsing_2` fold is pure-Python IR
dispatch. Closing it is a constant-factor tuning effort, not an algorithmic one.

### Deep right-recursion — `S = "a"*` (the asymptotic story)

This is the shape Leo (§6) targets. With Leo in place, `parse → tree` is now
**linear**, not the Θ(n²) a naïve Earley completer would give:

| N | Earley | µs/N | µs/N² | Lark | earley / lark |
|---|---|---|---|---|---|
| 100 | 1.40 ms | 13.98 | 0.140 | 2.80 ms | 0.5× |
| 200 | 2.61 ms | 13.04 | 0.065 | 5.51 ms | 0.5× |
| 400 | 5.21 ms | 13.03 | 0.033 | 10.84 ms | 0.5× |
| 800 | 10.50 ms | 13.13 | 0.016 | 20.18 ms | 0.5× |
| 1600 | 20.72 ms | 12.95 | 0.008 | 40.79 ms | 0.5× |

`µs/N` is flat (~13) and `µs/N²` falls toward zero — the signature of linear
scaling. On this shape `parsing_2` **beats Lark 2×**. `recognize` (Earley → bool vs
Lark → forest) is likewise linear and ~0.8× Lark:

| N | Earley | µs/N | Lark | earley / lark |
|---|---|---|---|---|
| 200 | 1.57 ms | 7.84 | 1.94 ms | 0.8× |
| 800 | 6.59 ms | 8.24 | 8.25 ms | 0.8× |
| 1600 | 12.79 ms | 7.99 | 15.68 ms | 0.8× |
| 3200 | 25.34 ms | 7.92 | 33.52 ms | 0.8× |
| 6400 | 52.71 ms | 8.24 | 68.79 ms | 0.8× |

**Takeaway:** algorithmically `parsing_2` is competitive — linear on the hard
right-recursive shape (winning outright), and asymptotically sound elsewhere. On
the realistic mixed ABNF workload it trails Lark by a stable ~2× constant factor on
the full text→`IrAst` product, which is a Python-vs-C tuning gap rather than a
complexity problem. Repeated `*`/`+` quantifiers parse in linear time thanks to Leo
(the desugared right recursion is deterministic — see §6/§7); the only remaining
sharp edge is very large *bounded* counts `{lo, hi}`, which recurse `hi`-deep at
desugar time (§7).

## References

- J. Earley (1970), *An Efficient Context-Free Parsing Algorithm*.
- J. Aycock & R. N. Horspool (2002), *Practical Earley Parsing* — nullable completion.
- J. M. I. M. Leo (1991), *A general context-free parsing algorithm running in
  linear time on every LR(k) grammar without using lookahead* — right-recursion.
- E. Scott (2008), *SPPF-Style Parsing From Earley Recognisers* — the shared packed
  parse forest via provenance links.
