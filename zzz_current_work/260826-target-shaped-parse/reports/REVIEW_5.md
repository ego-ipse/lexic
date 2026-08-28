# Plan review — target-shaped parsing, pass 5

**Reviewed:** 2026-08-27, independently against `targeter` /
`0faa7289`, the complete active-effort record and every prototype, plus the
current cache, product, PDA, Earley, reduction, templating, tokenizer, and
parallel seams named by the plan.

**Verdict: GO — begin §2 and the ABI/lifecycle portion of §3.** The current
design has no remaining architectural reason to retain a generated-model
bridge, a second template executor, or target-specific parser code. In
particular, the public declaration/private binding-owner split is now sound as
a design: cache residency cannot be mutated through a public morphism, an
artefact can release its entries, and an explicitly retained bound program can
outlive source-cache residency.

This is deliberately a limited GO. §3 must close the hard gates below before
§4 begins. §4 remains the generated-model ABI and paid-loop proof point; §5 is
the reducer-expression and direct-default-IR proof point; §7/§9 remain the
tokenizer/final-table and parallel-suspension proof points. None may claim a
performance result or use model-plus-fold as a production fallback.

## Architectural findings

### 1 — Following-child routing is feasible, but must be an occurrence-keyed *recognition-time* Earley transition

**Severity:** high — hard §3 exit gate, not a start blocker.

**References:** `DESIGN.md:295-307,402-407`; `TODO.md:178-201,328-334`;
`proto/route_continuation.py:20-143,156-223`; current PDA completion
`src/lexic/parsing/pda/runtime/kernel/execution.py:305-336`; current Earley
product boundary `src/lexic/parsing/products.py:80-109,273-310`; current
Earley dedup `src/lexic/parsing/earley/kernel/loop/state.py:57-85`.

The design has the necessary semantic shape: a decoded key publishes a finite
route and the immediately following `value` reference consumes it. The witness
also correctly checks escaped-equivalent decoded keys. The source Earley path,
however, currently recognizes a complete forest and only then calls
`fold.apply`; a post-order fold cannot change a child that has already been
predicted/scanned. The production operation must therefore execute the route
at producer completion while filing the parent continuation, and encode the
finite route in the *actual* Earley item identity/packing key before prediction.

Require one unique contextual producer-completion id (not merely a `string`
rule id), a one-shot consume/clear or occurrence-token check at the following
reference, and rollback/fork handling for the route lane. Demonstrate nested
members through PDA, ordinary Earley fallback, and an island/delegate: no stale
outer route may select an inner value, and no abandoned attempt may select the
next member. The hand-published prototype is a useful mechanism witness, not
that proof. Move this from a later composition task into §3's hard exit before
the generated-model migration.

### 2 — Exactly-one completion is correctly representable; verification must cover physical execution sites and exact integer storage

**Severity:** high — hard §3/§4 gate.

**References:** `DESIGN.md:274-293`; `TODO.md:178-189`; `proto/product_types.py:406-475,1360-1391`; current separate PDA build
`src/lexic/parsing/pda/compiler/program/flatten.py:246-427` and completion
`src/lexic/parsing/pda/runtime/kernel/execution.py:305-336`.

One range index plus separately tagged tables prevents expression/fused double
execution by construction. The prototype verifier establishes the local shape,
including missing/empty/out-of-bounds cases. Production must additionally
verify every contextual clone, Earley completion, token completion, attempt
sub-clone, and island/delegate table *after final binding*; no side table may
remain executable without its range. Its integer audit must use exact runtime
types (`type(value) is int`), not `isinstance(value, int)`, because `IntEnum`
passes the latter. The prototype's timing result supports keeping this strict
plain-int boundary.

### 3 — Transaction semantics are sound locally; isolate Earley alternatives at real ambiguity gates and account for fork cost

**Severity:** high — hard §3/§4 gate.

**References:** `DESIGN.md:222-241`; `TODO.md:193-201,396-410`;
`proto/product_types.py:89-246,1201-1296`; current ambiguity construction
`src/lexic/parsing/earley/kernel/forest/support/ambiguity.py:126-206`.

Constant-size marks and mutation-proportional rollback now cover sequence
append, mapping insert/key-set removal, builder allocation, and deferred
verdict truncation. That is the right lifecycle; parse-local, occurrence-owned
handles avoid an unsafe global builder. `ParseState.fork`, though, copies every
live builder and log in the witness. That is correct only if it occurs at an
actual competing arm meaning, never during ordinary Earley chart filing,
prediction, nullable advancement, or split handling. The implementation must
make this placement explicit and measure both valid and failed speculation with
large vocab-like maps. A losing alternate, failed island, and failed PDA attempt
must leave route, duplicate, verdict, and builder state untouched.

### 4 — Declaration/cache separation is ready, provided production uses the repository owner protocol rather than another weak-cache island

**Severity:** high — hard §3/§5 lifecycle gate.

**References:** `DESIGN.md:200-220`; `TODO.md:185-201,263-270`;
`proto/cache_lifetime.py:32-125,156-217`;
`proto/product_types.py:662-749`; `src/lexic/parsing/caches.py:35-153`.

The revised prototypes resolve REVIEW_3's blocker: declarations contain only
immutable data, and mutable entries/locks/factories are private. Their weak
source test and concurrent cold-bind test pass. The prototype registry is
still intentionally independent of `memo`/`track`/`adopt`/`release`; source
must not copy that as a permanent cache. The bound-product registry and every
derived PDA/Earley/replica entry need artefact ownership through the existing
transitive release protocol. A retained pool must own its bound program, while
the bound program must not keep the artefact alive. Verify explicit release as
well as collection and concurrent first bind.

For the later custom-morphism surface, retain the stated distinction: public
declaration data may not hold a mutable executor/factory. Any cold custom
constructor must be introduced only by lowering an immutable declared
operation/symbol into the private bound program; do not weaken this with a
public callback field. This does not delay §2/§3, but is required before the
custom public surface is final.

### 5 — Selection and direct tokenizer construction are architecturally coherent; both have intentionally later semantic gates

**Severity:** medium — §5–§7 gates.

**References:** `DESIGN.md:24-57,360-385,529-613`; `TODO.md:343-350,355-392`;
`proto/selection_contract.py:43-221`; current templating
`src/lexic/compile/output/templating.py:512-638`; current reader/finalizer
`src/lexic/api/json_tokenizer.py:74-150`,
`src/lexic/ir/text/tokenizer.py:33-62,347-401`.

The finite nested-mapping selection contract is complete enough to replace the
template executor: decoded-key order/absence/duplicate/shape/syntax precedence
are explicit, and it cannot silently become raw-span extraction. Bind it only
after real reducer operands emit mapping/value events, then exercise it solely
through `CompiledGrammar.reduce`.

Direct tokenizer construction is feasible without JSON `IrMap` or merge-dyad
lists. The final carrier necessarily owns encode/decode/ranks/pipeline, and
the current `from_merges` rebuilds encode/rank maps and derives decode. §7 must
therefore add one canonical final-table construction route if direct builders
already hold canonical tables; it must not add a second competing constructor
or sneak through `tokenizer_of`. Attribute those retained final allocations
separately from recognition and demanded decode before treating the extent
result as relevant tokenizer evidence.

### 6 — Fragment/shell composition has the required law; it is not yet an engine witness

**Severity:** medium — §9 gate.

**References:** `DESIGN.md:489-526`; `TODO.md:416-453`;
`proto/suspended_fragment.py:52-257`; current model-shaped shell route
`src/lexic/parsing/parallel/orchestrate.py:280-560` and
`src/lexic/parsing/parallel/stitch/model.py:1-260`.

The suspension contains the right state categories, joins stable verdict keys
rather than concatenating them, and proves regrouping for the witness. It does
not suspend an executing product frame or resume a compiled suffix. Keep the
current planner/discovery/certification/replicas/floor, but only license a
direct target when a compiled coordinator prefix, worker fragments, and
coordinator suffix prove exact sequential equality/refusal and root
validation/finalization once. Otherwise decline before submitting work and run
the same direct product sequentially; do not reuse a stand-in model shell.

## Verified

- The architecture retains grammar/formulation independence: signatures name
  semantic events, while the planned contextual state uses occurrence and route
  ids rather than JSON rule names (`DESIGN.md:128-172,295-307`).
- Default IR, Python JSON, extent, and tokenizer are distinct codomains with
  distinct cost accounts; the plan does not transfer the extent multiplier to
  tokenizer construction (`goal.md:257-292`, `DESIGN.md:747-801`).
- Superseded work is explicitly scheduled for deletion, while shared `foldkit`
  users are migrated rather than accidentally removed (`DESIGN.md:614-680`,
  `TODO.md:455-500`).
- Re-ran all executable witnesses and Pyright: all six prototype assertions
  passed; reducer inventory was GBNF 174, ABNF 162, EBNF 98, JSON 44; Pyright
  reported `0 errors, 0 warnings, 0 informations`. The inventory remains
  class reachability, not expression-semantic coverage.

## Start gate

**GO for §2 and the parsing-owned ABI/lifecycle work in §3.** Preserve the
immutable-declaration/private-registry boundary, one-completion-range rule,
typed non-widened carrier lanes, and parse-local transactional ownership.

Before §4, demonstrate the occurrence-keyed recognition-time route transition
in both engines, run the flat verifier over actual bound execution tables, and
show real rollback/fork isolation without paid-loop regression. Before §5–§9,
meet the reducer operand/differential, selection/tokenizer final-table, and
compiled-suspension/fragment gates above. No source or prototype was changed;
this review is the sole change.
