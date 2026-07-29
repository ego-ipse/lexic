# Design Decisions

**When to load:** understanding why something is designed a specific way; before reversing or changing a design choice; after landing a non-obvious decision (add an entry).

Significant choices with reasoning. Add an entry whenever a non-obvious decision is made or reversed.

---

## Ambiguity is a question about VALUES, and it is asked in one place

**Two derivations that build the same value are not an ambiguity.** A grammar
routinely derives one text several ways without meaning anything by it: an
inline group carves a digit two ways and folds identically, and two adjacent
nullable slots split a gap two ways to the same end. Refusing those refuses
valid input for a difference no consumer can observe — under the `plain` target,
where a fold builds dicts, it is not even hypothetical.

**Nor is it asked by counting.** The check compares the values built, not the
number of derivations found. `repr()` is not the value either: two dicts of one
content in different key orders are one value and two spellings.

**`same_value` is type-aware and structural**, because bare `==` is wrong in
both directions. It calls `IrStr("a")` and `"a"` equal — the IR wraps `str` and
`int`, so a leaf and its text compare equal while a consumer reading the field
sees two different things. And it calls a float NaN different from itself, and
two instances of any class that never defined `__eq__` different from each
other. A type that declined to define equality has declined to answer, and
"cannot tell" reads as no observable difference, hence no refusal.

**It lives in `parsing/earley/kernel/forest/ambiguity.py`** so the island
sub-parse, the reduce path and the Earley model completion decide it once and
the same way. The reduce path used to count derivations, and the cost was the
whole EBNF fallback: that self-grammar has adjacent nullable `ws` slots, so
every whitespace-carrying EBNF file derived at least two ways, reduced to
exactly one value, and was refused. The model completion used to not ask at
all — it took the first derivation, and the PDA took a different "first", so
an ambiguous arm choice was answered two ways in silence; `first_meaning`
(`earley/engine.py`) now asks on that path too.

**The opt-out is a resolver, not a flag.** `another_meaning` returns the
differing derivation itself — the witness — so a caller opting out of the
default refusal supplies a deterministic `Resolver` that is handed both
derivations and picks; how it picks is the caller's concern. The same
`AmbiguityPolicy` / `Resolver` vocabulary reaches wherever a derivation is
chosen: `parse_model`, the PDA's `IslandPolicy`, and the Earley completion.

**A flipped point is consumed at its first visit.** A unit cycle's same-span
completions make the chart CYCLIC (`a ::= b | "x"` / `b ::= a | "y"`), and a
pin that re-applied at its own key would name no finite derivation — the
pinned build walked `a → b → a` forever. Consumed
(`splits._descend` pops it; `FastTree` copies the caller's map), a pin names
the one-lap unroll, exactly the alternative whose value answers the question.
Family 0 needs no guard: the first family recorded for a key can only
reference completions recorded strictly earlier, so the default walk is
acyclic by causality.

**The forest already records where to look.** A key packing more than one family
IS an ambiguity point (Scott 2008), so the question is answered by a walk rather
than by enumerating derivations and hoping the interesting one comes early. One
flip per point suffices: a fold is compositional, so if no single alternative
changes the value, no combination does — linear in ambiguity points where
enumerating derivations is exponential in them.

**A many-production root is not an ambiguity point.** Its sibling productions
live in other accepting *items*, so `s ::= s s | "a"` over `"aaa"` reads
unambiguous to a walk that only follows links. Checked separately.

---

## A directive is not a privilege of surfaces with a line comment

`@start` and `@non-semantic` are read from source comments before the parser
runs. The scan used to take the flavour's `line_comment`, and ISO EBNF has only
`(* *)` block comments — so directive parsing was disabled for every EBNF
grammar, and a mechanism GBNF and ABNF could express, EBNF structurally could
not. That is a privileged formulation.

It was not academic. `json.ebnf` could not mark `ws` structural, so `ws` stayed
semantic, the stop-set analysis correctly refused to resolve it predictively and
compiled it as a fail-island, and since `json-text` references `ws` as its first
item, EVERY parse escaped to Earley at position 0. The same language as
`json.gbnf`, which compiles 126 clones and no islands.

A flavour now declares whichever comment form it has — `line_comment` or
`block_comment` — and the scanner reads directives from either. All three JSON
formulations now compile to byte-identical clone tables.

**The directives are also an argument**, not only a source comment: `Directives`
overrides what the grammar says, and keys the compile memo, because one source
compiled two ways must not hand back the first. `Vocabulary` bundles
`tokenizer` + `registry`, which were never two channels — they compose over a
default `unicode` before anything reads a terminal.

---

## The compiled artefact's four rulings

**The target is inferred, never a flag.** `classes` / `ir` / `plain` are one
projection over one symbol table, decided by the codomain of the reduction that
produced the value. A `target=` parameter would be a channel beside a real one:
the caller already chose, by choosing a product, and asking again invites the
two answers to disagree. The rule generalises — if a flag appears in the
projection, a wrong turn has been taken.

**The `.pyc` is written at export.** `UNCHECKED_HASH` makes byte-compiled output
outrank its source unconditionally, which is what buys the fast import. Its
price is that whoever writes the `.py` must write the `.pyc`: leaving it to the
first importer is how a reader silently gets yesterday's value. The same rule
orders the two files on disk — the stale cache is dropped before the new source
lands, and the fresh cache after, so no crash window leaves them disagreeing.

**`src/` carries no regex engine.** Field naming, name mangling and every other
text transform in the compile path are written as explicit character walks. A
regex is a second, opaque grammar engine living inside a grammar engine: the
one thing this codebase should never need to reach for is a different notation
for "what does this text mean". A static check enforces the absence, and it is a
floor — it catches an import, not a rewrite of one under another name.

**Record sharing is keyed on identity, plus equal-and-immutable.** Two nodes
share a record when the source shared the object, OR when they are equal and not
in-place mutable. Not identity alone: value-sharing is what keeps the tables
small. Not equality alone: that would merge two lists a caller intends to mutate
apart. The memo carries a **keepalive** with each key, because a memo key is
valid only while something holds the object — synthesized children are freed as
their frame pops, and their ids get handed straight back to different objects.

---

## 2026-07-29 — The island seam declares cross-span uncertainty instead of longest-matching through it

**Decision:** after `island_parse` picks the longest completion end `E`, any
other origin-0 completion end `E' < E` whose next character the island's
continuation accepts raises `PdaFail`. The continuation evidence is the
analysis' soft FOLLOW of the island rule, carried as
`PdaTables.island_follow` (whose key set IS the island set; `islands` is a
derived property) and threaded per reference via `IslandPolicy.follow`.
`follow=None` (a caller without analysis — the direct-call test seam) keeps
plain longest-match; every runtime route passes the real set.

**Why:** longest-match is only a DEFINED answer while no shorter completion
could also compose. A cross-span arm choice (`item ::= "a" | "ab"` then
`tail ::= "bc" | "c"` over `abc`) never shows the same-span gate one span
with two meanings — the PDA answered what gated Earley refuses, a public
invariant breach. `parse_model` falls back on `PdaFail` to **gated**
`earley_model`, so bailing is fully correct: the fallback refuses iff the
ambiguity is real. Soundness of the candidate set is the edge-liveness
window predicate (no completion reachable beyond `E`); soundness of the
check is FOLLOW ⊇ any one site's continuation — every error is a spurious
bail, never a wrong commit.

**The accepted cost:** k=1 FOLLOW over-approximates. vyx's benchmark corpus
trips it at the first island (`template-def`, ends 9/30, a space genuinely
in rule-level FOLLOW), so the vyx PDA route bails and the row runs gated
Earley until the ordered-attempt gate lands — correctness now, the speed
returns with the attempt design, which SEES each cross-span point and can
try the alternative composition instead of guessing from one character.
With the bail, vyx holds raw parity (0/194 divergent; row added for real —
its old "exclusion" subtracted a stem that was never in the list).

## 2026-07-29 — Island window growth: chart liveness at the edge zone, not a completion-column probe

**Decision:** `island_parse` grows its doubling window iff the windowed chart
has an item filed in the edge zone — the last `max(terms.lens)` columns
(`_may_extend` in `pda/runtime/islands.py`). The three old signals (no
completion yet; completion touches the edge; `can_extend_at` at the completion
column) are deleted, along with `can_extend_at` itself.

**Why it is sound:** `longest_start_completion` scans the whole window, so
every completion inside it is already known — more input can only add a
completion that consumes past the edge, and any derivation doing so leaves
visible evidence: a scanner filed at the edge column, or a multi-char literal
the window cut, whose scanner files nothing but sits at most the longest
literal short of the edge (hence the zone, not the single column). Runs cut by
the window land ON the edge; a declined delegate falls through to normal
seeding, so its continuations are ordinary items.

**Why the old probe was wrong twice.** Divergent: probing the completion
column re-answers identically at every window size (columns are a function of
the text prefix), so one persistent scanner — vyx's line interiors — grew the
window to the end of the input, re-parsing from scratch each time (~37× the
corpus through `island_run` on the vyx benchmark; the "anomaly" of the PDA
measuring slower than Earley there). Unsound: a multi-char literal can jump
the probed column without filing an item in it, so the probe answered "don't
grow" while a longer completion was reachable — a truncated longest match
spliced as the answer (`test_island_parse_grows_past_a_window_cut_multi_char_literal`
pins the shape).

**Impact:** `island_run` returns `(kern, completion | None)` — the kernel is
the predicate's evidence even on a miss, and a dead-chart no-match now fails
fast instead of growing to the end of the input first. `island_value`'s
fold-refusal reroute stays as the last line of defence.

## 2026-07-21 — Micro-perf floor: in-process A/B only; model count, not per-model cost, bounds the win

**Finding:** the only trustworthy way to measure a parse-engine change below roughly 15% is an **in-process, interleaved A/B** — baseline and candidate run in the same warm process, order randomized per sample, best-of-N reported. Cross-process comparisons (including git-stash-based before/after) and `cProfile` self-time both mislead at this scale: cross-process runs showed an apparent 6–11% win that vanished (and in one case reversed) under in-process A/B, because cold-start and allocator noise dominate a delta that small; `cProfile`'s per-call overhead inflates exactly the highest-call-count helper functions, misdirecting effort toward code that isn't the real steady-state bottleneck.

**Corollary — the parse-time floor is model count, not construction cost.** Runtime micro-optimization of the trusted PDA instance-build path (per-parse interning, call-site fast paths) stacks to roughly 10–12% cumulative before diminishing. The dominant remaining cost is *how many* model objects a parse builds, not the cost of building each one: a typical instance parse builds on the order of 1.5 models per input character, and most of that is one leaf model per character inside a quantified single-charclass run (whitespace, unescaped string content). Reaching substantially further requires collapsing a maximal single-charclass run into one span model instead of one model per character — which changes the generated model API (a `list[Char]`-shaped field becomes a `str`-shaped field), needs matching support in the analysis and clone-compiler layers, and has to account for escape-run heterogeneity (a string containing `\`-escapes is a span/escape/span sequence, not one clean span). Not yet built.

**Why it matters:** any future claim of a double-digit-percent parse-engine speedup should be treated as unproven until re-measured with an in-process interleaved harness; a structural (model-count) change is the only lever known to reach a 30%+ win.

---

## 2026-07-20 — FOLLOW-k arm gates: bounded lookahead windows, not a single FOLLOW char

**Decision:** where a nullable-greedy alternation's escape arm and body arm can't be told apart by each arm's single-character FOLLOW set, the PDA analysis computes a bounded `FOLLOW_k` window (k ≤ 3: a tuple of per-position character sets, EOF/END-tagged, lazily fixpointed only for rules that actually hit this branch) instead of demoting the decision to the Earley completion. The mechanism generalizes the existing single-CharSet `extend_follow` to windows (a single CharSet is the k=1 special case — one code path, not two).

**Why:** the GBNF charclass range-tail choice (does `-` start a range, or is it a literal dash right before the closing `]`?) is exactly this shape — the character that actually disambiguates is one position past the dash, not the dash itself, so a k=1 FOLLOW set can't separate the arms and every hit fell back to a full Earley completion. Reshaping the charclass grammar to route this choice through one empty-arm rule made it a single, analyzable decision point instead of two duplicated concrete-vs-negated rule pairs.

**Impact:** GBNF self-grammar-text parsing, which regressed to superlinear scaling from this one un-gated decision, returns to flat µs/char. The generalization from single FOLLOW to `FOLLOW_k` windows is additive — every previously-gated decision keeps its k=1 gate unchanged; only decisions that previously had no gate at all pick up a new one.

---

## 2026-07-20 — Shared fold idioms as IR bodies, except the absent-tail fill (`IrNone` is a legal value, not just an absence marker)

**Decision:** three fold idioms were duplicated across two hand-authored micro-grammars (the IR-constructor notation and the generated-module self-grammar): first+rest list collection, integer decoding, and filling an omitted trailing optional. The first two were single-homed as pure IR algebra bodies in a shared module and now drive both grammars. The third — filling an omitted optional — stays a small keyword-constructing procedural body, duplicated once, rather than becoming a fourth shared IR body.

**Why:** the naive shared form ("an omitted optional argument becomes `IrNone`") is lossy: `IrNone` is also a value an author can pass *explicitly* in this notation (constructing `IrQuantifier(0, IrNone)` for an open-ended upper bound is legitimate, valid notation), so a generic fill-with-`IrNone` body can't distinguish "the caller wrote `IrNone`" from "the trailing argument was absent" — collapsing the two would silently change what a round-trip reconstructs.

**Impact:** the shared module hosts the two idioms that are genuinely representable as pure IR bodies, plus a named-callable escape hatch for surface-specific procedural logic; the absent-tail idiom is duplicated exactly once instead of copied per call site, and `IrQuantifier(0, IrNone)` continues to round-trip correctly.

---

## 2026-07-11 — Reduction bodies are pure IR algebra; type-branching pipes into an `IrTypeMap` (Task 6.5)

**Decision (user ruling, hard):** flavour reduction bodies contain **zero Python functions**. A left-factored rule whose fold must branch on *what the tail matched* does it in the algebra: the tail rules reduce to type-distinct markers (a decoded `IrInt`, `IrNone`, an `IrChr`, a joined `IrStr`, or a sentinel like `_Q_MIRROR = IrStr("=")` — data, not code), and the parent's body is `IrPipe(IrArg(i), IrTypeMap(IrAction(<type>, <branch>), …))` — `IrPipe` rebinds the focus to the marker, `IrTypeMap` dispatches on its concrete type, and the argument channel rides through so branches still read the shared leading run (`IrThis()` is the marker itself, `IrArg(0)` the lead). An `IrLambda(def …)` in a grammar module is a review-blocking offence — **with no legacy exemption** (user escalation, same day): the HEAD-era handlers were purged in the same landing. Emit-side spelling went to its architectural homes — the class-point escape cascade and quoted-form spellability are now generic `EscapeCodec` algorithms (`encode_point`/`spellable`, ir/escapes.py) over per-flavour ClassVar *data* (`CLASS_SHORT`/`CLASS_META`/`QUOTE_SAFE`), reached from the actions via the dispatcher-codec leaves `IrEscapePoint`/`IrSpellable` (ir/flavour.py, the `IrEscape` pattern); the `=/` rule merge became the generic `IrMerge` action node; and the algebra gained the generic fillers `IrRadix` (emit-side inverse of `IrUnradix`), `IrOrd` (inverse of `IrGlyph`), `IrLen`, and `IrEach` (the variadic sibling of `IrAt`). Emit output byte-parity (22 artefacts: both self-emits + all GT canonical emits under both flavours) pinned the purge as observably free.

**Why:** grammar modules are data (the flavour = metadata + grammar + reducer + emit actions ruling). A Python `isinstance` ladder hides fold semantics from every IR consumer (no walk, no rebuild, no repr-as-codegen), silently swaps error typing (`int()` `ValueError` vs `IrUnradix`'s `UnsupportedConstructError`), and erodes the self-hosting endgame (an auto-generated flavour module cannot contain hand-written procedures). Task 6.5's six lambda folds were all expressible: `IrTypeMap`-over-a-piped-marker was sufficient for every branch shape (`q-counted`, `repeat-num`, `num-x/d/b`).

**Corollary — channel flattening comes from the grammar, not the fold.** Where a fold seems to need per-element mapping or arg slicing (ABNF `cvbody`: leading chars become *items* only when an alpha follows), restructure the *authored grammar* instead: an **inline group** desugars (`normalize`) to a synthetic rule whose parts **splice flat** into the parent's channel — the same machinery every quantified ref already rides — so `cvnac* (cvalpha cvany*)?` hands `cvbody` lead chars and case items in one flat channel, `IrArg(-1)`'s type picks the branch, and `IrSequence`'s authoring coercion (bare `IrLiteral` atoms lift to `IrItem`s) rebuilds the per-char expansion byte-identically. First inline group in an authored self-grammar; the reduce path treats it exactly like the quantifier synthetics it has always spliced.

**Impact:** `gbnf.py`/`abnf.py` reductions are def-free; `IrThis` joined both import blocks; `cvbody-tail` never existed in the landed shape. GT `parse_grammar` output byte-identical to pre-task HEAD (oracle-verified), so the decision cost nothing observable.

---

## 2026-07-11 — P6/P3 noise levers: attribution over hardcoding; peeks are fail-soft (Task 6.4)

**Decision 1 — the P6 licence carries a third clause.** SIM_60's pinned two-clause condition (`hard_follow ∩ FIRST = ∅` ∧ `gap ⊆ FIRST`) is sufficient for json but unsound in general: it would license a non-semantic loop eating into a *semantic* optional follower (`root ::= x "ab"?`, `x ::= [a-c]*` noise — `semantic_dump` changes). The plan's own risk note demands precision, so the licence adds `gap ∩ sem_follow(rule) = ∅`, where `sem_follow` is a FOLLOW fixpoint over *semantically-attributable* chars only (`pda/noise.py`): terminals count only inside semantic rules; a ref to a non-semantic rule contributes nothing (its subtree is excluded from `semantic_dump` wholesale, so chars stolen from it are noise↔noise by construction); a ref to a semantic rule contributes its *decomposition*, not its noise-polluted raw FIRST. This reproduces the SIM's json justification ("ws is the sole whitespace-leading rule") without hardcoding it.

**Decision 2 — W is grammar-derived, not per-flavour.** The P3 skippable alphabet is ⋃FIRST over **nullable** non-semantic rules: nullability is what separates a noise *run* (ws, filler) from a required-but-dropped token marker (dquote, defined) — exactly the ⚠ 6.0 constraint, with W itself derived. Gives json whitespace, ABNF ws+`;`, GBNF ws+`#` (matching the SIM's hand-pinned sets).

**Decision 3 — the P3 peek is non-consuming, hence fail-soft by construction.** The runtime skips the maximal W run only to *look*; the winning arm/iteration re-parses its noise from the original position. A wrong pick can therefore only fail-then-fallback, never silently mis-build — so the analysis separability conditions are a *determinism* (zero-fallback perf) guarantee, and mixed-terminal poisoning / end-open bailing in `ResidualFirst` err conservative without soundness pressure. Corollary: comment-bearing noise (GBNF `#…`, ABNF `;…`) poisons the char-set residual FIRST (the skip could land inside a comment body), so the GBNF/ABNF spine's P3 decisions stay islands until the folding-aware structured scanner lands with P5 (which needs it regardless).

**Decision 4 — stored gates are honored in every clone.** The compiler consulted taxonomy gates only under its per-clone hard-cont overlap heuristic; a clone whose hard tail didn't overlap the loop FIRST silently baked a stop-set that ate the soft-only noise run the gate exists to adjudicate (caught live by a `\t`-bearing json input). Rule: a stored gate is the analysis's decision for that node — judged against the rule's soft FOLLOW, which covers every clone — and is read back unconditionally.

**Decision 5 — staging flags die once their lever lands.** `P2_DEMOTION_ENABLED` deleted (user ruling: pre-v1, no legacy); flag-seam tests deleted with their symbol. `DELEGATES_ENABLED` stays until Task 8 — it is the still-standing delegation A/B gate, not a landed lever's leftover.

**Impact:** json island-free (16× vs 6.2 on the instance path: 751→46 ms); `Taxonomy` carries four gate channels; `pda/noise.py` + `test_noise.py` new; `_gate_take`/`_select_gated` shared runtime helpers in `flatten.py`.

---

## 2026-07-11 — P2 gate-spec channel: analysis stores, compiler reads (unified-parse-engine Task 6.3c)

**Decision:** The k-window gates the analysis consults during demotion are **stored on the taxonomy** and read back by the clone compiler — never recomputed. `GrammarAnalysis.taxonomy` (the renamed `_tax` slot, now a public **attribute** — deliberately not a property/method, so the R0904 20-public-method and R0902 7-slot caps are both untouched) is a `Taxonomy` carrying `arm_gates: dict[str, windows-per-arm]` and `loop_gates: dict[int, taken-windows]`.

- **Why option (a) (store) over recompute-in-compiler?** Dual derivation of the same soundness-critical spec is a divergence risk (task63fix F1: the seam previously carried *no* spec — the gates were computed and discarded). Single source of truth; the compiler's only job is alignment.
- **Arm gates keyed by rule name, licensed for rule bodies ONLY.** `arm_conflicts`' `label` for a rule body IS the rule name (`label in self.rules` is the discriminator — bracketed group labels can never collide with rule names). An inline group's arm overlap now stays a **hard note → the rule islands**, which strictly dominates the old part-(b) whole-grammar opt-out (the engine parses one rule instead of everything). Corpus has no such group.
- **Loop gates keyed by `id(IrItem)` — node identity.** Analysis and clone compiler walk the *same* lifted tree (`compile_pda` builds the analysis from the `lifted` it compiles), so the item node is the exact decision identity; label-keying (`rule[idx]`) is ambiguous between a rule arm's item k and a group sub-arm's item k. A conflicting re-store under one id raises (`UnsupportedConstructError` → whole-grammar opt-out) — the shared-node hazard is closed, not assumed away.
- **Specs stored cooked** (`kwindow.windows_of`: END/MORE/UNK tags dropped — the runtime's positionwise consistency test never reads them (task63fix finding 4) — dedup'd, deterministically sorted so specs compare with `!=`).
- **Alignment lives inside `compile_arms`' own enumeration** (`windows[idx]` attached in the same loop that drops empty-FIRST arms) — window↔arm drift is structurally impossible rather than checked after the fact. A FIRST-overlapping alternation reaching the compiler with **no** spec raises — the anti-trap tripwire (F2: an empty gate mis-parses, PdaFail-falls-back, and passes island-move + parity gates while unsound and slower).
- **Verified live:** chess `nonpawn` (loop, k=3) 0.0% fallback + 8.6× faster than the 6.2 island-hit path; `lo>k` EOF-exact arm selection end-to-end; GBNF-self 17→8 / ABNF-self 9→7 island moves exactly per the coverage map.

**Impact:** `Taxonomy` is public (`analysis.__all__`); `KTupleGate`/`ArmSpec.windows` reinstated in `clones.py` as read-side only; LL(2) 2-prefix machinery now lives in `kwindow.py` as free fns (`loop_policy` calls across); `_bake_reduce`/`_reduce_rewrite` live in `reduce_pda.py`. `P2_DEMOTION_ENABLED` defaults **True**; `False` is the A/B seam. See [[architecture]] and log 2026-07-11.

---

## 2026-07-06 — One IR fold type: `ModelFold` + `ModelBody` (unified-parse-engine Task 3)

**Decision:** The instance fold's authored form is now **one IR-native type**, `ModelFold` (`parsing/fold.py`), whose `bodies` is a per-rule `IrMap[IrRuleRef, ModelBody]` — the *same shape* the grammar-text `Reducer` carries its `reductions` in (a per-rule `IrMap` to `IrSelf` bodies). A `ModelBody(kind, ctor, n_items, fields, fast)` (an `IrNamedTuple`, `_child_attrs=()`) carries the model constructor as an `IrLambda` (`IrNone` for an `alternation`, which has none) plus structural metadata. On construction `ModelFold` **bakes** every body (`ModelBody.bake()`) to the flat-runtime `config: dict[str, RuleFold]` (`.baked`) — the record the PDA clone compiler and the engine-fallback `apply` consume **byte-for-byte unchanged**. `RuleFold`/`FieldFold`/`FastCtor` survive as that lowered/baked representation; `ModelBody.of(rf)` is the inverse lift and `ModelFold.from_config(dict)` the direct-from-baked (lowered) constructor.

- **Why merge `PositionalFold` into `ModelFold` rather than add a wrapper?** The task called for *one* fold type; the old `PositionalFold` was only the runtime executor over `dict[str, RuleFold]`. Absorbing its `apply`/`run_ok` onto `ModelFold` (which reads the same `self.config`) keeps the runtime logic unchanged while making the authored form the IR body-table. `collapsed_fold_tables(grammar, fold)` re-signs to `ModelFold`; nothing else in the engine changes.
- **Why `IrLambda(cls)` for the ctor?** It is the sanctioned procedural escape and `IrLambda(cls).eval IS cls` (free unwrap) — so baking recovers the exact constructor with zero indirection. Proven by `spike_bake.py` (176 rules across all 10 ground truths bake runtime-identically; 0 rules need an arbitrary body).
- **Name reclaimed.** The retired wrapper-rule `ModelFold` (`parsing/models.py`, deleted 2026-07-04) is unrelated; the name is now the one authored instance-fold.
- **Behavior-frozen.** A differential over 600 generated samples × both parse paths (PDA + engine) is byte-identical before/after; no perf loss (the flat clone is unchanged).

**Why:** unify the *authored* fold to an IR body-table so Task 4 can express the `Reducer` as the same per-rule `IrMap`-to-`IrSelf`-body type. The lowered `RuleFold` int-mode contract with the flat clone is deliberately preserved — the change is at the authoring seam, not the runtime.

**Impact:** New public exports `ModelFold`, `ModelBody` (`parsing/fold.py`); `PositionalFold` removed. `compile._fold_config` now returns the `IrMap` body-table; `_build_pda` takes `fold.baked`. See [[public-api]], [[architecture]].

---

## 2026-06-05 — Phase-0a algebra: `IrScalar`/`IrInt`, `IrOp` (no `Cmp` enum), `IrTuple.eval -> IrSelf`

**Decision:** Added the value-aware action algebra, deviating from the plan's prescribed shapes on four points:

1. **`IrScalar(IrLeaf)`** is the value-leaf base; it hosts `eval` *and* the type-aware `__eq__`/`__ne__`/`__hash__`/`__repr__` (consolidated up from `IrStr`). `IrStr(IrScalar, str)` and `IrInt(IrScalar, int)` carry only `_bound`. `IrStr.__new__`/`eval` removed. Added `__ne__` to fix a latent inconsistency (`str`/`int` supply their own `__ne__`, which ignored the leaf-kind check, so `a != b` disagreed with `not (a == b)`).
2. **`IrField.out: type[IrScalar]`** (default `IrStr`), made constructor-callable by a forwarding **`IrScalar.__new__(*args)`** — NOT the plan's `type[IrStr] | type[IrInt]` union (closed-set, forbidden) and NOT generic (a concrete default on a generic `out` is unsound for pyright).
3. **`IrOp(IrStr)`** operator leaf instead of the plan's **`Cmp` enum** (user directive: no Enum). The operator IS its string (`IrOp(">")`); `_OPS` maps it to an `operator` builtin; `eval` applies it to the operands in `nc`. `IrCompare(left, op: IrOp, right)` supplies both operands; `IrAnd` is short-circuit conjunction. A truth value is `IrInt ∈ {0,1}` — no `IrBool`. (User directive: comparison ops are a string-leaf node, never a Python `Enum`.)
4. **`IrTuple.eval` relaxed `-> Self` → `-> IrSelf`** so reducer subclasses (`IrAnd(IrTuple[IrSelf])`) can override `eval` to return `IrInt` — NOT the plan's `IrTuple[T, R]` two-param generic + `cast`. `IrSequence`/`IrAlternation` are untouched.

**Why:** Open classes over closed-set dispatch (no enum, no enumerated leaf union); avoid the plan's heavier generics where a one-line return-type relaxation suffices. All verified empirically (apply→pyright→suite).

**Impact:** `IrCond` now takes `test: IrSelf` (was `field: str`). New public exports: `IrScalar`, `IrInt`, `IrOp`, `IrCompare`, `IrAnd`. Full suite green (593), `pyright src/ tests/` = 0. See [[ir-shapes]].

---

## 2026-06-04 — Primitive-node model (V2): a node IS its payload

**Decision:** Replace the coercion-based node model with one where nodes *are* their payload. Three tiers: str-leaves (`IrLiteral`/`IrCharClass`/`IrRuleRef`) subclass `str` via `IrStr`; variadic collections (`IrSequence`/`IrAlternation`) subclass `tuple` via `IrTuple`; fixed-arity records (`IrItem`/`IrQuantifier`/`IrGroup`/`IrNot`/`IrRule`/`IrAst`) are frozen `IrComposite` dataclasses. Removed: `IrType`, `coerce`, the load-bearing `*args/**kwargs` `IrNode.__init__`, `_ir_field_types`, `IrStrLeaf`, `IrCollection`/`_items_attr`, and the `_str_name`/`_inner_str`/`__str__` cascade (replaced by `__repr__`-is-codegen). There are **no** `.value`/`.items`/`.arms` accessors — use the node directly.

**Why:** The old `__init__(*args, **kwargs)` masked ~174 pyright errors (standard-mode 0 was a lie). Making nodes their payload eliminates coercion, the load-bearing init, and the variance that produced those errors. Construction is now honest per-field dataclass `__init__`/`__new__`; whole-tree pyright is genuinely 0.

**Impact:** Every consumer reads leaves as `str` and collections as `tuple`; construction is variadic (`IrSequence(*items)`, `IrAlternation(*arms)`, `IrAst(IrTuple(*rules), start)`). Full suite green (572 tests), `pyright src/ tests/` = 0. See [[ir-shapes]].

---

## 2026-06-04 — Type-aware `IrStr.__eq__`

**Decision:** `IrStr.__eq__` is type-aware against other `IrStr` (distinct leaf kinds never compare equal — `IrLiteral("x") != IrRuleRef("x")`) but falls back to native `str` equality against a plain `str` (`IrLiteral("x") == "x"`). `__hash__` stays native `str.__hash__`.

**Why:** With leaves subclassing `str`, `IrLiteral("x") == IrRuleRef("x")` was `True`, poisoning structural tree equality and hashing (a `@cache` on `has_ruleref` returned stale results because structurally-distinct trees compared equal). The transitivity tension — `leaf == "x"` for both kinds *forces* `IrLiteral("x") == IrRuleRef("x")` — is resolved by making equality type-aware only among `IrStr` while preserving plain-`str` compatibility. Native hash means same-text different-kind leaves collide but compare unequal (eq is the tiebreaker), and leaves still match plain-`str` dict keys.

---

## 2026-06-04 — `IrThis` + lazy `IrReturn` for find-first (no callable)

**Decision:** Added `IrThis` — an identity body whose `eval` returns the dispatched node `n`. `IrReturn` lazy-evaluates its body against `(d, n, nc)` and re-raises the result, defaulting `value=IrThis()` so `IrReturn()` surfaces the matched node. `has_ruleref`'s visitor is pure algebra: `IrAction(IrRuleRef, IrReturn())`.

**Why:** Returning the *found* node from a predicate visitor needs access to `n` at eval time, which a constant `IrReturn(x)` cannot capture. An `IrCallable` raising `IrReturn(n)` was rejected — keep the action table declarative, no procedural escape hatch where algebra suffices. `IrThis` is the declarative "current node" primitive; `IrReturn` evaluating its body composes it cleanly and stays backward-compatible (`IrReturn(IrLiteral("v"))` still returns the literal).

---

## 2026-06-04 — Two type parameters `[Iri, Ir_co]`; `_bound` from the last

**Decision:** Generic nodes/actions carry two PEP 695 parameters `[Iri: IrSelf, Ir_co: …]` — `Iri` the input node type, `Ir_co` the covariant return type. `IrSelf.__init_subclass__` derives `_bound` from the class's **last** own type parameter (i.e. `Ir_co`), not the first.

**Why:** Adding `Iri` first shifted `Ir_co` to second position; the old `params[0]` derivation then resolved `_bound` to `IrSelf` (Iri's bound), breaking `IrField`/`IrConcat`/`IrJoin`/`IrEmitter` (`IrSelf() takes no arguments`, `'IrSelf' has no attribute 'join'`). `Ir_co` is conventionally last (sole param on single-parameter nodes, second in the pair), so taking the last is correct and keeps the existing `_Probe[T: …]` contract test passing.

---

## 2026-06-04 — No `cast`, no suppressions (reaffirmed)

**Decision:** During the V2 port, type errors are fixed at the root — correct annotations, `isinstance` guards that `raise` on the unexpected branch, or constructing the real node. No `cast`, no `# type: ignore`/`# noqa`/`# pylint: disable`. Owner instruction: "absolutely no cast."

**Why:** A `cast` re-hides exactly the variance the V2 model exists to expose. An `isinstance`-guard-then-`raise` documents the invariant and fails loudly if violated; a cast asserts it silently.

---

## 2026-06-04 — Open-set consumer rework deferred

**Decision:** The V2 migration is a mechanical port; IR consumers (`derive`, `codegen`, `parsing`, `generate`) keep their closed-set `isinstance` ladders and `dict[type, …]` tables for now. A **separate** spec/plan will re-home node-intrinsic logic onto the nodes and consumer policy onto open `IrDispatch` tables.

**Why:** Finish the migration green first (the safety net), then refactor — two independently-verifiable passes rather than one giant change. These ladders are legacy, not the target.

---

## 2026-05-28 — P12: IR passes are action tables, not closed subclasses

**Decision:** Every IR pass — transformer, emitter, visitor — is a `tuple[IrAction, ...]` plugged into a single concrete `IrDispatch[Ir_co]` (via `IrVisitor` / `IrTransformer` / `IrEmitter` presets). Passes are **constructed**, not subclassed. New IR types are added by extending the action tuple; no dispatcher subclassing required.

**Why:** Strengthens the original "open classes" rule. A closed pass-subclass forces every consumer to know every node type at subclass-definition time; an action table lets the table grow per-flavour or per-pass without touching the dispatcher. New AST node types ripple through table-builders, not through case statements.

**Impact:** `IrFlavour` IS-AN `IrEmitter`, configured by `actions = <FLAVOUR>_ACTIONS`. Adding a flavour means writing a new action tuple, not a new dispatcher class.

---

## 2026-05-28 — P13: Action bodies AND dispatcher are IR nodes

**Decision:** Both the per-target action body and the dispatcher itself live on the `IrNode` substrate. `IrDispatch[Ir_co]` IS-AN `IrCollection[Ir_co]` whose `_items_attr = "actions"`. Action bodies (`IrField`, `IrCallable`, `IrConcat`, `IrJoin`, etc.) are `IrNode`s with overridden `eval`.

> **Superseded (2026-06-04, V2):** `IrCollection`/`_items_attr` are gone. `IrDispatch[Iri, Ir_co]` is now an `IrComposite` whose `actions` is a plain tuple field (NOT a dispatched child). The "dispatcher and bodies are IR nodes" principle stands; only the base tier changed.

**Why:** Self-describing system. Dispatchers can be walked, rebuilt, printed via the same machinery as any IR tree. No special-case "outside the IR" objects.

**Impact:** The action-algebra modules (`ir/action.py`) and the dispatcher module (`ir/walk.py`) compose freely. `IrTransformer` can rewrite a flavour's action table just like any other IR tree.

---

## 2026-05-28 — P14: Dispatcher is generic in result type with LSP-compatible signature

**Decision:** `IrDispatch[Ir_co: IrSelf]` is generic in the produced type. Every dispatcher method follows the protocol shape `eval(d, n, nc) -> Ir_co` — identical for the dispatcher itself and every action body.

**Why:** A single `(d, n, nc) -> Ir_co` signature lets action bodies invoke `d.eval(d, child, ())` without any cast or shape conversion. Substitutability across the algebra is automatic.

**Impact:** Presets bind `Ir_co`: `IrVisitor` inherits `IrSelf`, `IrTransformer` binds `IrNode`, `IrEmitter` binds `IrLiteral`. `apply(root)` is the friendly entry that seeds `d = self`.

---

## 2026-05-28 — P15: Concrete-first MRO resolution; `IrAction` is a default-override unit

**Decision:** `IrDispatch._resolve(type(n))` walks `type(n).__mro__` left-to-right (concrete-first) and returns the first matching `IrAction`. Memoised per dispatcher instance. Misses fall through to `self.default` wrapped in a synthetic `IrAction`.

**Why:** A more specific `target_type` beats an ancestor without table reordering. Default-override is a single field swap on the preset; no special "default branch" mechanism is needed.

**Impact:** Adding a specialised action for `IrCharClass` doesn't break the generic `IrLeaf` action it inherits from. `default=IrRaise()` (strict) and `default=IrEmit()` (lenient) are interchangeable in one line.

---

## 2026-05-28 — P16: Short-circuit is intrinsic to `IrReturn` via `_Return`

**Decision:** `IrReturn` mixes `IrLeaf` and a private `_Return(BaseException)`. `eval` raises `self`; the surrounding `IrDispatch.apply` catches it and surfaces `.value` (or the instance, depending on the bound).

**Why:** Short-circuit needs no protocol participation from every other node. Any nested action can raise `IrReturn` and unwind to the dispatcher. `_Return` is a `BaseException` subclass so `IrCallable` handlers' `except Exception:` clauses cannot swallow it.

**Impact:** Conditional emission becomes trivial: `IrCond(field, IrReturn(IrStr("")), normal_op)` short-circuits cleanly. The `IrReturn` instance IS-AN `IrNode`, fitting the dispatcher's bound when surfaced.

---

## 2026-05-28 — P17: `IrLiteral` carries dual role (grammar literal + action constant)

**Decision:** `IrLiteral` is used both as a grammar AST leaf (the literal string in a rule body) and as an action-language constant (e.g. `IrConcat(parts=(IrLiteral("("), ...))`). The two are distinguished at eval time by `nc`-marker semantics: lazy `IrChild` puts a dispatched literal through `d.eval` (action body fires); direct calls inside action algebra short-circuit to `self.value`.

**Why:** Refusing to introduce a separate `IrText` constant node keeps the algebra small and uniform. Reusing `IrLiteral` means any constant string in an action body could be the target of an `IrTransformer` rewrite (e.g. "change all parenthesisation").

**Impact:** No `IrText` exists. Constants are just `IrLiteral(value)`. The role disambiguation is implicit in the calling convention, not in the type.

---

## 2026-05-28 — P18: Every IR node is callable

**Decision:** Every node implements `__call__(d, n, nc) -> Ir_co`. The default — inherited from `IrSelf` — is identity (`return self`). Value-producing nodes override. `Ir_co` defaults to `IrSelf`.

**Why:** A unified call shape lets *anything* in the IR be the body of an `IrAction`. The substrate has one protocol; specialisation is opt-in.

**Impact:** `IrAction(target, IrLiteral("x"))` is a valid action body — the dispatcher invokes `IrLiteral("x")(d, n, nc)` and gets `IrLiteral("x")` back. Pure-data nodes need no boilerplate to participate in dispatch.

---

## Vendor formats never enter `ir/`

A tokenizer pipeline was once modelled in `ir/encoding.py` by transliterating
**one vendor's** stages into IR nodes — a hand-implemented GPT-2 regex, its
byte table, and node types named after that vendor's pipeline steps. It got
there the obvious way: the goal was "reference-exact against this vendor",
and copying that vendor's stages is the shortest path to it.

The cost is not cosmetic. The spine then knows one product's answer instead
of the question, so a *different* vocabulary reads as unsupported even when
the concept is identical — and a format's serialization field names start
leaking onto IR nodes.

The rule: `ir/` models what a thing IS (`IrPretoken` — a spec whose `split`
partitions text). A format's own vocabulary lives with the reader for that
format, which `IrPretoken`'s open-set design already anticipates. Reading a
vendor's file is an application of lexic; being one is not.

Corollary for readers: a reader takes the grammar+reducer that parse its
document as **parameters**, so it privileges no formulation. That is what
makes a third-party format reader legitimate inside `src` at all.

---

## 2026-05-08 — Grammar is the ground truth, not the class

**Decision:** Grammar files are canonical. Generated classes are Python representations of a grammar, not sources of truth.

**Why:** The alternative ("class is canonical") biases every design toward "make the class more expressive" and demotes non-GBNF users (the llama.cpp population who come with existing `.gbnf` files). It also breaks cleanly once ABNF or other flavours land — "the class implies a flavour" only works if there's one notation.

**Impact:** `to_grammar(flavour)` is a first-class method on every generated class. `@grammar_rule` decorator (Slice D) produces the same `RuleSpec` shape as codegen-from-file — two authoring paths, one IR.

---

## 2026-05-08 — Parallel-track IR cutover (not in-place migration)

**Decision:** New IrItem-based pipeline built in `new_gbnf/` and future `new_codegen/` alongside the old pipeline. Single cutover commit (Task 18) replaces everything atomically.

**Why:** In-place migration would require every intermediate commit to satisfy both old and new tests simultaneously, creating complex invariant juggling. The parallel track lets each component be built and tested independently; the cutover is a rename + delete.

**Tradeoff:** Temporary code duplication (`new_gbnf/` mirrors parts of `gbnf/`). Acceptable given the cutover is planned and bounded.

---

## 2026-05-08 — Tasks 3 and 5 deleted (no parser wrapper, no adapter for new pipeline)

**Decision:** Deleted `new_gbnf/parser.py` (wrapper around `MetaGrammarParser`) and `new_gbnf/adapter.py` (adapter bridging old registry) from the plan.

**Why:** The new pipeline calls `MetaGrammarParser.for_flavour(GbnfFlavour)` directly. A wrapper would be a thin passthrough with no behaviour of its own. The adapter was needed only because the old `flavours.py` registry exists — once `flavours.py` is deleted at cutover, the adapter concept disappears too.

---

## 2026-05-08 — `_FIELD_BASE` lookup table replacing if/elif chain in `_field_map`

**Decision:** Replaced a 13-branch `if isinstance(atom, X)` chain with a `_FIELD_BASE: dict[type, Callable]` dispatch table.

**Why:** pylint flagged the chain as too many branches. The table is also consistent with `_ATOM_HINT` (already a table) and with the architecture's prescribed dispatch pattern (`BUILDER_BY_ATOM`).

**Contract distinction:** `_ATOM_HINT` always returns `str` (used for naming only); `_FIELD_BASE` returns `str | None` where `None` signals "fall through to Tier-3 positional". This difference is documented in comments and in [[field-naming]].

---

## 2026-05-08 — `CHARCLASS_NAMES` ground truth: 9 entries, `letter` not `alpha`

**Decision:** `[a-zA-Z]` → `"letter"` (not `"alpha"`). 9 entries total; `[a-zA-Z0-9_]` → `"alnum"` (only `_0-9` ordering, not `0-9_`).

**Why:** `letter` is more natural English than `alpha` (which implies "alphabetic" in a more technical sense). `alnum` captures the common identifier char class. The table is intentionally small — any unknown pattern falls back to `_sanitize_pattern`.

**Note:** Both orderings of hex digits (`[0-9a-fA-F]` and `[a-fA-F0-9]`) map to `"hex"` — intentional normalisation.

---

## 2026-04-29 — IrItem shape: quantifier on wrapper, not on leaves

**Decision:** `IrItem(atom, quantifier)` wraps every atom; leaves (`IrLiteral`, `IrCharClass`, `IrRuleRef`) carry no quantifier.

**Why:** In the old shape, quantifiers were fields on `CharClassAtom`, `QuantifiedLiteralAtom`, `RuleRefAtom`. This meant `LiteralAtom` had no quantifier (special case), and adding quantifiers to a new atom type required touching the dataclass. The new shape separates concerns: leaves are pure values, `IrItem` owns repetition.

**Impact:** An unquantified `IrLiteral` is `IrItem(IrLiteral("x"), Quantifier(1,1))`. A quantified literal is `IrItem(IrLiteral("-"), Quantifier(0,1))`. `_field_map` skips only `IrLiteral` with exactly `(1,1)`.

---

## 2026-05-08 — Cutover commitments (CQ #1, #2, #4)

**Decision:** Three named commitments enforced by Tasks 9–17 of the cutover plan.

- **CQ #1 — No `# FIXME` placeholders in emitted Python source.** `_repr_iritem` (in `new_codegen/model_emitter.py`) produces real Python for every IR shape; emitted modules never carry placeholder comments.
- **CQ #2 — No name-string hardcoding in `parsing/lark_builder.py`.** Non-semantic optionality flows from `RuleSpec.non_semantic_fields` + `IrItem.quantifier`. No `atom.name == "ws"` checks. Enforced by `test_no_ws_string_check_in_source`.
- **CQ #4 — Fixed canonical import block in every generated module.** `model_emitter.CANONICAL_IMPORTS` is a constant emitted unconditionally; no per-module import inference. Includes `Annotated`, `StringConstraints`, `Literal`, `ClassVar`, the full IR-AST surface (`IrAlternation, IrAst, IrCharClass, IrGroup, IrItem, IrLiteral, IrRule, IrRuleRef, IrSequence, Quantifier`), `RuleSpec`, and `GrammarModel`.

**Why:** All three are anti-temptation rules. Without CQ #1 emitters reach for placeholder text in unfamiliar shapes; without CQ #2 the lark builder accumulates one-off rule-name special cases; without CQ #4 import lists drift between generated modules.

---

## 2026-04-29 — `Flavour` ABC with class attributes only

**Decision:** Each flavour is a class with class attributes (`meta_grammar`, `escapes`, `emitter`, …) and two static methods (`parse_quantifier`, `parse_charclass`). No `__init__`, no instances as configuration.

**Why:** Flavours have no mutable state — they are configuration bundles. Class attributes are readable, introspectable, and don't require instantiation. `MetaGrammarParser.for_flavour(Cls)` takes the class, not an instance.

**Tradeoff:** The `emitter` class attribute uses `ClassVar[Any]` (typed loosely) to avoid an import cycle. Acceptable — the type is checked at test time.

---

## 2026-07-28 — Engine parity is RAW model equality, not semantic equality

**Decision:** The PDA and the Earley engine must build the *same model*, field for field. `deep_semantic` — which drops `semantic=False` binds at every level — is no longer the parity bar.

This retires "ruling 1", which had licensed the two paths to disagree: *"the PDA's greedy stop-set loop may split a `semantic=False` run differently from the engine's ambiguity resolution."* That licence lived only in a test module's docstring, which is why it could hold for a month without being a decision anyone could find.

**Why:** `@non-semantic ws` does **not** remove whitespace from the model. It is preserved as `Ws('')` *fields*, because `to_text()` round-trip needs the characters stored. So a consumer reading `.ws` can observe a difference the semantic bar declares invisible — the bar was hiding a real disagreement rather than describing an irrelevant one. Under the standing ruling that the engines are *required* to agree, a comparator that passes either way cannot be the test for it.

**What made it affordable:** the adjacent-nullable split fix. A *split* — one production carved two ways, same arm, different boundary — has a defined answer: the first slot owns the text. `is_arm_choice()` (`parsing/earley/kernel/tables/splits.py`) is the structural test that separates it from an *arm* choice, which is two different productions and is still refused. Once both engines resolved splits the same way, all three JSON formulations agreed at raw equality and the semantic licence had nothing left to excuse.

**Impact:**

- `tests/integration/lexic/parity/test_pda_parity.py` carries two tests that own different invariants and do not subsume each other: the wide differential (semantic bar) owns fallback behaviour, round-trip and the opt-out branch; `test_both_engines_build_the_same_model_not_just_the_same_meaning` owns raw equality.
- The semantic licence had been hiding 47 of 200 JSON inputs — the same characters landing in different `Ws` fields.
- Ambiguity is still **refused by default**. The engines are not permitted to pick. A caller may supply a deterministic resolver, and that resolver's behaviour is the caller's concern, not the engine's — it is not a fallback and not a flag.
- `RAW_PARITY_STEMS` excludes a stem only with a written reason. Exclusions are debts, not licences.
