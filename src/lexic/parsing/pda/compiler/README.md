# `parsing/pda/compiler` — compile the grammar into flat runtime tables

`compile_pda` turns a **lifted codegen grammar** (the shape
`GrammarAnalysis` runs on) into `PdaTables`: the clones the runtime walks,
the island set, and a lazy per-island `ParserTables` cache for the rules that
fall back to Earley. It reads the analysis' stored gate specs — never
recomputing — and raises `UnsupportedConstructError` if a stored spec cannot
attach to the arms it sees (taxonomy↔compiler drift is a bug to fix, not an
escape). This folder imports `../analysis` + `../core`.

## `clones.py` — the clone compiler

**Clones.** A rule is compiled once per distinct **hard continuation** that
reaches it, so its loop stop-sets are call-site-exact. `ensure_rule` reserves
the clone key with a pending placeholder *before* compiling, so recursion
resolves to the in-progress key and a repeat `(name, tail)` reuses the clone.
Island rules are never cloned — a reference carries an `IslandRef`, and a
`fail` island's ref raises `PdaFail` to force the engine fallback.

**Item specs.** Each grammar item compiles to a flat `ItemSpec`
(`lit` / `cc` / `ref` / `grp`) with its bounds and, for a loop, exactly one
loop gate drawn from the stored taxonomy: `StopGate` (the call-site-exact
stop-set), `PairGate` (2-char), `KTupleGate` (k-window), `PeekGate` (char-set
noise-skip), or `ScanGate` (structured noise-skip / probe). Arm selection is a
FIRST-gated `ArmSpec` list plus at most one nullable **default** arm; a
FIRST-overlapping alternation with no stored spec raises — the anti-guess
tripwire.

## `specs.py` — the compiler intermediate

The tuple-coded NamedTuples `compile_pda` produces before lowering:
`CloneKey`, `IslandRef`, the loop gates (`StopGate` / `PairGate` /
`KTupleGate` / `PeekGate`, with `ScanGate` from `core/` completing the union),
and `ItemSpec` / `ArmSpec` / `GroupSpec` / `CloneSpec`. This is the shape the
structural tests pin. A pure-data leaf — it imports only `CharSet`,
`RuleFold`, and `ScanGate`; `clones.py` re-exposes it as its public surface.

## `flatten.py` — the int-coded runtime program

The clone/arm/item specs are the *intermediate*; `flatten.py` lowers them once
per compile into `FlatClone` / `FlatArm` carrying `OP_*` op-codes and
pre-resolved `(chars, negated)` membership sets — the artifact the kernel walks
with pure integer dispatch. `optimize_program` then runs the specialisation
passes that carve the hot loop: exactly-once terminals, inlinable `value_str`
references, frame-less leaf clones, pass-through dispatch clones, exactly-once
calls (skipped for a clone that selects by a k-window / noise-skip / scan
gate, whose branch must survive dispatch). All of this is a build-time cost
paid once; the program is shared and immutable across every parse. `flatten.py`
imports nothing from `clones.py` — the `spec → flat` bridge lives beside the
specs it reads.

## `delegate_compile.py` — island-interior delegation

Given one island's sub-grammar, `DelegateSource` picks the conflict-free,
non-nullable, semantic interior rules worth delegating and compiles each to a
PDA clone that the island's Earley sub-parse runs in place of the item
machinery — for every island. It is a clean leaf: the two clone-compiler entry
points it needs arrive as **injected callables**, so it imports nothing from
`clones.py` and the `clones → delegate_compile` arrow runs one way.

See the package `README.md` (§11–§13) for the clone model, the flatten
artifact, and delegation in full.
