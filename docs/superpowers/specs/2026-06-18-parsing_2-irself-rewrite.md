# `parsing_2` → pure `IrSelf` — change catalog

**Date:** 2026-06-18
**Scope:** every file in `src/lexic/parsing_2/`. No real code here — this is the
map of *what changes* before any plan is written.

## The four rules

1. Every class descends from `IrSelf`.
2. No functions outside classes (no module-level `def`).
3. The only methods on a class are `eval` and dunders — **except** the
   explicitly-allowed library entry points.
4. State is held in `IrSelf` data structures (`IrMap`, `IrSeq`, `IrTuple`,
   `IrNamedTuple`, scalar leaves) — **except** where explicitly allowed.

## Exceptions requested (need your yes/no)

These are the only places the rules would otherwise force an unnatural shape.
Listing them so the rest of the catalog can assume them settled.

| # | Exception | Why |
|---|---|---|
| E1 | `parse` / `recognize` stay as the package's two entry points | Rule 3 reserves named methods for entry points; these are them. Question: methods on the parser, or thin module wrappers? |
| E2 | Plain `int` / `str` as **scalar payload** (e.g. `dot`, `origin`, `col`, rule names) | Already the established IR convention — `IrQuantifier.lo: int`, `IrRule.name: str`. Not introducing `IrInt`/`IrStr` for engine indices. |
| E3 | **One** mutable container leaf for the Earley chart | The chart is grown while iterated (the Earley fixpoint); `chart.py` already documents this as a deliberate concession. Alternative is a fully functional rebuild-per-step engine (slower, see Open Q2). |

## Per-file changes

### `item.py` — `EarleyItem`
- Already `IrSelf`. Violations: the four accessors `is_complete`, `next_item`,
  `next_symbol`, `advance` (rule 3).
- Change: fold each into the operation bodies that use them, or re-express as
  `IrSelf` operation nodes evaluated against the item on `nc`. `advance`
  (item → item) and `next_symbol` (item → atom/`IrNone`) are the two the
  driver and `ops` actually call.

### `chart.py` — `Column`, `Chart`, `Link`
- `Link` bare-`tuple` alias → an `IrNamedTuple` record `(predecessor,
  predecessor_end, child)` (rule 4).
- `Column`: `list`/`set` state → `IrSeq` + dedup, `add`/`__iter__`/`__len__`/
  `__getitem__` collapse to dunders. `add`'s "was-new" boolean is the part that
  needs the mutable-leaf exception (E3) or the functional rewrite.
- `Chart`: `list` columns + `dict` links → `IrSeq` of `Column` + `IrMap`
  keyed on `(item, end)`; `ensure` becomes a dunder/eval, not a named method.

### `item.py` + `chart.py` keys
- `IrMap` link keys are `(EarleyItem, int)` tuples today. Confirm they key
  cleanly under `IrScalar` type-aware equality, or wrap in an `IrNamedTuple` key.

### `ops.py` — `ParseCtx`, `Predict`, `Scan`, `Complete`, `EARLEY_OPS`
- `Predict`/`Scan`/`Complete` already `IrSelf` with only `eval` — keep.
- Kill module functions `_ctx`, `_advance_over_empty` (rule 2): `_ctx` is a
  trivial `nc[0]` read that inlines; `_advance_over_empty` becomes an `IrSelf`
  operation node (the predictor's Aycock-Horspool step) the `Predict` body
  evaluates, not a free function.
- `ParseCtx.nullable: frozenset[str]` → `IrSeq`/`IrMap` set (rule 4).
- Remove the `build_tree` free-function call (see `forest.py`).

### `forest.py` — `ParseTree`, `build_tree`
- `ParseTree` already clean.
- `build_tree` (rule 2 + local `list`): becomes an `IrSelf` operation node whose
  `eval` walks the provenance links and assembles the tree. Both call sites
  (`engine`, `ops` `Complete`) dispatch it instead of calling a function.

### `engine.py` — `EarleyParser`, `_ParseInputs`, free functions
- `_index`, `_nullable_rules` (+ 3 nullability helpers), `_matches` (rule 2):
  re-home as `IrSelf` operation nodes — a rule-index builder, a nullable-set
  builder, a terminal-match predicate. Each is `eval`-only.
- `_ParseInputs.nullable: frozenset` → `IrSeq`/`IrMap` (rule 4).
- `EarleyParser` driver methods `_build_chart`/`_close_column`/`_scan`/
  `_accepting_item` (rule 3): this is the hard core — the imperative loop must
  become `eval` bodies. See Open Q1/Q2.
- `recognize`/`parse`: keep as the entry points (E1).

### `normalize.py` — `_Rewriter` + 8 free functions
- `_Rewriter` is a plain class (rule 1) with ~12 named methods (rule 3) and
  `set`/`list` minting state (rule 4): becomes one or more `IrSelf` rewrite
  nodes whose `eval` does the rule-walk. The name-minting counter is mutable
  state — either a mutable-leaf exception or threaded functionally.
- `split_literals`/`flatten_groups`/`desugar_quantifiers`/`is_synthetic_name`/
  `_ref` (rule 2): the three rewrites become `IrSelf` transformer nodes; the
  ordering precondition (flatten → desugar → split) becomes a composed node.
- `SYNTHETIC_PREFIX`, `_ONE`: constants stay (data), `IrStr`/already-IR.

### `reduce.py` — `Reducer`
- `reduce`/`_reduced_children` (rule 3) + local `list` (rule 4): the bottom-up
  fold, synthetic-splice, and child-cleaning become `eval` bodies on `IrSelf`
  nodes. This is the same kind of work as the engine driver — a dispatch walk
  that today is hand-rolled in Python.

### `__init__.py`
- Imports + `__all__` only. No change beyond following renames.

## Open design questions (resolve before the plan)

**Q1 — How does the imperative Earley driver become `eval`-only?**
The loop (per column: predict/complete to fixpoint, then scan) is the one place
where "express the algorithm as `IrSelf` nodes" is non-trivial. Candidate shape:
a small set of driver operation nodes (`CloseColumn`, `Scan`, `BuildChart`)
whose `eval` carries the iteration, with the chart as the threaded state on `nc`.
The fixpoint cursor-walk and the `range(len(text)+1)` loop still need *some*
iteration construct — a Python loop inside an `eval` body, or an IR recursion
node.

**Q2 — Mutable chart (E3) vs. functional rebuild?**
- *Mutable-leaf* (recommended): keep `Chart` a single mutable `IrSelf` leaf,
  matching today's documented concession. Minimal churn, fast.
- *Functional*: every insert returns a new `IrMap`/`IrSeq` chart. Fully rule-4
  pure, no exceptions, but O(n) rebuilds inside an already O(n³) algorithm.

**Q3 — Accessor nodes vs. inlining (item.py).**
`advance`/`next_symbol` etc.: promote to first-class `IrSelf` operation nodes
(reusable, verbose), or inline their bodies into the operations that call them
(fewer nodes, some duplication)?

**Q4 — Does the `Reducer` rewrite share machinery with the engine driver?**
Both are "hand-rolled dispatch walks → `eval` bodies." Decide whether they reuse
a common walk node or stay separate.

## Suggested order (once Qs are answered)

1. Leaf state first — `chart.Link`, `Column`, `Chart` data shapes (rules 1/4).
2. `item.py` accessors (Q3).
3. `forest.build_tree` → node.
4. `ops.py` free functions → nodes.
5. `normalize._Rewriter` → `IrSelf` rewrite nodes.
6. `reduce.Reducer` fold → `eval` bodies.
7. `engine.py` driver → `eval` bodies (the hard one, Q1/Q2).
8. `__init__.py` + entry points (E1).

---

## Implementation outcome (2026-06-19 — src complete)

All eight files rewritten and compliant. Verified by: ABNF self-hosting fixpoint
green; group-hoisting + `+`/`{2,3}` quantifier desugaring parse correctly; `ruff`
check + format clean; the 816 non-`parsing_2` tests still pass. `parsing_2` /
`abnf_2` tests are **not yet ported** (next step).

**Decisions taken (resolving the Open Qs / exceptions):**
- **E1** — entry points are module-level functions: `engine.parse`, `engine.recognize`,
  and `normalize.{flatten_groups,desugar_quantifiers,split_literals,normalize}`.
- **E2** — plain `int`/`str` allowed as scalar payload only.
- **E3** — granted: the chart leaves (`Chart`/`Column`/`Links`) hold mutable
  `list`/`set`/`dict` internally, mutated via dunders (`in`, `+=`, `[k]=…`).
- **Q1** — Python loops live inside `eval` bodies (approach "A").
- **Q2** — mutable chart (not functional rebuild).
- **Q3** — `EarleyItem` accessors inlined at call sites (no trivial nodes).
- **Q4** — reducer fold and engine driver are separate walks.
- **normalize** — final design (option 1's dict-on-`nc` was tried then dropped as
  ugly/untyped): the three transforms are `IrTransformer` subclasses, so
  `IrRebuild`'s auto-walk does the `rules → arms → items` recursion (no hand-rolled
  loops). Minting state is a mutable `Minter` `IrSelf` leaf carried on the
  transformer (a field, fresh per call via `Field(default_factory)`), reached by
  action bodies through the dispatcher `d`; quantifier recursion passes bounds as
  `IrInt`, so `nc` stays `Sequence[IrSelf]`. No dict, no `Sequence[object]`.
- Rule-4 reading: governs *stored state*; transient locals inside an `eval`
  (building an `IrSeq`/`IrTuple`) are implementation, not state.

## API changes (the test-port contract)

Removed / renamed (old → new):
- `forest.build_tree(chart, item, end)` → `forest.BUILD_TREE.eval(d, item, IrTuple(chart, IrInt(end)))` (node `BuildTree`).
- `EarleyParser().parse(g, t)` / `.recognize(g, t)` → module-level `parse(g, t)` / `recognize(g, t)`.
- `Reducer(...).reduce(tree)` → `Reducer(...).apply(tree)`.
- `Column.add(item) -> bool` → `item in column` then `column += item`.
- `Chart.ensure(i)` → gone (indexing `chart[i]` auto-grows); `Chart.columns` → private `_columns` (use `chart[i]`, `len(chart)`).
- `Column.to_scan` → gone (driver re-derives scannable items by filtering the closed column).
- `chart.links[(item,end)]` now returns a `Link` record (`.predecessor`, `.predecessor_end`, `.child`) instead of a bare 3-tuple.
- `EarleyItem.is_complete` / `.next_item()` / `.next_symbol()` / `.advance()` → inlined; gone.
- `normalize.is_synthetic_name(name)` → removed (use `name.startswith(SYNTHETIC_PREFIX)`).

New symbols: `chart.{Link,Links}`, `forest.{BuildTree,BUILD_TREE}`,
`engine.{RuleIndex,NullableRules,Matches,AcceptingItem,CloseColumn,ScanColumn,BuildChart}`
(+ singletons `RULE_INDEX`/`NULLABLE`/`MATCHES`/`ACCEPT`/`CLOSE_COLUMN`/`SCAN_COLUMN`/`BUILD_CHART`;
the driver loop is split across `CloseColumn`/`ScanColumn`, orchestrated by `BuildChart`),
`reduce.{ResolveChildren,RESOLVE_CHILDREN}`,
`normalize.{Minter,SplitSeq,HoistItem,DesugarItem,CollectRules,Expand,OptChain,SplitLiterals,FlattenGroups,DesugarQuantifiers,normalize}`
(transforms are `IrTransformer` subclasses; `Expand`/`OptChain` have singletons
`EXPAND`/`OPT_CHAIN`). `ParseCtx.nullable` is now an `IrSeq` (was `frozenset`).

Test-porting rule: fix construction/call syntax to the new API, keep assertions;
remove a test only when its exact target symbol was deleted (e.g. `is_synthetic_name`,
`build_tree`, `Column.add`/`.ensure`, the `EarleyItem` accessors).
