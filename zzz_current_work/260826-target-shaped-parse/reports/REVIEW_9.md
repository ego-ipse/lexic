# Plan review — target-shaped parsing, pass 9

**Reviewed:** 2026-08-29, against branch `targeter` at `71d0c429`.
`git diff --stat 0faa7289 -- src` is empty, so every production citation below
is the exact release baseline the packet claims. Read in full: `INDEX.md`,
`context.md`, `goal.md`, `DESIGN.md`, `TODO.md`, `LEDGER.md`,
`reports/REVIEW_8.md`, `reports/PROTOTYPE_7.md`, `reports/PROTOTYPE_8.md`, and
every prototype those two reports cite — `local_meaning_fold.py`,
`root_meaning_incremental.py`, `persistent_meaning.py`,
`regular_region_proof.py`, `regular_region_lowering.py`,
`reducer_free_surface.py`, `route_continuation.py`, `shared_forest_refold.py`,
`carrier_gc_cost.py`, `baseline_rss.py`, plus `product_types.py` and
`demand_selection.py` where a current claim depends on them. Every
architectural claim cited was checked by opening the named production file in
this session. No benchmark was run, no source or prototype was edited, no agent
was dispatched, and this report is the only file created.

---

## Verdict

**GO.**

**Exact scope of this GO:** broad source implementation may begin at `TODO.md`
§2 and proceed through the queue as written. This is *not* a statement that
every later phase is proven. §4, §5, §7, §9, §11, and §12 keep their own hard
exits, and five of the findings below must be ruled before the phase that
consumes them opens (named per finding). None of them blocks §2, and none
reopens the product architecture, the deletion discipline, the cache/lifecycle
design, the flat-ABI shape, or a user-ruled decision in `LEDGER.md`.

**There are no blockers.** REVIEW_8's B1 and B2 are fully closed; B3 is
substantively closed but its stated condition set still admits two unsound
shapes (H1). All nine H-findings and all seven M-findings from pass 8 are
addressed; three left residue, tracked below.

---

## REVIEW_8 closure audit

| Pass-8 finding | State | Evidence checked this session |
|---|---|---|
| **B1** ambiguity relation vs. scope | **Closed, and stronger than required** | Child-local is rejected in `goal.md:216-224`, `DESIGN.md:630-647`, `TODO.md:739`; `local_meaning_fold.py` is retained only as the rejected counterexample. Critically, `another_meaning` is already called with the *accepting root handle* (`products.py:147-150`, `accept_handle`), so `ambiguity.py:188-206` is root-value today. The ancestor-cone replay is therefore a pure cost win with **no language change at all** — the §8 self-contradiction pass 8 found is gone because the generated-model product keeps today's semantics *and* gets the locality win. Residual: islands (H3). |
| **B2** unscheduled value-string consult | **Closed** | `TODO.md:407-416` schedules it in `pda/compiler/program/specialize.py` (the module exists) with its own separate generated-model and token-segmented non-regression gate; `DESIGN.md:578-590` and `goal.md:34-47` label the 0.351784 s row conditional on it. |
| **B3** regular proof weaker than stated | **Substantively closed; two shapes still admit** | `regular_region_proof.py` is a real FIRST/FOLLOW proof, not `build_recognizer` alone; `_prove` (`regular_region_lowering.py:202-216`) runs both; the acyclic-but-ambiguous decline witness *executes* (`:420-432`). But the condition set is incomplete — see **H1**. |
| **H4** region derivation owner | **Closed** | `_derive_region` composes `RegionSignature × RegionDemand` (`regular_region_lowering.py:81-100`); owner pinned at `compile/product/compose.py` (`DESIGN.md:596-597`, `TODO.md:455-459`); non-JSON catalog witness executes (`:499-513`) and `TODO.md:614-616` requires it before §7 opens. |
| **H5** morphisms modelled as executors | **Closed** | `run` is gone from both public classes; only `_BoundProduct` holds a callable (`reducer_free_surface.py:33-46, 48-51`). Residual: the *dispatch* shape is still unrecorded — **M7**. |
| **H6** `MapShape` successor | **Closed** | `compile/product/shape.py` named in `DESIGN.md:596-598, 941-943`, `TODO.md:455-459, 889-896`, `context.md:288`; the public-export removal is recorded. `MapShape` is confirmed exported at `compile/__init__.py:33,109` and has no other `src` consumer. |
| **H7** cross-process 1.40x | **Closed** | `_compare` (`regular_region_lowering.py:586-657`) alternates in one process, takes minima, and carries two same-body controls; 1.428162x with a 0.001129 s floor. Minor: both controls always run 3rd/4th in a round, so they are not order-matched to the comparands' slots — the min-of-rounds mitigates it. |
| **H8** GC-disabled budget quoted as a budget | **Closed in the four live documents** | `goal.md:451`, `DESIGN.md:871`, `context.md:374`, `TODO.md:678` all annotate 0.138739 s as GC-disabled provenance. `LEDGER.md:184` still states it unannotated, but inside the superseded *PRIOR SESSION* block. |
| **H9** raw route consumes `resolve=` | **Closed as a scheduled gate** | `goal.md:92-95`, `DESIGN.md:384-388`, `TODO.md:596-600` all state routing never touches `resolve=`; `route_continuation.py:228-248` proves raw/decoded distinctness. The zero-arm-choice property is asserted by construction in the prototype, so the §6 gate is the actual proof — an implementation-phase obligation, correctly guarded. |
| **M10** shared-forest witness under-models | **Closed** | `shared_forest_refold.py:147-158` adds the distinct `finished` set and the transparent `__rep_1` witness; `PROTOTYPE_7.md` §6 labels 2/2/1 a lower bound. Confirmed against `fold.py:495-500`, which returns without writing `results` for synthetic rules. |
| **M11** `TargetRefusalError` behaviour change | **Closed** | Recorded ruling at `DESIGN.md:488-491`, `TODO.md:242-249`; §13 pin at `TODO.md:1055-1058`. `exceptions.py` hierarchy and `compile/verdict.py:27`'s `Verdict` collision verified. |
| **M12** index canonicality vs. order-blind equality | **Closed** | `IrMapping.from_table` (`mapping.py:99-119`) gives duplicate refusal without `IrMap`'s repr sort (`:194-227`); `__eq__`/`__hash__` are order-blind (`:169-187`); `DESIGN.md:850-862` and `TODO.md:648-670` name the base, the construction-time validation, and the `tuple(items())`/repr/notation/payload/generated-module pins. |
| **M13** `split_model` bound | **Closed** | `TODO.md:800-803` states it as §9's entry condition; `orchestrate.py:574` confirms `split_model[M: IrNamedTuple]`. |
| **M14** `AGENTS.md` / doc-drift path | **Closed** | `AGENTS.md` exists as a symlink to `CLAUDE.md`; the plan no longer names it, and `TODO.md:76` now cites the correct `tests/integration/lexic/invariants/test_doc_drift.py`. (`CLAUDE.md:123` still cites the old path — a repo file, outside this packet.) |
| **M15** §5 stop factor | **Closed** | `TODO.md:534-537`: 3x early-warning bound. |
| **M16** odd GC rounds | **Closed** | `carrier_gc_cost.py:41-50` refuses an odd or <2 round count. |

---

## High findings

### H1 — The regular-region proof admits two shapes whose possessive lowering refuses strings the grammar derives, and the same proof gates §4's `value_str` consult

**Severity:** high — correctness and language preservation on `CompiledGrammar.parse`, not only on the §7 target.

**References:** `proto/regular_region_proof.py:131-145` (`_overlapping_arms`),
`:183-212` (`_prove_arm`, especially the two guards at `:204-206`);
`reports/PROTOTYPE_7.md` §2 (the stated condition list);
`DESIGN.md:594-606`; `TODO.md:407-416` (§4 consult), `TODO.md:688-711` (§7
region). Production lowering:
`src/lexic/parsing/pda/core/scanner.py:174-195` (`_item_source` — every item
`(?:atom){lo,hi}+`), `:198-200` (`_arm_source` — every arm `(?>…)`),
`:118-134` (`Recognizer.__init__` — arms joined `|` in authored order).

The proof is real and mostly careful: FOLLOW is threaded into referenced rule
bodies (`_prove_atom`'s `atom_follow`), so the `lead ::= "a"* / tail ::= "a"`
witness genuinely declines. Two shapes still slip through.

**Shape 1 — a nullable rule referenced at `{1,1}`.** `_prove_arm` computes
`repeats = hi is None or hi > 1` and `variable = hi is None or hi != lo`. For an
item with `lo == hi == 1` both are `False`, so *neither* guard fires even when
`atom.nullable` is `True`. Concretely:

```
entry ::= a a2
a     ::= "x" |
a2    ::= "x"
```

`_overlapping_arms(a)` passes (FIRST sets `{x}` and `∅` are disjoint; only one
nullable arm). `_prove_arm([a, a2])` computes `after = {x}` for `a`, sees
`variable == False`, skips the overlap test, and `_prove_atom(a, follow={x})`
proves each arm in isolation. The region proves. The lowering is
`(?>(?>x)|(?>))(?>x)`, which on input `"x"` commits `a` to the character and
then fails `a2` — a string the grammar derives, refused.

**Shape 2 — a nullable arm ordered before another arm.** `_overlapping_arms`
rejects two nullable arms and overlapping FIRST sets, but an atomic group
commits to the *first matching* alternative, and a nullable arm always matches.
`alt ::= "a"? | "b"` under a continuation `"c"` proves (union FIRST `{a,b}`
disjoint from `{c}`), and lowers to `(?>(?>(?:a){0,1}+)|(?>b))(?>c)`, which
takes the empty match on input `"bc"` and refuses.

Neither shape is exotic: canonicalisation drops empty-literal *items*
(`ir/grammar/transform/canonical.py`, rewrite 8b) but does not convert
`(x | ε)` into `x?`, so an arm-level-nullable rule referenced once survives into
canonical form. The shipped JSON formulations happen to be immune — every
nullable rule in `json.gbnf` is `ws`, spelled `( … )*`, whose variable
quantifier *does* trigger the overlap guard — which is exactly why the identity
witness does not catch this.

**Consequence.** `DESIGN.md:582-584` binds §4's `value_str` recognizer consult
to *this* proof ("the same language-preserving regular proof as an authoritative
region, not the fail-soft scanner licence"). An unsound admission therefore
narrows `CompiledGrammar.parse`'s accepted language at §4 — the phase whose exit
gate measures *performance*, not language — and §7's identity differential is a
witness set, not a proof, so it will not necessarily catch it either.

**Required (smallest correction):**

1. In the stated condition set (`PROTOTYPE_7.md` §2, `DESIGN.md:594-600`,
   `TODO.md:688-711`) and in `parsing/product/regular.py`, replace "variable
   repetition cannot consume a character owned by its continuation" with
   "**a variable *or nullable* atom** cannot consume a character owned by its
   continuation" — mechanically, `(variable or atom.nullable) and
   atom.first.overlaps(after)` declines.
2. Add the ordered-arm condition: **a nullable arm must be last**. "At most one
   nullable arm" is insufficient under ordered atomic alternation.
3. Add both minimal shapes above to `regular_region_lowering.py --mode
   identity` as decline witnesses beside the existing `AMBIGUOUS_SPEC`, so the
   §4 and §7 gates test the conditions rather than the corpus.

### H2 — The sequential-decline `<1.000 s` gate is not reachable from the packet's own numbers, and contradicts "the `<1.000 s` envelope is not contingent on the capturing lowering"

**Severity:** high — a gate quantity whose own evidence predicts it fires, discovered at §12 after eleven phases of work.

**References:** `goal.md:414-421` (the gate, and "when route anchors decline and
AUTO runs sequentially, gate the sequential row against the same envelope — the
decline case is not exempt"); `DESIGN.md:604-606` ("The ~105x objective is
contingent on this further lowering; the `<1.000 s` envelope is not");
`TODO.md:995-999`; `reports/PROTOTYPE_7.md` §4 (0.246319 s capture vs
0.351784 s interpreted, **1.428162x**) and §6 (0.700274 s median **aggregate
process CPU** / 0.130779 s wall, eight workers, GC enabled);
`proto/carrier_gc_cost.py:53-60` (the carrier is `CaptureProgram`/`MergeProgram`
— capture-based, not the interpreted ABI).

Arithmetic the packet supplies about itself:

- the carrier row covers **only the two dominant regions** and already spends
  0.700274 s of aggregate process CPU, capture-based;
- a sequential run of that same work is bounded below by that aggregate minus
  parallel overhead — the packet gives no number below it;
- the interpreted route multiplies the region work by 1.428162x;
- `PROTOTYPE_7.md` §4 itself records that the interpreted row "omits PDA frames,
  transactions, driver work, the merge region, and the remaining document".

So the sequential interpreted row starts somewhere in the 0.6–1.0 s band for
the two regions alone, before the driver, frames, transactions, the remaining
document, bind/setup, pipeline/root validation, and record construction. The MT
row has real headroom (0.130779 s wall × 1.428 ≈ 0.19 s); the sequential-decline
row does not. `DESIGN.md:604-606`'s claim that the envelope is not contingent on
the capturing lowering is defensible for the engaged row and not defensible for
the row `goal.md:420-421` explicitly refuses to exempt.

**Consequence.** Either §12's decline row fails for a reason the packet already
predicted and chose not to act on, or the "not contingent" ruling silently means
"not contingent, for the MT row only". Both leave the coordinator arbitrating a
gate mid-§12 with the old path already deleted at §10.

**Required:** make one of the two explicit, in `goal.md`, `DESIGN.md`, and
`TODO.md` §12 together — either (a) state that the sequential-decline row's
`<1.000 s` gate is contingent on the §7 capturing lowering and gate it only
after §7 lands, or (b) demote the decline row to *reported with attribution*
and keep the gate on the engaged `cores=AUTO` row alone. Do not leave both
sentences standing.

### H3 — Island ambiguity is settled at the island's own accepting handle, so "the complete requested root value" has no stated meaning for a delegated span

**Severity:** high — §8's exit gate ("PDA, Earley, islands, and target projections agree") is unsatisfiable as written for the shape B1 was ruled on.

**References:** `src/lexic/parsing/pda/runtime/islands.py:212-238`
(`_settle_two_meanings` calls `another_meaning(kern, handle, …)` with the
*island's* packed accepting handle on the *island's own* kernel) versus
`src/lexic/parsing/products.py:147-150` (document root);
`goal.md:216-224` ("the complete requested root value … not by an isolated
child's value"); `DESIGN.md:634-638` ("PDA islands use this same route, so a
target has identical semantics whether a span was predictive or delegated");
`TODO.md:795-796` (§8 exit).

The dropping-parent counterexample that killed child-local scope is exactly the
island shape: an island sub-parse whose two derivations build different island
values, inside a parent occurrence that drops or projects the difference away,
is refused today by `islands.py:233-237` and would be *accepted* by the
document-root relation `goal.md` now declares definitive. The packet states the
relation as the document root and simultaneously requires islands to agree with
it, without noting that the island's kernel has no access to the enclosing
document derivation — it is a separate `Kernel` over a window.

**Required:** state the island scope explicitly, once, in `goal.md` and
`DESIGN.md` §Earley-and-islands, and reconcile `TODO.md:795-796`:

- if islands keep today's span-local relation (the conservative, no-behaviour-
  change reading), say so and scope §8's "agree" gate to *the same span*, not
  the document root; or
- if islands widen to the document root, name the mechanism that carries the
  island's competing meanings out to the coordinating parse and add it as a §8
  bullet.

Either is fine; leaving it unstated makes §8's exit gate a judgement call.

### H4 — The route continuation is specified only for a producer and consumer that are siblings in one sequence; nothing states what happens otherwise, and refusing contradicts proof obligation 2

**Severity:** high — genericity across formulations, and an unowned design decision at §3/§6.

**References:** `DESIGN.md:365-370` (`RouteContinuation` names "the following
consumer item/reference position"), `:389-408`;
`proto/route_continuation.py:104-120` (`pda_child` refuses when `position !=
continuation.consumer_position`), `:180` (`consumer_position =
refs.index("value")` — an index *within `member`'s one sequence*);
`TODO.md:300-306` (§3), `:596-600` (§6); `DESIGN.md:1019-1020` (obligation 2:
"Two formulations exposing the same semantic signature compile the same target
schema without rule-name or generated-class knowledge").

Every shipped witness is a sibling shape — `resources/ground_truth/json.gbnf`
and `json.abnf` both spell `member = string name-separator value`, and the
native `JSON_GRAMMAR` matches. A perfectly legal alternative formulation of the
same semantic signature does not:

```
member ::= string tail
tail   ::= name-separator value
```

Here the discriminator producer completes in `member`'s frame and the routed
reference lives in `tail`'s. `DESIGN.md:390-394`'s "dedicated parent-frame lane"
has no reader at that depth. The Earley half generalises naturally — the sparse
`(waiting code, route) -> successor code` table can select a route-specific
`tail` code, and contextual codes then carry it down — but the PDA half needs
route-specialised intervening clones, and the packet says neither. `compile
refuses otherwise` (`DESIGN.md:368-369`) covers only nullable and
multi-discriminator producers.

**Consequence.** The implementer either invents contextual route propagation
mid-§6, or binds only sibling formulations — which makes the tokenizer target
formulation-dependent and breaks obligation 2 on a shape the corpus does not
happen to contain. That is the "no privileged formulation" bar in
`CLAUDE.md`, applied to a formulation rather than a grammar.

**Required:** state one rule before §3 lowers `RouteContinuation` — either the
route is propagated into intervening contextual clones/codes (name it in
`DESIGN.md:389-408` and `TODO.md:300-306`), or binding refuses a non-sibling
placement with words and `goal.md` records that declared precondition. Add one
non-sibling witness to §3's "Run nested mapping witnesses through PDA, ordinary
Earley fallback, and island/delegate execution" bullet, which today only varies
*nesting of mappings*, not the producer/consumer distance.

### H5 — The §1 exit prototype puts Python callables in the operand tables at every completion, and three documents forbid exactly that

**Severity:** high — an unresolved contradiction the §3 implementer must arbitrate.

**References:** `proto/product_types.py:408-432` (`Decoder`, `Validator`,
`SequenceFinisher`, `MappingFinisher`, `RecordConstructor` are all
`Callable[...]`, held in `OperandTables`), `:974`
(`program.operands.decoders[0](text)`);
`DESIGN.md:330-332` ("Frequently completed **lexical** rules use specialized
closed operations, not a Python callable hidden in a record") versus
`DESIGN.md:1039-1043` (obligation 9: "a target-specific callback cannot appear
in a **frequently completed rule**"), `goal.md:157-159`, `context.md:451-452`;
`TODO.md:320-322` ("a frequent **lexical** completion").

Three of the four normative statements say *frequently completed rule*; one says
*lexical*; the prototype that `TODO.md:236-245` certifies as the §1 exit pins
the forbidden shape. On the standing witness a vocabulary entry's key decode
runs 151,669 times through `decoders[i](text)` — a target-supplied Python call
per entry, in a rule that is structural, not lexical.

**Consequence.** At §3 the implementer must decide whether `DecodeOp`,
`InsertMappingOp`, and `RecordOp` operands index engine-owned closed operations
selected by int code, or a target-supplied callable table. The packet answers
both ways in different places, and the answer determines the flat-ABI shape that
§4's zero-tax gate then measures — i.e. it is not a decision that can be
deferred and revisited.

**Required:** state the boundary once, in `DESIGN.md` §Construction algebra, and
make `product_types.py`'s `OperandTables` record match it. The defensible
boundary is: the signature's declared scalar decodes and the sequence/mapping
begin/append/insert/finish operations are engine-owned closed ops selected by a
plain int; target-supplied callables are admitted only at collection *finish*,
root finalisation, and meaning comparison. Whatever boundary is chosen, remove
the `lexical`/`frequently completed` split so obligation 9 and `TODO.md:320-322`
say the same thing.

---

## Medium findings

### M6 — `parsing/product/` "imports only `lexic.ir`" is false for `regular.py`, and the alternative is a second possessive lowering

**References:** `DESIGN.md:919` ("The package imports only `lexic.ir`.");
`proto/regular_region_proof.py:19` (`from lexic.parsing.pda.core.charsets import
CharSet` — the proof is written in `CharSet` throughout);
`proto/regular_region_lowering.py:21-26` (`build_recognizer`, `compile_source`,
`Pattern`, `Recognizer` from `pda/core/scanner.py`);
`src/lexic/parsing/pda/core/scanner.py:38-41` (declares itself a leaf importing
only `lexic.ir` and `charsets`).

`regular.py` cannot state a first-set proof without `CharSet`, and §7's
capturing lowering cannot produce patterns without `compile_source`/
`Recognizer.pats`. The import is legal — `pda/core/` is a leaf and does not
import back — but the constraint as written is false, and an implementer who
honours it literally will re-derive `CharSet` and the possessive lowering inside
`parsing/product/`. That is a twin mechanism on a de-duplication effort, the
exact failure `feedback_consolidation_never_adds_a_twin` records.

**Required:** restate `DESIGN.md:919` as "imports `lexic.ir` plus the
`parsing/pda/core/` leaves (`charsets`, `scanner`)", and add one `TODO.md` §3
sentence that `regular.py` consumes `build_recognizer`/`compile_source` rather
than re-lowering. `TODO.md:318-319`'s leaf rule is already correct and needs no
change.

### M7 — The only typeable morphism-dispatch shape exists solely in a prototype, and `DESIGN.md`'s "the only cache" phrasing describes something that cannot be one object

**References:** `proto/product_types.py:635-642` (`ReductionMorphism[Result]` is
a **Protocol** with a private `_bind`), `:670-722` (`BindingRegistry[
Declaration, Result]`), `:858`, `:1006`, `:1126` (three *separate* module-level
registries, one per declaration kind);
`proto/reducer_free_surface.py:33-46` (morphisms with **no** `_bind`, a phantom
`Result` parameter);
`DESIGN.md:255-262` ("recursively immutable public signature/schema/algebra data
only; it contains no cache, lock, mutable factory, executor, or entry
dictionary"), `:269-274` ("This registry is the only cache …");
`TODO.md:483-495`. Neither `_bind` nor `Protocol` appears anywhere in
`context.md`, `goal.md`, `DESIGN.md`, or `TODO.md`.

A single heterogeneous `dict[key, BoundProduct[?]]` cannot yield
`BoundProduct[Result]` without a cast, which §1's own constraint forbids; and
`isinstance(into, ReductionMorphism)` dispatch is the shape review 3 blocked.
The one proved answer is the pair above — a private `_bind` on the declaration
plus one homogeneous registry per declaration kind. That is compatible with
"no mutable state on the declaration" but not with "*the* registry" as a single
object, and `reducer_free_surface.py` — the artefact `PROTOTYPE_7.md` §5 cites
as pinning the surface — omits `_bind` entirely.

**Required:** record the `_bind` protocol and the per-declaration-kind registry
in `DESIGN.md` §Codomain and `TODO.md` §5, and restate "the only cache" as "no
second cache of the same binding exists" rather than "one registry object".
Add `_bind` to `reducer_free_surface.py`'s classes, or annotate that its
morphisms are the data half only.

### M8 — §4 rewrites the generated-module authoring vocabulary without running the generated-twin gate

**References:** `TODO.md:390-392` (§4 migrates `foldkit.seq`/`model_fold` "plus
every notation/generated-self-grammar caller");
`reports/PROTOTYPE_8.md` §4 (`ModelBody`/`model_fold` consumers include notation
parse and the generated self-grammar); `src/lexic/compile/foldkit.py:36-49, 60,
123` (`ALT = RuleFold(...)`, `IrNamed`, `FOLD_SYMBOLS` — the no-`eval` symbol
boundary, which §4's `RuleFold` deletion forces to change);
`uv run python tools/check_generated.py` appears only at `TODO.md:715` (§7) and
`:1089` (§13).

§4 is the phase that changes the authored-fold vocabulary the twin modules and
`selfgrammar.py` are written in. The twin-clean gate first runs three phases
later.

**Required:** add `uv run python tools/check_generated.py` to §4's exit beside
the existing suite + pyright ledger bullet. While there, name `IrNamed`,
`FOLD_SYMBOLS`, `first_rest`, `absent_tail`, `ABSENT`, `FIRST_REST`, and
`DECODE_INT` in the §4/§10 foldkit bullets — only `seq` and `model_fold` are
currently named, and `IrNamed` is the mechanism that keeps the notation
symbol channel `eval`-free.

### M9 — §13 has no owner for the §5 frozen goldens, and the three reduce-differential property files lose their oracle at §10

**References:** `TODO.md:520-522` (§5 produces "frozen semantic and refusal
goldens … for Luna to port after the old oracle is gone"); `TODO.md:1018-1102`
(§13 — no bullet consumes them); `tests/property/lexic/test_reduce_differential.py`,
`test_reduce_differential_abnf.py`, `test_reduce_differential_ebnf.py`,
`reduce_differential_helpers.py`; `context.md:467-473` lists them as the primary
reduction-parity oracles.

Those three files compare the model+fold route against itself; after §10 deletes
`ReduceFold` their oracle does not exist, and their value — *fresh* Hypothesis
inputs — cannot be reconstructed from fixed goldens. §13's generic "port
assertions … delete only tests whose exact symbol disappeared" bullet does not
say which of the two happens here, and the default-IR product is the codomain
with the strictest parity claim in `goal.md:372-374`.

**Required:** one §13 bullet naming those four files and the §5 goldens
explicitly: state whether each is ported to the frozen corpora, re-pointed at a
property invariant that survives deletion (round-trip, refusal type/message,
contribution order), or deleted with the behaviour re-pinned elsewhere.

### M10 — The alternate-meaning dependency index is document-sized and appears in no cost or RSS account

**References:** `proto/root_meaning_incremental.py:186-203` (`_graph` walks the
entire default derivation to build `parents` and `owners` before any alternate
is evaluated); `DESIGN.md:296-302, 649-658` and `goal.md:180-192` (which say the
document-sized *memo* is not copied, but never that a second document-sized
structure is built); `TODO.md:750-756` (§8 requires the predecessor-key index
but does not size it); `TODO.md:990-994` (§12's RSS rows contain no ambiguous
scenario); `reports/PROTOTYPE_8.md` §2 (the RSS matrix is three unambiguous
tokenizer rows).

An ambiguous parse now allocates two structures proportional to the default
derivation — the completed-handle meaning memo and the predecessor/parent index
— where today's `another_meaning` allocates one `FastTree` plus one `results`
dict per flipped point. The new shape is almost certainly a net win; the point
is that the packet's cost account never names it, and §12's RSS gate has no row
that would observe it.

**Required:** one sentence in `DESIGN.md` stating that the dependency index is
proportional to the default derivation and is built once, only on a parse with a
real arm choice; and either one ambiguous-input RSS row in §12 or an explicit
statement that ambiguity is out of the RSS matrix.

---

## Final-product and coherence assessment

**Genericity.** Clean. `grammars/json.py` owns the JSON signature,
`api/json_tokenizer.py` owns the tokenizer schema, generic parsing receives int
tables only, and §14 re-verifies. The non-JSON catalog witness
(`regular_region_lowering.py:499-513`) and §6's "derive at least one non-JSON
repeated region … before §7" bullet answer the pass-8 privilege concern. The one
residual genericity risk is **H4** — a formulation-shape dependency, not a
grammar-name dependency, and the packet does not currently see it.

**No twin route.** §10 is specific and exhaustive, §14 re-verifies it, the
`stitch/model.py` question is *decided* rather than left open (`TODO.md:854-858`),
and the rejected `carrier.py` is named as never-to-be-reconstructed in three
documents. `ReduceFold`'s retention through the §9 exit is correctly framed as
an uncommitted oracle with no production caller. `MapShape`/`Template`/`spanify`
are confirmed to have no `src` consumer besides the `compile` façade, so the
deletion is genuinely contained.

**Parse non-regression.** Stated identically in `goal.md`, `DESIGN.md`,
`TODO.md`, and `LEDGER.md`, including the bugfix carve-out requiring explicit
user approval after isolated attribution. §4's gate compares opcode/capture
streams as well as timing, and the value-string consult (B2's closure) carries
its own separate row so it cannot trade parse speed for target speed. This is
the strongest part of the packet. **H1** is the one thing that can defeat it —
not by cost, but by silently narrowing what `parse` accepts.

**Measurement honesty.** Good, with the single exception in **H2**. Every
headline number now carries its GC state, the interpreted/capture ratio is
in-process with two controls, the carrier headline is collector-enabled, the
`<0.100 s` Python figure is correctly demoted to a pursued objective against a
0.084940 s `json.loads` frontier with the multiplier as the gate quantity, the
105x objective is scoped to the Qwen tokenizer scenario and made contingent on
the §7 lowering, RSS is scenario-matched with the warm row labelled a monotonic
high-water, and §12 re-measures `0faa7289` in the same alternating session
rather than dividing into quoted constants. The one-MT-benchmark-at-a-time rule
appears in the working protocol, §12, and `PROTOTYPE_7.md`'s verification note.

**Target-aware MT and the 2 KiB floor.** `MIN_CHUNK = 2 * 1024` and `AUTO = 0`
verified at `parallel/policy.py:23-26`; §9 keeps `SplitPlan`, certification,
policy, replicas, and the floor, and §12 forbids raising it or suppressing an
eligible row. Route anchors propose cuts and are certified through the same
composed product before submission, with decline-to-sequential and no all-mark
pre-pass. Worker-owned recognizers and the free-threaded refcount extension to
the flat operand/route tables are correctly named as a `replicas.py`-shaped
problem with a §12 ladder that must attribute loss to a *named* object.

**Typing.** No `Any`, `object`, `eval`, `exec`, or suppression is introduced by
the design as written; `Carry` stays typed through frames, tables, fragments,
and the bound runner. The one place the public API is not yet typeable *as
written in the plan documents* is the morphism dispatch — **M7** — which the
prototype solves and the plan does not record.

**Document coherence.** `INDEX.md`, `context.md`, `goal.md`, `DESIGN.md`,
`TODO.md`, and `LEDGER.md` agree on scope, ownership, phases, gates, deletions,
and numbers, with two exceptions already listed (`DESIGN.md:919` in M6, and the
`DESIGN.md:604-606` / `goal.md:420-421` tension in H2) plus one stale
unannotated `0.138739 s` at `LEDGER.md:184` inside a superseded prior-session
block.

---

## Strengths worth preserving

- **The B1 correction is better than pass 8 asked for.** `another_meaning` is
  already called with the accepting root handle (`products.py:147-150`), so the
  ancestor-cone replay reproduces today's verdict exactly and the generated-model
  product keeps its semantics *and* gets the locality win. Separately, replacing
  the variant-model relation with the reduced-root-value relation on `reduce` is
  a strict **widening** — two derivations with equal variant models always fold
  to equal values, because the fold is a function of the model — so the packet's
  "no deliberate narrowing" claim holds by construction, not by inspection.
- **`persistent_meaning.py` closes a gap nobody asked for.** Catching that
  dirty-cone *fold-body count* does not price eager-container equality or
  materialisation, and then refusing to transfer the sequence result to
  map/IR/tokenizer products by analogy, is the single most disciplined move in
  this packet.
- **The proof/lowering separation is right.** `prove_region` is a genuine
  FIRST/FOLLOW analysis that threads FOLLOW into referenced rule bodies, and the
  acyclic-but-ambiguous decline witness executes rather than being asserted.
  H1 is a gap in the condition list, not in the approach.
- **`shared_forest_refold.py`'s value-once/effect-per-occurrence gate.** A
  traversal-dependent fold count over a DAG would have produced nondeterministic
  duplicate-key refusals under a side-effecting ABI; catching it before source
  work is exactly what the prototype phase is for.
- **The deletion, documentation, and test-ownership discipline.** §10 names
  symbols not areas; §11 is a general pass, not a search-and-replace; §13 names
  the empty-edge rulings, the binding-registry lifecycle guards, the extent row,
  and the freethreaded fork-safety regression; §14 re-verifies each. The
  per-phase package-map rule keeps doc-drift green throughout rather than at the
  end.
- **The measurement contract.** Scenario-matched RSS with an explicit
  "never compare warm against the cold ceiling" rule, CPU-per-byte as a gate
  quantity beside wall so an MT row cannot pass by burning cores, and the
  refusal to use `tools/benchmark/compare.py` unchanged because its cohort
  preparation performs real parses.

---

## Gates that remain binding

Unchanged and non-negotiable for this effort:

1. **§3 exit** — one tiny sequence/map target through real PDA, Earley, and
   island/delegate paths; recognition-time routing; every physical completion
   table verified with `type(value) is int`; rollback and fresh-alternate
   isolation; cache release; value-once-per-shared-node with per-occurrence
   effects across all four witness shapes.
2. **§4 exit** — generated-model and token-segmented parse rows gated
   independently across PDA, Earley, islands, ambiguity, and eligible MT shapes,
   by alternating timing *and* opcode/capture stream comparison. Any regression
   closes the gate; a bugfix-related exception needs the user's explicit prior
   approval. The `value_str` consult carries its own row.
3. **§5 exit** — broad differential against `_ReduceEntry.variant.parse +
   ReduceFold.reduce` through `guarded.sh`, frozen goldens recorded, and the 3x
   direct-IR early-warning stop factor.
4. **§6** — zero route-created arm-choice ambiguity points on the toy raw
   selection and every JSON formulation; every empty-edge ruling implemented;
   one non-JSON derived region before §7 opens.
5. **§7 exit** — payload/notation/generated-twin fixpoint gate, the timed
   resident tokenizer row with its 3x stop factor, and the proved-regular
   lowering identical to the generic product on valid/empty/malformed/boundary
   cases across all four formulations, declining on loss of proof.
6. **§8/§9** — re-run the §5 property differential at both exits; the ambiguity
   verdict must equal a complete root refold on every witness, with the
   dropping-parent case accepted.
7. **§9** — `split_model`'s `IrNamedTuple` bound lifted as the phase's entry
   condition; every worker starts and ends in a compiler-proved fragment state;
   only the coordinator finalises.
8. **§10** — mandatory. "Unused but retained" is failure.
9. **§12** — one benchmark process at a time, alternating whole processes with a
   byte-identical control, `0faa7289` re-measured in the same session,
   scenario-matched RSS, CPU-per-byte in every row.
10. **§13/§14** — `tools/run_checks.sh` exits 0; coordinator reviews the full
    diff; no `Co-Authored-By`; the coordinator alone commits.

Add to these, before the phase that consumes each: **H1** before §4's
`specialize.py` task, **H3**, **H4**, **H5**, and **M6** before §3 opens,
**H2** before §7's timed exit, **M7** before §5's registry, **M8** before §4's
exit, **M9** before §13, and **M10** at any point before §12.

§2 is unblocked by all of them and may start now.
