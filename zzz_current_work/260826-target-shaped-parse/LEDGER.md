# Ledger — target-shaped parsing

## NEXT SESSION — start here (written 2026-09-01, usage exhausted mid-§4)

State: §2 and §3 are ACCEPTED (see their exit entries). §4 is in progress at
step 2 of Terra's approved seven-step sequence. Terra (Opus implementer) was
stopped by the user mid-increment; its last completed work is §4 step 1
(`model_plan` + `RecordConstructor`, differential green over 137 rules) and
the step-2 design verification (`lo` trace). Its NEXT action, ruled and
ready: write the product-side bake deriving flat clones from the product, and
the both-ways bake-identity witness over the corpus — byte identity for every
clone field except `lo`, which normalizes to `0 if optional else 1` under
the three-predicate behavioural proof plus an exhaustiveness pin (rulings in
the two entries below).

Working tree: NOTHING COMMITTED; the index holds the full §2–§4 diff (9
modified src files, 10 new across `parsing/product/` + `compile/product/`,
CLAUDE.md map lines). One attributed suite failure only (`test_test_parity`,
seven missing unit-test mirrors — Luna's at §13). One disclosed xdist flake
(`test_concurrent_distinct_documents_match_sequential[2]`) with a
chase-on-recurrence tripwire. All ten §2/§3 witnesses + `s4_model_plan` exit
0. First checkpoint commit is the §4 exit, after the coordinator's external
alternating profile.

On resume: re-read this ledger top-down through the §3 EXIT entry, re-arm
`tools/usage_watch.sh 90 60 540`, resume or respawn the Opus implementer
(transcript name `terra`; if respawning fresh, point it at TODO §4 + the
LEDGER rulings from "§4 opened" forward), and continue step 2.

## §4 step 2 finding: the flat runtime is already product-shaped (2026-09-01)

Reading before editing again paid off: `_bake_build`/`_build_plan` already
emit a capture layout (`clone.fields` = item + int mode + name + lo), a
construction plan in class-field order with inline defaults (`clone.plan`),
and the fast/defaults/needs_ends data — the runtime already speaks the
product vocabulary; only the authored layer above speaks `RuleFold`. Step 2
therefore derives the SAME flat clone from the product instead of the fold,
and its opcode account is structural: bake every clone both ways and assert
`fields`/`plan`/`fast`/`defaults`/`needs_ends` identical — zero added
paid-loop opcodes proved by identity of the flat outputs, stronger than any
timing argument (timing rows still come at the §4 gate).

Ordering ruling (coordinator-approved as Terra leaned): `_build_plan` needs
CLASS-field order, which differs from the record's capture order. The class
order is read OFF `cls` at bake time — a cold lowering step, one source of
truth per sequence (class order lives on the class, capture order on the
record) — rather than duplicated into `RecordConstructor` where the two
sequences could drift. The record supplies which captures fill which names
and which may be absent; the both-ways bake identity is the required witness.

`lo` normalization ruling (2026-09-01): Terra traced every runtime read of a
bound field's `lo` — exactly three sites in `build.py`, all inside `gtext`
branches, all zero-tests; no other mode consults it. The bake therefore
writes `lo = 0 if optional else 1`, and the ABI says what it means (this
field may be absent) instead of restating a quantifier the runtime cannot
use. Carrying raw `lo` forever in the record for byte identity was declined.
The step-2 account claims byte identity for every clone field EXCEPT
normalized `lo`, plus behavioural identity for `lo` proved by the three
predicates over both value classes — and the witness must also pin the
exhaustiveness of the three-site trace, so a future fourth `lo` reader
breaks it loudly.

## §4 step 1: model product authored, differential green (2026-09-01)

`model_plan` (in `compile/pipeline/synthesis.py`, beside the `fold_config` it
will replace) authors the generated-model product from the binding view.
`proto/s4_model_plan.py` (exit 0, coordinator-rerun) differentials it against
`fold_config` per rule over all eight ground-truth grammars — 137 rules, zero
disagreements on item read, capture mode, field name/order, validation-skip
licence, and class object. The gtext absence rule is proved on the real
corpus: `json_ws`/`json_arr` carry six optional gtext binds, all recorded
optional (Terra self-caught a contrived witness case — a bare quantified
literal is not a gtext bind — and repointed at the real `json_ws number`
shape). The ruled constructor record landed as `RecordConstructor` with the
fast licence as a FLAG, removing today's bound-method-in-table; lowering
validates `entry.cls` one level in. Nothing consumes `model_plan` yet.

Condition follow-ups (accepted): `defaults` was MEASURED, not guessed —
90/90 generated-class defaults across eleven grammars are Python `None` (the
model layer's deliberate absent-optional concession per ir-shapes), so the
coordinator's `Mapping[str, IrSelf]` hint was wrong; the field keeps the open
type with the measurement and reason in its docstring. The witness gained the
laundering-channel refusal — a well-formed `RecordConstructor` naming a
lambda as `cls` refuses — beside the bare-callable and caller-filled rows.
The gtext absence behavioural row is pinned as a STEP-3 exit condition (the
first moment a completion site can build a model), not a §4-end item.

Accepted deviation: `records.py` hit the 700 ceiling after trimming its own
prose; the reducer-expression layer moved to a sixth module
`parsing/product/expressions.py` (one-way dependency, pure relocation,
records.py now 581) — recorded on the §3 package bullet and in CLAUDE.md's
map. Disclosed flake: one xdist run failed
`test_shared_artefact.py::test_concurrent_distinct_documents_match_sequential[2]`;
it passes standalone 4/4, its file 12/12 x3, and the next full run; no
concurrency path was touched. Recorded for provenance — if it recurs it gets
chased, not re-run to green. Next: step 2, `RuleProduct` through the PDA
compiler chain, where the per-step opcode account starts.

## Ruling: ModelConstructor record in the constructor table (2026-09-01)

Terra stopped on the first §4 step with a real spec gap: `CaptureSpec(mode,
slot)` cannot carry `FieldFold`'s `name` (keyword construction) or `lo` (the
gtext absence rule — `lo == 0` with empty matched text means ABSENT, kwarg
omitted, default applied; dropping it silently turns every optional literal
group into `""`). And `FastCtor.make` is a bound positional constructor, not
the "class object" the §3 constructor-table wording names.

**Coordinator ruling:** the constructor operand table holds one immutable
`ModelConstructor` NamedTuple per rule — `cls` (the one binding-owned class
object), `names` (construction order), `optional` (capture indices that may
be absent), `defaults`, and `fast` (the validation-skip licence as a flag).
This preserves the constraint's INTENT — no arbitrary callable at a frequent
completion; every field is inert binding-derived data — and tightens today's
shape, which stores a bound method in a table. Rejected: widening
`CaptureSpec` with strings (flat per-capture arrays stay int-coded) and a
parallel per-rule field table (`RuleFold.fields` under a new name).
Conditions: `defaults` gets the narrowest honest value type (spell `IrSelf`
if that is the truth; `object` only if genuinely heterogeneous, with the
reason on the field); lowering remains the table's sole writer with its
class-check now validating `entry.cls`; the s3 witnesses' constructor rows
adapt; and the gtext absence-vs-empty-string case is a MANDATORY §4
differential row, since it is the silent-model-change trap this ruling
exists to prevent. `fold.py` stays alive beside the new records until the
completion sites move.

## §4 opened: caller inventory and scope rulings (2026-09-01)

Terra's pre-edit inventory: the six §4-deleted symbols reach 28 src files and
16 test files across five subsystems — fold, PDA compiler+runtime, Earley,
`parallel/` (orchestrate, replicas, all four stitch modules), and the compile
side. Coordinator scope rulings, recorded on the §4 deletion bullet:
`parallel/` is IN §4 scope for the mechanical re-plumbing onto the model
product's ABI (its model-shaped stitching semantics stay untouched; §9's
FragmentProduct generalization stays §9 — otherwise §4's exit claim that
`CompiledGrammar.parse` runs the common ABI would exclude the split path);
`templating.py` moves only mechanically to stay compiling, is never
re-expressed as a product, and §10 deletes it unchanged. Terra's bottom-up
sequence (author model product beside the fold → PDA compiler chain →
build/execution completion with the §3 descent/transparent findings → Earley/
island → parallel + compile side + trace → delete the six symbols → opcode
comparison) is approved, with the opcode account written per-step so any
added paid-loop opcode is attributable to the step that introduced it.
Flagged early by Terra, resolution deferred to arrival: `FastCtor`'s
validation-skip licence is a bound positional constructor, not a class — it
likely becomes a property of the rule's capture/completion plan rather than a
constructor-table entry.

## §3 EXIT ACCEPTED (2026-09-01)

Coordinator exit review: all ten witnesses rerun green, pyright 0 errors on
src+tests, full suite 5339 passed / 8 skipped / 1 failed — solely the
attributed `test_test_parity` mirror gate (seven new modules; Luna at §13).

Landed under §3: `parsing/product/` (records incl. the ExprProgram layer,
state, verify, regular, façade); `compile/product/` (lowering with three
ownership guarantees, bound-product lifetime on `parsing.caches`); the
physical-table verifier with the exact-class int audit; the authoritative
regular proof; the shared-forest value-once fix; the speculation measurement
(flat in retained, linear in mutations); the route lane (four stale cases,
both fork sites, uniform Side triple); the synthetic route program through
the real lowering chain; the dirty cone + meaning memo + replay (replay 3–4
nodes vs refold 5–6, same-answer asserted); and the Earley end-to-end target:
real recognition over `{a:1,bb:22}`, verified flat tables executed at the real
tree's completion sites, MANY through a transparent node, duplicates refused
with verdict, speculative insert rolled back exactly, a genuinely shared pad
completed once (Terra self-caught its first vacuous shared-node assertion and
made the count load-bearing).

Two §4-relevant executor findings recorded on §4's completion bullet:
collection Begin* ops run at DESCENT, not post-order; MANY captures look
THROUGH transparent repetition nodes. Moved, plainly: routing witnesses
execute at §6 (PdaTables carries no route data until a schema exists); PDA and
island/delegate end-to-end open §4 as its first differential; §3's route
coverage is synthetic-authored. §3's remaining unticked bullets are exactly
the §4/§6-deferred ones, annotated in place.

Next: §4 — migrate generated-model parsing onto the common ABI — on the same
warm Terra agent. §4 exits through the coordinator's external alternating
profile and the first checkpoint commit under the recorded grant.

## Ruling: §3's engine execution splits — Earley now, PDA/island at §4 (2026-08-31)

The tiny-target end-to-end hit the same structural boundary as routing:
`_complete` builds models through `clone.fold` (`RuleFold`), `FlatClone`
carries no `RuleProduct`/`CaptureSpec`/range index, and making clones carry
product data IS §4's opening migration. A parallel §3 completion path would
cost the model product a new `F_MODE` branch per frame completion — the exact
branch §3 forbids — and be scaffolding deleted at §4.

**Coordinator ruling (a third option beyond Terra's two):** the PDA and
island/delegate end-to-end execution moves to §4 as its FIRST differential —
§4 needs a non-model product to prove the ABI is not model-shaped, so the
tiny target opens that phase. But the EARLEY half executes NOW: Earley's
completion seam is a post-order fold over a real `ParseTree`, so a PROTO-side
product executor runs over real Earley recognition — real text, real
chart/FastTree shapes (nullables, transparent synthetics, shared subtrees),
product completions in post-order, `ParseState` transactions and mapping
duplicate policies exercised, built value asserted — with zero src branches.
This answers the asymmetry Terra rightly flagged (every mechanism proved,
none engine-executed): §3 exits with real-recognition-driven product
execution demonstrated on the Earley path, and derisks the capture layouts
against real tree shapes the hand-driven interpreter never produced. TODO's
§3 exit text is amended. Next: `proto/s3_earley_target.py`, then the §3 exit
report.

## §3 increment: meaning memo and cone replay landed (2026-08-31)

`MeaningMemo` + `remembered`/`replayed` land in
`earley/kernel/forest/support/ambiguity.py`: the default derivation's
per-handle subtrees and per-node values are retained (values only — no
builder handle, log, or engine state), an alternate seeds a fresh
`FastTree.memo` with every unchanged subtree so retained values stay
addressable, and only the dirty cone refolds. `ModelFold.apply` gained an
optional seeded-and-filled `results` map — omitted (every ordinary parse) it
is private and discarded, so the unambiguous path allocates nothing. Measured
on five packing shapes: replay folds 3–4 nodes where refold folds 5–6, with
the replayed value ASSERTED equal to a full refold on every shape including
the genuinely meaning-changing flip. Per-alternate isolation is a fresh
seeded dict per `replayed` call.

Accepted wording resolution: §3's "fresh isolated ParseState" names the
product executor's state, which does not exist yet; the isolation property is
kept with the executor that does (`ModelFold`), and `remembered`/`replayed`
take the fold as a parameter so §4/§5 re-point them at the product executor
and the phrasing becomes literal. Coordinator reran the witness and read both
diffs.

Remaining for the §3 exit: the tiny sequence/map target end-to-end through
real PDA / Earley fallback / island-delegate paths, then the §3 exit report.

## §3 increment: dirty ancestor cone landed and measured (2026-08-31)

`dirty_cone(kernel, root, flipped)` lands in
`earley/kernel/forest/support/ambiguity.py`: one forward link-table walk
builds reverse reachability (the same relation `ambiguity_points` uses), read
backwards from the flipped point. On five real packing shapes the cone is 1–2
handles against 15–23 reachable — a replay reuses 13–22 meanings instead of
refolding, versus today's whole-tree `build` per flip. Witness
`proto/s3_dirty_cone.py` (exit 0, coordinator-rerun) includes a
changed-meaning flip (`e ::= e e | "a" | "b"` over "aba") and honestly reports
the shape-differs/meaning-equal case rather than asserting it changes —
Terra's own correction, which matches goal.md §5's declared successor
relation. Cone soundness is stated structurally (a non-ancestor cannot
contain the flip), not measured; the witness says so explicitly.

**Ruling:** §3's "capable of" wording is confirmed — the cone mechanism
satisfies §3; the live memo wired into completion rides the product executor
(§4/§5) and the `another_meaning` replacement is §8's, per those sections'
own bullets. Making today's whole-tree `build` incremental first was
rejected as building on the vocabulary §4 deletes.

Also: Terra staged the working tree (`git add`) for diff visibility; nothing
committed. Coordinator reminder issued — visibility via
`--untracked-files=all` or `git add -N`; staging belongs to the coordinator
at commit time.

Remaining for the §3 exit: the tiny sequence/map target end-to-end through
real PDA / Earley fallback / island-delegate paths.

## Ruling: recognition-time routing executes at §6 (2026-08-31)

Terra hit the structural boundary of §3's route work: the lane read belongs at
clone entry (`_enter` substituting the destination clone), but `PdaTables`
carries no route/continuation/code→clone data and CANNOT until a
`TargetSchema` declares a discriminator at §6/§7 — the PDA compiler's analysis
rightly has no route concept. Wiring `_enter` now would add an attribute load
and `None` test to every clone entry (hotter than the fork sites, on the model
product's §4-priced paid path) guarding a branch that cannot fire.

**Coordinator ruling — option 2 of Terra's three:** §3 proves the routing
MECHANISM (the lane with four stale cases, both fork sites carrying it, the
authored→lowered→verified route chain with cardinality specialization);
recognition-time route selection executes at §6 where the first compiled
schema routes exist. This is distinct from the earlier rejected deferral: the
mechanism §4 rebuilds on is proved, and the model product routes nothing, so
§4 is untouched by the moved hop. Extending `PdaTables` with a dead field
filled by a hand-built tables witness was rejected as scaffolding masquerading
as coverage. §6 obligations recorded on its RouteOp bullet: route data enters
`PdaTables`; prefer a clone-baked consult (routed consumer clones marked in
their own data) over a global per-entry test so unrouted programs gain no new
branch; §3's moved nested-mapping/non-sibling/stale-route witnesses run there
through real parses; §12's parse rows gate the landed shape. TODO's §3 exit
text is amended accordingly. Unblocked and proceeding now: the Earley meaning
memo + dirty-cone replay and the tiny target end-to-end (the Earley
routed-successor table shares the §6 dependency and moves with it).

## §3 increment: side tuple widened to the uniform triple (2026-08-31)

`Side = tuple[list[Any], int, RouteLane | None]` lands in `admission.py`
beside `RouteLane`/`frames_copy`; `_side`, `_advance`, and `_converged` carry
the lane through both branches with save/install/restore beside `stack`/`pos`.
The triple is uniform (lane `None` for unrouted programs) so the
boundary-decision path stays one shape. Both PDA fork sites now carry the
lane. Coordinator spot-checked the diff and ran the PDA unit suite (823
passed); Terra ran the full suite BEFORE reporting (5339/8/1-attributed).

Two self-caught process events. The 700-line gate bit `decisions.py` at 708;
relocating `Side` to `admission.py` (placement, not shaving) was the fix.
Then, two lines over, Terra changed `control_signature`'s public signature
dressed as an improvement — six committed `test_lockstep.py` tests broke, and
Terra reverted and trimmed its OWN new docstring prose instead. **Standing
lesson ledgered beside the scripted-edit one:** when a size gate bites, the
honest moves are relocation to the right owner or trimming prose you just
wrote — never changing a signature existing callers depend on; an
"improvement" that only occurs to you while you are two lines over is
rationalisation.

Route half remaining: clone selection consulting the lane (recognition-time
publish/read/clear through real parses), then the Earley routed-successor
table, the meaning memo + dirty-cone replay, and the tiny target end to end.

## §3 increment: synthetic route program through the real chain (2026-08-31)

`proto/s3_route_program.py` (exit 0, coordinator-rerun) authors the
non-sibling `member ::= string tail; tail ::= separator value` shape at the
records layer and drives it through the real `lower_product` / `lower_routes`
/ `verify_program` chain — `path=(1, 1)`, three routed value clones as
separate contextual rules, cardinality specialization asserted per shape.

Writing it caught a latent defect no gate had flagged:
`OperandTables.routes` was typed as the AUTHORED `RouteTable` tuple, so the
runtime would have indexed unlowered pairs — the exact scan the route ruling
forbids — and `destination_of` (a pylint-driven addition) read a
`destinations` table `lower_routes` never populated, raising `IndexError` on
first real data. Both fixed: `OperandTables.routes` is now
`tuple[LoweredRoute, ...]`; `lower_routes(tables, continuations)` pairs each
table with its consuming continuation and attaches dense destinations
(mismatched lengths refuse); and `lower_product` is the route table's sole
writer via the new `LoweringOwned(constructors, routes)` record — one rule
for both engine-hot authored tables instead of two coincidences. Lesson
ledgered: an unexercised addition made to satisfy a linter is a defect
waiting; every such change gets a witness row when made.

Remaining for the §3 exit: `_fork_side`'s uniform-triple widening, clone
selection consulting the lane (recognition-time publish/read/clear through
real PDA / Earley fallback / island-delegate parses), and the Earley sparse
routed-successor table. Then the meaning memo + dirty-cone replay and the
tiny target end-to-end.

## §3 increment: probe fork wired; stale case (d) witnessed (2026-08-31)

`_probe` now forks the lane beside the stack under one `is not None` guard and
restores it in the same `finally` as `stack`/`pos`; `Attempting` declares the
`_routes` slot. The witness gained stale case (d) — a discarded probe fork
that published its own route AND consumed the outer route on its copy leaves
the original lane byte-identical — plus a wiring row that reads the source so
the fork/restore/guard halves cannot drift apart silently. Coordinator reran
the witness (exit 0) and read the decisions.py diff.

Incident, self-caught and disclosed: Terra's scripted edit anchored on a
`finally` block whose text repeats in two functions landed the restore in
`_advance` instead of `_probe`, breaking 65 tests (NameError on the parity and
split-model differentials). Found on the full suite before reporting, fixed by
positional anchoring; suite back to 5339/8/1-attributed. Standing lesson
recorded: no scripted edits anchored on repeating text in kernel files —
unique context or by hand, and full suite BEFORE reporting.

Next: the synthetic route-bearing program through the real
`lower_routes`+`verify_program` chain, `_fork_side`'s uniform-triple widening
in the same pass, and the routing witnesses through real PDA/Earley/island
paths including non-sibling `member ::= string tail`.

## §3 increment: route lane landed; fork-wiring ruling (2026-08-31)

`RouteLane` lands in `parsing/pda/runtime/admission.py` beside `frames_copy`,
publishing `(frame, consumer path, route)` keyed by depth with TWO independent
guards — frame identity (a later frame at a reused depth reads `NO_ROUTE`) and
clear-on-advance (a later sibling under the same live parent reads
`NO_ROUTE`) — plus explicit save/restore across live-stack attempts and a
`forked` remap that rebinds entries to the copied frames. `PdaKernel` gains
one `_routes` slot, `None` for every unrouted program (the generated-model
product permanently). Witness `proto/s3_route_lane.py` (exit 0,
coordinator-rerun) covers publish, all three stale cases, the real
`frames_copy` fork remap with aliasing checked, and the outer-route-survives
property on attempt abandonment. Parsing unit tests (1688) green — the slot
is behavior-neutral.

**Fork-wiring ruling (option 2):** `_probe`'s fork installs directly and its
lane copy is wired now; `_fork_side`'s side tuple widens to carry the lane
ONLY in the same pass as the synthetic route-bearing program, so the invasive
hot-signature change arrives together with the first thing that exercises it,
inside §3 and therefore still priced by the §4 gate. When it widens, the side
stays a UNIFORM triple (lane slot `None` for unrouted programs) so the
boundary-decision path stays monomorphic. Widening now for dead benefit and
deferring both halves past the lane work were rejected.

## §3 increment: speculation measured; route-scope ruling (2026-08-31)

`proto/s3_speculation_cost.py` (exit 0) proves the ParseState transaction
claims by measurement: mark+commit/rollback/commit are flat across a 100x
retained-size sweep (1.45–2.42x at microsecond absolutes) while rollback is
linear in mutations performed (16→4096 mutations: 0.000008→0.000917 s), with
correctness asserted before timing. The PDA/island WIRING of these
transactions remains engine-integration work, so the TODO bullet stays open.

Terra also surfaced two facts that shape the route lane: `frames_copy` is
positional so a depth-indexed lane remaps by construction at forks, and
`_attempt_run` speculates ON THE LIVE STACK under a depth watermark — so an
abandoned attempt needs an explicit lane save/restore, not fork-discard.
Accepted; the stale-route witnesses must cover it.

**Route-scope ruling:** nothing in `src/` can declare a route until §6/§7
supply schemas, so §3's routing exit runs on a SYNTHETIC route-bearing
program — hand-AUTHORED records driven through the real `lower_routes` +
`verify_program` path (never raw hand-built flat tables), exercising
publish/read/clear, later-sibling, abandoned-attempt, and fork semantics
through the real PDA, Earley fallback, and island/delegate paths, including
the non-sibling `member ::= string tail` shape. Speculative §6 compiler
emission was rejected (it would guess the schema declaration shape); deferring
the route half to §6 was rejected (engine mechanism must be proved before §4
rebuilds the model path on the same kernel). The §3 exit report must state
plainly that route coverage is synthetic-authored; schema-compiled routes are
§6's differential.

## Ruling: PDA route lane is cursor-side, not a frame slot (2026-08-31)

Terra found the plan's two §3 constraints collide against the real kernel:
"store `(consumer path, route)` in PDA frames" versus "the generated-model
product gains no extra frame slot on its paid path." The PDA frame is one
program-independent 9-element literal built at two sites in
`kernel/kernel.py`; widening it costs every product two elements per frame
push. The PDA also speculates by `frames_copy` stack forking, not by
mark-and-log, so "under rollback" means "rides the forked stack."

**Coordinator ruling:** the lane is cursor-side — one `PdaKernel` slot
(`_routes`), `None` for every program without route continuations (the
generated-model product permanently), indexed by frame depth so it is
semantically the parent frame's lane, copied beside the stack at the two fork
sites under one `is not None` guard. Model-path cost: one attribute plus one
fork-time test — no per-character, per-item, per-completion, or per-frame
work. All other route constraints stand unchanged (clear only after the first
routed occurrence advances; deeper children baked into the clone chain;
compiled scalar discriminator decode; no general evaluator; cardinality-
specialized lookup). Added obligation: lane validity is tied to the exact
parent frame instance — the §3 stale-route witnesses must cover a same-depth
LATER sibling and an abandoned attempt, not only the fork-discard case. TODO's
route bullet carries the ruling.

## §3 increment: lifecycle seam landed (2026-08-31)

`src/lexic/compile/product/binding.py` lands `BoundProduct[Result]` (ABC:
`run` + derived `stateful`), `ProgramProduct[Carry, Result]` (verified program
+ executor, no source retention), and the homogeneous
`BindingRegistry[Declaration, Result]` on the EXISTING
`parsing.caches.memo/track/adopt/release` protocol — entries dict registered
with `memo({}, 1)`, source bound via `track`, derived products `adopt`ed under
the same identity. Warm reads are lock-free with an identity double-check
against the live objects (recycled addresses cannot serve stale entries);
cold misses double-check under one lock. `proto/s3_lifecycle.py` (exit 0,
coordinator-rerun) covers warm identity, explicit release with
equivalent-rebind, collection, weak-source retention, an eight-thread
barrier race compiling once, and a pool-retained product running after both
release and source collection. TODO's lifecycle bullet is ticked; transitive
release of REAL engine-derived entries re-exercises at engine integration.
Terra's ExprProgram pushback was correct — it had already shipped in the
prior increment; the coordinator's re-flag was stale. Terra proceeds to the
PDA route-lane execution.

## §3 increment: ExprProgram layer, specialized routes, derived stateful (2026-08-31)

Terra landed the two coordinator scope additions and the lowering-side
constructor enforcement. `ExprCode`/typed expression records cover the seven
action categories and `RuleProduct.completion` is now `RuleBody =
RuleCompletion | ExprProgram` — the field's type selects the physical table,
so one-body-per-rule is structural; an empty expression program refuses at
lowering. `lower_routes` specializes by cardinality into slotted classes
(`UniformRoute`/`SingletonRoute`/`TableRoute`) whose `destination_of` composes
classification with dense destination indexing; nothing scans the authored
tuple at runtime. `lower_product` is the sole writer of the constructor
operand table: it takes `constructors: Sequence[type]`, refuses a non-class
entry, and refuses a caller-filled record. `stateful` is now DERIVED from the
lowered instructions (the six collection opcodes) rather than declared.

Coordinator reran both witnesses (exit 0) and confirmed the refusal rows.
**Standing note for §6:** the stateful derivation currently keys ONLY on
collection opcodes; DESIGN requires ParseState for deferred VERDICTS too, so
when the verdict-recording operation lands (poisoned schema states /
deferred-failure ValidateOp), it must join `_STATEFUL_OPCODES` or the
derivation must consult the declared failure order — do not bolt the parameter
back on. Coordinator approved Terra's proposed reorder: the `parsing.caches`
lifecycle seam next (smaller, independent, settles ownership), then the PDA
route lane.

## §3 increment: defect fixed, lowering landed (2026-08-31)

Terra fixed the returned `LAST_DUPLICATE` rollback defect with a third logged
mutation kind `MAPPING_REPLACE` carrying the overwritten entry and position in
a dedicated `_overwritten` lane, popped LIFO by undo; the pre-mark-overwrite
rollback case is now a witness row that fails against the old code. Both
minors are addressed: the verifier bounds capture modes to the lowered
vocabulary and refuses negative slots, and `OperandTables.constructors`
documents its binding-owned-only contract with lowering named as the §6
enforcer.

`src/lexic/compile/product/` now exists with `lower.py` (the pinned §5 layout
grows around it later). `lower_product` converts authored enums to exact
ints, gives each rule one instruction and a length-one fused range, and pools
operand rows per opcode. **Encoding ruling (coordinator-accepted):** a
multi-field operation lowers to one instruction whose operand indexes a row in
that opcode's OWN table — `*_operand_limits` became `*_operand_rows`, bounds
are `len(rows[opcode])`, every table stays typed with no catch-all array. The
per-completion double index (`rows[opcode][operand]`) is cold-priced as
acceptable; if the §4/§12 gates attribute hot-path cost to it the encoding is
revisited then. Witness `proto/s3_lowering.py` lowers a tiny sequence/map
target with container begin/finish and entry insert on different rules,
verifies, exact-int audits, and executes it through a proto interpreter —
explicitly NOT the §3 exit, which needs the real engines.

Coordinator reran all three §3 witnesses (exit 0) and confirmed the new
refusal/rollback rows. Still owed in §3: the authored typed
reducer-expression program record layer (its definition is §3's; lowering the
shipped reducers through it is §5's), route-continuation execution in both
engines, the routing witnesses, the Earley meaning memo + dirty-cone replay,
the `parsing.caches` lifecycle seam, speculation measurement, and the tiny
target through real PDA/Earley/island. Terra proceeds PDA-frame-lane first.

## §3 foundation reviewed — engine integration remains (2026-08-31)

Terra landed the §3 foundation and stopped deliberately before engine surgery:
`src/lexic/parsing/product/` in the pinned five-module layout plus README, and
the shared-forest fold fix in `parsing/fold.py` (a `folded` set distinct from
the value table; all four §3 witness shapes — duplicate-slot, pending-frame,
sibling-memo, transparent `__rep_1` — now fold each shared node's value exactly
once through the real Earley fallback, pinned by `proto/s3_shared_forest.py`).
`proto/s3_product_abi.py` pins the verifier's eight refusal messages, the
exact-int audit refusing a surviving `IntEnum`, LIFO transactions with
mutation-proportional rollback, and the regular proof's four declines plus the
decidable once-required-nullable proof. Coordinator reran both witnesses
(exit 0), pyright (0 errors), and the targeted invariant/parsing/parity suites
(2248 passed) — the parity/roundtrip greens are the evidence the fold change is
behavior-preserving.

Coordinator rulings:

- **Accepted deviation:** `regular.py` imports the first-set algebra
  (`KWindowFirst`/`collide`/`separable`/`extend_follow`) from
  `parsing/pda/analysis/gates/windows.py` beyond the pinned `pda/core` leaves —
  importing the repo's one FIRST implementation is what the
  no-reimplementation clause intends. TODO §3 and DESIGN record it.
- **Attributed failure:** `test_test_parity.py` fails naming the four new
  product modules' missing unit-test mirrors. Terra may not write committed
  tests and a false ALLOWED entry was rightly refused; the failure stays
  attributed until Luna mirrors the modules at §13. Everything else is green.
- **Defect returned to Terra (state.py):** a `LAST_DUPLICATE` `replace` on a
  key inserted BEFORE the live mark logs nothing, so rollback cannot restore
  the pre-mark value — a rolled-back speculation leaves the mapping mutated.
  Fix requires a logged replacement mutation carrying the old value; the
  docstring's claim that the enclosing insert's log entry covers it is wrong
  for the pre-mark case.
- **Minor returned:** the verifier bounds completion ranges and operands but
  not capture modes (an out-of-range mode passes); and
  `OperandTables.constructors` must pin, in words now and in lowering checks
  later, that it holds only binding-owned constructors — never arbitrary
  target callables — since `RecordOp` runs at frequent completions.

Remaining §3 work, in Terra's stated dependency order: the lowering pass, route
continuation execution (PDA lane + sparse Earley successor table +
recognition-time discriminator decode with cardinality-specialized lookup),
the routing witnesses including non-sibling `member ::= string tail`, the
Earley meaning memo + dirty-cone replay, the `parsing.caches` lifecycle seam,
measured valid/failed speculation, and the tiny sequence/map target through
PDA/Earley/island. Terra also re-ran repo-wide auto_fix against instruction,
then restored the 21 files itself; future formatting is per-file only.

## §2 implemented and accepted — production source has begun (2026-08-31)

Terra (Opus) implemented §2 in four files: the semantic-signature/target-schema
vocabulary in `src/lexic/ir/reduction.py` (SemanticSort str-leaf family and ten
sorts, `SemanticSignature`, the SchemaRoute family with Known/Extension/Entry,
SchemaCheck/SchemaChecks, DuplicatePolicy, the SchemaState family with
Accepting/Poisoned/Recovery, MeaningLaw, FailureOrder, `TargetSchema` with
`verify`), `SemanticVerdict` + `TargetRefusalError(LexicError)` in
`src/lexic/exceptions.py` (primitives-only verdict record with the `(pos,
order)` stable total key), `JSON_SIGNATURE`/`JSON_EVENTS` beside `JSON_REDUCER`
in `src/lexic/grammars/json.py`, and the three-way lazy-façade export in
`src/lexic/ir/__init__.py`. Every family base raises
`UnsupportedConstructError` with words; nothing in the vocabulary parses,
lowers, mutates, or names a format.

**Ruling (coordinator-confirmed, §6 builds on it):** the signature-to-reducer
data channel is two fields on `Reducer` itself — `signature: IrSelf = IrNone`
and `events: IrMap[IrRuleRef, IrStr]`. `SemanticSignature` is literally
rule-name-free so one object serves every formulation; the symbol→event anchor
lives beside the actions it describes, keyed the same way actions already are.
Authored, never inferred — body-shape inference is provably impossible
(`member` and `array` both reduce through `IrBuild(IrTuple)`).

§2 exit criterion holds: `proto/s2_signature_exit.py` (uncommitted witness)
compiles native + GBNF + ABNF + EBNF JSON, reduces one document to one value
through all four, confirms all four expose `JSON_SIGNATURE` by identity, and
diagnoses wrong-boundary, missing-event, and no-boundary mismatches before any
parse. Coordinator independently reran it (exit 0), pyright src+tests (0
errors), the full suite (`uv run pytest tests/ -q -n auto`: 5340 passed, 8
skipped), and `tools/run_checks.sh` (exit 0).

Incidents, both resolved: Terra ran `git checkout -- src/lexic/ir/reduction.py`
mid-work, reverting its own §2 file, restored it verbatim and re-verified; all
reported numbers are post-restore. The coordinator restored Terra's 21
out-of-scope `auto_fix.sh` reformats (tools/ + this effort's proto/) so the §2
diff is exactly four src files. The coordinator also fixed the pre-existing
trailing-whitespace failures that kept `tools/checks/10_sanity.sh` red
(committed reports PROTOTYPE.md/PROTOTYPE_2.md/PROTOTYPE_3.md/REVIEW_6.md plus
16 untracked historical files across old effort dirs — the untracked edits are
whitespace-only and irreversible; noted here for provenance). CLAUDE.md's
`exceptions.py` and `ir/reduction.py` package-map annotations were updated
mechanically.

Nothing is committed or staged; the first checkpoint commit remains the §4
exit. No parse-performance-relevant path was touched. Next: §3
(`parsing/product/` engine-neutral product ABI) on the same warm Terra agent.

## Round 16 folded — implementation may begin (2026-08-31)

The corrected Round 16 packet reran sequentially: both
`proto/shared_occurrence_ambiguity.py` and `proto/exact_lane_cost.py` exited 0.
The reopened audit reached `READY` on its fourth pass. Shared-occurrence
composition is closed: a packed chart node's meaning set is computed once and
each `(consuming handle, family index, kid slot)` occurrence ranges over it
independently. The occurrence-unrolled oracle agrees across the known shared-
DAG shapes, including genuinely shared transparent synthetics, and disproves a
family assignment keyed globally by packed handle.

The exact-lane policy is also closed. There is no arbitrary multiplicity cap or
resource refusal. Full enumeration pays one reducer application per local
family product plus image-dependent `same_value` comparisons. Constant
continuations, a family-aware end-to-end `ident`/`grow` certificate, and a
certified-second-root-meaning stop are exact shortcuts; an unproved case
executes exactly. Partial operations use bottom semantics and require a
distinct value-refusal exception.

Coordinator review found one counter boundary which does not reopen the design:
`law_lane_applications` counts the local witness and route lifts, not reducer
applications used to establish live families or the value comparisons. Active
documents therefore do not treat four as total lane cost. Production builds the
family chart on demand, caches baseline-family outcomes for liveness and route
reuse, and reports reducer applications and comparisons separately. This is an
implementation requirement, not a planning blocker.

The round also pins a fourth shipped defect: `ForestCtx.open` confuses a
suspended shared zero-width handle with a nullable cycle, so `DERIVATIONS`
emits malformed and incomplete duplicate-slot and pending-frame trees. It is
now in `CURRENT_BUG_REPORT.md` and §8's implementation queue. No planning or
user decision remains before §2. No source work or parsing regression is
authorized by the evidence itself.

## Prompt organization and durable orchestration (2026-08-31)

The investigator prompts now live together under `prompts/`, with every
durable index and ledger reference updated to the new path. The new
`prompts/ORCHESTRATOR.md` is deliberately status-agnostic: it requires the
orchestrator to establish the current phase from the active packet and working
tree before acting. It maps Terra work to Anthropic Opus and Luna work to
Anthropic Sonnet while leaving model selection to the orchestrator when task
complexity, context continuity, availability, or budget warrants a different
choice. Related work resumes the same warm agent; production and test roles
remain sequential.

## Coordinator review — shared-occurrence boundary and Round 16 (2026-08-31)

The delivered Prototype 15 executable reran cleanly with `python -B`; every
reported structural row reproduced and the only changed number was the report's
explicitly non-conclusive process-CPU sample. The coordinator nevertheless
rejected the packet's GENERAL composition closure. The prototype's own
`prove_oracle_precondition` asserts that no completed node has two parents and
no choice key is claimed twice, and `PROTOTYPE_15.md` §11 admits that a chart
where a key is reached twice is not exercised. That excludes the real
duplicate-slot, pending-frame, sibling-memo, and transparent-synthetic DAG
shapes already pinned by `proto/shared_forest_refold.py`.

The ruling is narrower than a mechanism rejection. The compiled continuation
certificate and every non-shared interaction witness remain closed. Forest
sharing is representation sharing: compute a shared node's meaning set once,
then let each consuming occurrence range over it independently. The global-key
assignment used by Prototype 15's oracle correlates those occurrences and is
not a valid control for that shape. `TODO.md` now carries an unchecked
**SHARED-OCCURRENCE COMPOSITION** gate, and `context.md`, `goal.md`, `DESIGN.md`,
`INDEX.md`, and `SUMMARY.md` state the same boundary. `DESIGN.md`'s stale claim
that no final reviewer returned `READY` is corrected to the recorded re-check
verdict without treating it as source authorization.

`prompts/PROMPT_16.md` tasks two remaining planning questions together: an
occurrence-unrolled oracle over the known shared-DAG shapes, and an exact-lane
cost policy which avoids silently replacing exact semantics with an arbitrary
cap. Resolver-pair scope is already settled: both engines provide complete-
document pairs only after root inequality and an actual resolver invocation.

## CURRENT SESSION — Prototype 15, the island-continuation composition (2026-08-31)

`proto/island_continuation.py` compiles one immutable continuation row per
contextual occurrence — keyed by consuming clone, channel slot, requested root
and bound product — and composes the mechanisms the packet already held rather
than adding a second architecture. The row carries the slot's class under the
real operation algebra plus two reachability lanes and nothing else; a typed
flatness walk shows it cannot hold a kernel, a derivation, a meaning or a
callable. The entry PINS its key objects, which is what `parsing/caches.py`
says a bare id-keyed dict must do to stay correct against address reuse —
correct and immortal until released; production's mortal owner is the
`CompiledGrammar` artefact through `parsing.caches`, which `cache_lifetime.py`
proved and this round does not re-derive.

The certificate is stated with its quantifiers: discarding an alternate is
universal over every flow path, so the grammar's over-approximation can only
withhold the shortcut; proving root inequality is existential and is therefore
verified against the chart's realized route. The rule-level half of the discard
is read BEFORE the island enumerates, so a constant continuation's alternates
are never built — `skipped_enumerations=1`, `seed_chart_nodes=0`,
`seed_products=0` and `seeds=0` against a control run's `control_seeds=1`.
(An earlier draft of this sentence cited "one seed derivation against a
control's three". That was true before the round's own later fix removed the
island's redundant second derivation; both runs now build one, and the saving
shows in the chart, product and seed columns above.) Two refusals keep the rows sound and both cost work rather
than correctness: a rule whose pre- and post-normalization contributing
references differ keeps no law, because a hoisted group or quantified repeat
splices the parent channel input-dependently and the authored `IrArg` index is
then not the chart's chain slot; and a `grow` obtained by retaining a MAPPED
focus keeps no law, because it is not injective over an empty focus. On the
recursive shipped grammars those refusals leave the shortcut a small minority
of rows, which is the honest cost of `PROTOTYPE_14.md` §4's still-open exact
channel-index obligation.

All the required cases execute over real tables, the real delegated island
seam and real authored reducer bodies, in GBNF and ABNF. Every witness runs
TWICE — once under its own table and once under a table that decides nothing —
and three things are required of every one, statically settled ones included:
the exact per-node lane equals the control's complete-Earley oracle, the
shortcut run's oracle equals the control's, and the declared verdict follows
from the control's cardinality. A constant continuation settles at zero
executed operations and zero chart nodes; an injective one proves inequality at
zero; a finite one executes and matches the oracle both when the alternatives
agree at the root and when they differ; two and three interacting occurrences
differ jointly while every one-flip comparison equals the baseline; ONE consumer
rule's two slots settle differently, as do two sibling sites of one island rule
under nested delegation, keyed on the delegated leaf object; and the
unambiguous control performs no lookup, descent, chart walk, execution or tree
build. Every derivation goes through one constructor and every recognition
through one entry, so a zero count is a fact about the code path. A cyclic
chart is refused by name to `cyclic_meaning`, and the precondition under which
the per-node and per-assignment relations coincide is checked on every witness
rather than assumed.

Two further results. The shipped `CompiledGrammar.reduce` returns the same
value the mechanism computes as its baseline wherever it does not refuse, with
the island's own meaning standing inside it exactly where the compiled row says
the continuation carries — grounding the semantics as the real reducer's. And
one `goal.md` §5 divergence is now executable: a document whose derivations
build different generated models but the same reducer value, refused by the
shipped model relation and accepted by the definitive root-value relation — the
declared successor relation, not a fourth shipped defect. That differential
cannot reach a document whose island CHOICE is live, because the shipped gate
refuses those; widening it needs `reduce(..., resolve=)`, which is `goal.md`'s
own public-surface work.

This round narrowed the resolver inputs before the later ruling: semantic
settlement needs no derivation pair, and an invoked `resolve=` receives the
complete-document pair under both engines. Production hot-path, memory and
parse-performance evidence remains
entirely open, as do the exact channel index, cache adoption into
`parsing.caches`, the emit-family and `YIELD` obligations, and the product
operations that do not exist yet. The prototype's root-down descent for the
consuming clone is an explicit stand-in for what production reads off the
island's entry frame or waiter code.

The fourth closure auditor returned `READY` on re-check, after its two
provenance blockers were fixed; the user ruled against spawning a fifth fresh
reviewer for documentation nits, so that verdict comes from an auditor which
had already read the packet. It also caught two fixes this round had claimed
and the files did not carry — an edit script aborted mid-way and the summary
was written from intent — both now applied and both recorded in
`reports/P15_ADVERSARIAL.md`. `READY` authorizes no source implementation and
accepts no parsing regression. Resolver scope is the already-ruled complete-
document contract, not an open decision delegated to the investigator.

No `src/`, test, harness, wiki or `pyproject.toml` file changed —
`git status --short -- src tests pyproject.toml .wiki` is empty and
`git diff --check` is clean. The effort's own tracked documents ARE modified;
they are the deliverable. The six named prototypes were rerun sequentially and
pass; Ruff, isort and Pyright pass on the new file; the tracked `resolver_pair`
bytecode artefact regenerated by the reruns is restored at the end of the
round. No multithreaded row was run at any point.

Three fresh adversarial reviewers ran sequentially, all `general-purpose`, no
Fable anywhere. The two topic reviewers each returned NOT READY with twelve
findings, four blocking; the closure auditor returned NOT READY three
times: four documentation-and-coherence blockers, then two numeric/provenance
ones, then one more. Every
finding and its disposition is in `reports/P15_ADVERSARIAL.md`, and the
auditor's own responses are in `reports/REVIEW_15.md`. Reviewer 1's blocking
four — an unsound drop
under a splicing channel, a bare id-keyed cache presented as a safety property,
counters whose zeros could not fail, and a shortcut measured after the work it
avoids — and Reviewer 2's blocking four — an undocumented whole-document chart
behind the EXECUTE lane, an unambiguous island that gained a tree, a linear
mechanism replaced by an exponential one without saying so, and a resolver that
re-recognized the island — are all fixed in the executable artefact, not argued
away.

Reviewer 3's four pass-1 blockers were about where the round's own conclusions
were written down rather than about the mechanism: a figure in the adversarial
record that its own later fix had superseded; the implementation queue and the
inventory left unfolded while the other four documents took Reviewer 2's
consequences; two mechanisms for one case in `DESIGN.md` with no precedence
stated; and the round's largest performance consequence carrying no labelled
gate. Three of the things now standing in the packet come from that pass, not
from Reviewer 2: the precedence ruling (the exact per-node relation governs and
the single-alternate overlay replay is its certificate-gated specialization),
the three new unchecked `TODO.md` §8 items, and the `PLANNING REQUIRED BEFORE THE
EXACT LANE LANDS — EXACT-LANE COST BOUND` gate, whose STATEMENT half gates the
exact lane's own implementation inside §8 while its MEASUREMENT half belongs
beside the §12 RSS row. Its pass-2 blockers were both numeric: the
EXECUTE census range was quoted as 80–95% where the artefact prints
73.9–95.6%, and this ledger recorded two reviewers where three had run. Its
pass-3 blocker was the same class one document further on — this ledger still
cited "one seed derivation against a control's three", the figure the round's
own earlier fix had invalidated; it now cites the chart, product and seed
columns that carry the claim, and the gate relabel above came from the same
pass.

Three of Reviewer 2's fixes changed what the round establishes. The exact
relation now runs over the DIRTY CONE beside a per-node baseline fold that is
the parse's own product: a new distant-island witness measures one dirty node
and two operation applications over a 161-node chart on an 81-character
document. The island's own set comes through that same per-node lane, so no
global family assignment is formed anywhere in the mechanism and an unambiguous
island builds exactly the one derivation `islands.island_parse` builds today.
And the seed retains its island kernel while — and only while — the occurrence
has an unsettled alternate, which removes the resolver's re-recognition and
gives `PROTOTYPE_14.md` §2's "deferred per-occurrence state" an executable
shape and a counter.

Three consequences are now stated rather than discovered later. The exact lane
needs a family-aware Earley chart, which the predictive path does not hold, so
an EXECUTE verdict there is an escalation — and the census puts EXECUTE at
73.9–95.6% of rows on the shipped grammars, while constant and injective rows
settle with no chart at all. Exactness is exponential in a single node's local
multiplicity where today's one-flip probe is linear and unsound; the
certificate and the cone bound how many nodes pay, not the local product.
Retaining the island kernel has a production release boundary this round does
not settle.

## PRIOR SESSION — Prototype 14 correction and active-plan fold (2026-08-30)

The coordinator reviewed the Prototype 14 code after the returned adversarial
`READY` and found six substantive survivors: discarded real tokenizer pipeline
payload, additive rather than multiplicative finite-image composition, a false
rule/span occurrence-uniqueness claim, explicit forbidden `object` use and
nested helpers, a stale quantified-nullable policy fork, and a production-ready
heading broader than the evidence. The earlier verdict is historical; the
corrected packet has not received a fresh external review.

All five touched prototypes now execute under the effort constraints.
`operation_slot_laws.py` proves finite `2 × 3 = 6` and `0 × 7 = 0`;
`scc_resolver_pair.py` reports one baseline and two spliced same-rule/same-span
occurrences and uses the explicit path as identity; `resolver_pair.py` has flat
module helpers and pins the third shipped ambiguity defect;
`tokenizer_validation_lanes.py` retains real fallback, unknown/fused-unknown,
byte remap, and atomic added-token payload while distinguishing the
tokenizer-format `special` flag; `nullable_quantifier_ambiguity.py` proves the
recognition/binding grammar split.

The nullable census is 0 sites in 15 canonical grammars and 71 compiler-made
sites across six relaxed codegen grammars. The selected solution does not
exclude a meaning-changing parser family: the parser recognizes the armed
pre-relaxation grammar, while binding and synthesis keep relaxed for optional
constructor fields. On all six exposed fixtures the current lifted relaxed
grammar equals armed, Earley and the gated product match today's public model,
and the forced PDA either matches or lawfully declines. Token-bound artefacts
concretize armed separately. `lift_optional_nullables` and every canceling
relax-then-lift parser route are deletion work. Authored optional nullable
sites remain semantic families.

The cyclic-production and tokenizer-three-lane planning gates are closed.
The later complete-document resolver ruling closes the user decision recorded
by this round. Production operation rows,
completion-time numbering, integrated ambiguity memory, PDA authored-family
placement, custom paid-loop neutrality, and all parse-performance comparisons
remain implementation gates. Three shipped ambiguity defects are now recorded
and owned. No `src/`, test, harness, wiki, or `pyproject.toml` file changed.
The corrected prototypes were rerun sequentially; no multithreaded benchmark
ran.

## PRIOR SESSION — Prototype 12 correction and shipped ambiguity scope (2026-08-30)

Prototype 12 and all five changed prototypes were audited against
`prompts/PROMPT_12.md`. Its final review gate was not met: four reviewers returned
`NOT READY`, no fresh reviewer examined the final text, and several mechanism
claims remained broader than their evidence. `reports/PROTOTYPE_13.md`
supersedes the four-way closure classification while retaining the useful
measurements and mechanisms.

The cyclic prototype no longer contains the arbitrary eight-round family
census or two-lap infinite-family evaluation. Finite components iterate to a
structural/value fixpoint; an injectively visible growing carrier decides
ambiguity from the SCC classification. Real-operation lowering and a
constructive complete resolver pair for an infinite SCC remained pre-§8 gates
at that session and are closed by the current Prototype 14 entry above.
The acyclic prototype now exercises the selected existential per-slot rule:
one real injective family path to a requested root is sufficient, and unrelated
dropping parents do not invalidate its constructive witness.

`proto/nullable_quantifier_ambiguity.py` establishes the shipped defect's
scope. PDA, Earley, and the public path silently choose among different models
for nullable atoms under `*`, `+`, `{0,2}`, `{1,2}`, groups, and directly empty
rules. Exact counts are unaffected. `?` is also affected, but
`lift_optional_nullables` erases its absent/present family and changes which
model wins. The generic rule is a nullable atom under a quantifier admitting
more than one count. The 15 canonical ground-truth grammars contain zero such
sites; Prototype 14 later finds 71 after compiler relaxation and separates the
recognition and binding moments.
The same probe confirms that `ambiguity_points` changes from zero to two after
deferred Leo expansion on one finished kernel, so complete readout owns that
expansion.

The ambiguity RSS control now runs the existing fused PDA model product rather
than a post-parse full-tree meaning table: at 4,001 characters it measured
0.004065 s process CPU, with no ParseTree/completed-handle memo. Candidate
ambiguity factories are not wired into current source, so the external control
does not claim a zero-allocation proof; the landed factories must supply it.
The retained flat layout and frame shape stand, while completion-time
family-aware numbering remains production work.
The custom real-pool lifecycle stands; its timed ParseTree extraction does not
close production paid-loop neutrality. The tokenizer relation is exact for the
currently specified constructors, while ordinal-domain, merge-reference, and
pipeline fallback/unknown semantics remain a final-contract investigation.

No `src/`, `tests/`, or `pyproject.toml` file was changed. The generated
`cyclic_meaning` bytecode artefact was removed. Ruff and Pyright pass on the
corrected prototypes; focused executable verification is recorded in
`PROTOTYPE_13.md`.

`prompts/PROMPT_14.md` now tasks the four remaining investigable gates plus clean
pre-fix baselines for the first two shipped defects. Its three internal adversarial
reviewers must run synchronously and sequentially as `general-purpose` agents;
Fable subagents are explicitly prohibited and may not be substituted.

## PRIOR SESSION — Prototype 11 evidence fold and surviving gates (2026-08-29)

`reports/PROTOTYPE_11.md` and its five revised/new prototypes were audited
against `prompts/PROMPT_11.md`, the active design, and their executable behavior. Ruff
and Pyright pass. The ambiguity-interaction, generic keyed-product,
resolver-pair, custom-binding, control, and trace-frame witnesses were rerun
sequentially; the interpreter reports `Py_GIL_DISABLED=1`. No Qwen benchmark
was rerun during the documentation audit.

Established results are now folded into `context.md`, `goal.md`, `DESIGN.md`,
and `TODO.md`. Production one-flip ambiguity is unsound on interacting sources;
per-node deduplicated meaning sets are the exact acyclic reference relation,
subject only to compiler-proved choice-free injective/constant continuation
shortcuts. Real carrier rows select cold comparison for recursive Python
dicts and document-level normalization for `IrMap`. Complete resolver pairs and
a one-island Earley splice with no second document recognition are feasible;
Prototype 14 later proves today's island derivations are not retained for free. The flat
CSR/forward-star index has dirty-cone parity and measured retained cost. The
custom binding core executes through source death, tier escape, eviction,
unhashable constructors, identity-safe caching, and concurrent free-threaded
cold binding.

No composite gate was falsely closed. Cyclic interaction still uses an
unbounded `2^k` one-lap fallback; tokenizer normalization omits duplicate-id and
duplicate-merge constructor refusals; the ambiguity control allocates and then
clears a real meaning overlay; the frame row shares one child tuple across all
depths and therefore underprices production-shaped frames; the custom witness
never enters a real retained pool; and resolver scope has no recorded user
ruling. `TODO.md` marks each established sub-decision closed and each remaining
mechanism or decision separately open. Production source remains untouched.

`prompts/PROMPT_12.md` assigns only the four remaining mechanism gates: exact cyclic
ambiguity, complete tokenizer refusal equivalence, dictionary-free flat
structures plus honest control/frame accounting, and real-pool custom binding
with paid-loop neutrality. Its done-gate requires two specialized internal
adversarial reviewers and one fresh closure auditor, invoked sequentially after
all benchmarks, with substantive findings fixed and rerun. If the investigator
cannot call its internal `Agent` tool, it must stop and leave the complete
reviewer prompts for manual execution rather than declaring readiness.

## PRIOR SESSION — Prototype 10 closure audit and next investigation (2026-08-29)

The external investigation produced `reports/PROTOTYPE_10.md` and four
prototypes. `reports/REVIEW_10.md` accepts the narrow results: single-island
seed continuation through an Earley cone/PDA trace, sibling accepting roots in
island discovery, sequence-only ordered meanings, rejection of the incremental
keyed treap and dict-of-sets dependency index, iterative equality, the retained
`DISTANT` RSS scales, and the immutable custom-class constructor symbol with a
homogeneous result-free plan cache. The user's prior ruling is explicit:
arbitrary custom classes remain in scope.

The audit rejects the report's composite closures. Purity does not make
multiple ambiguity sources separable; the Qwen cold row measured only one
plain encode dictionary; the resolver prototype counted complete-document
ambiguity points without constructing the pair; the RSS prototype allocated no
island trace lane and its control retained a memo; and the custom runner could
not execute after deleting its required source grammar. These remain marked
planning or decision gates in `TODO.md`. `prompts/PROMPT_11.md` assigns adversarial
interaction semantics, real keyed-product rows, real resolver pairs, a flat
dependency index plus corrected RSS protocol, and executable custom-binding
lifetime. Production source remains untouched.

The four Prototype 10 files pass Ruff and Pyright. Their ordinary witnesses
pass, which confirms that the review findings concern missing adversarial cases
and overbroad conclusions rather than broken stated examples. No Qwen or
multithreaded benchmark was rerun during this documentation pass.

## PRIOR SESSION — REVIEW_9 corrections and explicit planning gates (2026-08-29)

`REVIEW_9.md` returned GO for §2 and ten later-phase findings. The regular proof
now declines a once-required nullable atom which can steal its continuation and
an ordered alternation whose nullable arm is not last. The identity probe passes
those two witnesses beside the earlier variable-boundary case. Route lowering
now carries a finite route through intervening contextual PDA clones and Earley
successor codes rather than assuming producer and consumer are siblings. The
flat ABI prototype no longer stores target decoder, validator, or record-
constructor callables at frequent completions: engine-owned closed operations
are selected by plain integers, with target callables restricted to collection
finish, root finalization, and meaning comparison.

The first correction pass chose a whole-document Earley bailout for an
ambiguous PDA island. The user correctly rejected the inference: a parent which
drops or transforms a differing child proves only that the island cannot decide
locally, not that the island parse should be discarded. The corrected design
carries a cold alternate-meaning seed through the enclosing product continuation
and compares at the requested root. A complete Earley parse is reserved for a
differing root whose caller supplied `resolve=`, because that existing API needs
complete derivations. The public engaged `cores=AUTO` tokenizer
row remains the `<1.000 s` gate, while sequential route-anchor decline is a
reported diagnostic. Morphism `_bind` dispatch uses one homogeneous typed
registry per declaration kind. `parsing/product/regular.py` reuses the existing
PDA core `CharSet` and scanner lowering. §4 runs the generated-twin gate and
accounts for every named foldkit symbol. §13 consumes the frozen goldens while
preserving fresh property generators. §12 adds an ambiguous-input RSS row for
the document-sized dependency index.

`TODO.md` now defines `DECISION REQUIRED`, `PLANNING REQUIRED`, and `USER
DECISION REQUIRED` as hard gates. Remaining open work is visibly marked: the
island seed/dependency/replay mechanism before §8, product-specific
persistent-meaning keep/fallback decisions at §8, the custom-class keep/omit
decision at §6, the ambiguous RSS witness plan before §12, and any user-only
approval of a bugfix-related parse regression. `PROTOTYPE_9.md` records the
executed corrections. No production source was changed by this pass.

Five corrected prototypes pass Ruff and Pyright. Their executable witnesses
pass: typed products/transactions/fragments/overloads; three exact public
`reduce` overloads with inert declarations; decoded/raw non-sibling routes with
zero grammar-arm additions; native/GBNF/ABNF/EBNF/JSON/engine identity; and all
three unsafe possessive shapes declining. `git diff --check` passes, every
effort `.md`/`.py` basename appears in `INDEX.md`, and the current packet has no
stale whole-document island-bailout or sequential-decline-gate claim.

## PRIOR SESSION — REVIEW_8 corrections and implementation-ready pass (2026-08-29)

`REVIEW_8.md` returned NO-GO on three architectural claims: child-local
ambiguity narrowed the root-value language, the `<1.000 s` interpreted budget
depended on an unscheduled value-string recognizer consult, and scanner
admission did not prove possessive capture boundaries. Its remaining findings
identified an unowned region derivation, executable public morphisms, a
resolver-consuming raw route, incomplete synthetic-DAG accounting, stale GC
protocol, and missing pre-alpha cleanup successors.

`PROTOTYPE_7.md` now records the correction set. Real Earley completions keep a
baseline completed-handle memo and replay a packed family's dirty ancestor
cone by completed code, preserving the dropping-parent root verdict at three
alternate fold bodies versus a 1,207-body baseline. A conservative regular
proof adds acyclic closure, first-disjoint arms, non-nullable repeats, and
continuation/separator/terminator boundary ownership; it declines an acyclic
possessive counterexample which scanner admission accepts. Region input is
derived from semantic roles × target demand and works for a non-JSON catalog
grammar. The in-process order-balanced capture/ops comparison is 0.246319 s
versus 0.351784 s process CPU (1.428162x), with a 0.001129 s
duplicate-control floor;
the ops row remains conditional on the now-scheduled exact value-string
specialization. Public morphisms are inert declarations, raw routing adds zero
grammar arms and leaves `resolve=` untouched, transparent synthetic folds use
a distinct finished set, and the even eight-pair GC probe makes 0.700274 s CPU /
0.130779 s wall the collector-enabled carrier reference.

The final adversarial pass found one further cost overclaim: dirty-cone
fold-body count did not price eager-container equality/materialization.
`proto/persistent_meaning.py` adds exact immutable contribution trees with
identity sharing and one chosen-result materialization; a 65,536-leaf changed
path visits 18 nodes, an equal path-copy 33, and a dropped singleton one.

Step 0 is now complete. `src` is identical to `0faa7289`; the host is CPython
3.14.3t on an 8-core/16-thread Ryzen 5700X3D; the Qwen fixture hash and full
consumer inventory are frozen in `PROTOTYPE_8.md`. Isolated GC-on public-reader
rows return the same final-table digest and peak at 633,000 KiB resident-first,
632,888 KiB path-cold, and 838,120 KiB on the second call in one retained warm
process. The last number is a lifecycle-matched high-water reference, not a
leak diagnosis.

`context.md`, `goal.md`, `DESIGN.md`, and `TODO.md` now state these mechanisms,
owners, tests, performance gates, cleanup, and scenario-matched RSS denominators.
All work remains in the gitignored effort folder; `src` is unchanged. The next
fresh cross-model deliverable is `reports/REVIEW_9.md`.

## PRIOR SESSION — consistency and evidence correction (2026-08-28)

A full post-REVIEW_7 audit found four substantive gaps in the first ruling
pass. `select_raw` could not be called by the DESIGN's two reducer-required
overloads; “any compiled grammar” overstated its binding-derived map-shape
precondition; child-local ambiguity omitted separate accepting root items; and
the GC probe always ran enabled before disabled. The interpreted 0.368907 s row
also omitted too much production machinery to support the statement that it
carried the complete <1.000 s envelope.

`proto/reducer_free_surface.py` now pins three exact overloads and typed
MODEL/EXTENT raw-selection codomains. `regular_region_lowering.py` now covers
native/GBNF/ABNF/EBNF formulations, arbitrary 1/2/3 capture arity, the complete
vocab table/boundary, empty validity, and malformed refusal. The ambiguity
prototype covers separate root siblings beside child-local internal points.
The order-balanced eight-worker GC probe corrects the paired delta to
+0.005182 s wall / +0.005439 s process CPU; the old +0.016948 s claim is
rejected. Evidence and boundaries are in `reports/PROTOTYPE_6.md`.

`context.md`, `goal.md`, `DESIGN.md`, `TODO.md`, and `PROTOTYPE_5.md` are
reconciled to those results. `src` remains unchanged. No reviewer is called
until the prototypes and documents pass their local gates; the next fresh
review deliverable is `reports/REVIEW_8.md`.

## PRIOR SESSION — REVIEW_7 rulings folded, mechanisms prototyped (2026-08-28)

`reports/REVIEW_7.md` (coordinator + fresh cross-model pass) was verified
against source and plan: all fifteen findings held. The trivial findings are
folded into `goal.md`/`DESIGN.md`/`TODO.md` as recorded rulings; the
non-trivial or unclear mechanisms are prototyped in `proto/` and measured in
`reports/PROTOTYPE_5.md` — four REVIEW_7 mechanisms plus the finding-10
morphism exhibit `demand_selection.py` (a first spans-then-reparse draft of
it was rejected and deleted as unfaithful to the one-parse architecture). All
five new prototypes pass pyright, ruff check/format, and pylint 10.00/10 with
zero suppressions. `src` unchanged.

**Prototyped mechanisms.** (1) `regular_region_lowering.py`: the
proved-regular capturing lowering is generic (acyclic-closure proof via
`build_recognizer`, demand-derived positional groups, recursive region
declines) and identity-proven four ways — native lowering == GBNF-formulation
lowering == stdlib oracle == generic engine `reduce` over 4,000 entries. Its
interpreted-ABI probe reframes REVIEW_7's blocker 1: one recognizer consult
per rule completion plus flat int dispatch runs the 3.6 M-char vocab region in
0.368907 s sequential GC-on — 1.40x the 0.262931 s whole-entry capture, versus
11.93 s current. The 16.7x gap is per-character consumption plus model
construction, not "regex versus interpreter". Ruling recorded: <1.000 s rides
the interpreted ABI; ~105x is contingent on the capturing lowering, now a
gated §7-exit task. (2) `shared_forest_refold.py`: the fold walk executes a
shared subtree's body 2/2/1 times across three witness shapes for identical
two-slot sharing — traversal-dependent, so the side-effecting ABI would get
duplicated AND missing effects; §3 exit now requires value-once-per-node with
per-occurrence effects, all three shapes as witnesses. (3)
`local_meaning_fold.py`: alternate meanings fold at the ambiguity family's
child subtrees — declared verdict at 4 folds versus 2,414 root-rooted on a
601-char witness, and the dropping-parent divergence resolves toward the
declared local law, settling findings 6+8 together (value-meaning relation is
definitive; §5 enumerates divergences). Also: recursive `same_value` overflows
near depth 1000 — §8 makes the equality walk iterative. (4)
`carrier_gc_cost.py`: paired in-process GC delta on the composed carrier is
+0.016948 s wall (~11 %); GC state is now a recorded §0 protocol field and
production rows run collector-enabled.

**Rulings folded as plan edits.** Python <0.100 s demoted to pursued objective
(gate = multiplier versus current route); tokenizer <1.000 s gated at engaged
`cores=AUTO` with sequential and CPU-per-byte reported and the decline case
gated sequentially; timed rows at the §5 and §7 exits with a 3x stop factor at
§7; suite+pyright with attributed failing-file ledger at every exit from §4,
package-map lines updated mechanically per phase; oracle retained through the
§9 exit with §8/§9 differential re-runs; §12 re-measures the `0faa7289`
baseline in the same alternating session and needs the §0 RSS baseline;
free-threading ownership extended to per-completion-hot flat tables; exception
vocabulary declared (`TargetRefusalError`/`SemanticVerdict` — bare `Verdict`
is taken); `resolve=` on both `reduce` overloads; empty-edge rulings
(`select({})` refuses, empty vocab/merges valid); `ProductProgram[GrammarModel,
GrammarModel]` typing; `parsing/trace.py` assigned to §4;
`compile/product/` layout pinned; `stitch/model.py` decided-keep; §13 gains
select-contract, extent, and binding-registry-lifecycle rows.

**Finding 10:** the reducer-free extraction capability stays as the
`select_raw` grammar-demand morphism; feasibility and contract are prototyped
in `proto/demand_selection.py` (`reports/PROTOTYPE_5.md` §6): the selection
compiles into contextual clones over any compiled grammar with no
reducer/signature — one engine parse per document, kept models/extents built
during it, undemanded subtrees recognition-only, deterministic key routing,
syntax-first shape verdicts, declaration-ordered round-trippable models or
statically model-free certified extents, empty-level and raw-duplicate
refusals, demand-local retention (2 models + 998 key records over 1,000
entries), formulation-independent (GBNF == native JSON), raw keys declaredly
distinct from decoded. All REVIEW_7 re-entry conditions are satisfied.

## PRIOR SESSION — reviewed handoff (2026-08-27)

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

**Checkpoints:** the coordinator reviews and commits after §4,
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
