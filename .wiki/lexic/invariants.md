# Invariants

**When to load:** checking whether a proposed change is safe; understanding what dispatch tables must do; verifying round-trip or property test obligations.

Source: `prototyping/next/1_NORTH_STAR.md`. Every change must preserve these.

## Non-negotiable

**Grammar is canonical.** Every class has a lossless `to_grammar(flavour)` path to the grammar text it represents. The class is Python's view of the grammar, not the source of truth.

**Round-trip fidelity.** `parse(text, grammar).to_text() == text` on every grammar-valid input. Property tests on all ground-truth grammars stay green.

**No regression.** The full test suite (1500+ tests, see CLAUDE.md §Commands for the current count) stays green after every change.

**One way per task.** One parse function, one emit method, one round-trip method. No alternate APIs, no legacy shims, no "simpler subset" wrappers.

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
