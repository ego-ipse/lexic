# T6 — the kernel trace protocol

Landed. The machine keeps an account of itself, the account is a re-run, and
the unwatched path is untouched — structurally, not by promise.

**Gates: `tools/run_checks.sh` EXIT=0 · `pytest tests/ -q -n auto` 4079 passed,
8 skipped · property under `tools/guarded.sh 8G 600` EXIT=0 (20 passed) ·
`tools/run_examples.sh` EXIT=0 · `tools/check_generated.py` CLEAN ·
`space_3/gate.py` 24 gestures · 13 keys · 0 failures.**

**Test count delta: +57** (4022 → 4079): 23 unit (`parsing/test_trace.py`), 32
corpus (`parity/test_watched_runs.py`), 2 performance
(`performance/test_trace_perf.py`).

---

## Placement, argued

**`src/lexic/parsing/trace.py`** — the parsing root, beside `fold.py` and
`products.py`, exported from `lexic.parsing`.

Three reasons, in order of weight:

1. **The arrow proves the cost model.** Nothing under `parsing/pda/` imports
   the trace; the trace imports the kernel. Put the watcher inside
   `pda/runtime/kernel/` and the instrumentation sits in the same package as
   the paid loop, where the next person to touch the driver will reach for it.
   At the root the dependency direction is the claim, and a test walks
   `parsing/pda/**.py` asserting the string `parsing.trace` appears nowhere.
2. **It is a PRODUCT, at `products.py`'s tier.** A watched run is what the
   engine hands back when asked a different question, not an internal of the
   predictive runtime.
3. **The room imports from the public surface.** `lexic.parsing` is that
   surface, and `CompiledGrammar.pda_tables()` (already public, already
   documented as "the trace substrate a `PdaKernel` subclass runs over") is the
   other half a consumer needs. No compile-side change was required.

## The shape

```python
TraceEvent(order, kind, rule, verdict, span)   # kind ∈ TRACE_KINDS
Trace(IrSeq[TraceEvent])                       # .of_kind(kind)
WatchedRun(events, cap, capped, derived)
watch(tables, text, fold, *, cap=TRACE_CAP, resolve=None) -> WatchedRun
WatchedKernel(PdaKernel)                       # the instrumentation, as a subclass
```

`span` is `IrSpan` — T3's record, not a parallel vocabulary. That is the ruled
middle position made real: a trace row and an emission extent point into one
document with one type, so the machine room's co-selection composes with the
reading room's without a translation shim.

## Pay to watch — how it is enforced rather than asserted

`WatchedKernel` is a **subclass**, following `_ReducePdaKernel`'s precedent
exactly (the reduce twin exists in its own module for the same reason: "the
model kernel is left byte-for-byte unchanged — its hot path carries no reduce
branch"). Every recording point is an override that flushes, notes, and
delegates. `PdaKernel` gained nothing: no slot, no flag, no branch.

Three gates hold it:

- **structural, decisive**: for every function in `vars(PdaKernel)`, the
  compiled code object's `co_names`/`co_varnames` are asserted to contain none
  of `{_note, _flush, events, capped, _scanned, cap}`. An `if self.watching:`
  added anywhere in the kernel fails this test however it is spelled.
- **layering**: no file under `parsing/pda/` mentions `parsing.trace`.
- **measured** (`tests/performance/`, guarded, in-process, interleaved): the
  unwatched median is taken ALONE, then again interleaved with watched runs of
  the same document; the interleaved median must not exceed the solo one by
  more than 2×. This catches the non-obvious regression too — a second kernel
  subclass can poison the driver's call sites through inline-cache misses even
  with no source change. Measured this session on `json.gbnf`: unwatched
  286 µs, watched 541 µs, **ratio 1.89×**. The second perf test asserts that
  ratio is above 1 — if watching ever became free, the watch stopped recording.

## Decisions inside the latitude

1. **A scan is a run of text, not one event per terminal.** The driver matches
   an exactly-once literal or char class INLINE, with no call to intercept
   (`kernel.py`'s `OP_LIT1`/`OP_CC1` branches). A per-terminal stream could
   therefore only be built by instrumenting the paid loop — the one thing the
   cost model forbids. So a scan is the text consumed between two decisions,
   attributed to the frame that consumed it, flushed at each seam BEFORE that
   seam's own event so the order is the machine's own. The corpus gate proves
   nothing is lost: the scans tile every generated document over every shipped
   grammar, with no gap and no overlap, ending exactly at the input's end.
2. **A refused run comes back rather than raising.** The predictive machine
   failing is ordinary — the compile seam catches `PdaFail` and retries on the
   gated engine — and it is the run most worth watching (the probe/rollback
   story only appears on inputs the gates cannot settle). `watch` therefore
   catches `PdaFail`, records it as the stream's final event with the engine's
   words and offset, and reports `derived=False`.
3. **The product carries NO model, and that is the "re-run" fact.** The spec
   asks the product to say the run re-executed. A `rerun: bool` that is
   structurally always `True` is decoration, not data. What actually varies —
   and what the product therefore says — is `capped` and `derived`; the re-run
   is carried by the shape: a `WatchedRun` holds no model *because* a caller
   watching a parse already holds one from a different execution, and handing
   back a second would invite the two to be read as one. Flagging this as the
   place where I answered the spec's letter differently than it reads.
4. **Four kinds, closed.** `scan`, `probe`, `rollback`, `gate` — the spec's
   own list, gated as a closed set. An island escape is deliberately NOT a
   fifth kind: its text still lands in the scan stream, and inventing a word
   the ask did not name would be exactly the speculative generality the M7
   ruling warns about.
5. **A gate event is a gate the ANALYSIS had to decide** — a k-window, a
   prefix negation, a structured-noise scan, an attempt set — not the
   FIRST-char selector read, which every entry does and which would drown the
   stream in table reads.
6. **`WatchedKernel.__init__` mirrors the base's signature exactly**; the cap
   is per-run state that `watch` sets on the instance, like the cursor.
   (pylint's `too-many-arguments` pointed at the growth; the substitutable
   constructor is the better answer anyway.)

## What a stream looks like

`item ::= "a" | "ab"` against `"abc"` — the overlap the gates cannot settle:

```
0 gate      item  'attempt over 2 entries'                       IrSpan(0, 0)
1 probe     item  'attempt entry'                                IrSpan(0, 0)
2 scan      item  'a'                                            IrSpan(0, 1)
3 probe     item  'attempt entry'                                IrSpan(0, 0)
4 scan      item  'ab'                                           IrSpan(0, 2)
5 rollback        'attempt at 0: arm choice spans two ends (2,…' IrSpan(0, 0)
```

and `json.gbnf` against `{"a": 1, "b": [2, 3]}` — 22 events, gates at each
`value` entry, scans tiling the document:

```
0 gate  value           'prefix negation over 2 arms'  IrSpan(0, 0)
1 scan  begin-object    '{'                            IrSpan(0, 1)
2 scan  string          '"'                            IrSpan(1, 2)
…
5 scan  name-separator  ': '                           IrSpan(4, 6)
```

## Gates

| The ask's gate | Where |
|---|---|
| Determinism — two watched runs, identical streams | unit (both a deterministic and a forking input) + corpus, every grammar × 4 documents |
| Honesty — the cap is drawn, never silent | `capped` true at `cap=3`, false uncapped, and the parse still derives at `cap=1` |
| Reference fidelity — spans inside the document, names resolve | unit + corpus: every span within bounds, every `rule` a name in the compiled grammar (or `""` for an unnamed group) |
| Perf — the unwatched path untouched | the structural code-object gate, the layering gate, and the guarded interleaved A/B |

Plus three the spec did not name: the scans tile the document; a scan's verdict
slices back out of the text by its own span; and watching does not change what
the parse says (the watched re-run derives exactly where the unwatched parse
does, over the corpus).

## What changed

| File | Change |
|---|---|
| `src/lexic/parsing/trace.py` | NEW — the records, `WatchedKernel`, `watch` |
| `src/lexic/parsing/__init__.py` | seven names on the engine floor's surface |
| `CLAUDE.md` | the module's line |
| `.wiki/lexic/public-api.md` | the watched run on the `lexic.parsing` root section |
| `.wiki/log.md` | the entry |
| `tests/unit/lexic/parsing/test_trace.py` | NEW — 23 |
| `tests/integration/lexic/parity/test_watched_runs.py` | NEW — 32 (8 grammars × 4) |
| `tests/performance/lexic/test_trace_perf.py` | NEW — 2 |
| `tests/corpus.py` | NEW — the generated-documents recipe, shared with the addressed-emission gates (pylint's duplicate-code found the copy; sharing it is the right answer, and it keeps the two suites agreeing on what "the corpus" is) |
| `tests/integration/lexic/roundtrip/test_addressed_emission.py` | uses the shared recipe |

No suppressions, no `eval`, no `pyproject.toml`, no commit.

## Known boundaries, stated

- **Token grammars** (`think.gbnf`, `vyx.gbnf`) are outside the corpus gate:
  their input is a token segmentation, so a character span means something
  else there. The watcher runs on them; nothing asserts their spans.
- **An island's interior is not traced.** The escape to the gated Earley
  sub-parse is a different engine; its consumed text appears as an ordinary
  scan under the island's rule. Tracing the Earley kernel is a separate ask,
  not a corner of this one.
- **A `LexicError` from an ambiguous island propagates** rather than becoming
  an event. That is the ENGINE refusing (the ambiguity doctrine), not the
  predictive machine failing, and folding the two would blur a distinction the
  repo maintains everywhere else.

## Process note

`tools/auto_fix.sh` reformatted tracked `zzz_current_work/` files four more
times; restored each time by re-applying the saved pre-existing zzz diff, so
the tree still carries only T3's licensed `space_3/praxis/reading.py` swap.

## Gate output tail

```
sanity: OK · lint: OK · typecheck: OK · pylint: OK   →  EXIT=0
4079 passed, 8 skipped, 3 warnings in 35.92s
guarded property  →  20 passed, EXIT=0
run_examples.sh   →  EXIT=0
check_generated   →  CLEAN: 0 pyright errors, 0 unaccepted pylint findings
space_3/gate.py   →  24 gestures · 13 keys · 0 failures
trace A/B (json)  →  unwatched 286 µs · watched 541 µs · 1.89x
```

T7 not started (holding, as instructed).
