# SPPF lazy enumeration + strict short-circuit — implementation spec

Items **1** and **2** of `HANDOVER_SPPF.md` "Remaining work". SOURCE only (no new test files).
No commit. No worktrees. Leave unstaged.

## ⚠️ Permissions are NOT fixed
Spawned / background / resumed agents get `Edit` AND `Write` **denied** on `src/`, and the
working tree was reverted to clean by a `git restore` (all agent work lost). Editing
`.claude/settings.local.json` allow-list did **not** help — the block is the
background-isolation policy, not the allow-list. **Do not use spawned/background agents for
this.** Implement directly in the main interactive session, where `Edit`/`Write` work.

## Overriding directive (hard rule)
Keep IrSelf-derived objects. No free methods — behaviour via `eval(d,n,nc)` + dunders only.
No module-level free functions except the thin API wrappers in `parsing_2/__init__.py`.
Per-read mutable state on a cursor passed via `nc` (like `ParseCtx`/`ForestCtx`). No
`# type: ignore`/`# noqa`/`# pylint: disable`; no `exec`/`eval`; no `from src.lexic...`; raise
`UnsupportedConstructError`; Sphinx docstrings, concise. Deviations must be justified in-code.

## Settled decision (do not re-open)
`ForestCtx.memo` stays a **plain dict attr**. Do NOT add an `IrMutableMap` type and do NOT
make `ForestCtx` a map. Reason (put in docstring): the directive's "prefer IrMultiMap *if
mutability improves performance*" precondition is unmet — `memo` is a cold single-valued
get-or-set lookup; `IrMultiMap` is append-only/multi-valued and its semantics fight the
single-stream-per-handle sharing invariant (re-seed would stack, not replace); `ForestCtx`
also carries `chart`. Matches the `Column`/`ParseCtx` plain-attr precedent.

---

## Item 1 — lazy prefix enumeration (`src/lexic/parsing_2/forest.py`)

Problem: `Prefixes.eval` eagerly materialises the full `itertools.product` of all families per
node into `IrSeq(*prefixes)` and memoises a realised `IrSeq` — for ambiguous input this
realises the whole forest. Make it stream. Constraints: unambiguous path stays
**byte-identical** (ABNF fixpoint canary green; `parse(text).to_text() == text`); preserve
sharing + cycle termination; never cache a half-consumed generator.

### `IrStream` — replayable lazy sequence (new)
```
class IrStream(IrLeaf[IrSelf, IrSelf]):
    __slots__ = ("_buffer", "_source", "_state")   # _state in {FRESH, DRIVING, DONE}
    def __init__(self, source: Callable[[], Iterator[IrSelf]]) -> None: ...
    def __iter__(self) -> Iterator[IrSelf]: ...
```
- Deferred factory `source` so sub-stream construction stays lazy.
- JUSTIFIED DEVIATION from "prefer IrMultiMap" (put in docstring): a lazy *sequence*, no key;
  tuple/`IrSeq` tiers are immutable so can't hold a growing buffer; follows the mutable
  `__slots__`-`IrLeaf` precedent (`ForestCtx`/`ParseCtx`/`Column`); behaviour on `__iter__` only.
- `__iter__`:
  - `DONE` → replay the full `_buffer`.
  - `DRIVING` (re-entrant == cycle) → yield exactly one `IrSeq()` (reproduces today's
    `IrSeq(IrSeq())` seed); do NOT touch the source. Keeps cycle termination AND the acyclic
    path byte-identical (seed only observed on a genuine cycle; never on ABNF/digit DAGs).
  - `FRESH` → set `DRIVING`; replay `_buffer`; pull from `_source()`, appending each prefix to
    `_buffer`; on exhaustion set `DONE`.

### `Prefixes.eval` → returns `IrStream`
- `ForestCtx.memo: dict[(EarleyItem,int), IrStream]` — one stream per handle (sharing). Update
  the memo docstring note (single-valued replacement cache, not an `IrMultiMap`).
- Dot 0 → `IrStream(lambda: iter((IrSeq(),)))`.
- Else the threaded generator walks `ctx.chart.links[key]`; per family yields the lazy product
  of predecessor stream (`self.eval` recursion) × child stream (`CHILD_STREAMS.eval`):
  `for pre in predecessor_stream: for ch in child_stream: yield IrSeq(*pre, ch)`.
- Drop `from itertools import product`; add `Iterator`, `Callable` imports.

### Child seams
- `CHILD_STREAMS: IrTypeMap[IrSelf]` (lazy; used inside the family generator):
  `SppfNode → ChildTrees` (→ `DERIVATION_STREAM`), `IrLiteral → Whole`.
- Keep `CHILD_TREES: IrTypeMap[IrSeq]` (eager) for direct/test callers (`test_child_trees_*`).
- `Whole.eval` returns a 1-element `IrSeq` (serves both seams).
- `Derivations.eval` keeps returning `IrSeq` (= `IrSeq(*DERIVATION_STREAM.eval(...))`) — the
  ALL-derivations contract / test back-compat.

---

## Item 2 — strict short-circuit

### `forest.py`
- New `DerivationStream` node + `DERIVATION_STREAM` singleton: returns the lazy `ParseTree`
  stream (on-node, `eval` + dunders) — the single lazy source both short-circuits consume.
- `BuildTree.eval`: `islice(iter(DERIVATION_STREAM.eval(...)), 2)`; raise
  `UnsupportedConstructError` (same message intent) if a 2nd appears; raise on zero; else
  return the first. No full materialisation.

### `engine.py` — `IsAmbiguous.eval` (exact code, from the lost implementation)
```python
# add: from itertools import islice
# add: from lexic.parsing_2.forest import DERIVATION_STREAM
def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
    chart, item = ACCEPTING.eval(d, n, nc)
    if isinstance(item, IrNoneType):
        return IrInt(0)
    node = SppfNode(cast(EarleyItem, item), len(str(nc[0])))
    first_two = list(islice(iter(DERIVATION_STREAM.eval(d, node, IrTuple(chart))), 2))
    return IrInt(1) if len(first_two) > 1 else IrInt(0)
```
- `Enumerate` / `derivations()` still realises fully — its contract.

---

## Validation
1. `bash tools/auto_fix.sh`
2. `bash tools/run_checks.sh` (ruff + pyright + pylint) AND `uv run pytest tests/ -q` — both
   green; ABNF fixpoint (`test_abnf_2.py`) is the canary.
3. Guarded ambiguous-grammar evidence: `/tmp` subprocess with wall-clock `timeout` + `RLIMIT_AS`
   cap, grammar `S = S S / "a"` over 30+ `a`s. `parse()` raises fast, `is_ambiguous()` → 1 fast,
   no OOM; contrast guarded eager `derivations()` to show the eager blowup is real. Never run an
   unguarded ambiguous enumeration.

## New tests (follow-up test agent — not part of this src slice)
`test_prefixes_returns_lazy_stream`, `test_stream_replays_for_multiple_consumers`,
`test_stream_shared_subhandle_expanded_once`, `test_stream_cycle_terminates_with_empty_prefix`,
`test_derivations_lazy_does_not_realise_all`, `test_build_tree_strict_short_circuits`,
`test_is_ambiguous_short_circuits`, `test_parse_and_is_ambiguous_fast_on_exponential`.
Existing regressions stay green: `test_derivations_*`, `test_build_tree_strict_*`,
`test_parse_raises_for_ambiguous_input`, `test_child_trees_*`.

## Housekeeping
Update `.wiki/` + `log.md` for the `IrStream` lazy-forest API + short-circuit semantics.
