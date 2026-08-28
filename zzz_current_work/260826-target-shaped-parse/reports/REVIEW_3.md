# Plan review — target-shaped parsing, pass 3

**Reviewed:** 2026-08-27, against the current `context.md`, `goal.md`,
`DESIGN.md`, `TODO.md`, `LEDGER.md`, `reports/REVIEW_2.md`,
`reports/PROTOTYPE_2.md`, every `proto/*.py`, and the current cache, product,
PDA, Earley, reduction, and parallel seams on `targeter` / `0faa7289`.

**Verdict:** **no start yet.** The revision resolves the three design gaps from
REVIEW_2: it now has a real following-child continuation in the architecture,
one tagged completion range, a bounded transaction representation, explicit
selection semantics, and a suspended direct-product shell law. One architectural
blocker remains: the claimed immutable morphism declaration publicly contains
its mutable cache. That makes cache mutation capable of changing binding
semantics, not merely cache residency.

Once that declaration/cache separation is corrected, implementation may begin
§2 and the ABI portion of §3. It may not begin §4 or claim tokenizer/parallel
performance until the phase gates below have been demonstrated in the real
engines.

---

## Blocker

### 1 — `Morphism` is only shallowly immutable; its public cache can change a binding answer

**Severity:** blocker

**References:** `DESIGN.md:200-216`; `TODO.md:95-98`; `proto/cache_lifetime.py:68-137,150-187`; `proto/product_types.py:696-757,865-906`; current ownership contract `src/lexic/parsing/caches.py:16-29,91-153`.

**Issue:** `Morphism` is a `NamedTuple`, but it exposes `cache:
BoundCache[Result]` (`proto/cache_lifetime.py:126-137`). `BoundCache.entries` is
public and mutable (`:68-106`). Replacing or removing an entry for the same
grammar/reducer identity changes which `BoundProduct` is returned; it therefore
changes binding semantics. The declaration also exposes a mutable factory
object. The more complete type prototype has the same ownership shape:
`TypedMorphism` owns its public mutable cache, lock, factory, and executor
(`proto/product_types.py:696-757`), and `SelectionMorphism` does likewise
(`:865-906`). A `NamedTuple` prevents replacing the field, not mutating the
referent.

The weak source reference proves only that this particular entry can disappear
when the grammar dies. It does not make the cache a pure implementation detail,
does not freeze the declaration which determines a bound program, and does not
give the existing artefact ownership protocol a single owner. This contradicts
the plan's assertion that the declaration is immutable while a morphism owns a
typed identity cache.

**Required architectural action:** make `ReductionMorphism[Result]` a public,
fully immutable declaration of signature/schema/algebra data only. Put mutable
binding entries, locks, and source-release registration in a distinct private
compiler/artefact-owned cache record or registry, keyed by the declaration's
stable identity plus grammar and reducer identities. Register that registry's
derived program/PDA/Earley/replica entries through `parsing.caches` ownership;
a cache eviction must be a pure recomputation and must never alter the declared
binding. Add a proof that public declaration mutation is impossible and that an
explicitly retained pool-owned bound program remains valid after source release.
Do not rely on a convention that callers leave a public `entries` dictionary
alone.

---

## Implementation-phase gates

### 2 — Route continuation is correctly designed, but the prototype has not lowered one contextual occurrence into either engine

**Severity:** high

**References:** `DESIGN.md:291-303`; `TODO.md:176-187`; `proto/route_continuation.py:35-87,108-143,156-223`; current PDA completion `src/lexic/parsing/pda/runtime/kernel/execution.py::_complete`; current Earley item filing `src/lexic/parsing/earley/kernel/loop/state.py:57-85`.

**Finding:** The design now states the necessary mechanism: producer completion,
following consumer position, frame route lane with rollback, and route-bearing
Earley identity. This is formulation-neutral and rules out post-value
projection. The prototype, however, manually publishes the route before calling
the child selectors (`proto/route_continuation.py:197-222`). Its
`producer_completion` is a rule index for `string`, not a contextual completion
occurrence (`:156-188`), and neither child function consults it. It therefore
does not prove that an arbitrary completion of the same rule cannot affect a
different parent occurrence.

**Required phase action:** make early §3 lower an occurrence-scoped continuation
id into one PDA frame and one Earley item key, with a defined clear/pop lifetime
after the consumer starts. Before §4, run a nested mapping witness through PDA,
Earley fallback, and an island/delegate path: outer and inner members must route
independently, escaped-equivalent keys must agree, and rollback must leave no
route for the next attempt. This is a gate, not a reason to restore a generic
value parse.

### 3 — Fragment/shell composition has the right law, but no product parser has yet been suspended and resumed

**Severity:** high

**References:** `DESIGN.md:485-523`; `goal.md:180-197`; `proto/suspended_fragment.py:60-203,206-257`; current model-shaped paths `src/lexic/parsing/parallel/orchestrate.py` and `src/lexic/parsing/parallel/stitch/interior.py`.

**Finding:** Entry/exit lower/upper/route state, stable verdict ordering, and
associative carry/duplicate joins are now explicit. The witness uses the real
routed splitter, and its regrouping law is useful. But `parse_piece`,
`suspend_shell`, and `resume_shell` are hand-written line parsing and source
slicing (`proto/suspended_fragment.py:146-203`), not a coordinator executing a
compiled product prefix, retaining live capture/accumulator handles, then
resuming its compiled suffix. It cannot establish that a live route lane,
transaction mark, deferred validation, or root finalizer survives the actual
split boundary exactly once.

**Required phase action:** retain this as the §9 gate. Run one compiled product
through coordinator-prefix, worker interiors, associative document-order join,
and coordinator suffix; prove exact equality/refusal with sequential execution
for terminated, routed-interior, and shell shapes. If an exact bounded
suspension cannot be derived, decline the split before submitting workers. Do
not adapt the existing generated-model stitchers.

### 4 — Completion exclusivity is representable; every real execution site still needs verification and execution proof

**Severity:** medium

**References:** `DESIGN.md:270-309`; `TODO.md:176-182`; `proto/product_types.py:406-519`; `reports/PROTOTYPE_2.md:58-71,101-114`.

**Finding:** One `FlatRuleProduct.completion` index plus checked tagged ranges
does make expression versus fused/recovery/delegate selection exclusive. The
verifier rejects the relevant malformed prototype tables. No current PDA clone,
Earley completion, island, attempt sub-clone, or token completion owns this
field yet, so the prototype cannot show that an actual runtime reaches precisely
one range.

**Required phase action:** invoke the verifier when every physical table is
bound and before each engine executes it; give every contextual site exactly one
index. Differentially demonstrate a default expression range and a fused range
on the same lower occurrence, asserting that only the selected range runs. Keep
the unknown-action default at compile time.

### 5 — The selection contract is now coherent; its current executable surface is deliberately not a parser

**Severity:** medium

**References:** `DESIGN.md:32-81`; `goal.md:19-40`; `proto/selection_contract.py:43-221`; `proto/product_types.py:837-911`.

**Finding:** Declaration order, absence, decoded duplicate refusal, nested shape
verdicts, syntax-first failure, and recognition-only unselected values are now
specified. `select(...)` and both `reduce` overloads share the intended bound
product seam. The dedicated witness consumes synthetic semantic events; the
older `SelectionBound.run` constructs values directly from the document text
(`proto/product_types.py:837-911`). Neither is evidence of parser integration.

**Required phase action:** bind selection only after a reducer has actually
lowered the required mapping/value events, and test it through the one `reduce`
entry on reordered, escaped, nested, duplicate, malformed, and discarded
values. It must not become a template executor or a model/fold fallback.

### 6 — Transaction safety is materially improved, but Earley fork and paid-loop cost remain unmeasured

**Severity:** medium

**References:** `DESIGN.md:218-237,428-454`; `TODO.md:191-202`; `proto/product_types.py:89-246`; `proto/opcode_cost.py:18-78`.

**Finding:** Marks are constant-size and rollback now undoes logged mutations
rather than scanning builders. That closes the prior representation defect. An
Earley `fork` still clones every live builder and mutation log
(`proto/product_types.py:235-246`), and all execution witnesses bypass the PDA
and Earley paid loops. The opcode microbenchmark only establishes the narrow
plain-int comparison claim.

**Required phase action:** prove that state forks happen only at real competing
meanings, isolate route/duplicate/verdict mutations, and measure valid and
failed speculation with large retained accumulators. At §4 compare generated
model opcode streams and measured loop work against the baseline; reject a
target branch, frame allocation, or callback in a frequent completion.

### 7 — Formulation independence, reducer lowering, and tokenizer speed are still acceptance evidence, not prototype claims

**Severity:** medium

**References:** `DESIGN.md:128-172,305-315,701-745,747-780`; `goal.md:54-74,257-292`; `proto/product_types.py:623-628`; `proto/reducer_coverage.py:1-188`; `proto/product_types.py:1016-1120`.

**Finding:** The plan correctly makes signatures independent of rule names and
labels the Qwen result a hypothesis. The current source-compatibility witness
only compares a grammar with the grammar stored beside its reducer
(`proto/product_types.py:623-628`); it does not bind one target through distinct
native/GBNF/ABNF/EBNF formulations. Reducer coverage inventories node classes
but writes zero operands and has no instruction interpreter. The tokenizer
executor directly decodes the entire text before root construction
(`proto/product_types.py:1016-1120`), so it cannot demonstrate eliminated
model/fold work or final-table cost.

**Required phase action:** before removing the oracle, lower and execute every
operand of every shipped reducer/notation/generated-self-grammar action with
raising coverage; bind equal semantic signatures through independently authored
formulations; and differentially test PDA, Earley, islands, ambiguity, and
sequential execution. Profile the completed direct tokenizer path externally,
separating recognition, demanded decoding, final vocabulary/inverse/rank/pipeline
allocation, and every eligible split shape. No grammar-specific shortcut is
licensed by the plan.

---

## Verified

- The revised design gives `RouteOp` a continuation that selects the following
  child before entry in both engines, rather than treating the route as a
  post-completion value.
- The cache prototype passes its concurrent first-bind and source-lifetime
  checks; the issue is declaration ownership/mutability, not its weak-reference
  cleanup mechanism.
- The transaction and completion-range prototypes now meet their stated local
  representation checks; the six executable prototypes pass, and Pyright over
  `proto/` reports zero errors, warnings, and information messages.
- The selection and fragment documents now state the important semantic laws;
  the reports do not falsely claim source integration or Qwen numbers.
- Current production reduction remains `CompiledGrammar.reduce` → variant model
  parse → `ReduceFold.reduce` (`src/lexic/compile/artifact.py:311-342`), and
  current parallel stitching remains model-shaped. None of the new witnesses
  provides a hidden runtime bridge.

## Start gate

**Do not start §2/§3 while blocker 1 remains.** Correct the public immutable
declaration versus mutable cache-owner boundary and re-prove artefact release
through that boundary. Then §2 and the declaration/flat-table portion of §3 may
start, with findings 2, 4, 5, and 6 as hard early phase gates. §4, direct
reduction migration, parallel engagement, and performance claims wait for the
real-engine proofs above. No source, prototype, or plan file was changed by this
review; this report is the sole change.
