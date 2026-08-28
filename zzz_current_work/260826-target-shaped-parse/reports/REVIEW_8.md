# Plan review — target-shaped parsing, pass 8

**Reviewed:** 2026-08-28, against the working tree on branch `targeter`
(source baseline `0faa7289`; the unstaged active-work edits to `context.md`,
`goal.md`, `DESIGN.md`, `TODO.md`, `LEDGER.md`, `proto/carrier_gc_cost.py`,
`proto/local_meaning_fold.py`, `proto/regular_region_lowering.py`, and
`reports/PROTOTYPE_5.md` are the reviewed state, not HEAD). Packet read in
full: `context.md`, `goal.md`, `DESIGN.md`, `TODO.md`, `LEDGER.md`,
`TBD_after.md`, `reports/REVIEW_7.md`, `reports/PROTOTYPE_5.md`,
`reports/PROTOTYPE_6.md`, and the prototypes `reducer_free_surface.py`,
`demand_selection.py`, `local_meaning_fold.py`, `shared_forest_refold.py`,
`regular_region_lowering.py`, `carrier_gc_cost.py`. Every architectural claim
cited below was checked by opening the named production file in this session.
No command was run, no agent dispatched, and no file except this report was
modified.

**Verdict: the architecture still stands, and pass 7's fifteen findings are
substantively folded in — but two of the three rulings that closed pass 7's
hardest findings are not what the evidence they cite supports.** Finding 8's
"local meaning" mechanism was adopted as a cost fix and silently changed the
ACCEPTED LANGUAGE; finding 1's two-regime decision assigned the `<1.000 s`
gate to an interpreted ABI whose throughput number depends on a mechanism the
fourteen-phase queue never schedules. Those are B1 and B2. B3 is new: the
`§7` capturing lowering's witness proves a strictly weaker property than the
proof obligation `DESIGN.md` states, over a lowering that is not
language-preserving in general. The remaining findings are bounded plan edits,
but H3 deletes a public export whose only replacement is a prototype import
of the very symbol being deleted.

## Blockers

### B1 — The ambiguity ruling conflates the RELATION with its SCOPE; the adopted scope narrows the accepted language and contradicts the invariant it cites

**Severity:** blocker — correctness, and an unrecorded public-behaviour
change on `parse` as well as `reduce`.

**References:** `goal.md:216-224`; `DESIGN.md:614-628,630-647`;
`TODO.md:673-676` versus `TODO.md:684-692`;
`proto/local_meaning_fold.py:74,180-198`; `reports/PROTOTYPE_5.md:96-116`;
`src/lexic/parsing/earley/kernel/forest/support/ambiguity.py:10-16,130-157,160-206`;
`src/lexic/compile/artifact.py:340-342`; `CLAUDE.md:404-409`.

Pass 7 finding 6 asked one question — should ambiguity be judged by the
reduced VALUE or by the built variant MODEL? — and the recorded ruling
(`goal.md:216`) answers it correctly: the value relation is the right one, and
`ambiguity.py`'s own docstring agrees. Finding 8 asked a different question —
where should the alternate fold be ROOTED? — and `proto/local_meaning_fold.py`
answers it with child-rooted folds for a 2,414→4 cost win. The ruling then
merges the two into one sentence: "the value-meaning relation is definitive
… and it is the only relation that can keep a difference a dropping parent
erases" (`goal.md:222-224`). Those are two independent changes, and only the
first is what `CLAUDE.md` licenses.

The prototype's own `dropping-parent` row is the proof that they differ:
`Witness("dropping-parent", AMBIGUOUS, "xz", {"root": "drop"}, False, True)`
(`proto/local_meaning_fold.py:74`) — root verdict *no difference*, local
verdict *differs*. That is a document whose produced value is unique being
REFUSED. `ambiguity.py:10-16` states the opposite as the module's reason for
existing ("Refusing those refuses valid input for a difference no consumer
could observe"), and `CLAUDE.md:404-406` states the invariant as "A span whose
derivations build two different models raises" — in the dropping-parent shape
they build the same one. The change is a language narrowing on `parse` and
`reduce`, presented in the packet as a correction toward the invariant.

`TODO.md` §8 then contradicts itself. `TODO.md:673-675` requires "Generated-model
products reproduce current model-value ambiguity semantics"; `TODO.md:684-692`
requires alternate meanings to be folded at the differing CHILD subtrees,
"never a root-rooted whole-document refold per flipped point". The
dropping-parent witness shows those two bullets cannot both hold for the
generated-model product — a generated model whose rule drops a child is
exactly the shape that diverges. Terra cannot implement §8 as written.

There is a second, quieter gap. `_key_differs`
(`proto/local_meaning_fold.py:180-198`) folds the child subtree with a
rule-name-keyed policy. Production's `MeaningOp` is occurrence-keyed
(`DESIGN.md` §demand), and the child handle is built through
`FastTree(kernel, {}).build(child)` with no parent context — the plan asserts
"fresh local state" makes this sound without stating how the child's
CONTEXTUAL completion range is selected when §6's contextual clones have given
one lower rule several occurrence variants.

**Required:**

1. Split the ruling in `goal.md`/`DESIGN.md` into two recorded decisions:
   (a) the value relation supersedes the variant-model relation — approved,
   unchanged; (b) the fold SCOPE. For (b), either prove the child-local
   relation sound and complete with respect to the root-value relation, or
   record explicitly that acceptance narrows, name the class of documents
   newly refused (dropping/projecting parents), and get the user's ruling —
   this is not a divergence to "enumerate and attribute" at §5, it is a
   deliberate reduction of the accepted language.
2. Resolve the `TODO.md` §8 self-contradiction. If the generated-model product
   keeps today's semantics, it keeps root-rooted folds and does not get the
   locality win; say so.
3. State how a child-rooted fold selects the child's contextual completion
   range once §6 has cloned it, or make locality conditional on the child
   having exactly one contextual variant.

### B2 — The gated `<1.000 s` row rides a throughput mechanism no phase schedules

**Severity:** blocker — performance feasibility and queue completeness.

**References:** `goal.md:34-47,431-441`; `DESIGN.md:560-580`;
`reports/PROTOTYPE_5.md:39-56`; `proto/regular_region_lowering.py:27-29,258-301`;
`src/lexic/parsing/pda/runtime/matchers.py:241-256,309-323`;
`TODO.md` §§3-7 (no bullet for this mechanism).

The two-regime ruling assigns `<1.000 s` to the interpreted ABI and makes only
`~105x` contingent on the capturing lowering (`goal.md:34-47`). The number
that licenses it is `PROTOTYPE_5.md`'s 0.368907 s `ops` row. Read
`_entry_ops`/`_run_ops` (`proto/regular_region_lowering.py:258-301`): every
entry rule is consumed by ONE `patterns[args[index]].match(text, pos)` — a
compiled-recognizer consult per rule completion. That is not the shipped
engine. `vstr_once` (`matchers.py:309-323`) is "select, match, slice, build,
append" per iteration and `run_span_once` (`matchers.py:241-256`) is one
Python call per run iteration.

`DESIGN.md:561-569` names the missing mechanism precisely — "A `value_str`-
classified rule whose closure the recognizer compiler accepts **may** be
consumed by one compiled-recognizer consult per occurrence instead of the
current per-character loop" — and then never converts it into a task.
`TODO.md` §3 builds the ABI, §4 migrates the model path under a strict
zero-tax rule, and §7's only gated performance bullet (`TODO.md:636-649`) is
the capturing REGION lowering, which the same ruling says `<1.000 s` does not
depend on. So the gated row's evidence assumes a mechanism the queue does not
build, and §7's 3x stop factor (`TODO.md:655-661`) would fire at a point where
the only remedy is unscheduled work.

**Required:** add the per-occurrence value-string recognizer consult as an
explicit task with its own owner and gate — most naturally at the §3 or §4
exit, since it changes the paid loop the §4 non-regression gate measures — or
withdraw the `ops` row as evidence for the `<1.000 s` regime and re-derive
that gate from a measurement of the ABI as actually scheduled.

### B3 — The regular-region witness proves a weaker property than the stated proof, over a lowering that is not language-preserving in general

**Severity:** blocker — genericity and correctness of the §7 gated task.

**References:** `DESIGN.md:571-575`; `TODO.md:636-649`;
`proto/regular_region_lowering.py:129-142,150-173`;
`src/lexic/parsing/pda/core/scanner.py:1-41,174-200,361-390,393-414`;
`reports/PROTOTYPE_5.md:13-38`; `reports/PROTOTYPE_6.md:31-45`.

`DESIGN.md:571-573` states the proof obligation as three conjuncts: "repeated
entry, acyclic simple closure, **no arm ambiguity**". `_prove`
(`proto/regular_region_lowering.py:129-133`) is `build_recognizer(rules, roots)`
and nothing else. `build_recognizer` (`scanner.py:393-414`) proves exactly two
things: the closure is acyclic (`_closure`, `scanner.py:361-390`) and every
atom is a simple recognizable construct (`_compile_arms`). It does not test
arm ambiguity. One third of the stated proof is absent from the witness and
from the mechanism the witness demonstrates.

The gap matters because of what the recognizer IS. `scanner.py:174-200` lowers
every item possessively — `(?:atom){lo,hi}+` — and every arm and reference
atomically — `(?>…)`. The module docstring (`scanner.py:1-41`) is explicit that
this is correct because the scanner is "recognition-only and fail-soft": the
winning branch re-parses the noise, so a wrong commit costs nothing.
`_lower` (`proto/regular_region_lowering.py:150-173`) takes those same sources,
concatenates them into one entry pattern, and makes it the AUTHORITATIVE
consumer of the region. Under that use, atomic arms mean an alternation whose
first arm is a prefix of a later one commits to the prefix and the entry fails;
possessive items mean a greedy rule that overshoots its successor cannot give
back. Both refuse strings the grammar derives. The JSON vocab witness is
immune because `string`/`name-separator`/`int` happen to be boundary-
deterministic; `PROTOTYPE_6.md:31-45` adds formulations, arity, empty and
malformed edges but no shape where the acyclic-closure proof passes and the
possessive concatenation disagrees with the engine.

**Required:**

1. State the proof obligation as executable conditions — arm non-ambiguity AND
   boundary determinism across concatenated entry rules — and implement them in
   the compiler-side proof, not just in prose.
2. Add a decline witness: a region whose closure is acyclic and simple but
   whose concatenation is ambiguous, proven to decline rather than to answer
   differently from the generic product.
3. Because `build_recognizer` was written for a fail-soft consumer, record
   whether the §7 task reuses it or needs its own non-possessive lowering; the
   plan currently assumes reuse without noting the semantic difference.

## High findings

### H4 — Region DISCOVERY is unproven and has no owner

**Severity:** high — genericity.

**References:** `proto/regular_region_lowering.py:54-75,116-119`;
`reports/PROTOTYPE_5.md:198-205`; `TODO.md:636-649` (§7), `TODO.md:722-728`
(§9 route anchors); `DESIGN.md:571-580,663-674`.

`RegionSpec` is hand-authored locator data (opener rule, entry rule tuple,
demanded item indices, separator, terminator), and `_region_start` finds the
region by `text.index('"vocab": {')`. `PROTOTYPE_5.md:198-205` concedes this:
"Production route compilation must derive equivalent regions from the composed
lower×upper grammar without naming rules." Neither §7's gated bullet nor §9's
route-anchor bullet names the analysis that produces a `RegionSpec` from
grammar + schema, and no phase owns it. The §7 task therefore has no input and
§9's anchors have no source, while the `~105x` objective is declared contingent
on both.

**Required:** name the owner (the natural home is `compile/product/compose.py`,
pinned at `TODO.md:420-428`), and require the derivation to be demonstrated on
at least one non-JSON witness before §7's gated task opens — the same "no
privileged formulation" bar `CLAUDE.md:424-429` sets.

### H5 — The pinned overload prototype models morphisms as executors, which is the shape review 3 blocked

**Severity:** high — the API prototype does not witness the contract it is
cited for.

**References:** `proto/reducer_free_surface.py:33-47,61-75,121-128,181-191`;
`DESIGN.md:255-262`; `reports/PROTOTYPE_6.md:6-28`; `LEDGER.md:113-121`.

`DESIGN.md:257-260` is categorical: "`ReductionMorphism[Result]` is recursively
immutable public signature/schema/algebra data only; it contains no cache,
lock, mutable factory, **executor**, or entry dictionary." The prototype cited
as pinning the exact surface gives both morphism classes a `run` method
(`reducer_free_surface.py:36-38,44-46`) and dispatches through
`isinstance(into, ReductionMorphism)` then `into.run(text, reducer)`
(`:181-191`). What is proven is the three-overload inference and the exact
`RawSelection[GrammarModel]` / `RawSelection[CertifiedExtent]` codomains —
which is real and valuable. What is NOT proven is that those overloads still
infer exactly when the morphism is declaration-only and the runner is a
separately bound `BoundProduct[Result]` looked up by identity. That is the
harder typing question, and it is the one §5 implements.

**Required:** re-pin the surface with declaration-only morphisms and a bound
runner, or annotate `PROTOTYPE_6.md` §1 and `DESIGN.md`'s overload block that
`run` is a prototype affordance with no production counterpart, so §5/§6 do not
reproduce it.

### H6 — `MapShape` is on the deletion list and is the only implementation of `select_raw`'s binding precondition

**Severity:** high — a public export removed with no named successor.

**References:** `TODO.md:799-807` (§10 deletion), `TODO.md:541-557` (§6
`select_raw`), `DESIGN.md:842-851`;
`src/lexic/compile/output/templating.py:82-140` (`MapShape`,
`MapShape.for_entry`, and `_section_for` at `:136`);
`src/lexic/compile/__init__.py:33,109` (public export);
`proto/demand_selection.py:16,187-201`;
`reports/PROTOTYPE_6.md:26-28`.

`select_raw`'s stated precondition is "the compatible mapping shape derivable
from binding data" (`DESIGN.md:83,845-847`). The only code that derives it is
`MapShape.for_entry` — which resolves key/value fields from `compute_binding`
and finds the section by the nesting cycle the value field closes
(`templating.py:99-140`). `proto/demand_selection.py:190` calls exactly that.
`TODO.md:799` deletes `MapShape` outright, and `MapShape` is a public name in
`lexic.compile.__all__`. No phase assigns the derivation a new home, and §6's
bullet says only "derives a compatible recursive map shape from the entry
rule's own binding data" — which is the behaviour, not the owner.

**Required:** name the successor owner and move the derivation there in §6,
before §10 deletes `templating.py`; and record that the public name `MapShape`
disappears from `lexic.compile` with `select_raw` as the replacement surface.

### H7 — The 1.40x interpreted-vs-capture ratio is a cross-process comparison of a toggleable change, with no control row

**Severity:** high — the two-regime ruling's load-bearing number.

**References:** `proto/regular_region_lowering.py:442-450,461-489`;
`reports/PROTOTYPE_5.md:39-56`; `goal.md:34-47,431-441`; `DESIGN.md:560-569`;
`docs/STYLE.md:176-189`.

`main` selects ONE execution model per invocation from `--mode` and never runs
the other, so `capture` (0.262931 s) and `ops` (0.368907 s) come from two
separate processes. `docs/STYLE.md:178-182` classifies exactly this — one
method's body, swappable by a flag — as toggleable, and says cross-process
"cannot resolve it: two byte-identical trees measure ±2.7% apart". The two
rows also report the median, where the toggleable protocol says take the min,
and no byte-identical control row is published for either. The delta is large
enough (40%) that it probably survives, but the packet's own measurement
contract (`DESIGN.md:1007-1028`) forbids treating it as settled on this
evidence, and it is the number the whole regime split rests on.

**Required:** re-measure `capture` versus `ops` in one process, alternating,
min-of-rounds, with a control row — or mark the 1.40x figure provisional in
`goal.md`, `DESIGN.md`, and `PROTOTYPE_5.md` §2 until it is.

### H8 — The composed-carrier budget still quotes the GC-disabled number pass 7 rejected

**Severity:** high — measurement validity and documentation coherence.

**References:** `goal.md:418-424`; `DESIGN.md:1063-1073`; `context.md:359-363`;
`TODO.md:618-625`; `reports/PROTOTYPE_6.md:86-99`;
`proto/carrier_gc_cost.py:75-101,151-191`; `reports/REVIEW_7.md:299-311`.

Pass 7 finding 11 required two things: correct the delta, and "restate the
carrier budget with GC enabled". `PROTOTYPE_6.md` §4 does the first
(+0.005182 s wall, +0.005439 s CPU; the +0.016948 s fixed-order claim
rejected) and the ledger records it. The second was not done. `goal.md:419`,
`DESIGN.md:1063-1066`, `context.md:361`, and `TODO.md:620-623` all still carry
`0.138739 s` with its `0.121197 / 0.017504 / 0.000032` decomposition and no GC
annotation — a number taken inside a `gc.disable()` window. The corrected
GC-enabled median from the same carrier is `0.140949 s`
(`PROTOTYPE_6.md:88-92`). The gap is small; the inconsistency is not, because
`goal.md:441` now makes per-row GC state a contract quantity and every row
above it violates that contract.

**Required:** replace the headline budget with the GC-enabled row and its GC
annotation everywhere it appears, or state at each site that `0.138739 s` is
GC-disabled provenance and not a budget.

### H9 — `select_raw`'s route determinism is stood in by the caller's own resolver channel

**Severity:** high — an unresolved semantic collision on a shipped surface.

**References:** `proto/demand_selection.py:486-514`;
`reports/PROTOTYPE_5.md:161-169`; `TODO.md:541-557` (esp. `:555-557`);
`DESIGN.md:109-117` (overload 3 carries `resolve=`), `DESIGN.md:66-68`;
`src/lexic/parsing/products.py:273-306`.

The prototype's demand grammar is genuinely ambiguous: a selected key's literal
arm and the fallback arm both derive the same entry. `_prefer` settles it by a
specialized-over-poison-over-fallback score and is handed to `parse_model` as
the `Resolver` (`demand_selection.py:509-514`). So the morphism consumes the
one ambiguity opt-out channel that `DESIGN.md:109-117` also exposes to the
caller on the same overload. `TODO.md:555-557` says the stand-in "is replaced
by the real route continuation", but no prototype shows that raw-key dispatch
compiles to a grammar with no arm-choice ambiguity point, and nothing states
what a caller-supplied `resolve=` means on a `select_raw` product.

**Required:** a §6 sub-gate that the compiled raw-key routing produces zero
arm-choice ambiguity points on the toy and both JSON formulations, plus a
stated rule for the caller's resolver on that path (it should reach genuine
document ambiguity and never the morphism's own dispatch).

## Medium findings

### M10 — The shared-forest witness under-models the production walk

**Severity:** medium — the §3 gate is right, its quoted numbers are a floor.

**References:** `proto/shared_forest_refold.py:123-158`;
`src/lexic/parsing/fold.py:480-491,495-500`; `reports/PROTOTYPE_5.md:69-88`;
`TODO.md:325-332`.

`_walk_folds` writes `results.add(id(node))` for every node it expands.
`ModelFold._fold_node` (`fold.py:495-500`) returns early WITHOUT writing
`results` when the rule is synthetic (`__rep`/`__opt`/`__grp`), so such a node
fails the `id(k) not in results` guard (`fold.py:485`) on every subsequent
parent visit. Real re-execution over synthetic chains is therefore worse than
the 2/2/1 witness, not equal to it. The finding and the §3 exit gate are
correct; the numbers should be labelled a lower bound, and one synthetic-rule
shape added to the three witnesses.

### M11 — `TargetRefusalError` silently changes the refusal type of a shipped reader

**Severity:** medium — public behaviour change, currently unrecorded.

**References:** `DESIGN.md:452-476`; `TODO.md:242-249`;
`src/lexic/api/json_tokenizer.py:144,194,255,298,305,333,356,360,406,419`;
`src/lexic/exceptions.py:40-85`.

Every tokenizer-reader refusal today is `UnsupportedConstructError`. After §7,
the semantic ones become `TargetRefusalError(LexicError)` — a SIBLING, not a
subclass, so `except UnsupportedConstructError` around `read`/`read_from_path`
stops catching them. Pre-0.1 that is allowed, but it should be a recorded
ruling with a §13 pinned row, not a consequence of the vocabulary table.

### M12 — Tokenizer-index canonicality is enforced by validation while equality and hash stay order-blind

**Severity:** medium — the exact failure mode `IrMap.from_table` exists to
prevent.

**References:** `DESIGN.md:806-820`; `TODO.md:603-617`;
`src/lexic/ir/action/mapping.py:100-120,169-187,218-234`;
`src/lexic/ir/text/tokenizer.py:271-317`.

`IrMapping.__eq__` compares `_table` and `__hash__` hashes a frozenset of its
items (`mapping.py:169-187`) — both order-independent. `IrMap.from_table`
sorts precisely because "a wrongly-ordered map re-encodes to itself" and the
export fixpoint cannot catch it (`mapping.py:220-227`). The three tokenizer
index roles deliberately skip that sort. So canonical id/rank order becomes an
invariant that equality cannot detect the violation of, enforceable only at
construction. The plan should state (a) which base the roles subclass —
`IrMapping` gives duplicate refusal without the sort (`mapping.py:100-120`),
which is the natural answer and preserves the `_indexed` refusal
`context.md:365-369` insists on — and (b) that canonical order is a
construction-time validated invariant with a §13 row pinning the
noncanonical-input path.

### M13 — `split_model`'s `IrNamedTuple` bound is a §9 entry condition, not a bullet

**Severity:** medium — sequencing.

**References:** `src/lexic/parsing/parallel/orchestrate.py:574-581`;
`TODO.md:738-739`; `DESIGN.md:686-704`.

`split_model[M: IrNamedTuple]` constrains every MT result today. `IrTokenizer`
satisfies it; a recursive Python `dict`/`list` product does not. §9 lists the
lift as one bullet among twenty. It is a precondition for every other §9
bullet and should be stated as the phase's entry condition.

### M14 — `AGENTS.md` does not exist, and the doc-drift test path in the plan is wrong

**Severity:** medium — two instructions Terra cannot follow as written.

**References:** `TODO.md:61-64` and `TODO.md:843-844` (both name
`AGENTS.md`); no `AGENTS.md` exists at the repository root;
`tests/integration/lexic/invariants/test_doc_drift.py:1,27,97` (the guard
reads `CLAUDE.md` only) versus `TODO.md:61-64` and `CLAUDE.md:123` which both
cite `tests/integration/test_doc_drift.py`.

The per-phase package-map rule is the right mechanism; it names a file that is
not there and a test at a path that is not there.

### M15 — Only the §7 timed row carries a stop factor

**Severity:** medium — the §5 early-warning gate has no threshold.

**References:** `TODO.md:497-499` (§5 timed direct-IR probe),
`TODO.md:655-661` (§7 3x stop factor); `reports/REVIEW_7.md:105-123`.

Pass 7 finding 3 asked for a timed row at §5 AND §7 so an architectural miss
surfaces before §10 deletes the fallback. §5 got the probe but no threshold, so
a §5 result an order of magnitude off budget does not block §6. Give §5 a
recorded stop factor or state that it is diagnostic only and §7 is the sole
early gate.

### M16 — The corrected GC probe is order-unbalanced at its default round count

**Severity:** medium — small, and it is the probe whose whole purpose was
removing an order confound.

**References:** `proto/carrier_gc_cost.py:107-108,160-161`;
`reports/PROTOTYPE_6.md:80-99`.

`order = (True, False) if number % 2 else (False, True)` with `--rounds`
defaulting to 7 gives four enabled-first pairs and three disabled-first. The
per-pair median mitigates it, but the fix for an order confound should require
an even round count; add the validation to `_validate_options`.

## Verified strengths

Checked against source in this session and confirmed sound:

- The exception vocabulary is coherent and the collision is real:
  `LexicError` / `UnsupportedConstructError` / `IrKeyError` /
  `FieldValidationError` are exactly as `DESIGN.md:452-476` assumes
  (`src/lexic/exceptions.py:40-85`), and `compile/verdict.py:27` genuinely owns
  the bare name `Verdict`, so `SemanticVerdict` is a necessary spelling.
- `parsing.caches` exposes exactly `memo`/`adopt`/`track`/`release` with
  transitive adoption and weak-finalizer ownership
  (`src/lexic/parsing/caches.py:62-155`); the §3/§5 lifecycle bullets map onto
  the real protocol, and `CompiledGrammar` already drives it
  (`artifact.py:180`).
- `_MODEL_CACHE`/`_TOKEN_TABLES` (`parsing/products.py:183-237`) are tables
  and PDA state keyed by `(grammar, fold, tier)` identity, not a bound-product
  memo — the "`parsing.products` owns no second product memo" requirement is
  achievable without restructuring.
- `IrTokenizer`'s real surface is `name`/`encode`/`decode`/`ranks`/`pipeline`
  /`segmenter` with `from_vocab`/`from_merges`/`_build`
  (`ir/text/tokenizer.py:271-344`); the §7 three-index rework maps 1:1 onto it,
  and `IrMapping.from_table` (`mapping.py:100-120`) supplies duplicate refusal
  without `IrMap`'s sort, which is exactly the base the plan needs.
- `AUTO = 0`, `MIN_CHUNK = 2 * 1024`, and the worker policy are where the plan
  says (`parsing/parallel/policy.py:23-76`); the floor is not being moved.
- `parse_model` is PDA-first with Earley completion and carries `resolve`
  through both routes (`products.py:273-306`); `reduce` today takes no
  resolver (`artifact.py:311-342`), so adding it is additive.
- `shared_forest_refold.py` faithfully replicates the real push guard
  (`fold.py:485`), and the finding it reports — traversal-dependent fold
  counts over a DAG — is genuine and would be a nondeterministic duplicate-key
  refusal under a side-effecting ABI. The §3 exactly-once/per-occurrence exit
  gate is the right fix.
- `local_meaning_fold.py`'s cost claim is real: 2,414 root-rooted folds versus
  4 child-rooted on the 601-character witness, and the recursive `same_value`
  overflow near depth 1000 (`ambiguity.py:130-157`) is a real defect the §8
  iterative-comparator bullet correctly schedules.
- `regular_region_lowering.py --mode identity` genuinely proves what it prints:
  the recursive spec declines, native/GBNF/ABNF/EBNF capture identical rows,
  1/2/3 arity works, the full vocab region ends at the exact shell boundary,
  `{}` is valid, and three malformed shapes refuse — including agreement with
  `compile_ast(JSON_GRAMMAR).reduce(...)`, the generic engine product. That is
  a strong genericity result for the lowering GIVEN a region.
- `demand_selection.py` demonstrates the load-bearing claim of finding 10: one
  `parse_model` call per document, kept models built in place with certified
  spans, a static reachability proof that the extent variant reaches no
  model-building rule, and 2 models + 998 key records over 1,000 entries.
- The deletion discipline is complete and specific: §10 names every symbol,
  §14 re-verifies it, and `TODO.md:764-770` correctly converts the
  `stitch/model.py` question from an optional consolidation into a decision.
- Documentation coherence is otherwise good: the package-map-per-phase rule,
  the `.wiki/log.md` entry, and the doc-drift-green-throughout requirement all
  exist (`TODO.md:61-64`, `TODO.md:836-845`).

## Decisions and prototypes still required before source implementation

1. **B1** — split the ambiguity ruling into relation and scope; rule the scope
   explicitly as a language change; fix the §8 self-contradiction; state how a
   child-rooted fold selects a contextual completion range.
2. **B2** — schedule the per-occurrence value-string recognizer consult with an
   owner and a gate, or re-derive the `<1.000 s` regime without the `ops` row.
3. **B3** — state and implement the full regular-region proof (arm
   non-ambiguity, boundary determinism); add the acyclic-but-ambiguous decline
   witness; decide whether the possessive `build_recognizer` lowering is reused.
4. **H4** — assign an owner for region derivation and require a non-JSON
   witness before §7's gated task.
5. **H5** — re-pin the overload prototype with declaration-only morphisms, or
   annotate `run` as prototype-only.
6. **H6** — name `MapShape.for_entry`'s successor owner in §6 and record the
   public-export removal.
7. **H7** — re-measure `capture` versus `ops` in-process with a control, or
   mark 1.40x provisional.
8. **H8** — restate the carrier budget with the collector enabled everywhere it
   appears.
9. **H9** — add the §6 zero-ambiguity-point gate for raw-key routing and state
   the caller-resolver rule.
10. **M10-M16** — each is a bounded plan edit with a recommended shape in its
    finding; accept, amend, or reject per item.

No finding reopens the product architecture, the deletion discipline, the
cache/lifecycle design, the flat-ABI shape, or any decision `LEDGER.md`
records as user-ruled.

## Verdict

**NO-GO for beginning source implementation as scheduled.**

Conditional GO for **§2 alone** — the declarative signature/schema vocabulary
and the exception vocabulary are verified against real source, carry no
dependency on B1-B3, and were already approved by passes 4, 5, and 7.

**§3 stays closed** until B1 is ruled: its exit gates alternate isolation and
shared-forest fold discipline, both of which are governed by the ambiguity
scope decision, and §8's bullets are currently mutually unsatisfiable.

**§7 stays closed** until B2 and B3 are ruled: its gate quantity depends on an
unscheduled mechanism and its gated task depends on an under-specified proof.

H5, H6, H7, H8, H9 and M10-M16 are editing-pass work and do not independently
gate §2.

## Re-entry condition

Fold the B1-B3 rulings and the H4-H9 edits into
`goal.md`/`DESIGN.md`/`TODO.md`/`LEDGER.md`, restate the GC-enabled carrier
budget, and re-measure the interpreted-versus-capture ratio in-process. B1
requires a user ruling because it changes what Lexic accepts; B2 and B3 can be
closed by the coordinator with a scheduled task and a stated proof. No further
prototype is needed for the medium findings.
