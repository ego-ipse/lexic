# Plan review — target-shaped parsing, pass 7

**Reviewed:** 2026-08-28, against `targeter` / `0faa7289`, the complete
active-effort record (`context.md`, `goal.md`, `DESIGN.md`, `TODO.md`,
`LEDGER.md`, `reports/REVIEW_5.md`, `reports/REVIEW_6.md`,
`reports/PROTOTYPE_3.md`, `reports/PROTOTYPE_4.md`), the measured prototypes
(`proto/parallel_region_cost.py`, `proto/composed_native_tokenizer.py`), and
the production seams the plan names. This pass combines a coordinator
strategy/engineering review with an independent fresh-context cross-model
reviewer; findings from both are merged into one sequence, most severe first,
and deliberately exclude everything passes 5 and 6 already said. Every cited
mechanism was verified by opening the referenced file in this session. No
source, prototype, or plan document was changed; this report is the sole
artefact.

**Verdict: the architecture stands; the load-bearing arithmetic and the late
gates do not.** Six prior passes audited mechanism correctness — isolation,
lifecycle, routing, canonical identity — and that ground is solid. What no
pass audited is whether the engine being built can run at the speed of the
evidence used to justify it, and whether the phase queue would discover a miss
before the point of no return. Finding 1 is the review's center of mass:
until it has a scheduled mechanism or a recorded regime decision, §§2–11 are
being scheduled against numbers from a different execution model. Findings
2–5 convert the plan's late gates into phase-local ones. Findings 6–8 are
correctness landmines in the Earley half. The remainder are decisions and
plan-completeness gaps that are cheap now and expensive at §13.

## Blockers

### 1 — The tokenizer evidence measures per-entry capturing regexes; the scheduled engine consumes value strings per character, and no phase closes the gap

**Severity:** blocker — performance feasibility.

**References:** `proto/parallel_region_cost.py:80-92,141-170`;
`proto/composed_native_tokenizer.py:36-43`;
`src/lexic/parsing/pda/runtime/matchers.py:241-266,309-339`;
`src/lexic/parsing/pda/runtime/kernel/attempt_inline.py:1-8`;
`src/lexic/parsing/pda/core/scanner.py:1-40,129-134`;
`src/lexic/parsing/pda/compiler/program/lower.py:489-507`;
`reports/PROTOTYPE_3.md:29`; `reports/PROTOTYPE_4.md:74-79`;
`260821-one-path/reports/i23_report.md:94`; `DESIGN.md` §parser consequences;
`TODO.md` §§3–9.

The selected 0.138739 s carrier is a loop that concatenates the lower
`string`/`name-separator`/`int` rule sources into **one** compiled regex with
named groups and consumes an entire `"spelling": id` entry per
`transition.match(...)` call. The shipped engine has no such shape: `vstr_once`
is one select/match/slice/build/append per character, `run_span_once` is one
Python call per run iteration, and the only grammar-to-regex lowerings in
`src` are the noise-closure scanner (recognition-only, capture-free) and the
arm-admission prefix. Nothing in the fourteen phases schedules lowering a
compiler-proved regular composed region into a capturing recognizer;
`PROTOTYPE_3.md:193-196` states the requirement obliquely and `TODO.md`
§9 legislates only the *ownership* of fragment recognizers, not their
existence.

The arithmetic: the current reduction-variant parse runs 11.932296 s at one
core (0.957 MB/s per core) on the witness; the prototype carrier covers the
two regions holding 99.8–100 % of the bytes in 0.713501 core-seconds
(16.0 MB/s per core). That is a **16.7× per-core gap** between the measured
evidence and the engine as scheduled. The regimes differ: the <1.000 s
resident AUTO envelope needs roughly **2.4×** the current per-core rate —
plausible from deleting model construction plus schema specialization — while
the ~105× / ~0.164 s objective needs the full 16.7× and is reachable only
through the regex-shaped fragment program. The plan nowhere distinguishes
these regimes, and its §12 miss-handling ("attribute and optimize remaining
recognition, decode, final-table, allocation, and RSS costs") presumes the
residual is a constructor, not the recognition model itself.

**Required:** before §2, either (a) add an explicit, gated task (at or before
the §7 exit): lower a compiler-proved regular composed region — repeated
entry, no recursion, no ambiguity — into one capturing recognizer per entry,
derived from lower rule sources with no grammar-name case, proven identical to
the generic product on the same region and gated the way §4 gates the model
path; or (b) record the two-regime decision in `goal.md`: <1.000 s is pursued
without that mechanism, ~105× is explicitly contingent on it. Additionally,
measure one grammar-derived completion-op loop over the Qwen vocab region and
publish it beside the 0.121197 s regex row, so the interpreted ABI has a
throughput number before source work relies on its absence.

### 2 — The <0.100 s recursive-Python gate is unmeasured, has no worker-shape contract, and sits 18 % above a C reference

**Severity:** blocker — acceptance coherence.

**References:** `goal.md` §final outcome and §performance acceptance;
`reports/PROTOTYPE_3.md:26`; `reports/PROTOTYPE_4.md` scenario table
("product implementation unmeasured").

`json.loads` — C, single-threaded — measures 0.084940 s on the witness. The
plan gates a pure-Python engine at <0.100 s for the same recursive value over
11,422,654 bytes, names no worker shape for the row, and holds no measurement
of any part of the path. A correct product landing at, say, 0.9 s — a 15×
improvement over the current route — would be recorded as a failed gate
against a floor that is a language-implementation property.

**Required:** rule the row's meaning before §6: (a) gate at the public
`cores=AUTO` engaged shape on the witness host with the sequential row
reported beside it; or (b) demote the number to a pursued objective like the
105× figure; or (c) measure a partial-path probe before §6 opens and then
classify. Whichever is chosen, record it beside the tokenizer row so the two
core codomain gates carry the same kind of contract (see finding 5).

## High findings

### 3 — The first timed measurement of any target product arrives at §12, after §10 has deleted the fallback

**Severity:** high — sequencing.

**References:** `TODO.md` §4 gate, §5/§7/§9 exits, §10, §12.

§4's measured gate deliberately covers the generated-model path that bypasses
the new machinery; §5, §7, and §9 exits are correctness-only. So the
transactional, route-driven, accumulator-streaming path is first timed at
§12 — after the oracle, the templating executor, and the model-stitch paths
are deleted and the docs rewritten. If the miss is architectural (finding 1),
the rollback is seven phases deep with no old path in the tree.

**Required:** add a timed resident-text row to the **§7 exit** (ready
tokenizer, sequential and AUTO, external process, alternating, byte-identical
control) and a direct-IR throughput probe to the **§5 exit**, both recorded in
`reports/` using the existing proto harness. State a stop factor: if the §7
row misses its envelope by more than it, the effort halts there with the old
path still present. §12 remains the complete matrix.

### 4 — The suite, Pyright, and the done-gate are dark from §4 to §13, across five checkpoint commits

**Severity:** high — regression visibility.

**References:** `TODO.md` working protocol (Luna-only gates), §4
("tests relevant to changed files"), §5 (proto-only differential), §§6–11
(no test execution scheduled); `CLAUDE.md` "No regression. The suite stays
green."; 25 of 232 test files reference symbols scheduled for deletion.

Between §4 and §13 no phase runs the suite or Pyright, yet five checkpoint
commits land in that window and §1's entire feasibility premise is a typing
claim. A genuine regression introduced in §6 is indistinguishable from a
deletion casualty because no document records what "red" is allowed to mean.
Separately, `tests/integration/test_doc_drift.py` goes red the moment §3 adds
`src/lexic/parsing/product/` and stays red until §11's doc pass, so the
repository done-gate is unusable as a smoke signal for eight phases.

**Required:** at every phase exit Terra runs
`uv run pytest tests/ -q -n auto` and `uv run pyright` and ledgers the exact
failing-file set with a one-line attribution each; an exit is blocked by any
failure not attributable to a deliberate deletion, and the attributed set may
only shrink once §13 begins. Additionally, each phase that adds, moves, or
deletes a module updates the `CLAUDE.md`/`AGENTS.md` package-map lines in the
same phase (mechanical edit; §11 remains the prose pass), keeping doc-drift
green throughout. Neither change gives Terra test-authoring work.

### 5 — The tokenizer gate row has no defined worker shape, and gating only an MT row has known failure modes

**Severity:** high — acceptance coherence.

**References:** `goal.md` §performance acceptance ("less than 1.000 s wall
for resident text"; "report sequential and 1/2/4/8/16-worker results");
`reports/PROTOTYPE_3.md:29-30` (11.932296 s one core, 8.335490 s AUTO);
`i23_report.md:94` (33.100436 core-seconds for the same stage);
`src/lexic/parsing/parallel/policy.py:64-76`; `DESIGN.md` §parallel parsing
(decline-to-sequential).

The <1.000 s envelope names no worker count; the 0.1387 s feasibility carrier
is an eight-worker figure. Three consequences need ruling. (a) If the gate is
sequential, it demands roughly 5× more single-thread work than the evidence
supports. (b) If the gate is the engaged AUTO row, note the current MT path
buys 1.43× wall for 2.77× CPU *with* table replicas already in place — so a
sequential product several times slower than today could pass the headline
gate while every non-engaged caller (small hosts, pools, declining anchor
shapes) gets the slow path; `cores` is public. (c) When route anchors decline
and AUTO runs sequentially, the gate row as an "engaged shape" does not exist
at all — the plan does not say what gates then. Aggregate process CPU per byte
should be a reported gate quantity beside wall in every case, so an MT row
cannot pass by burning cores.

**Required:** one recorded ruling covering the gate row's worker shape, the
sequential row's status, the decline case, and CPU-per-byte reporting — for
both the tokenizer and the Python-JSON rows (finding 2).

### 6 — The current and new ambiguity relations differ by construction; "exactly differential, including ambiguity" can be unsatisfiable

**Severity:** high — §5 exit oracle.

**References:** `src/lexic/compile/artifact.py:311-341` (current `reduce`
refuses via the variant parse); the `same_value` comparison over built variant
`GrammarModel`s; `DESIGN.md` §Earley and islands (`MeaningOp` over the
constructed value); `goal.md` §correctness acceptance item 1; `TODO.md` §5
exit oracle.

Today ambiguity under `reduce` is judged by structural comparison of two built
variant models. The new product judges it by the declared meaning law over
reduced values. Two derivations whose variant models differ but whose reduced
values coincide are refused today and accepted tomorrow; making the relations
agree would require rebuilding the models §5 deletes. The plan asserts parity
without analysing it, then makes the assertion a mandatory exit oracle.
`CLAUDE.md`'s own invariant — "the question is about VALUES" — argues the new
relation is the correct one.

**Required:** rule now that the value-meaning relation supersedes the
variant-model relation. §5's differential then compares values and refusal
types exactly, with ambiguity-refusal divergences enumerated, attributed, and
coordinator-reviewed rather than required to be zero.

### 7 — Shared SPPF nodes can execute a side-effecting completion twice

**Severity:** high — §3/§8 correctness.

**References:** `src/lexic/parsing/earley/kernel/forest/fasttree.py:86-88`
(memoised subtree spliced into several parents — the built tree is a DAG);
`src/lexic/parsing/fold.py:485` (`if k.__class__ is ParseTree and id(k) not
in results` — an after-the-fact membership guard); `DESIGN.md` §construction
algebra (`AppendSequenceOp`/`InsertMappingOp` mutate parse-local builders).

Two parents can both push the same shared child before either has folded it,
so the fold body runs twice on one node. For today's pure constructors that is
wasted work and an overwritten memo entry. Under the new ABI a doubly-visited
node appends its builder entry twice, and the transaction log holds no mark to
undo it because nothing failed: a valid document nondeterministically trips
the duplicate-key refusal depending on fold interleaving. The design discusses
isolation between alternatives and workers at length and never mentions
idempotence under DAG re-entry.

**Required:** §3's exit gains: side-effecting completion operations execute
exactly once per shared forest node, guarded at fold entry, with a
shared-subtree (nullable / unit-chain) witness through the Earley fallback.

### 8 — "Only the declared local meaning" has no mechanism; the engine refolds from the root per alternate

**Severity:** high — §8 design gap.

**References:**
`src/lexic/parsing/earley/kernel/forest/support/ambiguity.py:160-206`
(`another_meaning` calls the root-rooted build once per sibling root and per
flipped ambiguity point); `DESIGN.md` §Earley and islands ("computes only the
declared local meaning"); `TODO.md` §8 (isolation bullets only).

Nothing in the engine or in §8's bullets computes a subtree-local meaning, so
the honest cost of the design as scheduled is n+1 full-document target folds
at n ambiguity points — for a streaming tokenizer, n+1 full re-streams of
151k vocabulary entries with fresh accumulators.

**Required:** either §8 gains an explicit requirement that alternate meaning
folds are rooted at the ambiguity node with fresh local state (making the
design's "pays another target fold only at an actual competing arm" true), or
the "local" claim is deleted and ambiguity is priced at n+1 full folds. One
or the other, recorded.

### 9 — The differential oracle freezes at §5, but §6, §8, and §9 all change the default-IR path afterwards

**Severity:** high — differential coverage.

**References:** `TODO.md` §5 (broad differential and frozen goldens at the §5
exit), §6 (contextual clones, demand fixpoint), §8 (`MeaningOp`, fresh
alternate state), §9 (bound-product `Request`, fragment composition), §10
(oracle deleted); `goal.md` §correctness acceptance item 1.

The most differential-hungry changes — contextual cloning, ambiguity
rewiring, parallel composition — happen after the last fresh-input comparison
and are covered only by fixed goldens, which are weakest exactly for ambiguity
and composition. The oracle survives uncommitted until §10 anyway.

**Required:** keep `ReduceFold` importable as the uncommitted oracle through
the §9 exit, and add to §8 and §9: re-run the §5 property differential through
`tools/guarded.sh` from `proto/` at each exit, recording command and result in
`reports/`.

### 10 — Deleting templating for `select` drops a reducer-free, model-returning capability, and the loss is recorded nowhere

**Severity:** high — scope decision needed.

**References:** `src/lexic/compile/output/templating.py:583,628-630`
(`template(compiled, shape, spec)` takes no reducer; `Template.run` returns
kept `GrammarModel`s); `getting_started/ex10_templating.py:3-11,53-58`
("works over ANY compiled grammar … grammar-native, not format-native";
asserts `.to_text()` on extracted values);
`tests/unit/lexic/compile/output/test_templating.py:47-48` (toy grammar, no
reducer anywhere); `DESIGN.md` §decision ("a reducer/signature unable to
supply decoded mapping/value events is refused at binding"); `TODO.md` §10
(deletion list), §11 (ex10 rewrite).

Three capabilities disappear with no successor and no recorded loss:
extraction over any grammar without a signature-bearing reducer (everything
except JSON at §2); a round-trippable `GrammarModel` result (`select` returns
reducer values); and `spanify`-style raw-span extraction (the extent target is
a different declaration). Pass 5 blessed the swap on key/order/duplicate
semantics without checking what the current entry point requires of its caller
or returns to it. The ex10 rewrite is additionally contingent on §6 proving
the JSON reducer binds to the GBNF ground-truth formulation.

**Required:** a decision, not a default: (a) keep one reducer-free extraction
morphism in the new architecture — occurrence-demand driven, `GrammarModel`
or certified-extent codomain, no `SemanticSignature` required — so `select`
is the beginner surface over reducers and this is the general one; or
(b) record in `goal.md` that reducer-free grammar-native extraction is
deliberately dropped pre-0.1, rewrite ex10 as a JSON+reducer example, and
accept that the toy-grammar extraction tests are deleted rather than ported.

## Measurement-contract findings

### 11 — The candidate budget was measured with GC disabled; the baseline was not

**Severity:** medium. **References:**
`proto/composed_native_tokenizer.py:182,199` (`gc.disable()` immediately
before the clock, `gc.enable()` in `finally`); `i23_report.md` (no GC note);
`TODO.md` §0 baseline protocol (no GC field).

The 0.138739 s carrier and its 79–82 MiB RSS delta were taken inside a
GC-disabled window on a workload allocating ~300k strings; the 17.203148 s
reference carries no GC statement, and no acceptance row names a GC contract.
The production path runs with GC on. **Required:** add GC state to the §0
frozen protocol, restate the carrier budget with GC enabled, and forbid GC
manipulation in `src`.

### 12 — §12 compares against quoted historical constants, contradicting §0's own alternating-process rule

**Severity:** medium. **References:** `TODO.md` §0 ("compare it later in
alternating whole processes, not by trusting measurements from different
machine states") versus §12 ("compare them with the like-for-like current
17.203148 s resident and 17.416359 s historical path references").

A multiplier whose denominator is a quoted number from a prior effort's host
state can be wrong on landing day. **Required:** §12 re-measures the
`0faa7289` baseline in the same alternating session as the candidate; the
historical constants remain as provenance only.

### 13 — "Reduce peak RSS" is an acceptance criterion with no baseline anywhere

**Severity:** medium. **References:** `goal.md` ("…and reduce peak RSS");
`TODO.md` §0 matrix (no RSS field) and §12 (records RSS with nothing to
compare against); `i23_report.md` (wall and CPU only); `PROTOTYPE_4.md:79-81`
(the only RSS number in the record is the prototype's own increase).

The direction is not even obvious: the new product retains the same final
tables while the old path's peak included transients freed at different
times. **Required:** measure baseline RSS on the `0faa7289` tree in the §0
matrix (resident and cold/warm path rows) and state the criterion as a
number, or downgrade the line to a reported quantity.

### 14 — Free-threading ownership stops at regex patterns; every other per-completion-hot shared object gets the shape just diagnosed as the bug

**Severity:** medium. **References:** `reports/PROTOTYPE_3.md:41-56`;
`DESIGN.md` §parallel parsing (recognizer ownership only);
`src/lexic/parsing/parallel/replicas.py` (exists precisely because shared
table objects were a contention source); finding 5's 2.77×-CPU-for-1.43×-wall
figures, measured *with* replicas in place.

`ProductProgram`/`BoundProduct` flat operand and route tables are one shared
immutable object every worker touches per completion. **Required:** extend
§9's ownership requirement from "compiled recognizer" to every
per-completion-hot object where measurement shows refcount traffic, and make
the §12 ladder attribute scaling loss to a named object rather than reporting
an aggregate.

## Plan-completeness findings

### 15 — Declarations the plan owes before the phases that need them

**Severity:** medium in aggregate; each item is a one-paragraph plan edit.

(a) **Refusal vocabulary.** The plan pins failure *order* precisely but never
names exception classes for: signature/morphism mismatch at binding, invalid
route producer, physical-table verifier failure, the raised semantic verdict,
repeated decoded keys, and `from_indexes` validation. `exceptions.py` holds
`LexicError` / `UnsupportedConstructError` / `IrKeyError` /
`FieldValidationError`; `.wiki` has an error-vocabulary page for exactly this
choice, and Luna must pin type+message against something declared. Decide the
assignment before §2. Note `src/lexic/compile/verdict.py:27` already owns the
name `Verdict` for an unrelated concept — the target-verdict family needs a
non-colliding spelling.

(b) **`reduce` and the resolver.** `CompiledGrammar.parse` takes `resolve=`
(`artifact.py:217`) — the opt-out `CLAUDE.md` names as *the* ambiguity
opt-out. The planned `reduce` overloads take none, so target products have no
opt-out at all. Decide: add `resolve=` to both overloads, or record that
target products deliberately have none pre-0.1.

(c) **Empty-edge contracts.** Unstated: `select({})`; a spec leaf that is
neither `KEEP` nor a mapping; a non-mapping root document under a selection;
a zero-entry `model.vocab`/`model.merges` (present-but-empty is not "missing
fields"). Each needs a one-line declared ruling before tests freeze an
accident.

(d) **`ProductProgram[GrammarModel, RootModel]` is untypeable.** The start
class is synthesized at runtime (`compile/pipeline/synthesis.py`) and has no
static name; `parsing/fold.py:354` already spells the seam correctly as
`ModelFold[M]` bound at `GrammarModel`. Restate the §4 bullet as
`ProductProgram[GrammarModel, GrammarModel]` and keep the real constraint:
the model product's `Result` never widens past `GrammarModel`.

(e) **Unaccounted consumers and open layouts.** `parsing/trace.py` — a public
`PdaKernel` subclass shadowing exactly the completion surfaces §4 rewrites —
appears nowhere in the ownership map; assign it (follow the rewrite, public
surface unchanged). `compile/product/`'s file layout is open while its
sibling `parsing/product/` was deliberately pinned; pin it or record why not.
`TODO.md` §9's "keep `stitch/model.py` … **or** migrate it" is an optional
consolidation that will not happen at phase 9 of 14 — make it a decision
either way. §7's one bullet for the three tokenizer index roles hides a
payload-codec / zero-import reader / notation / generated-twin blast radius;
give the §7 exit a payload/notation/twin fixpoint gate
(`tools/check_generated.py` plus round-trip) before its checkpoint.

(f) **§13 coverage gaps.** Luna's list never names: the `select` contract
itself (order, absence, retained identity, decoded/escape-equivalent
duplicates, shape verdicts, syntax-first precedence, plus whatever (c)
rules); the extent target (the only codomain with no committed-test row); or
binding-registry lifecycle regression guards (concurrent cold bind compiles
once, eviction recomputes equivalently, bound program retains no artefact,
pool-retained program valid after release, transitive derived-cache release —
the design's hardest concurrency claims, currently proven only by Terra-side
one-time witnesses). Three bullets.

## Verified

- `parsing.caches` exposes exactly the `memo`/`track`/`adopt`/`release`
  protocol the plan cites (`caches.py:62-137`).
- An Earley item is one packed int `code << bits | origin`
  (`earley/kernel/tables/records.py`); the sparse routed-successor table maps
  to new contextual *codes*, so route identity rides the existing item
  representation without widening — the §3 routing claim holds structurally.
- `IrTokenizer` today holds `encode`/`decode`/`ranks` map fields with
  `from_vocab`/`from_merges`/`_build`; the §7 three-index rework maps 1:1
  onto the real surface (`ir/text/tokenizer.py:271-317`).
- The environment is Python 3.14.3 free-threading with the GIL actually
  disabled; the regex-cache ownership concern is real and prototyped.
- Port targets exist for the trace and templating migrations
  (`tests/unit/lexic/parsing/test_trace.py`,
  `tests/unit/lexic/compile/output/test_templating.py`).
- `tools/benchmark/` does not reference the reduction path; only
  `tools/profile_tokenizer_path.py` does, through the public API §12 already
  names.

## Decisions required from the user

1. Finding 1: schedule the capturing regular-region lowering, or record the
   two-regime decision (<1 s without it, 105× contingent on it) — plus the
   completion-op throughput probe either way.
2. Finding 2 + finding 5: one ruling covering both codomain gates — worker
   shape (`cores=AUTO` engaged vs sequential vs both), the decline case, the
   sequential row's status, and CPU-per-byte reporting.
3. Finding 6: rule the value-meaning ambiguity relation definitive, with
   enumerated divergences at §5.
4. Finding 8: subtree-local alternate folds, or priced n+1 full folds.
5. Finding 10: reducer-free extraction — keep one general morphism, or record
   the deliberate capability drop.
6. Finding 15(a): the exception-class assignment (and the `Verdict` spelling).
7. Finding 15(b): `resolve=` on `reduce`, or a recorded no-opt-out ruling.
8. Findings 3, 4, 7, 9, 11, 12, 13, 14, 15(c–f): each is a bounded plan edit
   with a recommended shape in its finding; accept, amend, or reject per item.

## Re-entry condition

Update `goal.md`/`DESIGN.md`/`TODO.md`/`LEDGER.md` with the rulings above.
The source-start gate stays closed until finding 1 has a scheduled mechanism
or a recorded regime decision, findings 3 and 4 have converted the late gates
into phase-local ones, and findings 6–8 are ruled — everything else can be
folded into the same editing pass. No finding here reopens the product
architecture, the deletion discipline, or any decision the ledger records as
user-ruled.
