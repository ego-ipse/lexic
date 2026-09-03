# Terra S4C — the §4 close-out after Reviewer 2 (2026-09-03)

You are a fresh Opus implementer continuing §4 of the target-shaped-parse
effort. Your predecessor `terra-s4b` was lost at the session limit after its
second reviewer reported; nothing that reviewer found has been fixed. You
inherit its brief, its report and its handover, and you close §4's source.

## Read first, in this order

1. `CLAUDE.md`, `docs/STYLE.md` (§7 measurement, §11 test deletion).
2. `zzz_current_work/260826-target-shaped-parse/LEDGER.md` — the top block
   "NEXT SESSION — start here" is the authoritative restart; the rest of the
   ledger is the history of every ruling you must not reopen.
3. `zzz_current_work/260826-target-shaped-parse/prompts/TERRA_S4.md` — your
   predecessor's brief; every rule in it binds you.
4. `zzz_current_work/260826-target-shaped-parse/reports/S4_TERRA.md` —
   sections "FOR LUNA", "Reviewer 1 — the paid path", "Reviewer 2 — the
   contracts (recovered verbatim by the coordinator)", and the final
   "Coordinator restart note". Do not re-read the whole file; it is 2 100
   lines of settled history.
5. `zzz_current_work/260826-target-shaped-parse/TODO.md` §4 — the reopened
   completion-range bullet, the open value-string and verification bullets,
   the Luna-before-hold bullet.

The tree is `7d60f575` (Savepoint 10), clean. Re-read every file before you
edit it.

## The work, in this order

1. **Reviewer 2 finding 3 — the verified program is not the executed one.**
   `ModelBinding.__init__` lowers and verifies a `ProductProgram`, then builds
   `ProductExecutor` from the AUTHORED rules; `_complete_node` runs the
   authored `RuleProduct.completion` through `construction_of`;
   `program.completions` is read by `verify.py` alone. Root fix: the executor
   completes from the verified program's completion ranges and operand lanes;
   the authored operations are lowering input only, held nowhere the runtime
   reads; the replica copy copies verified tables instead of re-lowering.
   Proof: a witness that every rule's executed completion is the program's
   own range and that no second representation exists; the switch
   differential; the paid-path bytecode witness (zero added instructions on
   any pre-existing paid branch — the standing rule). Then, and only then, the
   TODO bullet may be marked again, with the evidence.
2. **Finding 1 — `prove_regular` gives a referenced rule the region follow.**
   Thread each reference's own continuation (the referencing arm's remainder,
   composed with the follow) through the closure walk. Witness rows in
   `proto/s4_consult_soundness.py`: `root ::= word "z"; word ::= a b;
   a ::= ("px" | "p"); b ::= "x"` must decline; the ref-free twin
   `a ::= "p" "x"?` must decline. Declining closures larger than one rule is
   the retreat, not the fix; take it only with the reason written.
3. **Finding 2 — the clone's tail skips nullable followers.** `extent_consult`
   unions the FIRST of the skipped nullable followers into the tail (the
   analysis already knows them), and `eligibility.py`'s docstring says what is
   true. Witness row: `root ::= word gap "z"; word ::= "x" [a-b]+ "q"?;
   gap ::= "q"*` — the proof must now ask the question.
4. **Finding 4** — add the island `EmptyResult` vs `Completed(None)` refusal
   to the "FOR LUNA" created-contracts list with a suggested pin. Add
   Reviewer 2's two stale-fold lines (`compile/notation/parse.py:571`,
   `compile/module/selfgrammar.py:406`) to the §11 list beside Reviewer 1's.
5. Rerun, all exit 0: consult soundness, extent differential, switch
   differential, bytecode witness, census, `s4_bake_identity`, every
   `s3_*`/`s4_*` witness.
6. **The GC-ON acceptance rows.** `proto/s4_consult_gate.py` with the
   collector ENABLED, same protocol (7 rounds, alternating, min, process
   time, quiet machine). Window 1 (GC off) is provenance only. Announce
   "WINDOW START" to the coordinator with the exact runs and WAIT for the
   grant; the user keeps the machine quiet on it. Record the GC state on
   every row.
7. The §4 verification bullets in `TODO.md`, and a fresh full-suite run at
   `-n 8` with every failure attributed by file.
8. Update the "FOR LUNA" section so it is complete against the tree you
   leave: every new or moved module, every deleted-target test with where its
   behaviour lives, every changed contract with the pin, every created
   contract. Write the restart point. Stop. Luna runs after you; you do not.

## Rules that bind you

- No timing outside a granted window; nothing else runs during one.
- Zero added instructions on any pre-existing paid branch; proved by bytecode.
- No `Any`/`object`/`cast`, no suppressions, no private cross-module imports,
  no default-argument state, ≤4 indent levels, one-line docstrings, files
  under 700 lines without shaving pre-existing prose.
- Never commit. Never touch `pyproject.toml`. Never revert a formatting hunk.
- Every ruling in the ledger stands: the list frame stays; group-only case 2
  is a recorded asymmetry revisited at §7; the consult's +9 on OP_LIT is
  disclosed for the user, not waved through and not removed by you.
- Report in `reports/S4_TERRA.md`, appending dated sections; each section
  carries the exact commands and exit codes. Message the coordinator at each
  finding closed, at the window request, and when you stop.
- If your context is compacted, re-read the ledger block and this file
  before acting.
