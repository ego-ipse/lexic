# Investigator prompt 11 — close the remaining target-shaped parse gates

Work in `/home/mika/projects/lexic` on the active effort
`zzz_current_work/260826-target-shaped-parse/`.

Read, in order:

1. `AGENTS.md`/the supplied repository instructions and `docs/STYLE.md`;
2. the effort's `INDEX.md`, `context.md`, `goal.md`, `DESIGN.md`, and `TODO.md`;
3. `reports/PROTOTYPE_10.md` and `reports/REVIEW_10.md`;
4. the four Prototype 10 files and the production seams named below.

The design remains green. This is a focused investigation round, not a rewrite
and not production implementation. Do not edit `src/`, `tests/`,
`pyproject.toml`, or the active planning documents. Put every new or revised
prototype in this effort's `proto/`; never use `/tmp` for prototypes. Deliver
one factual report at `reports/PROTOTYPE_11.md`. Do not commit or push.

Strict constraints: no `eval`, `exec`, `Any`, `object`, cast-based erasure,
ignore/suppression directive of any kind, grammar-specific branch in generic
machinery, external model library, or second parse API. Use `uv run` for Python
tools. Run no benchmarks concurrently; in particular, run each multithreaded
or Qwen-scale row alone. Report process CPU and wall separately. Do not modify
production code to instrument it.

## A. Make multiple and nested ambiguity exact

The one-flip claim in `proto/island_alternate_seed.py` and production
`src/lexic/parsing/earley/kernel/forest/support/ambiguity.py::another_meaning`
is not justified by purity. Produce an executable counterexample with two
independent ambiguity sources for which the baseline and each single flip have
equal requested-root meanings while the joint alternate differs. Exercise at
least:

- a pure conditional or validation operation allowed by the planned product
  algebra;
- two sibling island seeds;
- a nested seed;
- a keyed-product interaction if its declared duplicate/order law can expose
  one.

Then prototype the exact replacement. Compare at least these candidates:

- value-set propagation with semantic deduplication at each completed parent;
- operation-specific separability certificates which permit linear replay only
  when the compiler proves the law;
- a hybrid which carries combinations only across interacting continuation
  cones.

Do not accept unconditional Cartesian enumeration as the final architecture,
but do not discard combinations without a proof. Count retained meanings,
completion executions, allocations, and maximum live state for independent,
interacting, dropped, equal, nested, and separate-accepting-root witnesses.
State the exact invariant the compiler/runtime will enforce. Determine whether
production `another_meaning` is already unsound for any public `build` contract
and record the required eventual correction without editing it.

The single-seed baseline-plus-alternates carrier, Earley cone, PDA trace, and
sibling-accepting-item requirement are already accepted. Preserve them unless
the counterexample proves one independently wrong.

## B. Measure the real keyed products

The prior 0.025-second row measured only a plain encode dictionary. Build and
compare the actual candidate result for each distinct law:

- recursive Python mapping under every admitted duplicate policy;
- real `IrMap`, including canonical ordering and real IR leaves;
- real ready `IrTokenizer`, including encode, decode, ranks, pipeline,
  segmenter, root construction, and validation.

Separate semantic replay from final carrier construction, but include both in
the total. Cover equal, changed-value, key-set-changing, duplicate, and dropped
alternates. Use small and medium generic grammar witnesses as well as the real
Qwen fixture; JSON is evidence, never a privileged implementation. Measure the
exact cold eager fallback and any exact shareable alternative which could
plausibly beat it. The ordered sequence tree and incremental treap are already
rejected for keyed products; do not spend the round rehabilitating them.

Report current-versus-candidate cost per product, not one multiplier applied to
all products. A representation earns adoption only if its equality, duplicate,
order, construction, retained-memory, and chosen-result materialization laws
all pass.

## C. Resolve the resolver handoff with real trees

Use the real island/delegate and Earley kernels to construct both complete
document derivations corresponding to a differing island seed. Do not substitute
an ambiguity-point count for a pair. Invoke actual deterministic resolvers and
verify that the selected target meaning corresponds to the returned derivation.

Compare island-local and complete-document pairs with a context-sensitive
resolver capable of choosing differently between those scopes. Decide which
scope satisfies the public invariant that PDA and Earley expose the same
ambiguity opt-out. Measure recognition and tree-construction cost separately,
and prove that refusal and equal-root paths perform no complete-document
reparse. If a complete pair cannot be reconstructed from the delegated chart,
show the exact missing information rather than merely asserting it.

## D. Implement and price the real ambiguity structures externally

Keep the `DISTANT` grammar and pad 2,000/8,000/32,000 scaling ladder. Replace
the dict-of-sets candidate with at least one concrete flat representation, such
as dense completed-handle numbering plus CSR/forward-star parent and owner
edges. Prove dirty-cone parity against the dict-of-sets oracle and report:

- keys, nodes, and edges separately;
- bytes per character and bytes per edge;
- build CPU, replay CPU, wall, and peak RSS;
- the cost of obtaining dense numbering;
- cleanup/lifetime behavior.

Allocate the proposed PDA seed/trace frames for real and measure them over
varying ancestor depth and seed count. Do not report an estimated population as
allocated memory.

Correct the control protocol. It must exercise a path on which ambiguity
machinery is genuinely unreachable and assert that no meaning memo, dependency
index, overlay, seed, or trace is allocated. The ambiguous candidate row must
still assert the correct semantic verdict. Keep processes isolated and state
which allocations `tracemalloc` can and cannot attribute; do not include lazy
chart expansion in a named product-structure bucket.

## E. Finish the custom-class mechanism proof

Keep the decided public shape: one immutable class object as constructor symbol
plus inert declaration data. Keep a homogeneous result-free cached plan and a
reconstructed result-typed bound view. Remove every class inspection, including
`__qualname__`, and do not introduce a factory, callback executor, import-path
lookup, or mutable rebinding registry.

Prototype a bound executable which still runs after its source artefact and
registry entry die, because it retains exactly the immutable derived tables it
needs rather than accepting the source grammar again at `run`. Exercise:

- frozen, validating, generic, and unusual-metaclass classes;
- declaration equality/identity and unhashable class objects;
- id reuse and equivalent recomputation after eviction;
- concurrent cold binding on the free-threaded interpreter;
- pool retention followed by source collection and a successful parse/build;
- constructor failure at cold root finalization;
- zero constructor/callback traffic in frequent completions.

If value-keyed declarations cannot support arbitrary class objects, replace the
cache key with a weak, id-reuse-safe identity mechanism and prove its lifecycle.

## Deliverable and gates

`reports/PROTOTYPE_11.md` must distinguish:

- decisions conclusively closed;
- mechanisms proven but still requiring production integration measurement;
- user decisions still open;
- failed candidates and why they stay rejected.

Do not call a gate solved conditionally while leaving its correctness premise
unproven. Include exact commands and complete relevant outputs. Run Ruff format,
Ruff check, and Pyright over every prototype you add or change, plus each
prototype witness. Search the touched files for all forbidden constructs. End
with an explicit list of recommended planning-document edits, but do not apply
them.
