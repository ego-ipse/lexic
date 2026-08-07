# The gate — why the PDA leaves the fast road one char into the first rulename

**Status: SOLUTION A IMPLEMENTED AND GREEN** (2026-08-07, after external
review — see §10, and §11 for what landed). Sections 0–9 are the investigation
as written *before* the fix; read them in the past tense. The probe variants
have been re-pointed accordingly: `today` is now the fixed pass, and
`unconditional` reproduces the bug.

---

## 0. The answer in one paragraph

The PDA is not wrong. `relax_non_semantic` — the third codegen pass — rewrites
every top-level reference to a `semantic=False` rule to `min=0`. In the GBNF
metagrammar the noise rule `n` is non-semantic *and load-bearing*: `gbnf.py`
engineers maximal munch structurally, and its own design note says so
("adjacent items need real noise unless the next atom is non-name (seq-rest),
inter-rule noise is REQUIRED (rules-rest)"). The pass deletes exactly that
requirement, so the grammar the engines actually see is **genuinely ambiguous**
— `a ::= bc` is one ruleref or two. The ambiguity is real at the *atom* site;
the probe-fork fires at the *rulename-definition* site, one character in,
because the attempt licence is rule-level rather than per-site. Undo the
relaxation and all ten ground-truth grammars ride the PDA with no resolver:
vyx **4.6 s → 0.028 s**.

## 1. The repro

Ten characters, on the real metagrammar (`probes/repro.py`):

```
'a ::= "x"\n'   PDA rides
'ab ::= "x"\n'  ProbeFork: attempt loop at 1: taking and stopping are both viable
```

The gate's own charsets predict which characters fork, and the prediction holds:

```
'a1 ::= "x"\n'  PDA rides        digit — not in the soft continuation
'a- ::= "x"\n'  PDA rides        dash  — not in the soft continuation
'a ::= bc\n'    ProbeFork at 7 — and this one is GENUINELY AMBIGUOUS
```

That last line is the one that matters. `ab ::= "x"` forks but parses fine
without a resolver — a *spurious* probe. `a ::= bc` forks **and** Earley
refuses it without a resolver — a *real* ambiguity. Two different facts, one
gate.

## 2. The site, mechanically

`probes/gate_dump.py` walks every clone spec. The metagrammar has **357 clones
and exactly one attempt-gated item**:

```
rulename.arm0.item1  (ref → namechar)
  take-set (atom FIRST)   '-0123456789A-Z_a-z'
  soft continuation       '\t\n\r !"#()*+.:<?A-Z[_a-z{|'
  BOTH → forks on         'A-Z_a-z'
```

`gate_take`'s `GATE_ATTEMPT` branch (`parsing/pda/compiler/flatten.py:194`)
raises `ProbeFork` iff the boundary char is in both sets. Letters and `_` are
in both; digits and `-` are not — which is precisely why `a1` and `a-` ride.

Where the two sets come from:

- the take-set is `FIRST(namechar)`, the loop's own alphabet;
- the soft continuation is `analysis.taxonomy.attempt_loops[id(item)]`, filed by
  `beyond_at` (`analysis/analysis.py:648`) as **`scope.tail` — the rule-level
  FOLLOW, unioned over every reference site**.

`rulename` is referenced at two sites with very different continuations:

| site | what may follow | letters? |
|---|---|---|
| `rule ::= rulename n? "::=" alternation` | `n`, then `:` | no |
| `atom ::= … \| rulename \| …` | another item | **yes** |

And an attemptable rule gets **one canonical clone**, deliberately — see
`_spec_ruleref` (`compiler/clones.py:271`): "ONE canonical clone per attemptable
rule … per-tail clones made every (rule, pos) re-attempt a fresh key: measured
60% of all sub-runs on the vyx corpus." So the union licence is installed at
*both* sites. The fork at position 1 is the atom site's ambiguity firing at the
definition site, where nothing is ambiguous. `beyond_at`'s docstring already
names the trade: *"the union follow keeps the audit alive at the cost of
spurious probes, and per-SITE precision is the honest narrowing."*

## 3. The root cause — and it is two breakages, not one

`relax_non_semantic` (`compile/pipeline/passes.py:201`). `probes/shapes.py`
prints both sides of it:

```
authored                     codegen (today)
n ::= nunit{1}               n ::= nunit{0}            ← (b)
rules-rest ::= n{1} rule{1}  rules-rest ::= n{0} rule{1}   ← (a)
seq-rest ::= n{1} item{1}    seq-rest-arm1 ::= n{0} item{1} ← (a)
   | item-nonname{1}            | item-nonname{1}
```

**(a) Mandatory noise references become optional.** `seq-rest ::= n item` was
the entire maximal-munch mechanism: an item following another item without real
whitespace *must* be an `item-nonname` (a non-name atom). Relaxed to `n? item`,
`seq-rest` becomes indistinguishable from `first-item ::= n? item`, and a
rulename may sit flush against another rulename.

**(b) The noise rule itself becomes nullable.** `nunit` is also non-semantic, so
`n ::= nunit+` is rewritten to `n ::= nunit*` — after which `n` derives the
empty string, and *every* reference to `n` in the grammar matches nothing,
including any the pass did not touch. (b) alone would suffice to break the
discipline; (a) and (b) both fire.

The consequence, verified with the public API:

```
a ::= bc     →  UnsupportedConstructError: ambiguous input — two derivations
                that mean different things; supply a resolver
```

That is the metagrammar's model-product ambiguity, previously banked as a
separate unlocated finding. It is the same bug. It also explains why the two
findings looked independent: the ambiguity lives at the atom site, the fork
fires at the definition site.

The module header calls all three passes "language-preserving-for-instances".
For `hoist_groups` and `hoist_arms` that is true. For `relax_non_semantic` it is
**false**: `min=1 → min=0` over a non-nullable rule strictly widens the accepted
language, and widening can introduce ambiguity. It is language-preserving
exactly when the target rule is nullable — because once `ε ∈ L(N)`,
`L(N)^{lo..hi} = L(N)^{0..hi}`. That equivalence is the whole basis of the
proposed fix.

## 4. Why the earlier synthetic falsification was right

Yesterday's note recorded that synthetic shapes — bare tail loop, ws/noise +
literal follows, two occurrences with disjoint follows, even one occurrence with
a letter-follow — all ride the PDA, and concluded the cause was *not* generic
FOLLOW-union conservatism. That conclusion was correct and is now explained: in
those shapes the loop demotion succeeds (a k-window or peek gate separates the
branches), so no attempt licence is ever filed. Here demotion cannot succeed,
because after relaxation the boundary genuinely *is* ambiguous. The union FOLLOW
is the amplifier; the relaxation is the cause.

## 5. Measurements

`probes/corpus.py`, the metagrammar reading all ten ground-truth grammars:

| variant | route | resolver | vyx (9,417c) | json.gbnf |
|---|---|---|---|---|
| `today` | ProbeFork on **all ten** | required on all ten | 4.561 s | 0.509 s |
| `off` | PDA on all ten | none | 0.029 s | 0.007 s |
| `nullable` | PDA on all ten | none | **0.028 s** | 0.007 s |

Round-trip holds in every cell. The Earley fallback is ~n^3.2 on this grammar
(measured earlier: 4,281c/0.37 s vs 8,750c/3.79 s), which is why the win scales
with document size — **163×** on vyx, and it grows.

Suite, full, under each variant:

| variant | result |
|---|---|
| `off` | 8 failed, 3766 passed |
| `nullable` | **3 failed, 3771 passed** |

The three: two pin the pass's own contract using a *non-nullable* `ws ::= " "+`
(`test_relax_sets_min_zero_on_noise_refs`,
`test_build_codegen_grammar_composes_all_three_passes`), and one is a pinned
compiler number (`test_clone_count_matches_pinned[c.gbnf]`, 69 → 75). All three
pin the behaviour being deliberately changed; none is a parse, round-trip or
parity regression.

## 6. What the fix costs — stated exactly

`probes/cost.py`. The narrowing makes a **non-nullable** noise rule in a
mandatory slot mandatory again:

```
ws ::= [ \t]*    'a b': accepted    'ab': accepted     (unchanged)
ws ::= [ \t]+    'a b': accepted    'ab': REFUSED      (was accepted)
```

Across the corpus, only `c.gbnf` has a non-nullable `ws` (`ws ::= ([ \t\n]+)`);
`arithmetic`, `json`, `json_arr`, `json_ws` all have nullable ones and are
completely unaffected. c.gbnf still compiles clean, and every one of its own
fixtures still passes — only its pinned clone count moves.

Whether that narrowing is *correct* is the actual question: the author of
c.gbnf wrote `ws`, not `ws?`. Today the engine silently overrides them.

## 7. Proposed solutions

### A — Relax only refs to nullable noise rules  ⟵ recommended

The minimal diff, and the principled one: keep the pass, add the one condition
under which it is language-preserving.

```python
targets = ast.non_semantic & nullable_names(ast.rules)
```

Nullability must be computed on the **pre-relax** grammar, or the pass becomes
self-fulfilling (relaxing `n ::= nunit+` makes `n` nullable, which would then
license relaxing every ref to `n` — breakage (b) licensing breakage (a)).
`variants.relax_nullable_only` is written as exactly this diff and is what the
`nullable` column above measures.

- **Keeps:** the convenience for the common `ws ::= [ \t]*` idiom — the noise
  field stays optional in the model, which is what the four nullable-`ws`
  grammars rely on.
- **Drops:** the silent language-widening for non-nullable noise.
- **Costs:** three test updates; c.gbnf's instance language narrows as above.
- **Implementation seam:** the only nullability fixpoint is
  `parsing/pda/analysis/predicates.nullable_names`, not exported from
  `lexic.parsing`. Either export it there (`lift_optional_nullables` already
  crosses that seam) or move it to `ir/grammar/`, where grammar nullability
  arguably belongs — it is a property of an `IrAst`, not of an engine. The
  second is the cleaner home and the larger change.

### B — Delete `relax_non_semantic` entirely

Authored quantifiers are the truth; a grammar that means "optional" writes `ws?`
— the metagrammar itself already does, at `rule ::= rulename n? "::="` and
`first-item ::= n? item`.

- **For:** one fewer language-changing rewrite; `non_semantic` keeps its real
  jobs (the reducer's DROP policy, model-field suppression) and stops silently
  editing the grammar. Simplest thing that can possibly work.
- **Against:** 8 test failures rather than 3, and it changes the *model shape*
  of the four nullable-`ws` grammars (noise fields become non-optional) for no
  language benefit — the case where relaxation is genuinely free.

### C — Split by provenance: relax `@non-semantic` directives, not authored flags

Would fix the metagrammar (its `n` is authored `semantic=False`, no directive)
at zero cost to any user grammar.

**Rejected, and worth recording why.** It privileges a flavour's own formulation
over a user's — the same shape as the hardcoding ban ("no privileged
formulation: every mechanism works over ANY formulation"). It also needs a
provenance channel that does not exist: directives currently *replace* the
rules' `semantic` flags, so by the time the pass runs the two are
indistinguishable. Two meanings for one concept, to dodge one bug.

### D — Per-site attempt licences  (orthogonal; do not bundle)

Everything above removes the *trigger*. The *mechanism* survives: because an
attemptable rule has one canonical clone carrying a rule-level union licence,
any grammar with a genuinely ambiguous adjacency at **one** reference site will
probe-fork at **every** site of that rule — and the fallback is whole-document
Earley, not an island. `beyond_at`'s docstring already flags per-site precision
as the honest narrowing, and `_spec_ruleref` records why the single clone exists
(memo identity; per-tail clones cost 60% of sub-runs on vyx). Reconciling those
two is a real design question and deserves its own effort. A cheaper partial:
make the fork *island* the undecidable span instead of failing the whole
document, so only the ambiguous region pays.

`probes/gate_dump.py` shows this is not hypothetical — c.gbnf carries an
attempt gate of its own (`statement-arm7`, forking on `e`, the dangling
`else`), and vyx.gbnf-as-an-instance-grammar carries several.

## 8. Recommendation

**A**, with `nullable_names` moved to `ir/grammar/` if that move is in scope, or
exported from `lexic.parsing` if it is not. Then re-state the three pinned tests
against the new contract — they should assert *both* halves ("a nullable noise
ref relaxes; a required one does not"), since the required half is now the
interesting one. Gate on `tools/run_checks.sh` exit 0 plus the parity
differentials, per the standing rule for engine changes.

**D** as a separate effort, not folded in.

While implementing A, fix the module header: `relax_non_semantic` is not
"language-preserving-for-instances" today, and under A it becomes so — the
docstring should say which condition makes it true.

## 9. Reproducing all of it

```bash
zzz_current_work/260807-pda-linearity/run_all.sh      # everything, all variants
uv run python .../gate/probes/repro.py      [today|off|nullable]   # the ten-char repro
uv run python .../gate/probes/gate_dump.py  [today|off|nullable]   # every attempt gate
uv run python .../gate/probes/shapes.py     [today|off|nullable]   # what the pass rewrites
uv run python .../gate/probes/corpus.py     [today|off|nullable]   # route + timing, all ten
uv run python .../gate/probes/cost.py       [today|off|nullable]   # what the fix costs

PYTHONPATH=zzz_current_work/260807-pda-linearity \
  tools/guarded.sh 8G 1800 -- uv run pytest tests/ -q -n auto -p relaxnull
```

`variants.py` holds the three relaxation bodies and patches
`passes.relax_non_semantic` in place; `relaxoff.py` / `relaxnull.py` are the
pytest plugins that do the same for a suite run. Nothing writes to `src/`.

---

## 10. Review — the opsis-radical session's take (appended after independent verification)

Spot-checked before opining: `repro.py today` reproduces (including `a ::= bc`
forking as the genuine ambiguity) and `corpus.py nullable` reproduces (all ten
ride the PDA, round-trip holds, vyx 0.028s). Endorsed, with four notes:

1. **A is right, and for a sharper reason than the ε-equivalence alone**: the
   pass entangles two jobs — model-shape ergonomics (absence instead of
   empty-noise nodes; legitimate, and free exactly when the noise is nullable)
   and language editing (never legitimate). A keeps the first and drops the
   second; B throws away the free half for purity. The rejection of C is this
   repo's own no-privileged-formulation law applied correctly.
2. **Sequencing the seam**: land A with `nullable_names` exported from
   `lexic.parsing` (the `lift_optional_nullables` precedent); treat the
   `ir/grammar/` move as a separate cleanliness effort — it means rewriting a
   fixpoint into the strict tier's idiom, and the 163× win should not wait on
   a style migration.
3. **A gap in the plan's day-one costs**: CLAUDE.md's Directives section
   documents the current behaviour verbatim ("their refs get min=0") — under
   A that sentence is false for non-nullable targets. Add: CLAUDE.md, the
   wiki, and the doc-drift test, alongside re-stating the three pinned tests
   to assert BOTH halves (the required half is now the load-bearing one).
4. **D's cheaper partial has constitutional weight**: "the fork islands the
   undecidable span instead of failing the whole document" aligns with the
   standing escapes-are-islands ruling — it is not merely an optimisation
   candidate. Keep it unbundled, but rank it accordingly.

The ruling itself is the user's, once, out loud: A narrows the accepted
language of any grammar with a non-nullable non-semantic rule (c.gbnf's `'ab'`
goes from silently accepted to refused). This reviewer's position: that is not
the cost of the fix — it IS the fix; the current behaviour is the engine
second-guessing an authored quantifier, which the repo's first principle
forbids.

---

## 11. What landed (solution A, per the §10 review)

**`src/lexic/compile/pipeline/passes.py`** — `relax_non_semantic` narrowed to
one line, `targets = ast.non_semantic & nullable_names(ast.rules)`, solved on
the incoming grammar. Docstring rewritten to carry the ε-equivalence, the GBNF
case, and the self-fulfilling-fixpoint trap; the module header no longer claims
all three rewrites are language-preserving unconditionally.

**`src/lexic/parsing/__init__.py`** — `nullable_names` exported (review note 2:
the `lift_optional_nullables` precedent; the `ir/grammar/` move is deferred as
a separate cleanliness effort, not a blocker on the 163×). Named in the module
docstring beside the engine floor, with its reason.

**Tests re-stated to assert BOTH halves** (review note 3). In
`passes_cases.py`, every `ws` fixture that meant to exercise relaxation is now
genuinely nullable (`" "*` not `" "+`) — five cases were passing for the wrong
reason once the pass narrowed. Three cases now stand where one did:

- `test_relax_sets_min_zero_on_nullable_noise_refs` — the ergonomic half;
- `test_relax_keeps_refs_to_required_noise_rules` — **the load-bearing half**,
  the one this bug needed and nothing pinned;
- `test_relax_reads_nullability_from_the_incoming_grammar` — pins the trap: a
  noise rule the pass would itself make nullable does not thereby license
  relaxing refs to it (the exact `n ::= nunit+` / `nunit` shape).

`test_clones.py` — `PINNED_CLONE_COUNTS["c.gbnf"]` 69 → 75.

**Docs** (review note 3): `CLAUDE.md`'s Directives section no longer says "their
refs get min=0" flat; `.wiki/lexic/codegen.md`'s pass bullet carries the
condition and its reasoning; `.wiki/lexic/decisions.md` gains *"A codegen pass
may not overrule an authored quantifier"* with the accepted cost and the
still-open per-site question; `.wiki/log.md` logs it.

**Gates, all green:** `tools/run_checks.sh` exit 0 · full suite 3776 passed,
8 skipped · parity differentials + property suite 141 passed ·
`tools/check_generated.py` CLEAN (49 modules, 0 pyright errors) ·
`tools/run_examples.sh` exit 0.

**Verified after landing:** all ten ground-truth grammars ride the PDA with no
resolver, round-trip holding — vyx **4.451 s → 0.029 s** measured against the
`unconditional` variant on the same machine, same run.

**Not done, deliberately:** solution D (per-site attempt licences, and islanding
the undecidable span rather than failing whole-document). Review note 4 ranks
the islanding half as constitutional rather than optional — it follows the
standing escapes-are-islands ruling. Unbundled, still open.

---

## 12. Is solution D worth doing? — the premise, measured

Before building D, the same question the relaxation fix earned: **does anything
real still take the slow road, and what does it cost there?**

`forkcount.py` (a pytest plugin that tallies `PdaFail` / `ProbeFork` by raise
site — patching `__init__` on the existing classes, never substituting
subclasses; a sibling subclass breaks `except PdaFail` and 51 tests with it)
over the whole suite:

```
PdaFail        6321      ← overwhelmingly the attempt machinery's own control
ProbeFork         9         flow: a sub-run fails, the loop closes. Expected.
```

**Nine forks in 3,776 tests, and all nine are the same subject:** vyx.gbnf as an
*instance* grammar — pipe-list values (`|a|b|c`) and dict-defs (`D:col{a=1 b=2}`),
raised at `runtime/kernel/kernel.py:341` and `:563` (the runtime's attempt/probe
decisions — a different site from the metagrammar's flat `GATE_ATTEMPT`). No
other grammar in the corpus forks at all any more.

Then the cost, which is a question about SIZE, not count — `probes/scaling.py`
grows a vyx block body of real corpus lines and times the public parse against a
non-forking body of the same size:

```
 lines   chars     forking body        plain body
     1      29   fallback  0.003s     PDA  0.000s   ×8
     8     135   fallback  0.007s     PDA  0.001s   ×7
    32     495   fallback  0.024s     PDA  0.003s   ×8
```

**A flat ×7–8, and it scales linearly.** That is the finding that decides D. The
~n³·² blowup measured earlier was specific to the *metagrammar* — a dense
grammar where chart density compounds. On vyx the fallback is a constant factor:
the chart stays sparse, so a fork costs a multiplier, not an explosion. A
10,000-char vyx packet full of dict-defs extrapolates to ~0.5 s against ~0.06 s
— worth having, nowhere near the 163× superlinear prize solution A carried.

**Recommendation: not now.** Three reasons, in order of weight:

1. **The prize is a constant factor on one grammar's constructs.** A was 163×
   and superlinear on every grammar read through the metagrammar. D is ×7–8 on
   vyx packets that contain pipe-lists or dict-defs. Real, bounded, not urgent.
2. **D's first half fights a deliberate, measured decision.** Per-site attempt
   licences mean per-site clones, and `_spec_ruleref` records why there is
   exactly one: per-tail clones made every `(rule, pos)` re-attempt a fresh memo
   key — *60% of all sub-runs on the vyx corpus*. Reversing that trades a
   measured cost on the common path for a measured gain on the rare one, and
   nobody has measured the trade. That is its own investigation, not a fix.
3. **Scope.** This is an ergonomics effort with a live ladder (rung 2's second
   half). D is a lexic engine effort and belongs in its own directory with its
   own gate.

**What would change the answer:** evidence that large vyx packets carrying these
constructs are a real workload. The forks are on vyx's *own* common syntax, so
if packet bodies grow, the ×8 starts to matter. That is a vyx question, not a
lexic one.

**If D is built, build only its second half first** — island the undecidable
span instead of failing whole-document. It is the review's constitutional half
(escapes are islands), the island machinery already exists (`runtime/islands.py`,
`island_tables`, the delegate compile), and it collapses the ×8 without touching
the clone-identity decision at all. Half one can then be judged on what is left.
