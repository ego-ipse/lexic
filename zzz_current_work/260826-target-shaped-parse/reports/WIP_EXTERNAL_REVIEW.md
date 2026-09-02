# WIP external review — hold until the §4 pre-checkpoint gate

> **INTERIM SNAPSHOT — DO NOT FOLD OR ACT ON IT YET.**
>
> §4 implementation and the external review are both still in progress. More
> gates will follow. Later increments may answer findings below, so this file
> must be reconciled against the completed §4 source before it becomes a final
> review. It does not interrupt the current implementation and does not certify
> the current state.

## Scope

Read-only review refreshed on 2026-09-02 against savepoint `fa3b9ccf` and the
unstaged §4 work then visible. The comparison anchors were `0faa7289` (effort
baseline) and `dffa821f` (the product-completion restart).

The review inspected the complete product path and its consumers: authored and
flat ABI, lowering, verification, model binding, Earley completion, PDA bake
and completion, islands, token parsing, replicas, ambiguity replay, JSON
semantics, and the current §4 reports and prototypes. Small isolated grammar
diagnostics were run where a claim needed a counterexample. No benchmark, full
test suite, source file, or prototype was changed by this review.

This snapshot covers a moving worktree. A finding is about the observed source,
not a claim that the implementer has finished or failed to address it.

## Assessment

The migration is now substantive and should not be discarded. The old
`parsing/fold.py` channel is gone; `ModelBinding` reaches the PDA, Earley,
token, island, trace, replica, and stitch paths; model construction distinguishes
record, value-string, pass-through, and unlicensed validated construction; and
completion result presence no longer overloads Python `None`.

The checkpoint is not ready in this snapshot. The main remaining problems are
not prototype polish: they affect proof soundness, the authority of the bound
program, ordinary parse cost, and contracts that later target-shaped lowering
will rely on.

## Current findings

### High — the regular proof applies the region's outer follow to every referenced rule

`parsing/product/regular.py::prove_regular` builds the root's recognizer closure,
computes one `tail` from the region's external follow, and checks every rule in
that closure against that same tail. A referenced rule instead needs the
continuation at each occurrence that calls it.

Concrete witness:

```gbnf
root ::= sub "a"
sub ::= inner "c"
inner ::= "b" "c"*
```

The grammar engine accepts and round-trips `bca`. Yet
`prove_regular(rules, "sub", CharSet.from_chars("a"))` returns a proof whose
recognizer cannot consume the valid `sub` extent. `inner` was proved against
the outer `a`, not its local `c` continuation, so its possessive `"c"*` steals
the caller's `c`.

The existing consult-soundness prototype covers inline-group continuation, not
named-rule continuation. A census of the currently installed ground-truth
consults found no recognizer closure larger than one rule, which limits present
corpus exposure but does not make the generic proof sound. The proof must
propagate occurrence-local follow through the closure, or conservatively
decline every closure shape for which it cannot do so. A nested-reference
witness belongs in the eventual gate.

### High — the verified flat program is neither the sole authority nor fully frozen

`ModelBinding` lowers and verifies `program`, but it also retains the caller's
authored `rules` mapping and constructs `ProductExecutor` from that mapping.
Earley completion executes those authored records directly. PDA build
specialization also reads authored rules and construction data; the flat
clone's completion reference remains provenance rather than executable
authority.

A one-rule diagnostic showed the consequence:

- `binding.rules` was a mutable `dict`;
- `binding.executor.rules is binding.rules`;
- `binding.program.rules` was an immutable tuple;
- clearing `binding.rules` after verification left the verified program intact
  but made the same valid parse refuse because its product vanished.

This does not require the PDA to interpret generic bytecode in its paid loop.
Compile-time specialization is desirable. It does require one frozen, verified
bound authority and engine-specific projections derived from that authority.
The current `compile/README.md` statement that one compiled program is executed
by both engines is stronger than the implementation.

The nested data also needs an immutability audit: lowering accepts arbitrary
mappings, route records retain mapping-shaped data, and replica construction
re-lowers retained authored ownership. Equality between replicas is not the
same property as deriving all consumers from one immutable verified artefact.

### High — Earley and token completion resolve construction afresh for every node

`product/tree.py::_complete_node` calls `construction_of` on every completed
node. For records and cold symbols, that builds a new `Construction`, rebuilds
the optional-index `frozenset`, and may call `fast_construct()` through
`_licence_of` every time. The deleted fold path resolved this configuration
once when the fold was created, and PDA specialization likewise resolves it
once while baking a clone.

This is duplicated work on the ordinary Earley path, the token path, and any
ambiguity replay or fallback that completes trees. It is therefore a direct
no-regression concern, not merely ABI cleanup. The binding/executor should
pre-resolve one immutable completion/construction row per rule. External
Earley and token comparisons should measure that corrected shape, not accept
the current avoidable per-node cost.

### High — physical verification still accepts malformed operand semantics

`product/verify.py` now checks many opcode rows and operand-table bounds. That
is a real improvement over the earlier snapshot, but the claimed cold gate is
still incomplete.

A constructed program containing `DecodeOp(0, 999)` lowered and passed
`verify_program`, leaving the invalid decoder tuple `(0, 999)` in the verified
artefact. The verifier bounds the decoder-table entry, but does not validate
the decoder vocabulary and its operands.

The final verifier also needs explicit checks for the remaining cross-table
relations: capture modes against the lanes their completion can consume,
constructor capture/name/optional/default consistency, route identifiers and
destinations, continuation indices, and uniqueness or validity wherever an
integer is a code rather than merely an array position. Some lanes are not
executed by the current model product, but §5–§9 plan to rely on them; that is
why the generic verification contract must be true before those stages.

### High — the `SymbolExpr` cold-only restriction remains prose, not structure

`RuleProduct` permits an expression program containing `SymbolExpr` for any
rule, lowering exposes the registry to every product, and
`construction_of`/PDA bake can turn a sole symbol expression into the callable
used at completion. Nothing in the type or binding surface prevents a symbol
callback from being placed on a frequently completed grammar rule.

The current shipped census being cold is evidence about today's declarations,
not enforcement of the promised ABI. Either give cold symbolic transforms a
structurally distinct declaration/binding path, or lower the intended general
operation into the engine's real product algebra. A registry key alone solves
`eval`; it does not solve hot-path authority or cost.

### High — JSON's numeric semantic event is attached to the wrong boundary

`grammars/json.py::JSON_EVENTS` maps the complete `number` rule to `integer`
and the interior `frac` suffix to `fraction`. The suffix does not carry the
complete signed/exponent-bearing value, and an exponent-only number such as
`1e3` has no `frac` occurrence at all.

The integer/fraction choice must be made at the completed number boundary from
the complete semantic value or an equivalent target declaration. The generic
engine must not hardcode JSON names or spelling. The corresponding completed
TODO claim should be reopened until that formulation-neutral boundary exists.

### High — the no-erasure gate is not met

The late-restart diff is not an adequate basis for claiming that no forbidden
types were added. The active product code still contains newly introduced
`object` boundaries, including the symbol registry and constructor protocol in
`product/lower.py`, and `verify_exact_ints` uses `Iterable[object]` where the
input is specifically an integer-coded table. The broader PDA work still
contains unresolved `Any` frame and sink boundaries and suppression comments
tracked by the §4 gate.

The effort's explicit rule is no `Any`, `object`, or ignore directive. These
boundaries need named protocols, carrier parameters, or concrete heterogeneous
record shapes. Calling the erasure honest does not satisfy the gate; changing
that rule would require the user's explicit decision.

## Reconciliation with the first snapshot

The first review was written before several later savepoints. Its findings now
stand as follows:

| Earlier finding | Current status |
|---|---|
| Switch differential did not switch completion | **Closed.** The fold module and completion channel have been removed. |
| Authored product could not express model semantics | **Closed.** Pass-through, record, value-string, and unlicensed construction are represented. |
| `SymbolExpr` was an unrestricted callback channel | **Open.** The restriction remains documentary. |
| JSON numeric semantic boundary was wrong | **Open.** The mapping remains unchanged. |
| Ambiguity replay conflated absence with Python `None` | **Closed.** Completion uses an explicit present/empty result. |
| Physical verification was incomplete | **Improved, still open.** Many lane bounds exist; decoder and relational validation remain. |
| Ordinary parsing carried unapproved work | **Pending its scheduled gate.** Do not infer a regression or approval before clean external measurement. |
| Forbidden erasure and suppressions remained | **Open.** Suppression cleanup and type-boundary cleanup are separate obligations. |
| Baseline-result reuse was underspecified | **Closed in the plan.** Reuse is now limited to family facts and identical child-image keys, not transformed lifts. |

## Deliberately later gates — not findings yet

The following are scheduled work, not evidence that the current increment is
wrong:

- Luna's full test mirror and contract port have not run yet.
- The consult measurements were taken with cyclic GC disabled. The ordered
  GC-on acceptance gate and the user's keep/drop decision are still open.
- The clean external alternating comparison against the original parser has
  not run yet. No parsing performance conclusion should be drawn before it.
- Documentation still contains stale fold-era descriptions; the general docs
  pass is scheduled after implementation and cleanup.

The current Terra report's consult wins and small control overhead are useful
directional data, not the final performance proof. In particular, JSON remains
one witness rather than a privileged client, and each supported grammar and
route needs its own current-versus-projected comparison.

## Interim pre-checkpoint disposition

Do not nuke the migration on the evidence in this snapshot. The replacement of
the fold channel and the shared product semantics are valuable and materially
closer to the intended architecture.

Before the §4 checkpoint is accepted, the completed source should be checked
for all of the following:

1. sound occurrence-local continuation in regular-region proofs, with a nested
   named-reference witness;
2. one immutable verified binding authority and immutable engine projections;
3. construction resolved once per rule, not once per completed tree node;
4. a verifier whose advertised physical and relational guarantees are true;
5. a structurally enforced answer for cold symbolic transforms;
6. a formulation-neutral complete-number semantic boundary;
7. removal of forbidden erasure and suppressions;
8. Luna, generated-twin, clean external parsing, and ordered performance gates.

This list is provisional. Re-review the final §4 increment, close what the
later implementation demonstrably solved, and add any issue exposed by the
remaining gates before folding the review into the plan.
