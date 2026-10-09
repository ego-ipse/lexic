# Invariants

**When to load:** checking whether a proposed change is safe; understanding what dispatch tables must do; verifying round-trip or property test obligations.

Every change must preserve these.

## Non-negotiable

**Grammar is canonical.** Every class has a lossless `to_grammar(flavour)` path to the grammar text it represents. The class is Python's view of the grammar, not the source of truth.

**Round-trip fidelity.** `parse(text, grammar).to_text() == text` on every grammar-valid input. Property tests on all ground-truth grammars stay green.

**Ambiguity is refused, by both engines.** Both engines apply the configured split decider top-down to select the preferred carvings, then refuse surviving arm alternatives that produce different model values unless a caller-supplied resolver resolves them, rather than one engine quietly picking — the PDA's "first" and Earley's "first" are not the same first, and a parser that answers an ambiguous question is not answering the question asked. Ties keep their alternatives for the ambiguity check; chart order never breaks a semantic tie. The test is about VALUES, not derivation counts: a grammar routinely derives one text several ways without meaning anything by it. Which carving a span keeps is the split DECIDER's, a value in the parse configuration both engines consult: leftmost-longest over the authored slots, top-down, the boundaries first. A choice between derivations whose boundaries differ is decided by it — a repetition's iteration count, an operator's grouping, an arm that exists only where an earlier slot ends early — and is never refused. Only an *arm* choice at the boundaries the decider keeps, two different productions over one span that each derivation shares, is a question the grammar left open. The opt-out is a caller-supplied deterministic resolver, not a flag; it reaches whichever engine ends up choosing, so the answer never depends on the route.

**No regression.** The full suite stays green after every change, and `tools/run_checks.sh` exits 0 — it prints a pylint score even while failing, so the exit code is the gate, not the output.

**One way per task.** One parse function, one emit method, one round-trip method. No alternate APIs, no legacy shims, no "simpler subset" wrappers.

**`ir/` is vendor-neutral.** No third-party format, product or model name
appears in `lexic.ir` — not in code, not in a docstring, not in an example.
The spine models the *concept*; a format's own vocabulary is declared beside
the reader that knows it (`lexic.api`), and `IrPretoken` is open-set so a
vendor's families need no dispatch-table edit in the engine. A named
*algorithm* (Earley, the ranked-merge rewrite) is not a vendor, and neither
is ordinary terminology that predates a product — "byte-level" describes a
vocabulary spelled over bytes; `ByteLevel` is one library's class.

A grep in `test_layering_invariants.py` catches NAMES. **It is a floor, not
a proof**, and reading it as one is the actual hazard: two escapes so far
were introduced by the very commits claiming to close this class, and both
used neutral characters — a byte-token spelling (`<0xNN>`) and a docstring
generalised past what the code did. Neither names a vendor.

So the question to ask when adding to `ir/` is not "does the grep pass" but
**"is this value the CONCEPT, or one producer's answer to it?"** A grep
cannot ask that. Evidence that nothing cheaper will: a targeted adversarial
review also failed to separate provenance from defect on this exact question
— it filed the finding, chased it, and withdrew it.

**An emitted module and its `.pyc` agree, always.** Lexic writes the
byte-compiled form itself, under `UNCHECKED_HASH`, which makes it outrank its
source unconditionally. So every path that lands a module must leave the pair
consistent at every point — including a crash between two steps. Whoever writes
the `.py` writes the `.pyc`.

**A compiled artefact refuses rather than reads wrong.** Its tables carry a
digest; its symbols carry the rules they were built against, or — for a class
carrying no rule — the module they came from. Each catches a different way the
value can be right-looking and wrong: an altered table, a recompiled grammar, a
name rebound to another module's class. None of them is optional, because all
three failures are silent without it.

**A memo key is valid only while something holds the object.** Any cache keyed
on `id()` must keep the object alive for the cache's lifetime. An id is reused
the moment its object is freed, and a lookup then answers confidently about a
different object — which no test of the cache's own behaviour will show.

**Arrows go one way.** Runtime depends on IR; codegen depends on IR; runtime does not depend on codegen. The two deliberate exceptions in `compile.py` and `base.py` are fixed and documented. See [[architecture]].

## The windowed find answers exactly what the serial walk answers

`par_find` is a different algorithm from `find` — windows, an underflowing
stack, a replay — reaching the same answer. The invariant is region-for-region
equality: same count, same offsets, same rule, same separators, same ORDER.
It is proved by differential over every bench grammar and both ground-truth
json formulations, at several window counts and both floors, plus fuzzed
ragged documents, since `find` is a SCAN and must agree on malformed input too.

Two properties the differential must keep or it proves nothing. A grammar whose
vocabulary carries an opaque interior is REFUSED the windows, so comparing one
only shows that the refusal returns the serial answer — the windowed path is
exercised through grammars asserted to be skip-free. And a character carrying
two roles, a separator that is also a closer, is what distinguishes the sweep
alphabet from the classification spelling; a fixture holding that property is
required, and asserted to hold it.

## The parser's per-character loop is pinned by its bytecode

Split discovery may be rewritten freely. The loop that executes once per input
character may not change as a side effect of that work, and since both are
edited in the same efforts the question is answered by the compiled code rather
than by recollection: each named function is pinned by the SEQUENCE OF ITS
INSTRUCTION OPNAMES. Not the source, which reformats; not raw `co_code`, which
moves when a constant is renumbered.

A red row asks a question rather than reporting a defect — if the loop itself
was the work, the digests are regenerated by an explicit documented step and
that diff is the record. An interpreter upgrade moves every row at once, which
is the tell for regenerating rather than investigating.

## The artefact is the flat program, not what it was lowered from

A compiled artefact carries what the runtime executes and nothing it was built
through. `PdaTables` holds the flat `PdaProgram`; the authored
`CloneSpec`/`ArmSpec`/`CharSet` layer the clone compiler produced on the way
there is a compile-time intermediate and goes away with the compiler that made
it. Keeping it "for introspection" held a fifth to two fifths of the artefact's
GC-tracked population alive for the life of the process, walked by every full
collection, read by nothing on the parse path.

A caller that genuinely wants the specs compiles them itself
(`compile_clones`), where their lifetime is its own. That is the general shape:
an intermediate's owner is whoever is still using it, and "a test might want to
look" is not a reason for an artefact to retain one.

## Atom union is closed but versioned

No code constructs an atom whose type is not in the declared union. Adding a new type (e.g. `TokenAtom`) is a minor version bump and requires updating every dispatch table. Dispatch tables must have explicit `raise UnsupportedConstructError` defaults — a missing type is always caught at dispatch, not silently mishandled.

## Ground-truth grammars

These live in `resources/ground_truth/`. All integration and property tests run against all of them; a change that makes any one fail is a blocker regardless of unit-test status:

`arithmetic`, `c`, `chess`, `japanese`, `json`, `json_arr`, `json_ws`, `list` (`.gbnf`), plus `arithmetic`/`json` `.abnf` siblings used for cross-flavour compile parity.

## Forks nest three deep at most, and only when a forked verdict is asked again

A fork's frames carry `inherited`, and `adopt_inherited` prepends the values of
the whole chain (`Frame.inherited_prefix`, oldest first), so a fork of a fork
builds with every origin's values and writes to none of them.

A boundary inside a side resolves greedily by class, a guess, except while a
forked verdict is asked again (`_retried`): then the boundary gets a verdict of
its own (`_nested_verdict`), as does an island's extent inside a side, up to
`NESTING_DEPTH` sides deep and within `_NESTING_BUDGET` nested verdicts per
retry. Past either it stays a guess, and a nested verdict that is itself
undecidable does too. `frames_copy` raises past `NESTING_DEPTH` forks, so the
bound is checked rather than carried. A nested side settles the sub-runs its
outer side still has to (`_inherited_floors`); an entry its own drive started
at the bottom owns its root.

A retried drive spends the budget, so it cannot be reproduced by driving again:
a side built while `nesting` is set keeps its ledger, and the rank reads the
sides at hand.

## What these invariants mean in practice

- You cannot add a new atom type without updating every open dispatch table it touches (`codegen/binding.py`, `codegen/model_emitter.py`, each flavour's emit `actions`, its `Reducer`).
- You cannot change `to_text()` without running property tests.
- You cannot add a new entry point that bypasses `compile.py` without a discussion.
- You cannot open a new runtime→codegen import edge.
- You cannot make an interior boundary resolve by forking without teaching
  `adopt_inherited` to walk the `inherited` chain first.

## No module reaches into another module's private names

A name two modules share is its defining module's public surface: it drops its
underscore there and joins that module's `__all__` when it has one, or it moves
to the module that owns the behaviour. Nothing under `src/`, `tests/`, `tools/`
or `ext/` imports `_name` from another module or reaches it there in any other
spelling: an attribute read, a `getattr`/`setattr`/`monkeypatch` string, a key
of the module's `vars()` or `__dict__`, or a dotted patch target. `__dunder__`
names are not private. A module's own private stand-in for a public name it
patches keeps its underscore.

The rule covers a module's names only. A test may reach into a class's or an
object's private attributes to see what a method did, and that does not make
them public. Outside tests, such a reach means a public interface may be missing
— a design question, not a renaming. Enforced by
`tests/integration/lexic/invariants/test_no_private_imports.py`, an AST walk
over every file.
