# Ledger — target-shaped parsing

## CURRENT SESSION — reviewed handoff (2026-08-27)

**Scope:** replace model-then-fold reduction with one engine-neutral product
architecture which constructs the requested final codomain during recognition.
The standing tokenizer witness must reach a ready `IrTokenizer` without a
generated JSON model, full JSON `IrMap`, sidecar carrier tree, `ReduceFold`, or
`tokenizer_of` traversal on the reader path.

**Starting tree:** branch `targeter` at `0faa7289` (`Prepare 0.0.2a0 release`).
The rejected direct-carrier commit and its source changes were nuked by the
user. The remaining uncommitted carrier file was deleted by the user before
this effort was separated. Do not reconstruct or salvage that implementation.

**Design state:** substantive pass 2 is recorded in `reports/REVIEW_2.md`. Its
three blockers now have focused executable mechanisms in
`route_continuation.py`, `cache_lifetime.py`, and `suspended_fragment.py`:
following-child routing happens before entry in both engine state models,
morphism binding cannot retain an expired compiled artefact and serializes a
concurrent cold build, and routed/shell MT carries a concrete suspended product
continuation with associative duplicate/verdict joins rather than a generated
model. Pass 3 then found that the public declaration still embedded the mutable
cache owner. That blocker is now corrected: public morphisms contain recursively
immutable declaration data only, while a distinct private compiler/artifact
registry owns locks, factories, executors, entries, and source release.
`product_types.py` also uses constant-size marks, mutation-proportional undo,
and one checked tagged completion-range index over separate instruction tables.
`selection_contract.py` fixes the finite nested-mapping beginner semantics. All
prototypes pass the repository Pyright environment and their executable
assertions; see `reports/PROTOTYPE_2.md`. Source implementation has not started.

**Performance feasibility:** `reports/PROTOTYPE_3.md` profiles the actual
grammar-derived capture loop. The loss was a shared cached regex pattern, not
dict allocation or the already-local source string. Cache-distinct worker
patterns reduce exact eight-worker vocab capture/join from 0.097326 s to
0.064854 s; the same ownership result holds for GBNF, ABNF, and EBNF. Separate
whole-region discovery is rejected because it costs 0.392020 s and duplicates
capture. Compiler-derived route proposals plus O(workers) cuts build both Qwen
high-volume regions, joins, duplicate state, and exact ranks in 0.113811 s on
eight workers. A shell representation/control check costs 0.001864 s over the
6,098-character Qwen shell and declines nested false, reordered, and escaped
proposals, but is not production typed-hole certification.

`reports/REVIEW_6.md` correctly rejected adding that native capture number to a
freeze of separately pre-created IR leaves. `reports/PROTOTYPE_4.md` closes the
carrier accounting gap: per-entry IR scalars/dyads cost 0.346817 s and are
rejected; primitive tokenizer-index payloads measure 0.138739 s from resident
text through capture/join, canonical immutable indexes, and an actual tokenizer
record, with about 79–82 MiB first-run RSS growth. Encode/decode order is token-id
order and ranks order is rank order, so equality/hash and every emitted form
have one canonical physical order without repr sorting in the direct case.
Small fields, the production shell, target setup, pipeline/root checks, and the
ready result remain unmeasured. `src` remains unchanged.

The user clarified that 105x is a Qwen tokenizer optimization goal, not a
universal gate for every reduction. Every codomain instead reports current and
projected like-for-like performance. The current tokenizer references are
17.203148 s resident and 17.416359 s path-inclusive. An isolated source read
measured 0.046713 s first-read / 0.019701 s median, but does not replace the
historical 0.213211 s stage; final resident, cold-path, and warm-path rows stay
separate.

**Start gate:** `reports/REVIEW_4.md` and the fresh independent
`reports/REVIEW_5.md` both give GO for §2 and ABI/lifecycle §3. §3 now owns the
real recognition-time route, physical completion-table verification,
transaction/fresh-alternate cost, and cache-release integration gates; §4
remains closed until they all pass. The parsing ABI owner is decided as the focused
`src/lexic/parsing/product/` package (`records.py`, `state.py`, `verify.py`, and
one `__init__.py` façade), not an open file-versus-package choice.

**Final coordinator rulings:** Earley routed advancement uses a sparse
`(waiting contextual code, route) -> successor contextual code` table so the
existing packed item carries identity and ordinary `_advance_all` stays
untouched. PDA retains `(consumer position, route)` in the parent frame until
that occurrence advances. Earley ambiguity folds each actual alternate from a
fresh state; production does not clone live builders. Direct tokenizer parsing
builds primitive encode/decode/rank payloads together and finalizes through the
required `IrTokenizer.from_indexes` tail over three tokenizer-native immutable
index roles, canonical by id/rank.
Tokenizer schema mappings are closed:
fields are consumed, explicitly irrelevant/recognition-only, or refused;
dynamic maps are deliberately open. No accidental pre-alpha reader behavior
or old internal structure is a compatibility obligation.

**Authority and sequence:** the user's grant remains: “Grants remain
applicable. Commit meaningfully (orchestrator only).” The 2026-08-27 ruling
licenses coordinator-only checkpoint commits without requiring the full
done-gate at each checkpoint; the reviewed series is squashed into `main` after
Luna's final gates. Terra implements all source and cleanup first. The
coordinator profiles the generated-model ABI at §4 and the complete source
after §11. Only then does Luna write/port tests and own formatting, lint,
pyright, and gates. Terra and Luna run sequentially. If tests or formatting
require a source correction, return to Terra, reprofile the exact corrected
tree, then return to Luna.

**Checkpoints and compaction:** the coordinator reviews and commits after §4,
§5, §7, §9, and §11. Terra writes a checkpoint report and ledger update, then
continues warm through adjacent increments. Run `tools/usage_watch.sh 90 60
540` during agent-heavy work and follow the repository's hold/resume protocol.
The first checkpoint includes the external §4 paid-loop measurement. The §5
checkpoint includes the last broad direct-versus-`ReduceFold` differential and
leaves the old oracle with no production caller.

**Hard measurement ruling:** instrumentation never touches `src`. Prototypes
live only in `zzz_current_work/260826-target-shaped-parse/proto/`; reports live
in `zzz_current_work/260826-target-shaped-parse/reports/` and retain the
established report style. Run one benchmark process at a time and never run two
multithreaded benchmarks concurrently.

**Parsing non-regression ruling:** existing generated-model and
token-segmented parsing performance may not regress. Reduction, tokenizer,
memory, or MT gains cannot offset it. A correctness bugfix does not waive the
gate; after isolated measurement and attribution, only the user's explicit
final approval may accept such a regression.

**Final optimization audit:** the stale prototype `ParseState.fork` and builder
clones were removed; fresh alternatives/islands now carry only finished values
and verdicts. Generated-model parsing must allocate no unused `ParseState`, run
no transaction/range-verifier branch, and gain no frame slot or generic
completion dispatch. Recognition-time route decoding must be direct lowered
scalar work, with cardinality-specialized lookup rather than the prototype's
tuple scans. Target-aware MT uses route proposals plus pre-submission typed-hole
shell certification and per-fragment entry/exit certification, not an all-mark
pre-pass, and every concurrently hot recognizer is physically worker-owned
despite the regex source cache. The tokenizer final-table accumulator uses the
selected primitive index roles; canonical `IrMap` repr ordering is not a
tokenizer requirement, while id/rank order is. MT baseline/candidate
processes are prepared
and warmed serially; `tools/benchmark/compare.py` is not used unchanged because
its concurrent preparation performs real parses. Base parsing remains equally
fast or becomes faster while each codomain reports its own current/new
comparison and the Qwen tokenizer path independently pursues the roughly 105x
goal.

**After queue:** `TBD_after.md` carries the user-pinned 16-core 8–10x target,
payload/export optimization, and the putative I22 step-5 overlap question. None
is permission to interrupt or widen the active `TODO.md` implementation.
