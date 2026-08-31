# Ledger — target-shaped parsing

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
