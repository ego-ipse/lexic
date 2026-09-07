# `parsing/product` — the engine-neutral product ABI

One compiled program, executed by both engines. A
`value_str`/`sequence`/`alternation` fold vocabulary would make the generated
model the engine's privileged construction shape; a `ProductProgram` is neutral
instead, so building a generated model is a *specialisation* rather than the
thing every other target has to be expressed in terms of.

## The two layers, and why they are separate

```
authored records ──lowering──► flat int-coded tables ──verify──► the paid loop
 (readable, typed,              (plain ints indexing            (compares and
  IntEnum allowed)               separate typed tables)          indexes ints)
```

The authored layer is what a compiler writes. The flat layer is what an engine
runs. Nothing carries an `IntEnum` across that boundary: `verify_exact_ints`
audits with `type(value) is int`, deliberately **not** `isinstance` — an
`IntEnum` member satisfies `isinstance(x, int)` and would ride into a runtime
table, paying an enum lookup on every completion.

## One completion range per rule

A rule holds exactly one `CompletionRange`, tagged with the physical table it
indexes. The expression table (the reducer's own algebra) and the fused table
(a target constructing directly) are separate objects, so *"a rule executes one
or the other, never both"* is structural rather than a convention — there is no
pair of fields for a rule to populate twice.

`verify.py` runs once per bound program and refuses a missing, empty,
mis-tagged, or out-of-bounds range, an unknown opcode, and an operand past its
typed table. It is cold work: a defect of the artefact is diagnosed with words
*before* the loop starts, never as a crash inside it.

## Two bodies, one field

A rule's `completion` is ONE field holding either a fused target operation or
the reducer's own `ExprProgram`. Its *type* decides which physical table the
rule lowers into, so "executes one or the other, never both" is a property of
the record — not a rule about not filling two fields.

The expression vocabulary (`ExprCode`) covers what a reducer body actually
does: access, build, compute, control, lookup, refusal, contribution. §3 owns
its definition; lowering the shipped reducers through it is §5's job.

## Routes never scan

`RouteTable` is the authored cold record — a tuple of pairs. Lowering
specializes it by actual cardinality into one of three classes: `UniformRoute`
(a dynamic mapping classifies nothing), `SingletonRoute` (one equality test),
`TableRoute` (one dictionary probe). Each answers `route_of` with its own code,
so a routed completion pays one call and no test of which shape it holds, and
`destination_of` composes classification with dense destination indexing —
they are two halves of one decision at a producer's completion.

A tuple scan measured 121.9–907.8 ns against 28.9–33.5 ns for a dictionary over
2–64 routes, so nothing scans the authored pairs after lowering.

## What may be a callable, and where

Only three operand tables hold a target-supplied callable — collection finish,
root finalization, and meaning comparison — and none of the three runs at a
frequent completion. Scalar decode, validation, mapping insertion and declared
record construction are engine-owned codes selected by plain int. That boundary
is what keeps the character and item loops free of any test for which codomain
is active.

## State is parse-local, and optional

`ParseState` holds every mutable builder and deferred verdict of ONE parse,
alternative, or worker; it is never shared or cached. Sequence and mapping
accumulators live in separate typed lanes addressed by occurrence-owned
handles, so `Carry` never widens to carry a builder and there is no parse-global
"current collection".

A product with no mutable builder and no deferred verdict — the generated-model
product among them — allocates none, and its completion path pays no state, no
transaction test and no extra frame slot. Whether a product is stateful is
DERIVED from its own lowered instructions, never declared beside them: a
declaration could say `False` for a product that plainly accumulates, and then
the no-state guarantee would rest on a promise instead of on the program.

Speculation is transactional: a `ProductMark` is five integers whatever the
builders hold, undo is proportional to what was actually mutated since the
mark, and a successful outer commit copies nothing — it drops the log, because
a committed mutation is simply kept.

## `regular.py` owns a proof, not a heuristic

A region is regular here in an operational sense: a possessive recognizer over
it accepts exactly what the grammar accepts, consuming exactly as far. Three
obligations, all required — an acyclic simple closure, first-disjoint ordered
arms with any nullable arm last, and boundaries whose atom cannot eat its own
successor's first character. Declining is always safe; the region falls back to
the interpreted product.

The first-set algebra is `pda/analysis/gates/windows.py`'s and the possessive
lowering is `pda/core/scanner.py`'s `build_recognizer`. This module owns the
proof and nothing else — there is no second copy of either.

## Layering

`__init__.py` is the package's one import surface; nothing outside reaches into
a submodule, so the package can be rearranged without a second import path
appearing. The package is a leaf with respect to the rest of lexic: it imports
`lexic.ir`, `lexic.exceptions`, and the `pda` leaves that already own character
sets, first-set windows and possessive lowering — never `lexic.compile`,
`lexic.grammars` or `lexic.api`.
