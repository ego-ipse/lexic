# Invariants

**When to load:** checking whether a proposed change is safe; understanding what dispatch tables must do; verifying round-trip or property test obligations.

Every change must preserve these.

## Non-negotiable

**Grammar is canonical.** Every class has a lossless `to_grammar(flavour)` path to the grammar text it represents. The class is Python's view of the grammar, not the source of truth.

**Round-trip fidelity.** `parse(text, grammar).to_text() == text` on every grammar-valid input. Property tests on all ground-truth grammars stay green.

**Ambiguity is refused, by both engines.** A span whose derivations build two different models raises rather than one engine quietly picking — the PDA's "first" and Earley's "first" are not the same first, and a parser that answers an ambiguous question is not answering the question asked. The test is about VALUES, not derivation counts: a grammar routinely derives one text several ways without meaning anything by it. A *split* — one production carved two ways, same arm, different boundary — has a defined answer (the first slot owns the text) and is never refused; only an *arm* choice, two different productions over one span, is a question the grammar left open. The opt-out is a caller-supplied deterministic resolver, not a flag; it reaches whichever engine ends up choosing, so the answer never depends on the route.

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

## Probes never nest — a POLICY invariant, not a shape one

A fork's frames carry `inherited`, and `adopt_inherited` prepends **one**
origin's sinks at the build. That is the whole prefix only because forks never
nest: every `inherited` chain is length 1.

Nothing structural prevents nesting. One branch does — `if self._caches.probing:`
in `decisions.py`, which resolves an interior boundary greedily by class instead
of forking again. `_fork_verdict` is the only entry to either `frames_copy` call
site, and it sits in that branch's `elif`. `frames_copy` raises if the root frame
of the stack it is copying already carries `inherited`, so the policy is checked
rather than carried.

Two plausible optimisations break it **silently**, producing a model with values
missing and no exception anywhere:

- committing a winning probe's stack instead of re-driving a decision already
  paid for — the committed frames would still be marked;
- resolving interior boundaries exactly, to kill `uncertain` — that is the very
  branch the invariant rests on.

Either needs `adopt_inherited` to walk the chain first. Do not add that walk
before then: with forks that cannot nest it is dead code that makes nesting look
supported.

## What these invariants mean in practice

- You cannot add a new atom type without updating every open dispatch table it touches (`codegen/binding.py`, `codegen/model_emitter.py`, each flavour's emit `actions`, its `Reducer`).
- You cannot change `to_text()` without running property tests.
- You cannot add a new entry point that bypasses `compile.py` without a discussion.
- You cannot open a new runtime→codegen import edge.
- You cannot make an interior boundary resolve by forking without teaching
  `adopt_inherited` to walk the `inherited` chain first.
