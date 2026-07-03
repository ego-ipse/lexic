# Engine optimization — investigation findings & ranked plan

Follow-up to `Disputed.md` (all claims verified 2026-07-03; full-vs-subset
regression confirmed grammar-driven, prediction-cost mechanism confirmed).

## Where the noise knowledge actually lives today (3 disconnected places)

| layer | mechanism | reaches the engine? |
|---|---|---|
| user grammar source | `@non-semantic` directive (`ir/directives.py`) | **No.** Flows only into `derive_specs` → `RuleSpec.non_semantic_fields` (semantic_dump filter) + min=0 ref relaxation. Semantic layer only. |
| self-grammar parse (`parse_grammar`) | `Reducer.noise` IrMap (`ABNF_NOISE`/`GBNF_NOISE`, DROP per rule) | **Yes, partially.** `collapsed_tables(reducer, g)` collapses noise runs — but only single-char-unit star/plus shapes (see below). |
| instance parse (`CompiledGrammar.parse`) | — nothing — | **No.** `parse_first` runs plain `compile_tables`; zero collapse, zero noise knowledge. |

So: directives are *metadata about* noise, not the below-chart mechanism.
The below-chart machinery **does already exist** — `parsing/lexruns.py`
(`RunTerm` maximal-munch collapse with three proofs: fixed charset,
derivation uniqueness, FOLLOW disjointness) — but it is:

1. **Shape-limited**: only synthetic `*`/`+` runs whose unit is a
   single-char charset collapse. ABNF's `comment = ";" ... CRLF` inside
   `c-nl`/`c-wsp` is a sequence, so the entire comment/newline noise layer
   stays per-char in the chart.
2. **Not wired into `Parse`/`ParseFirst` at all** — only `Recognize`
   (maximal) and `ParseReduced` (reducer-checked).

## Measured facts (disputed corpus, 920 chars, reducer-collapsed tables)

- Full grammar: **26.3 items/char**; subset: **12.2** — the 2.16× item
  blow-up fully explains the wall-clock 1.7×.
- Noise machinery (`wsp`/`c-wsp`/`c-nl`/`crlf`/`SP`/`LF`/`endrule`/
  `comment`): **27 % of all items** — on a corpus with zero comments.
- `num-val` family (`%d`/`%b`/`%x` alternatives): **13 %** — on a corpus
  with almost no `%x`.
- **31 % of all chart items are dead on arrival** (the symbol after the dot
  cannot start at that input position); 6 641 of 7 622 DOA items are
  predictor-seeded dot-0 items. This *undercounts* the waste: each dead
  dot-0 item also triggers the prediction cascade of its own first symbol.
- 10 run candidates prove on the full grammar; 8 survive the reducer check;
  recognition (maximal, 10) is barely faster than reducer-collapsed —
  **run collapse is exhausted; prediction is the remaining cost.**
- Instance side (arithmetic.gbnf, 504 chars): plain kernel 10.4 ms vs
  maximally-collapsed 7.6 ms (**1.37× left on the table**); and
  `CompiledGrammar.parse` total is 19.4 ms — **FastTree + ModelFold is
  ~46 % of instance parse time** on top of the kernel.

## Ranked plan

### 1. FIRST-gated prediction (biggest win, engine-general)

In `Kernel._close`/`_seed`: before seeding rule `rid` at column `i`, test
`text[i] in FIRST(rid)`; per-arm refinement: seed only dot-0 arms whose
arm-FIRST contains `text[i]`. The FIRST computation already exists
(`lexruns._Analysis.first`) — hoist it into `ParserTables` at compile time
(per-rule/per-arm frozensets), so the kernel pays one set-membership test
per predict. Kills ≥31 % of items *plus their cascades* on the full ABNF
grammar; benefits every grammar including instances. Stays inside the
compiled-tables/kernel design (no per-parse allocation, no free functions).

**Correctness care:** a nullable rule must still be predicted (Aycock-
Horspool advance + its empty completion's SPPF provenance) even when
`text[i] ∉ FIRST` — filter only non-nullable rules/arms, or seed just the
empty-deriving arms on a FIRST miss. Poisoned FIRST (charset too large) ⇒
never filter that rule. Leo is unaffected (fewer items, same chains).

### 2. Wire run collapse into the instance path

`ParseFirst` runs plain tables today. Mirror `reduce._run_mode` with a
ModelFold-side check: a proved run may collapse iff its unit leaves carry
no `RuleSpec` and no wrapper rule — then the run lands as one multi-char
str leaf, which `_subtree_text` already handles. Noise (`@non-semantic`)
rules must stay text-preserving (round-trip fidelity: `to_text()` must
reproduce ws), so instance runs are RUN_STR-like, never RUN_DROP —
chart work still collapses, text survives as a leaf. Measured ceiling:
1.37× kernel on arithmetic.

### 3. Generalize RunTerm → noise skip-machine (the true `%ignore` parity)

The 27 % comment/newline noise layer can't be a charset run, but every rule
in it is reducer-DROPped — no tree shape needs reconstructing, only
language preservation + no ambiguity leak (the same licence
`recognition_tables` already exploits). Compile the noise sub-grammar
(rules transitively reachable only from DROP roots) into a small scanning
automaton as table data (`';' [^\n]* CRLF` is regular), guarded by the same
FOLLOW-disjointness proof. This is the Lark-lexer-parity endgame; bigger
job, do after 1–2 land and re-measure — 1 may already pay most of it
(comment arms die at predict time when `text[i] != ';'`).

### 4. models.py wrapper diet (fold into the codegen refactor)

Every field-bearing item becomes a `<rule>--f<idx>` wrapper rule — an extra
rule + completion layer per field. FastTree+ModelFold ≈ 46 % of instance
parse time. Candidates: skip wrappers for unquantified single rule-refs
(the child subtree is already a structural boundary); resolve fields from
arm dot-positions instead. Belongs in the upcoming codegen rework, not a
standalone change.

## Old-shim cleanups noticed on the way (not perf)

- `ir/directives.py` docstring still explains itself in terms of *Lark's*
  `%ignore` — stale since the 2026-07 cutover.
- `ir/emit.py` (`render_specs`) is dead code — consumed only by its own test.
- `utils/quantifiers.py` — already flagged in CLAUDE.md; consumed only by
  `codegen/aliases.py`; goes with item 4.

## Expected outcome

Item 1 alone should pull the full-grammar product path from 26 µs/char
toward the high teens (items/char ceiling ~18 from DOA removal alone,
cascades extra); items 2–3 close the remaining gap toward the subset's
12 items/char. Engine mechanics need no rework — this is all compile-time
table enrichment plus one gate in the predictor.
