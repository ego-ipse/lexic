# Invariants

**When to load:** checking whether a proposed change is safe; understanding what dispatch tables must do; verifying round-trip or property test obligations.

Source: `prototyping/next/1_NORTH_STAR.md`. Every change must preserve these.

## Non-negotiable

**Grammar is canonical.** Every class has a lossless `to_grammar(flavour)` path to the grammar text it represents. The class is Python's view of the grammar, not the source of truth.

**Round-trip fidelity.** `parse(text, grammar).to_text() == text` on every grammar-valid input. Property tests on all ground-truth grammars stay green.

**No regression.** The full test suite (1500+ tests, see CLAUDE.md §Commands for the current count) stays green after every change.

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

## Atom union is closed but versioned

No code constructs an atom whose type is not in the declared union. Adding a new type (e.g. `TokenAtom`) is a minor version bump and requires updating every dispatch table. Dispatch tables must have explicit `raise UnsupportedConstructError` defaults — a missing type is always caught at dispatch, not silently mishandled.

## Ground-truth grammars

These live in `resources/ground_truth/`. All integration and property tests run against all of them; a change that makes any one fail is a blocker regardless of unit-test status:

`arithmetic`, `c`, `chess`, `japanese`, `json`, `json_arr`, `json_ws`, `list` (`.gbnf`), plus `arithmetic`/`json` `.abnf` siblings used for cross-flavour compile parity.

## What these invariants mean in practice

- You cannot add a new atom type without updating every open dispatch table it touches (`codegen/binding.py`, `codegen/model_emitter.py`, each flavour's emit `actions`, its `Reducer`).
- You cannot change `to_text()` without running property tests.
- You cannot add a new entry point that bypasses `compile.py` without a discussion.
- You cannot open a new runtime→codegen import edge.
