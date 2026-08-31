# Review 15 — final packet closure audit

The `final packet closure audit` reviewer's response, copied verbatim. Each pass is a fresh reviewer
running the role against the packet as it stood, and every response is below in
order. The dispositions are recorded in `reports/P15_ADVERSARIAL.md` §3.

---

## Pass 1 — NOT READY

Reviewer 3 — final packet closure audit. Verdict: NOT READY (4 substantive blockers, all documentation/coherence; the executable artefact itself is sound).

WHAT I VERIFIED CLEAN

- `git status --short -- src tests pyproject.toml .wiki` empty; `git diff --check` clean. Working-tree modifications are confined to the effort's own tracked documents (DESIGN.md, LEDGER.md, context.md, goal.md, proto/island_continuation.py, reports/P15_ADVERSARIAL.md, reports/PROTOTYPE_15.md). No source, test, harness or wiki file changed.
- `uv run python island_continuation.py` → exit 0. Every case-table figure in PROTOTYPE_15.md §3 lines 199–253 reproduces exactly, as do §4 lines 366–372, §5 line 421–426, §6 line 439–443, §7 line 478–480, §8 lines 494–503 (drop <5% and the four census rows), §9 line 538, §3.2 lines 285–290, and the artefact-flatness / artefact-lifetime / registry-residency rows (§1 lines 65–80). The elision claims at §3 lines 190–193 hold for `shortcut_root_meanings`, `settlement_baseline_products` and `seed_baseline_products`.
- No forbidden constructs in island_continuation.py: no `Any`, `object`, `cast`, `# type: ignore`/`noqa`/`pylint: disable`, no builtin `eval`/`exec`, no nested `def` (the indented defs are class methods), no thread/multiprocessing import.
- No parse regression is authorized: PROTOTYPE_15.md:645-646 and INDEX.md:213-215 both say so explicitly; PROMPT_15.md:182 repeats it.
- Resolver scope is NOT silently selected. TODO.md:954-959 keeps `DECISION REQUIRED BEFORE §8 — RESOLVER SCOPE` unchecked and states "No user ruling is inferred from the investigator report." PROTOTYPE_15.md:597-603 (Q6) answers "All of it… Nothing here selects a scope." PROTOTYPE_14.md:808-811 opens with "USER DECISION REQUIRED. Nothing below selects it," and its recommendation at :846-865 closes "The user rules." That is a stated recommendation, not a selection.
- P14's coordinator correction (P14_ADVERSARIAL.md:716-761) is consistent with the packet: it supersedes the historical READY, closes the quantified-nullable user question, and leaves resolver scope as the only open user decision — matching INDEX.md:14-16.

BLOCKERS

B1 — a deliverable states a number the current artefact contradicts.
`reports/P15_ADVERSARIAL.md:149-150` records F4's verification as "Case 1 records `skipped_enumerations=1` and `seed_trees=1` against a control run's `control_seed_trees=3`." The current run prints `control_seed_trees=1` for `const-consumer`, and `reports/PROTOTYPE_15.md:272` now says `control_seed_trees=1`. The 3 was true before Reviewer 2's B1 fix (P15_ADVERSARIAL.md:300-311) removed the island's second derivation; it is no longer reproducible. Since P15_ADVERSARIAL.md is the audit trail an implementer re-runs against, mark it superseded by B1 or restate it. Note that with `seed_trees=1` on both runs, the F4 saving now shows only in `seeds` (0 vs `control_seeds=1`) and `seed_chart_nodes=0` — the record should cite those columns instead.

B2 — TODO.md and INDEX.md were not folded for Reviewer 2's three consequences, though the same round folded them into the other four active documents.
PROMPT_15.md:34-36 requires coherent updates to INDEX.md, context.md, goal.md, DESIGN.md, TODO.md and LEDGER.md. The working-tree diff shows the three Reviewer-2 consequences landing in DESIGN.md:754-764, context.md:336-343, goal.md:277-281 and LEDGER.md:96-116. `grep -n "dirty cone\|exponential\|escalat\|retained island kernel\|Earley chart" TODO.md INDEX.md SUMMARY.md` returns nothing. Concretely:
  - TODO.md:864-891 (`PLANNING REQUIRED BEFORE §8 — CONTINUATION COMPOSITION CLOSED`) describes the closed gate but never says the EXECUTE lane needs a family-aware Earley chart and is therefore an escalation on the predictive path (PROTOTYPE_15.md:344-353), never states that exactness is exponential in a node's local multiplicity (PROTOTYPE_15.md:398-406), and never states that the seed retains an island kernel per ambiguous occurrence with an unsettled production release boundary (PROTOTYPE_15.md:452-461).
  - INDEX.md:14-18's gate list names "family-aware numbering, new operation-law rows, integrated memory, custom paid-loop neutrality, and every parse-performance comparison" and none of the three.
An implementer working from the queue alone (INDEX.md:39 — "TODO.md is the implementation queue") would build the mechanism without any of them.

B3 — two different mechanisms for the same case sit in DESIGN.md with no precedence stated, and TODO.md prescribes only the older one.
DESIGN.md:754-764 (new this round) says what neither shortcut settles "reaches the exact per-node relation," confined to the dirty cone, with a per-node baseline fold and "No global family assignment is formed anywhere."
DESIGN.md:793-797 (unchanged) says "At an actual internal semantic-choice family, the default derivation's completed-handle memo is reused and only the alternate family's ancestor cone is replayed to the root through a sparse overlay over the read-only baseline… The verdict is therefore exactly the complete requested value."
TODO.md:1011-1018 prescribes only the second: "For one alternate family, mark its completed owner and ancestors dirty, replay only that cone in a fresh isolated product state… use a read-only baseline plus one sparse alternate overlay."
These are two different computations of the same single-family case, and the prototype implements the first — PROTOTYPE_15.md:564-565 (Q1) states the settled lanes build no "dependency index, an overlay, a meaning memo." I am not asserting they are irreconcilable (DESIGN.md:789-791 does carve multiple/nested sources out of one-flip), but the packet nowhere says which governs, and INDEX.md:39-41 rules that a DESIGN/TODO disagreement must be reconciled before source work. Reconcile or state precedence.

B4 — the round's largest stated performance consequence has no labelled gate.
PROTOTYPE_15.md:606-608 (Q7) answers "Is any planning or prototype gate still open before source implementation? For the island-continuation composition: no." PROTOTYPE_15.md:626-630 simultaneously records that replacing the linear one-flip probe with the exact relation "is exponential in a node's own local multiplicity, and no bound on it is claimed… This is the round's largest performance consequence and it is unmeasured." Nothing in TODO.md §8 (lines 862-1098) carries it: no unchecked item requires a bound or a measurement of the exact lane's local product, and §8's Exit clause (TODO.md:1095-1098) states only correctness conditions. The only measurement gate is §12, which is post-implementation (INDEX.md:209). Under INDEX.md:213-215 / CLAUDE.md's rule that a parse regression needs explicit post-measurement user approval, that places the discovery of an unbounded cost after the mechanism has landed. This is a gate-placement/labelling fix — add an unchecked §8 item — not new prototype work.

NON-BLOCKING (listed once, no action required for READY)

- PROTOTYPE_15.md:194 claims "Nothing is elided that differs from a column shown." `control_seeds` is elided (:191-192, excused only "where §3.1 quotes them") and differs from the shown `seeds` on `const-consumer` and `const-consumer-abnf` (1 vs 0); §3.1:272 quotes `control_seed_trees` only. The direction is conservative — it understates the round's own saving.
- `reports/REVIEW_15.md` is linked as existing at INDEX.md:55 and INDEX.md:136 and listed as a round file at PROTOTYPE_15.md:695-696, and does not exist. P15_ADVERSARIAL.md:216 says it is written when Reviewer 3 returns, so this resolves when this response is copied in — but PROTOTYPE_15.md §12 presents that list as a statement about the working tree.
- Commit eb205ebe added a tracked bytecode artefact (`proto/__pycache__/operation_slot_laws.cpython-314.pyc`) while INDEX.md:198-199 declares `__pycache__/` "local tool artefacts, not part of the packet." Currently clean in `git status` (my run regenerated nothing).
- I did not re-run the six oracle prototypes listed at PROTOTYPE_15.md:678-683; the prompt limited me to one run of island_continuation.py. Those exit-0 claims are unverified by this audit.

NOT READY

---

## Pass 2 — NOT READY

Reviewer 3 — final packet closure audit, pass 2. Verdict: NOT READY (2 substantive blockers, both numeric/provenance accuracy in active documents; the executable artefact and every mechanism claim I could check are sound).

WHAT I VERIFIED CLEAN (independently, not from the dispositions)

- `git status --short -- src tests pyproject.toml .wiki` empty; `git diff --check` clean, both before and after my runs. Working-tree modification is confined to nine of the effort's own tracked files (DESIGN.md, INDEX.md, LEDGER.md, TODO.md, context.md, goal.md, proto/island_continuation.py, reports/P15_ADVERSARIAL.md, reports/PROTOTYPE_15.md). No source, test, harness or wiki file changed. The tracked `proto/__pycache__` .pyc was not disturbed by my seven runs.
- `uv run python island_continuation.py` → exit 0. I ran the six oracle prototypes too (the prompt permitted it): `operation_slot_laws`, `route_continuation`, `root_meaning_incremental`, `island_alternate_seed`, `ambiguity_interaction`, `resolver_pair` — all exit 0, confirming PROTOTYPE_15.md:689-696 which the previous pass could not verify.
- `uv run ruff check` / `ruff format --check` / `pyright` on island_continuation.py: clean, 0 errors, 0 warnings — confirming P15_ADVERSARIAL.md:479-487.
- Every case-table figure in PROTOTYPE_15.md §3 lines 199-256 reproduces exactly, as do §3.2:286-292, §3.3:302-309, §4:367-375, §5:423-428, §6:440-446, §7:477-482, §9:539-542, and §1's flatness/lifetime/residency rows (:65-81). All four elision-equality claims at :188-192 hold on every row, and the `control_seeds` exception at :193-196 is exactly the two const rows (1 against 0).
- No forbidden construct in island_continuation.py: no `Any`, no `object` annotation (the only `object` is the word in a docstring at :278), no `cast`, no `type: ignore`/`noqa`/`pylint: disable`, no builtin `eval`/`exec` (the sole `.eval(` at :560 is lexic's own IR action protocol), no nested `def`, no thread/multiprocessing import.
- The mechanism claims map to code, not to prose. `island_meanings`:703 reads `unobservable_rule` before `exact_meanings`:707, so the skip really precedes the set work while the one baseline derivation at :700 is built either way — which is what §3.1:273-277 now says. `_dirty_cone`:1104-1124 seeds from >1 family or >1 leaf option and closes upward, so a non-dirty node provably has a singleton set equal to its baseline; `_node_set`:1181-1198 is a genuine per-node product over deduplicated child sets, not a one-flip probe; `settle`:984-986 returns inequality from a realized injective route with other occurrences held at baseline, which is a sound existential witness; `_resolver_pair`:2158-2173 splices from `payload.kernel`, the kernel the seed retained, with `document_recognitions` and `island_runs` asserted unchanged at :2122-2123.
- Cited production seams exist as described: `OP_ISLAND` and the zero-measured-occurrence note at `src/lexic/parsing/pda/runtime/kernel/kernel.py:396-410`; `products.py`'s Earley-only-on-`PdaFail` route at its module docstring:6-7; `compile/reduce/fold.py:403` `contribute`; `compile/artifact.py:252` `resolve=`. I also executed the load-bearing weakref claim at PROTOTYPE_15.md:92-94: `weakref.ref` on `IrAst` and on `Reducer` both raise `TypeError`.
- No parse regression is authorized: PROTOTYPE_15.md:658-659, TODO.md:920-922, INDEX.md:219-221, PROMPT_15.md:182.
- Resolver scope is not silently selected, and I checked every document that touches it rather than trusting one: TODO.md:985-990 unchecked with "No user ruling is inferred from the investigator report"; PROTOTYPE_15.md:599-605 "All of it… Nothing here selects a scope"; PROTOTYPE_14.md:808-810 "USER DECISION REQUIRED. Nothing below selects it" and :864-865 "The user rules"; DESIGN.md:858-862 "the user must decide"; goal.md:266-267 "the still-open choice"; CURRENT_BUG_REPORT.md:211-214 "the user has not yet ruled". No document claims READY, and DESIGN.md:11 states plainly that a final fresh reviewer has not returned it.
- Pass 1's four blockers are genuinely disposed of, verified against the artefact rather than the record: B1 — P15_ADVERSARIAL.md:148-155 now cites `seeds=0`/`control_seeds=1`, `seed_chart_nodes=0`, `seed_products=0`, all of which the current run prints for `const-consumer`, with the superseded 3 labelled. B2 — TODO.md:892-911 carries the dirty cone, the deliberate Earley escalation and the retained kernel as three unchecked items, and INDEX.md:16-24 names all three. B3 — precedence is stated in both places, DESIGN.md:793-797 and TODO.md:1047-1054, with the per-node relation governing and the overlay as its certificate-gated specialization. B4 — TODO.md:912-922 is a labelled `PLANNING REQUIRED AT §8 EXIT — EXACT-LANE COST BOUND` and PROTOTYPE_15.md:607-618 (Q7) now names it as a gate this round opened.

BLOCKERS

C1 — the EXECUTE census range the round cites is contradicted by the round's own output, and the wrong figure has been written into the implementation queue.

`reports/PROTOTYPE_15.md:511-512` states "DROP is under 5% everywhere and EXECUTE is 80–95%". Computed from the census the current run prints:

- gbnf `rows=170 verdicts={'drop': 8, 'execute': 162}` → EXECUTE 95.3%
- abnf `rows=138 verdicts={'drop': 6, 'execute': 102, 'injective': 30}` → EXECUTE **73.9%**
- ebnf `rows=90 verdicts={'drop': 4, 'execute': 86}` → EXECUTE 95.6%
- json `rows=60 verdicts={'drop': 2, 'execute': 48, 'injective': 10}` → EXECUTE 80.0%

The actual range is 73.9–95.6%. ABNF sits six points below the stated floor because it is the one shipped grammar where the certificate still yields injective rows (30 of them). The DROP half of the sentence is correct (4.7 / 4.3 / 4.4 / 3.3%). The figure is repeated at `reports/PROTOTYPE_15.md:636`, `TODO.md:904-905`, `LEDGER.md:108-109`, `reports/P15_ADVERSARIAL.md:289-290` and `:437-439`. TODO.md:900-905 is an unchecked implementation item whose whole justification is "the census puts EXECUTE at 80–95% of rows, so this is the common path" — an implementer would be planning the escalation route against a number the artefact does not produce. This is pass 1's B1 class exactly: a deliverable stating a figure the current artefact contradicts. The substance survives the correction (EXECUTE is still the common path on every grammar); only the range is wrong, so this is a five-place figure fix, not mechanism work.

C2 — `LEDGER.md` records two reviewers where three ran, and attributes the third's consequences to the second.

`LEDGER.md:83-84`: "Two adversarial reviewers ran sequentially and both returned NOT READY with twelve findings each, four blocking each". A third fresh reviewer ran the closure-audit role and returned NOT READY with four blockers — `reports/P15_ADVERSARIAL.md:411-415` and `reports/REVIEW_15.md:13` both record it — and the packet changed materially as a result. `LEDGER.md:96` then heads the round's substantive changes as "Three of Reviewer 2's fixes", but two of the changes now standing in the packet are Reviewer 3 pass-1 dispositions, not Reviewer 2's: the precedence statement at `DESIGN.md:793-797` / `TODO.md:1047-1054` is its B3 (`P15_ADVERSARIAL.md:441-452`), and the `PLANNING REQUIRED AT §8 EXIT — EXACT-LANE COST BOUND` gate at `TODO.md:912-922` is its B4 (`:454-465`); the TODO/INDEX fold itself is its B2 (`:428-440`). `INDEX.md:41` makes LEDGER.md the effort's chronological state and corrections record, and it currently contradicts the adversarial record on both the review count and the provenance of a planning gate. Two sentences fix it.

NON-BLOCKING (listed once, no action required for READY)

- `reports/PROTOTYPE_15.md:196` "Every other elided column equals a column shown" is false for five of the columns the same sentence elides. On the `interacting-with-a-dropped-third` row the run prints `row_lookups=7`, `descent_steps=9`, `multiplicity_nodes=2`, `one_flip_trees=4`, `oracle_trees=1` against a shown `seed_trees=3` — none of those equals a shown column. This is the residue of the pass-1 non-blocking note: the fix correctly excepted `control_seeds` but left the blanket claim covering the five columns that carry no equality parenthetical. Nothing elided contradicts a shown column, so the direction is harmless.
- `reports/PROTOTYPE_15.md:504` quotes `cpu=0.048225`; my run printed `cpu=0.049503`. Expected variance for a timing sample, and the report's own line disclaims it and draws no conclusion — but it is the one figure in §1–§9 that does not reproduce, worth a word if the section claims exact reproduction.
- `TODO.md:912-922` labels the gate "AT §8 EXIT" while its body says "Before the mechanism lands" and defers the measurement to "beside the §12 RSS row", and `INDEX.md:215` places §12 after implementation. The enforcement obligation — state the bound or the refusal — is correctly at §8 exit; the measurement is not, and the two sentences read as one gate. A clarifying clause would remove the ambiguity, but the placement that pass-1 B4 actually objected to has been fixed.
- I did not re-run the shipped test suite, any benchmark, or any timing comparison; the prompt forbade it. Everything in §11's not-proved list therefore remains unverified by this audit, which is what §11 says.

NOT READY

---

## Pass 3 — NOT READY

Reviewer 3 — final packet closure audit, pass 3. Verdict: NOT READY (one substantive blocker: a superseded figure surviving in LEDGER.md, the same class and the same number pass 1's B1 removed elsewhere). Everything else I could check independently is sound, including both pass-2 dispositions.

WHAT I VERIFIED CLEAN (independently, against the artefact, not the dispositions)

- `git status --short -- src tests pyproject.toml .wiki` empty; `git diff --check` clean, before and after all seven of my runs. Working-tree modification is confined to nine of the effort's own tracked files (DESIGN.md, INDEX.md, LEDGER.md, TODO.md, context.md, goal.md, proto/island_continuation.py, reports/P15_ADVERSARIAL.md, reports/PROTOTYPE_15.md). No source, test, harness or wiki file changed. No `.ruff_cache` or `__pycache__` file was regenerated or dirtied by any of my runs — `git status --short` is byte-identical before and after.
- `uv run python island_continuation.py` → exit 0, and all six oracle prototypes → exit 0 each (`operation_slot_laws`, `route_continuation`, `root_meaning_incremental`, `island_alternate_seed`, `ambiguity_interaction`, `resolver_pair`), confirming PROTOTYPE_15.md:701-708.
- Every case-table figure in PROTOTYPE_15.md §3 (:207-256) reproduces exactly, as do §3.2:293-298, §3.3:309-315, §4:374-380, §5:430-433, §6:447-451, §7:484-487, §9:552-553, §1's flatness/lifetime/residency rows (:65-80), and the §8 census. The elision-equality claims at :187-196 hold on every row: `shortcut_root_meanings`=`control_root_meanings`, `settlement_baseline_products`=`settlement_chart_nodes` (0/0 … 161/161 … 3/3), `seed_baseline_products`=`seed_chart_nodes` (incl. 10/10 on sibling-and-nested), `control_seed_trees`/`control_seed_products`=their twins (4/4 on sibling-and-nested), and `control_seeds` differs from `seeds` on exactly the two const rows (1 against 0). The five cost counters named at :200-202 for `interacting-with-a-dropped-third` (`row_lookups=7`, `descent_steps=9`, `multiplicity_nodes=2`, `one_flip_trees=4`, `oracle_trees=1`) match, and are indeed that row's maxima.
- Pass 2's C1 is genuinely fixed in all five places and the arithmetic is right: gbnf 162/170=95.3%, abnf 102/138=73.9%, ebnf 86/90=95.6%, json 48/60=80.0% → 73.9–95.6% at PROTOTYPE_15.md:521 and :648, TODO.md:905, LEDGER.md:110 and :127, P15_ADVERSARIAL.md:289 and :437. DROP 4.7/4.3/4.4/3.3% is correct. The only surviving `80–95%` strings are the two that must survive: the verbatim reviewer response at REVIEW_15.md:74/81 and the finding statement at P15_ADVERSARIAL.md:500.
- Pass 2's C2 is fixed: LEDGER.md:83-110 now records three fresh `general-purpose` reviewers, the auditor's two passes, and which changes came from which pass, citing reports/REVIEW_15.md.
- Pass 1's B2/B3/B4 hold. TODO.md:892-922 carries the dirty cone, the deliberate Earley escalation and the retained kernel as three unchecked items plus the labelled `PLANNING REQUIRED AT §8 EXIT — EXACT-LANE COST BOUND`; INDEX.md:16-24 names all three; precedence is stated in both DESIGN.md:790-797 and TODO.md:1046-1054, with the per-node relation governing and the overlay as its certificate-gated specialization.
- The mechanism claims map to code. `island_meanings` builds the one baseline derivation at island_continuation.py:700, then reads `unobservable_rule` at :703 and returns before `exact_meanings` at :707 — the skip really precedes the set work, which is what §3.1:279-283 now says. The const witness is a real authored action (`("wrap", IrStr("fixed"))` at :1408 and :1527) evaluated through `reducer.body(...).eval(...)` at :560, not a policy dictionary. `retained_island_kernels` increments only when `alternates` is non-empty (:714), matching the "unambiguous island retains nothing" claim. `DISTANT_PAD = 40` at :1361 gives the 81-character document the three documents cite.
- No forbidden construct in island_continuation.py: no `Any`, no `cast`, no `object` annotation (the only hit at :398 is the word in prose), no `type: ignore`/`noqa`/`pylint: disable`, no builtin `eval`/`exec`, no nested `def`, no thread/multiprocessing import.
- No parse regression is authorized: PROTOTYPE_15.md:670-671, TODO.md:920-922, INDEX.md:219-221, PROMPT_15.md:182. No document claims READY; DESIGN.md:11 states plainly that a final fresh reviewer has not returned it.
- Resolver scope is not silently selected, checked in every document that touches it: TODO.md:987-992 unchecked with "No user ruling is inferred from the investigator report"; PROTOTYPE_15.md:611-617 "All of it… Nothing here selects a scope"; PROTOTYPE_14.md:810 "USER DECISION REQUIRED. Nothing below selects it" and :862 "The user rules"; DESIGN.md:861 "the user must decide"; goal.md:266 "the still-open choice"; CURRENT_BUG_REPORT.md:213 "the user has not yet ruled".
- Prototype 14 and its coordinator correction (P14_ADVERSARIAL.md:716-761) are consistent with the packet: the historical READY is superseded, the §3b fold is recorded at PROTOTYPE_14.md:1042-1048, CURRENT_BUG_REPORT.md:3 and :186 carry the three defects and BUG 3, and resolver scope is left as the only open user decision — matching INDEX.md:15-16.
- Gate labelling is otherwise accurate. TODO.md:864-888's `[x] CONTINUATION COMPOSITION CLOSED` discloses its own stand-ins inside the gate text (rule-level half only; production reads the key off the entry frame or waiter code rather than the root-down descent), so the tick does not overstate. SUMMARY.md was not in PROMPT_15.md:34-36's fold list and contradicts nothing (:73 and :105 agree with the round).

BLOCKER

D1 — the superseded `control_seed_trees=3` figure still stands in LEDGER.md, the one active document pass 1's B1 fix did not reach.

`LEDGER.md:22-23` reads: "the rule-level half of the discard is read BEFORE the island enumerates, so a constant continuation's alternates are never built — `skipped_enumerations=1` with one seed derivation against a control's three."

The current run prints, for `const-consumer`: `seed_trees=1 control_seed_trees=1`. Both runs build one seed derivation. The "three" is exactly the figure Reviewer 2's B1 fix invalidated when it removed the island's redundant second derivation, and exactly the figure pass 1's B1 struck from `P15_ADVERSARIAL.md` (now correctly labelled superseded at :419-421) and from `PROTOTYPE_15.md:280` (now `control_seed_trees=1`). That fix corrected two files; LEDGER.md was not in its scope and still carries the number, in the paragraph that predates this round's diff (it is committed text at eb205ebe, so `git diff` on LEDGER.md does not surface it).

This matters beyond arithmetic because the sentence uses the wrong number as its evidence for the round's headline claim — that the constant continuation's alternates are never built. With `seed_trees=1` on both runs, the saving shows in `seeds=0` against `control_seeds=1`, `seed_chart_nodes=0` and `seed_products=0`, which is precisely the re-citation P15_ADVERSARIAL.md:425-426 adopted. `INDEX.md:41` makes LEDGER.md the effort's chronological state and corrections record, so it currently contradicts both the corrected report and the artefact on a load-bearing figure. This is the third instance of the class pass 1 called B1 and pass 2 called C1 — a deliverable stating a number the artefact does not produce — and the two earlier instances were treated as blocking. One sentence fixes it.

NON-BLOCKING (listed once, no action required for READY)

- `TODO.md:911-919` still reads with its two halves in tension: the body says "Before the mechanism lands, state the bound…" while the label is `PLANNING REQUIRED AT §8 EXIT` and §8's Exit clause (TODO.md:1132-1134) sits after the exact lane has landed. Pass 2 raised this and the fix correctly separated STATEMENT from MEASUREMENT; the actionable instruction ("before the mechanism lands") is unambiguous on its own, so I agree with pass 2 that it is not blocking, but the marker word and the body still name different moments.
- `PROTOTYPE_15.md:279-281` cites "the control run's `control_seed_trees=1`" as what case 1 is measured "against", where both runs print 1. The real contrast in that sentence is the chart walk and `seeds`/`seed_chart_nodes`/`seed_products`, which the same section and §3.1 do carry. Accurate but uninformative as cited — and it is the sentence D1's LEDGER twin got wrong.
- `row-census cpu` printed 0.050712 on my run against PROTOTYPE_15.md:510's 0.048225. The report already says outright that this is the one figure that does not reproduce and draws no conclusion from it, which is the right disposition; the spread is now three samples wide (0.048225 / 0.049503 / 0.050712).
- `reports/REVIEW_15.md` is not tracked by git (`zzz_current_work/` is gitignored at .gitignore:45 and the packet's other files were force-added), while INDEX.md:61 and :142 list it as part of the authoritative packet and PROTOTYPE_15.md:719-723 names it as a round file. Whether to add it is the user's call at commit time, not a packet defect.
- `DESIGN.md:752-755` now opens two consecutive paragraphs with near-identical sentences ("what neither settles reaches the exact per-node relation" / "What neither shortcut settles reaches the exact per-node relation"), an artefact of the B3 insertion. Prose only; flagged because you asked for coherence, not because it changes meaning.
- I ran no benchmark, no timing comparison and no test suite, and made no edit. Everything in PROTOTYPE_15.md §11's not-proved list remains unverified by this audit, which is what §11 says.

NOT READY

---

## Pass 4 — NOT READY, then READY on re-check

Pass 4's first response raised two provenance/gate-labelling blockers (E1: the
pass-3 gate relabel had reached `TODO.md` only, so `LEDGER.md` and
`PROTOTYPE_15.md` Q7 still named the superseded label and moment; E2:
`LEDGER.md` recorded two closure passes where three had run and omitted pass
3's blocker). The user ruled that no fifth fresh agent should be spawned to
re-review documentation nits, so the fixes were sent to the same auditor. Its
re-check verdict, verbatim:

Reviewer 3 — final packet closure audit, pass 4 re-check. Verdict: READY. Both blockers are genuinely fixed; no substantive blocker remains. Two of the three non-blocking items you reported as addressed are not in the files — neither is blocking, but I am correcting the record rather than accepting the account.

E1 — FIXED, both halves.

- `LEDGER.md:110-114` now names the gate `PLANNING REQUIRED BEFORE THE EXACT LANE LANDS — EXACT-LANE COST BOUND` and states the split verbatim: "whose STATEMENT half gates the exact lane's own implementation inside §8 while its MEASUREMENT half belongs beside the §12 RSS row." That matches `TODO.md:912-926` word for word on both the label and the two moments.
- `PROTOTYPE_15.md:627-633` (Q7) now reads "The gate has two halves at two moments, and `TODO.md` places them: production STATES the bound it enforces — or the refusal it raises past it — before the exact lane lands, inside §8; the MEASUREMENT of that lane on an ambiguous input belongs beside the §12 RSS row. Neither half substitutes for the other." The "measure … before the mechanism lands" clause I blocked on is gone.
- `grep -rn "AT §8 EXIT — EXACT-LANE"` now returns only audit-trail hits: `REVIEW_15.md:68/85/109` (verbatim reviewer responses, which must survive) and `P15_ADVERSARIAL.md:460` (the pass-1 B4 disposition, explicitly superseded by the relabel recorded at `:565-567`). No active document carries the old label.

E2 — FIXED. `LEDGER.md:87-91` now reads "the closure auditor returned NOT READY three times: four documentation-and-coherence blockers, then two numeric/provenance ones, then one more", and `LEDGER.md:117-123` states pass 3's blocker ("this ledger still cited 'one seed derivation against a control's three', the figure the round's own earlier fix had invalidated"), its re-citation to the chart, product and seed columns, and attributes the gate relabel to that same pass. It now agrees with `P15_ADVERSARIAL.md:541-559` and `REVIEW_15.md:98-136` on both the pass count and the provenance.

CORRECTIONS TO YOUR ACCOUNT (both non-blocking, neither changes the verdict)

- The census CPU spread was NOT widened to four samples. `P15_ADVERSARIAL.md:569` still reads "(0.048225 / 0.049503 / 0.050712)", and `0.051303` appears nowhere in the packet. Harmless — `PROTOTYPE_15.md:511-516` disclaims that figure outright and draws no conclusion from it — but the fix you described is not in the file. My re-run printed a fifth value, `cpu=0.049550`, which is the point the disclaimer already makes.
- `DESIGN.md`'s status paragraph does NOT name Prototype 15. `grep -n "Prototype 15\|PROTOTYPE_15\|island_continuation\|island-continuation" DESIGN.md` returns nothing; `DESIGN.md:3-12` still names Prototype 14 and its coordinator rerun as the establishing round. Non-blocking exactly as I scoped it originally, because `DESIGN.md:751-800` carries the round's content in full — but unfixed.
- The third item IS in place: `PROTOTYPE_15.md:726-729` now records that importing `resolver_pair` regenerates its `__pycache__` entry and running Ruff rewrites `proto/.ruff_cache/`, that both directories are tracked, and that each was restored with `git checkout` after the last run.

FINAL SWEEP (figures and gate labels an active document states that the artefact or the queue does not carry)

- I re-ran `island_continuation.py` once: exit 0, and the output is byte-identical to my pass-4 run on every line except the disclaimed `row-census cpu` sample. Every §3 case-table figure, both ABNF rows, all four elision-equality claims, the `control_seeds` exception on exactly the two const rows, the five cost counters and their maxima, §3.2/§3.3/§4/§5/§6/§7/§9 rows, the flatness/lifetime/residency rows and all four census rows still reproduce exactly.
- `git status --short` is byte-identical before and after that run — no tracked `.ruff_cache` or `__pycache__` file was regenerated or dirtied. `git status --short -- src tests pyproject.toml .wiki` is empty and `git diff --check` exits 0. Working-tree modification remains confined to the same nine tracked effort files.
- Round figures in active documents all check out against the run: 161-node chart, one dirty node, two operation applications, the 81-character document (`DISTANT_PAD = 40` at island_continuation.py:1361-1362), 73.9–95.6% EXECUTE with DROP under 5%, and the const-witness columns `skipped_enumerations=1` / `seed_chart_nodes=0` / `seed_products=0` / `seeds=0` against `control_seeds=1`. `SUMMARY.md` carries none of the round's figures and contradicts nothing.
- `LEDGER.md:88-89`'s "twelve findings, four blocking" for each topic reviewer matches `P15_ADVERSARIAL.md:80` and `:280` — that is the reviewers' own stated count, recorded identically in both places, not a discrepancy with the lettered sub-points.
- Gate labelling is accurate throughout. `TODO.md:864-891`'s `[x]` discloses its own stand-ins inside the gate text; `TODO.md:892-911`'s three unchecked items and `:912-926`'s planning gate are unchecked and correctly placed; `TODO.md:989-994`'s `DECISION REQUIRED BEFORE §8 — RESOLVER SCOPE` is unchecked with "No user ruling is inferred from the investigator report". `INDEX.md:212-213` treats every `PLANNING REQUIRED` marker as a hard gate, and the relabelled gate still carries that prefix.
- Resolver scope is not selected: TODO.md:989-994, PROTOTYPE_15.md:612-618, PROTOTYPE_14.md:809-810 and :864, DESIGN.md:8 and :858-862, goal.md:266-267, CURRENT_BUG_REPORT.md:210-213. No parse regression is authorized: PROTOTYPE_15.md:670-671, TODO.md:924-926, INDEX.md:219-221, PROMPT_15.md:182. No document claims READY on its own behalf; DESIGN.md:11 still says a final fresh reviewer has not returned it.

I ran no Ruff, Pyright, benchmark, timing comparison or test suite, and made no edit. `proto/.ruff_cache/` is tracked, so a Ruff invocation would rewrite a tracked file — `PROTOTYPE_15.md:711-712`'s clean claim is therefore unverified by me, as it was in pass 4 (passes 2 and 3 both verified it). Everything in `PROTOTYPE_15.md` §11's not-proved list remains unverified by this audit, which is what §11 says. READY neither authorizes source implementation nor accepts any parsing regression.

READY

---

**Coordinator note.** The two corrections the auditor made to the account are
right and are now actually applied: the CPU spread is recorded five samples wide
and `DESIGN.md`'s status paragraph names Prototype 15. An edit script had
aborted on a failed anchor after writing two of its four files, and the round's
summary of it was written from intent rather than from the files —
`reports/P15_ADVERSARIAL.md` records that. The `READY` above is from the fourth
fresh closure auditor on re-check, not from a fifth fresh reviewer; the user
ruled against spawning one for documentation nits.
