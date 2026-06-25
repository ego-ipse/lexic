# Handover — SPPF ambiguity support for `parsing_2`

**Status:** in-progress, (memory-unsafe — do not run against
the ABNF self-host until the blowup below is fixed). Recogniser + forest + public
entry points are written; reduce-enumeration, tests, wiki, and the memory fix remain.


---

## Goal

Replace Lark (`parsing/`) with `parsing_2`'s native Earley engine **without losing
power** — specifically, **support ambiguous grammars**. Today's engine modelled
only the single-derivation (unambiguous) case. This work makes the chart's
provenance links a **Shared Packed Parse Forest** (Scott 2008, *SPPF-Style Parsing
From Earley Recognisers*) so all derivations are representable.

## Approved API contract (settled with the user — implement exactly this)

- `parse(grammar, text) -> ParseTree` keeps its signature but is **strict**: on
  ambiguous input (root handle packs > 1 derivation) it **raises**
  `UnsupportedConstructError` ("use the forest/enumerator"). Unambiguous input must
  return the **identical** result as before and must **not** raise. Rationale: a
  single `ParseTree` cannot honestly represent a forest, so never silently pick one.
- Separate, honestly-named entries (no mode flag that mutates the return type):
  - `parse_forest(grammar, text) -> SppfNode | IrNone` — the SPPF root handle.
  - `derivations(grammar, text) -> IrSeq[ParseTree]` — ALL derivations (empty on no
    parse). The explicit "give me everything" path; nothing silently discarded.
  - `is_ambiguous(grammar, text) -> bool`.
- The forest **always** records every family (cheap, makes ambiguity detectable);
  "first"/"all" are reached only via the explicit entries.

These are all **implemented** in the stashed `engine.py`.

---

## Design as implemented (file by file)

### `chart.py` — `Links` is now a packed-family table
- `Links._table: dict[(item, end), list[Link]]` (was a single `Link`).
- Surface (dunders only): `key in links`; `links[key]` returns a fresh `IrSeq`
  snapshot of families (empty on miss, safe to iterate while the live list grows);
  `links += (key, link)` appends a family **deduped** by `link not in bucket`.
- `Link.child` is now an `SppfNode` reference (shared, never flattened) or a
  terminal `IrLiteral`.

### `ops.py` — record families unconditionally
- `Complete.eval`: builds a shared `SppfNode(done, col)` (NOT an eager
  `BUILD_TREE`) and records a family **even when the advanced item already exists**
  (dropped the `if advanced not in current` guard) — a second derivation of the same
  item is an ADDITIONAL family. **Note:** this already lands the perf review's
  "defer eager subtree build in Complete" win — see the optimizations handover.
- `Predict.eval`: nullable Aycock-Horspool advance likewise records its
  empty-derivation `ParseTree` family unconditionally.

### `engine.py` — one chart, many readers
- `_accepting(grammar, text) -> (parser, chart, item, end)`: shared front half;
  builds the chart once and finds the accepting start item.

  ⚠️ **IrSelf-purity deviation to review:** `_accepting` is a **module-level free
  function**, and `parse_forest`/`derivations`/`is_ambiguous` are free functions
  too (matching the pre-existing `recognize`/`parse`). The rule is "no free
  functions; prefer eval/dunders." The pre-existing entry points were already free
  functions, so this is consistent with what was there — but it was **not**
  explicitly justified/approved. Flag for the user: either accept (entry-point
  orchestration mirrors the old shape) or re-home onto an `IrSelf` dispatch node.
- `recognize`, `parse` (strict), `parse_forest`, `derivations`, `is_ambiguous` —
  all wired over `_accepting`.

### `forest.py` — the SPPF node shapes + readers (all `IrSelf`, behaviour on `eval`)
- `ParseTree` — one derivation (unchanged).
- `SppfNode(item, end)` — pure-data handle; families come from `chart.links`. Claims
  to be intrinsically binary (one predecessor + one child per family) so "binarised
  by construction." **This claim is the crux of the bug below — verify it.**
- `ForestCtx(chart)` — mutable read cursor with a `memo: (item,end) -> IrSeq` of
  expanded prefixes (sharing + cycle termination). Rides `nc` like `ParseCtx`.
- `Prefixes.eval` — expands a handle to its kid-sequence prefixes: dot 0 → single
  empty prefix; else the **`itertools.product`** over each family's predecessor
  prefixes × consumed-child derivations. Memoised per `(item, end)`; seeds the memo
  with `IrSeq(IrSeq())` before recursing to terminate cycles.
- `Derivations.eval` — wraps a completed handle's prefixes into `ParseTree`s (all).
- `CHILD_TREES` (`IrTypeMap`): `SppfNode`→`ChildTrees` (recurse via `DERIVATIONS`),
  `IrLiteral`/`ParseTree`→`Whole` (own sole derivation).
- `BuildTree.eval` — strict single façade: enumerates via `DERIVATIONS`, raises if
  `len(trees) > 1`, else returns `trees[0]`.

---

## 🔴 CRITICAL: the memory blowup (why it OOMs the machine)

Running `parse(ABNF_GRAMMAR, abnf_source)` (the self-host fixpoint) exhausts memory
and crashes the PC. **Do not run it.** Two compounding causes:

1. **Spurious ambiguity from naive Earley→SPPF.** Removing the first-insertion guard
   and recording a family on every re-derivation is only correct with Scott's
   specific intermediate/packed-node identity. `SppfNode`'s "binary by construction"
   claim is the load-bearing assumption — if a family's identity does not collapse
   *equivalent* derivations reached through different item orderings, the **even
   unambiguous ABNF grammar accumulates many families per node**, i.e. spurious
   ambiguity. The right-recursive `__rep` rules (from `normalize.py`) are exactly
   where O(n) complete items per column pile up.

2. **Eager full enumeration.** `Prefixes.eval` materialises the **entire**
   `itertools.product` of all families at **every** node into `IrSeq(*prefixes)` —
   no laziness. Combined with (1), the product explodes combinatorially and is
   realised into memory. Worse: **`parse()` (strict-single) still enumerates
   *everything* via `DERIVATIONS` before checking `len(trees) > 1`** — so it pays the
   full explosion just to discover "ambiguous," instead of short-circuiting at the
   second derivation.

### Fix direction (for whoever resumes)
- **Verify/repair family identity first.** Before any enumeration, confirm the
  unambiguous ABNF grammar yields **exactly one family per `(item, end)`**. Instrument
  `Links` bucket sizes on a *tiny* input. If buckets exceed 1 on unambiguous input,
  the SPPF construction has spurious ambiguity — this is the real bug, and likely
  needs Scott's intermediate-node binarisation scheme (don't rely on `SppfNode`'s
  implicit-binary claim without proof).
- **Make `parse()` short-circuit.** It must detect ">1 derivation" *without* fully
  enumerating — e.g. ask the root handle for ambiguity by walking families lazily and
  stopping at the second, or build the single derivation greedily and only raise when
  a second family is encountered. Never materialise the full product to return one tree.
- **Make enumeration lazy** (generators, not eager `IrSeq(*...)`), so `derivations()`
  streams and a caller can stop early.

---

## Remaining work

1. **Fix the memory blowup** (above) — gating; nothing else is safe until this is done.
2. **`reduce.py` enumeration.** Likely small: `derivations()` already returns
   `IrSeq[ParseTree]`, so "reduce all" = map the existing single-tree `Reducer` over
   each tree. The `Reducer` itself should need no change (keep the single-derivation
   path identical → fixpoint stays green). Add a thin "reduce every derivation" entry
   only if the user wants reduce-side enumeration; confirm with them.
3. **`__init__.py`** — export `parse_forest`, `derivations`, `is_ambiguous`, `SppfNode`.
4. **Tests** (`tests/unit/lexic/parsing_2/`):
   - New ambiguous-grammar tests on a **tiny** input (e.g. `S = S S / "a"` over
     `"aaa"`, or `E = E "+" E / "a"`): recogniser accepts; `is_ambiguous` true;
     `derivations` yields the expected distinct trees; strict `parse` raises.
   - **Port** existing `test_chart.py` / `test_forest.py` / `test_init_parsing_2.py` /
     `test_reduce.py` to the new APIs (`links += (key, link)`, families list, new
     forest nodes). Fix construction/calls, keep assertions; delete a test only if its
     exact target symbol was removed.
5. **Wiki + log** — drop the "unambiguous-only / SPPF not shown" caveats in
   `forest.py` and `chart.py` module docstrings are already updated; mirror that in
   `.wiki/` and add a `log.md` entry. Document the new public API.
6. **Cleanup** — delete throwaway `_t1.py` at repo root (confirm it's scratch first).

## Hard constraints (the user's explicit rules)
- Keep IrSelf-derived objects; engine stays an IR construct (eval/dispatch + logic on
  classes; per-parse mutable state in a cursor like `ParseCtx`/`ForestCtx`, not free
  functions/NamedTuples). **The free-function entry points above need an explicit
  decision** (accept or re-home).
- No free functions/methods beyond that; prefer `eval`/dunders; prefer `IrSelf`.
  Any bent rule needs a written justification.
- No `# type: ignore` / `# noqa` / `# pylint: disable`; no `exec`/`eval` builtins; no
  `from src.lexic...`. Error vocabulary (`UnsupportedConstructError`), no silent
  dispatch defaults. Sphinx docstrings, concise.

## Testing protocol (learned the hard way)
- **NEVER** run the SPPF code against the full ABNF self-host until family identity is
  proven bounded. Use 3–5 character inputs.
- Add a hard guard when experimenting: run under a subprocess with a wall-clock
  timeout and an RLIMIT_AS memory cap so a blowup fails fast instead of taking the
  machine down.
- The ABNF fixpoint (`test_abnf_2.py::test_self_hosting_fixpoint`) is the canary for
  *correctness* once memory is safe — but it is the **worst** thing to run while the
  blowup exists.
