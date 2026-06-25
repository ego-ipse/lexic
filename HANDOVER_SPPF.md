# Handover — SPPF ambiguity support for `parsing_2`

**Status:** feature complete and green. The recogniser, forest, public API,
reduce path, tests, and the memory fix are all done; `bash tools/run_checks.sh`
(ruff + pyright + pylint) and `uv run pytest tests/ -q` are fully green, including
the ABNF self-host fixpoint (`test_abnf_2.py`) — the correctness canary. The
machine is **no longer at risk**: the OOM was a specific bug (below), now fixed,
and unambiguous input is bounded.

What remains is **non-gating deferred robustness** (lazy enumeration + strict
short-circuit) — see "Remaining work". The separate performance effort lives in
`HANDOVER_OPTIMIZATIONS.md`.

---

## Goal

Replace Lark (`parsing/`) with `parsing_2`'s native Earley engine **without losing
power** — specifically, **support ambiguous grammars**. The chart's provenance
links are a **Shared Packed Parse Forest** (Scott 2008, *SPPF-Style Parsing From
Earley Recognisers*) so all derivations are representable.

## Approved API contract (settled with the user — implemented exactly)

- `parse(grammar, text) -> ParseTree` keeps its signature but is **strict**: on
  ambiguous input (root handle packs > 1 derivation) it **raises**
  `UnsupportedConstructError`. Unambiguous input returns the **identical** result
  as before and does **not** raise.
- Separate, honestly-named entries (no mode flag that mutates the return type):
  - `parse_forest(grammar, text) -> SppfNode | IrNone` — the SPPF root handle.
  - `derivations(grammar, text) -> IrSeq[ParseTree]` — ALL derivations (empty on
    no parse).
  - `is_ambiguous(grammar, text) -> IrInt` — truth value (`IrInt ∈ {0,1}`, the IR's
    no-`IrBool` rule).
- The forest **always** records every family (cheap, makes ambiguity detectable);
  "first"/"all" are reached only via the explicit entries.

**Where the API lives:** the five entries are thin wrappers in
`parsing_2/__init__.py`, each a one-line `NODE.eval(EarleyParser(), grammar,
IrTuple(IrStr(text)))` delegation. All orchestration is on `IrSelf` nodes in
`engine.py` (`Recognize`, `Parse`, `ParseForest`, `Enumerate`, `IsAmbiguous`,
fronted by `Accepting` which builds the chart once). `engine.py` has **no** free
functions.

---

## Design as implemented (file by file)

### `chart.py` — `Links` is a packed-family table
- `Links` now **subclasses `IrMultiMap[(item, end), Link]`** — it inherits the
  backing-dict singleton tuple, `key in links`, snapshot `links[key]` (a fresh
  `IrSeq`, safe to iterate while the live bucket grows), and identity eq/hash;
  the **only** override is `__iadd__`, which adds the SPPF **dedup** (`if link not
  in bucket`). A key with > 1 distinct family is an ambiguity point.
- `Link.child` is an `SppfNode` reference (shared, never flattened) or a terminal
  `IrLiteral`.

### `ops.py` — record families unconditionally; nullable identity
- `Complete.eval`: builds a shared `SppfNode(done, col)` (not an eager
  `BUILD_TREE`) and records a family **even when the advanced item already
  exists** — a second derivation is an ADDITIONAL family.
- `Predict.eval`: the nullable Aycock-Horspool advance records the **same**
  `SppfNode(EarleyItem(ref, arm, len(arm), col), col)` child the completer records,
  **per empty-deriving arm** (an arm derives empty when every item is a nullable
  ruleref — generalises to transitively-nullable rules). This is the OOM fix (see
  below). The logic is inline in `eval` (no helper methods — IrSelf protocol is
  `eval` + dunders only).

### `engine.py` — one chart, many readers, all on nodes
- `Accepting.eval(d, grammar, (IrStr(text),)) -> IrSeq(chart, item)` — shared
  front half; builds the chart once and finds the accepting start item.
- `Recognize` / `Parse` (strict) / `ParseForest` / `Enumerate` / `IsAmbiguous` —
  one `IrSelf` node each, driving `Accepting` then their own read. The public
  wrappers in `__init__.py` delegate to these.

### `forest.py` — SPPF node shapes + readers (all `IrSelf`, behaviour on `eval`)
- `ParseTree` — one derivation. `SppfNode(item, end)` — pure-data handle; families
  come from `chart.links`.
- `ForestCtx(chart)` — mutable read cursor with a `memo: (item,end) -> IrSeq` of
  expanded prefixes (sharing + cycle termination), rides `nc` like `ParseCtx`.
- `Prefixes.eval` — expands a handle to its kid-sequence prefixes via the
  `itertools.product` over each family's predecessor prefixes × consumed-child
  derivations. Memoised; seeds `IrSeq(IrSeq())` before recursing to terminate
  cycles. **Eager today** (see Remaining work).
- `Derivations.eval` — wraps a completed handle's prefixes into `ParseTree`s (all).
- `CHILD_TREES: IrTypeMap[IrSeq]` — `SppfNode`→`ChildTrees` (recurse via
  `DERIVATIONS`), `IrLiteral`→`Whole`. Typed `IrTypeMap[IrSeq]` so a direct
  `.eval` keeps its concrete return type (see the toolkit note).
- `BuildTree.eval` — strict single façade: enumerates via `DERIVATIONS`, raises if
  `len(trees) > 1`, else returns `trees[0]`. **Enumerates fully today** (see
  Remaining work).

### Toolkit change in `ir/mapping.py` (root-cause typing fix, not a cast)
`IrTypeMap` is now generic over its return type — `IrTypeMap[Ir_co: IrSelf =
IrSelf]` with an `eval -> Ir_co` override (mirroring `IrDispatch[Iri, Ir_co]`). A
table used **directly** as a dispatcher (e.g. `CHILD_TREES: IrTypeMap[IrSeq]`)
keeps its concrete result type instead of erasing to `IrSelf`, so consumers
iterate the result without a narrowing cast. The `= IrSelf` default leaves every
bare `IrTypeMap` (the common `IrDispatch.actions` case, consumed via `resolve`)
unchanged. This replaced the earlier `cast(...)` band-aid in `Prefixes.eval`.

---

## Root cause of the OOM (fixed — recorded for posterity)

`parse(ABNF_GRAMMAR, abnf_source)` exhausted memory because of **nullable
double-recording**, not generic spurious ambiguity. For a nullable rule the
advanced item `(item, end)` got **two** `Link` families that were the *same*
derivation in *different object shapes* — `ParseTree(ref, IrSeq())` from the AH
advance vs `SppfNode(empty_completion, col)` from the completer. `Link` equality is
tuple equality, and `ParseTree(...) != SppfNode(...)`, so dedup failed → every
nullable node had bucket size 2 → ~2^k spurious derivations along the
right-recursive `__rep` chains → OOM. ABNF is nullable-saturated (`*`/`?` desugar
to nullable synthetic rules). Fix: make both provenances reference the **same**
`SppfNode`, so they dedup to one family. Verified: buckets = 1 on unambiguous
input, exactly one derivation; genuine ambiguity (`S = S S / "a"`) still yields
every family.

---

## Remaining work — deferred robustness (non-gating)

With the nullable fix, **unambiguous** input yields exactly one family per node and
is memory-safe under the current eager enumeration, so these two refinements were
deferred. They matter only for **ambiguous** input, where the derivation count can
be exponential (e.g. Catalan growth for `S = S S / "a"`).

### 1. Lazy prefix enumeration (`forest.py` `Prefixes.eval`)
Today `Prefixes.eval` materialises the entire `itertools.product` of all families
at every node into an eager `IrSeq(*prefixes)`. For an ambiguous parse this
realises the whole forest into memory. Make it **stream** (generators) so
`derivations()` yields lazily and a caller can stop early.
- **Constraint:** keep the unambiguous single-derivation path byte-identical (the
  ABNF fixpoint canary must stay green).
- **Constraint:** preserve sharing + cycle termination. `ForestCtx.memo` currently
  caches a realised `IrSeq` per `(item, end)` and seeds `IrSeq(IrSeq())` before
  recursing to break cycles; a lazy rework must keep both (a shared sub-handle
  expanded once; cyclic recursion terminating) without re-expanding shared
  sub-handles or caching a half-consumed generator.

### 2. Strict `parse()` / `is_ambiguous()` short-circuit
`BuildTree.eval` (the strict façade, behind the `Parse` node) enumerates
**everything** via `DERIVATIONS` and only then checks `len(trees) > 1` — so it pays
the full (potentially exponential) enumeration just to discover "ambiguous".
`IsAmbiguous` has the same flaw (`len(derivations(...)) > 1`). Make both detect
">1 derivation" **without** full enumeration: walk families lazily and stop at the
second derivation (or build the single derivation greedily and raise the moment a
second family appears). Never materialise the full product to return one tree or to
decide ambiguity.

These compose: once `Prefixes` is lazy, both short-circuits are "take the first two
lazily". Suggested order: lazy `Prefixes` first, then `parse` / `is_ambiguous` on
top.

**Independent of `HANDOVER_OPTIMIZATIONS.md`:** F1 (left-recursion / the O(n²)
chart-construction scaling) is about *building* the chart; this is about *reading*
the forest. They don't conflict.

### Housekeeping
- Wiki + `log.md` not yet updated for the new public API / dropping the
  "unambiguous-only" caveats (CLAUDE.md asks for this).
- Repo-root scratch files `_t1.py`, `bench_parsing.py`, `_validate_radix.py` are
  still present — confirm before deleting.

---

## Hard constraints (the user's explicit rules)
- Keep IrSelf-derived objects; engine stays an IR construct (eval/dispatch + logic
  on classes; per-parse mutable state in a cursor like `ParseCtx`/`ForestCtx`).
  **No methods on nodes beyond `eval` + dunders.** Public free functions are the
  thin API wrappers in `__init__.py` only; any other deviation needs a written
  justification.
- Fix typing at the root (e.g. the `IrTypeMap[Ir_co]` generic), not with
  call-site casts where a real type fix is available.
- No `# type: ignore` / `# noqa` / `# pylint: disable`; no `exec`/`eval` builtins;
  no `from src.lexic...`. Error vocabulary (`UnsupportedConstructError`), no silent
  dispatch defaults. Sphinx docstrings, concise.

## Testing protocol
- The full suite is safe to run now (verified): `bash tools/run_checks.sh` and
  `uv run pytest tests/ -q`. The ABNF fixpoint is the correctness canary.
- When working on the lazy rework, still guard ambiguous-grammar experiments with a
  subprocess wall-clock `timeout` + `RLIMIT_AS` cap until laziness is proven — an
  ambiguous grammar over a long input is exponential by nature, and an eager bug
  there would reintroduce a blowup.
