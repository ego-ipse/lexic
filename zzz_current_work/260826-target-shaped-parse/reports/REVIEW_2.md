# Plan review — target-shaped parsing, pass 2

**Reviewed:** 2026-08-27, against the revised `context.md`, `goal.md`,
`DESIGN.md`, `TODO.md`, `LEDGER.md`, `reports/REVIEW_1.md`,
`reports/PROTOTYPE.md`, every source prototype, and the named current parser,
reduction, ambiguity, parallel, templating, tokenizer, and map-construction
seams on `targeter` / `0faa7289`.

**Verdict:** **do not start broad source implementation yet.** The revision
closed REVIEW_1's public-overload and type-feasibility questions, and it
correctly adds the missing reducer-expression program. It does not yet specify
three mechanisms on which the direct tokenizer and target-aware MT claims
depend. Implementing through them now would force the author either to retain a
model-shaped bridge or to invent a second execution path mid-migration.

The blockers below need a short design/prototype revision first. The remaining
items are implementation-phase proof obligations; they are not reasons to
retain the old path or to add a compatibility route.

---

## Blockers

### 1 — `RouteOp` has no continuation mechanism to select the following lower child

**Severity:** blocker

**References:** `DESIGN.md:263-268`, `TODO.md:295-297`,
`proto/product_types.py:246-250,426-433`, current PDA completion boundary
`src/lexic/parsing/pda/runtime/kernel/execution.py::_complete`, and the JSON
member sequence `src/lexic/grammars/json.py` (`member ::= string
name-separator value`).

**Issue:** The schema's main saving requires decoding an object key and then
selecting the specialised program for the *next* `value` occurrence. The
proposed `RouteOp` only maps an already-completed text capture to an integer;
the prototype's `route()` simply returns that integer. `RuleProduct` completes
after its captures have been parsed, so neither it nor `FlatRuleProduct` says
how that route changes the next reference clone/frame before `value` is
entered. Static contextual cloning cannot express a branch on an arbitrary
decoded string by itself.

Without an explicit generic semantic-continuation instruction, the source work
will either parse the value through the generic program and project later, or
smuggle target logic into the item driver. Both defeat the stated product and
paid-loop rules.

**Required architectural action:** add a typed route-result lane and a generic
continuation transition to the product/frame ABI. It must name the producer
completion, the following item/reference position, the finite route-to-clone
table, extension/recovery route, and rollback scope. Lower one real JSON
`member` route through both PDA and Earley before §3/§4 work, demonstrating
that a decoded `model` key enters a specialised value program while an escaped
equivalent key takes the same route. The transition must be plain compiled data
in the runtime, not a target callback or a rule-name case.

### 2 — morphism-owned strong identity caches violate the repository cache-lifetime invariant

**Severity:** blocker

**References:** `DESIGN.md:189-195`; `TODO.md:91-93,253-260`;
`proto/product_types.py:548-600,716-744`; current lifetime contract
`src/lexic/parsing/caches.py:1-36,92-153`; current reduction cache ownership
`src/lexic/compile/artifact.py:476-578`.

**Issue:** The design assigns the bound-program cache to a morphism, while the
prototype cache holds the compiled grammar and reducer strongly in each entry.
A reusable tokenizer morphism therefore retains every compiled/rebound/derived
grammar and its bound parser program for as long as the morphism lives. This is
the exact identity-cache retention problem the current `memo`/`track`/`release`
protocol exists to avoid. The declaration is also mutable in the prototype, so
the cached program is not protected against post-bind mutation of the target
definition.

This affects repeated-document service use, not only cold setup. It also makes
the claim that cache keys are safely pinned incomplete: pinning identities is
correct only when the entry has a bounded owner.

**Required architectural action:** make a morphism declaration immutable, but
place the bound-entry lifetime under the compiled artefact (or an equivalently
tracked identity memo owned by it), not under the reusable morphism. Preserve
the result-typed `BoundProduct` seam while proving that artefact release drops
all product/PDA/Earley/replica entries and that a global morphism cannot retain
an expired grammar. Test concurrent first binding as well; the current plan
does not state whether duplicate concurrent compilation is accepted or
serialized.

### 3 — fragment state is insufficient for the existing shell/routed split families, and verdict join is not lawful

**Severity:** blocker for the claimed target-aware parallel architecture

**References:** `DESIGN.md:444-472`; `TODO.md:380-399`;
`proto/product_types.py:415-423,455-474,1000-1007`; current split ownership and
shell reconstruction `src/lexic/parsing/parallel/orchestrate.py:304-355,475-511`
and `src/lexic/parsing/parallel/stitch/interior.py:82-133`.

**Issue:** `FragmentProduct` currently carries only lower/upper endpoints, a
carry, and verdicts. That is enough for a closed sequence example, but not for
the existing routed-interior and region-shell families: those paths parse an
enclosing stand-in shell and use its generated-model route to identify and
replace the interior. The revised design forbids that model bridge, yet it does
not specify the compiled shell continuation/capture that replaces it or how it
receives the upper-schema context.

The prototype also concatenates fragment verdict tuples. Its own demonstration
joins a left verdict ordered `2` before a right verdict ordered `1`; root
finalization selects the first entry. Thus the proposed join does not implement
the declared earliest ordered semantic verdict, and associativity alone is not
enough.

**Required architectural action:** define a fragment as a concrete suspended
product continuation, not merely endpoints plus a value. For each admitted
split shape, state what parses the enclosing shell, what data crosses the cut,
how the schema continuation is resumed, and the associative join law for
carry, decoded-key state, deferred validation, and verdict order. Specify a
stable total verdict key and a merge which preserves it independently of worker
completion. Prototype one routed/interior or region-shell target fragment with
no generated-model shell. If that cannot be proved, remove that shape from the
direct-product licence and explicitly run that target sequentially from the
start; do not defer the decision to a model stitcher.

---

## Implementation-phase proof obligations

### 4 — one expression range or one fused range is a stated invariant, not yet a representable/verifiable program property

**Severity:** high

**References:** `DESIGN.md:248-257,357-367`; `TODO.md:239-249`;
`proto/product_types.py:330-364`; `proto/reducer_coverage.py:80-170`.

The prototype has one `opcode`/operand per flat rule and no expression-range
table, range kind, or verifier relating a contextual clone to exactly one
range. It therefore cannot prove completeness or exclusivity for an
expression-lowered rule, a fused rule, a recovery rule, an island delegate, and
an attempt sub-clone. Before migrating the model product, make this a checked
flat-program invariant: every executable contextual completion site has one
tagged range, all referenced operands exist, and no site has both ranges. Run
that verifier on PDA clones, Earley completion tables, island delegates, and
token tables.

### 5 — the reducer inventory proves node-class reachability, not executable action lowering

**Severity:** high

**References:** `reports/PROTOTYPE.md:55-58,153-160`;
`proto/reducer_coverage.py:80-170`; JSON's actual action operands and dispatch
at `src/lexic/grammars/json.py:330-475`; shared authored-fold users noted in
`context.md:87-96`.

Every lowered prototype instruction has operand zero and every operand table
is empty. This omits the actual constant values, field/index access,
constructors, maps/type maps, radix values, refusal messages, and control
structure needed by real reducer actions. It also inventories only four
reducers, whereas the plan requires notation and generated-self-grammar
authored folds to migrate.

This is not a reason to abandon the expression program; it is the reason not
to treat the reported 174/162/98/44 counts as semantic coverage. The §5 exit
must first use an exhaustive owner/caller inventory, lower real operands into
separate typed tables, execute the interpreter differentially, and prove that
the lowering dispatch raises for an unregistered action class.

### 6 — the type prototype establishes static inference, but its executors do not validate one-product execution

**Severity:** high

**References:** `reports/PROTOTYPE.md:20-39,153-170`;
`proto/product_types.py:680-691,846-853,869-934,1121-1140`.

`SelectionBound.run` returns the input text for every requested path without
parsing or selecting a semantic occurrence. The default and tokenizer
executors call a hand-written decoder; the tokenizer decoder supplies a fixed
three-entry vocabulary and one merge. These are intentional type witnesses,
not parser executions. They cannot support claims about no generated model/IR
construction, decoded-route selection, rollback under a real PDA attempt,
Earley/island parity, or Qwen performance.

Keep the prototype as the static feasibility result, but label it that way in
all subsequent reports. The first source checkpoint needs a real tiny grammar
executed through both engines before any performance attribution is made.

### 7 — `select` and the overloaded `reduce` signature share a channel, but selection semantics are underspecified

**Severity:** high

**References:** `DESIGN.md:32-64,286-309`; `goal.md:21-36`;
`proto/product_types.py:675-749`; current public template behavior
`src/lexic/compile/output/templating.py:539-628`.

The overloads are sound for result inference and `select` does enter the same
binding channel. What is absent is the selection morphism's value contract:
missing selected keys, repeated/dynamic keys, nested arrays, duplicate decoded
keys, ordering, and the result type/value ownership are not declared. The
prototype accepts any reducer advertising the string event `mapping`, then
returns a path-to-IR map regardless of the document.

Before deleting the template path, specify `Selection` as a semantic morphism
over the signature, including its accepted event shapes and each of the above
outcomes. A selection which only supports finite nested objects is valid, but
must refuse incompatible shapes during binding rather than silently project a
different language. Then the two overloads form one coherent API rather than a
well-typed placeholder beside it.

### 8 — transaction layout needs a hot-path cost and rollback proof before it is used for large targets

**Severity:** medium

**References:** `DESIGN.md:198-212`; `TODO.md:170-176`;
`proto/product_types.py:150-186`.

The prototype creates a length snapshot for every live sequence and mapping at
each mark. Mapping rollback then rebuilds every retained key set from all
retained entries. This is correct for the small example, but it is neither
constant-time marking nor rollback proportional only to mutations. Repeated
attempts around a large or deeply nested target can turn it into a material
allocation/rehash cost, directly opposing the Qwen goal.

Choose and document a transaction representation with an explicit cost bound
(for example per-builder mutation logs and reversible key-set changes), then
measure it under valid and failed speculation. A successful mark must remain
copy-free, as promised; an unchosen Earley alternative may copy only its
isolated state, never mutate the selected state.

### 9 — the performance goal remains plausible only as a measurement hypothesis

**Severity:** medium

**References:** `goal.md:229-278`; `DESIGN.md:535-548,707-746`;
`src/lexic/ir/text/tokenizer.py:64-76,347-401`.

The design is right not to transfer the extent result to tokenizer construction.
It also correctly calls for a final-table constructor: the current
`from_merges` path builds/canonicalises encode and rank maps and derives the
inverse map. A direct target cannot claim the proposed Qwen multiplier until it
either feeds a one-pass final constructor or attributes those retained costs.
No grammar-specific shortcut is needed, but the §7/§12 evidence must show that
the generic composed route removes enough branching and representation work to
pay for final vocabulary, inverse vocabulary, ranks, and pipeline allocation.

---

## Verified

- The two public `reduce` overloads and the result-only bound seam type-check
  in the prototype without widening the semantic carrier at the frame,
  Earley-meaning, or fragment declarations.
- The prototype correctly identifies why sequence/mapping handles cannot share
  the semantic carrier lane, and why runtime opcode tables must contain plain
  integers rather than `IntEnum` instances.
- The default path today is still model-then-fold:
  `CompiledGrammar.reduce` obtains `_ReduceEntry.variant.parse(...)` and then
  calls `ReduceFold.reduce`; the reduction cache is artefact-lifetime-managed.
- The current Earley ambiguity boundary builds full parse-tree derivations via
  `AmbiguityPolicy`/`another_meaning`; target-aware meaning must therefore use
  a fresh isolated product state for each candidate and a final fold only for
  the selected derivation.
- Current parallel split/region paths are explicitly model-shaped, including
  synthetic shell parsing and model splice/rebuild. They cannot be reused by a
  direct product merely by changing the worker result type.
- The tokenizer reader still calls `compile_ast(...).reduce(...)` and then
  `tokenizer_of`; the final tokenizer constructor currently owns map
  canonicalisation and inverse-map construction.
- All prototype files and the requested plan/reports were read. No source,
  prototype, or plan file was changed; this report is the sole review change.

## Start gate

Implementation may start after blockers 1–3 are resolved in the design and a
focused prototype demonstrates each mechanism. At that point, start §2/§3 with
items 4–8 as mandatory phase gates. Do not start the broad §4 model-product
migration or claim Qwen performance before those gates hold.
