# Log

## Parity is raw model equality, and ruling 1 is retired

The PDA and the Earley engine must build the same model field for field.
`deep_semantic`, which drops `semantic=False` binds at every level, is no longer
the bar — it passed whether or not the engines agreed, so it could not be the
test for a requirement that they do.

Ruling 1 had licensed the disagreement, and it lived only in a test module's
docstring. That is why it survived a month without being a decision anyone could
look up. `.wiki/lexic/decisions.md` now carries it.

What made the stricter bar affordable was separating a *split* from an *arm
choice*. A split is one production carved two ways — same arm, different
boundary — and it has a defined answer: the first slot owns the text. An arm
choice is two different productions, and that is still refused. `is_arm_choice()`
in `parsing/earley/kernel/tables/splits.py` is the structural test. Once both
engines resolved splits identically, the semantic licence had nothing left to
excuse; it had been hiding 47 of 200 JSON inputs, the same characters landing in
different `Ws` fields.

Ambiguity is still refused by default. A caller may supply a deterministic
resolver, whose behaviour is the caller's concern — not a fallback, not a flag.

## Ambiguity is about values; directives are not a line-comment privilege

Two derivations that build the same VALUE are not an ambiguity. The decision
moved to `parsing/earley/kernel/ambiguity.py`, where the island sub-parse and the
reduce path both reach it — the reduce path used to count derivations, which
left the EBNF flavour with no working Earley fallback at all (its self-grammar
has adjacent nullable `ws` slots, so every whitespace-carrying file derived two
ways, reduced to one value, and was refused).

`same_value` is type-aware and structural: bare `==` calls `IrStr("a")` and `"a"`
equal, and calls a NaN — or any class that never defined `__eq__` — different
from itself. A type that declined to define equality has declined to answer.

Separately, `@directives` stopped being a privilege of surfaces that happen to
have a line comment. ISO EBNF has only `(* *)`, so directive parsing had been
disabled for every EBNF grammar; `json.ebnf` therefore could not mark `ws`
structural, compiled it as a fail-island, and escaped to Earley on EVERY parse.
A flavour now declares whichever comment form it has. All three JSON
formulations compile to byte-identical clone tables.

`Vocabulary` and `Directives` put both on the public entry points.

See `lexic/decisions.md` for the reasoning and `lexic/public-api.md` for the
surface.

---

## Compiled payloads: a parsed VALUE as an importable module

`compile/payload/` writes whatever lexic parsed as a module — four flat literals
(`TYPES`/`ORIGINS`/`STRS`/`NODES`) plus an import of the reader emitted beside
it. `export_value(value, path, *, module=None)` is the entry.

Three targets, `classes` / `ir` / `plain`, are **one projection over one symbol
table**, decided by the codomain of the reduction that produced the value —
there is no target parameter. A `plain` payload reads back with zero lexic
modules imported.

The reader is lexic-free, and emitted **once per directory** as
`payload_reader_<tag>.py` where the tag is the digest of its own source, so an
artefact cannot bind to a different reader. At import an artefact checks a
digest over its tables, a shape digest over the RULES its symbols carry, and —
for a symbol carrying no rule — the module it came from.

`compile/writer.py` is now the single last step for both exporters: it renders
tables through the layout algebra, validates, byte-compiles and lands the module
so its source and `.pyc` can never disagree. The twin exporter's export gate
reads its `GRAMMAR` structurally instead of splitting the source text.

Wiki: [[lexic/generated-modules]] (the artefact, the targets, the writer),
[[lexic/public-api]] (`export_value`), [[lexic/decisions]] (target inferred not
flagged; the `.pyc` at export; no regex engine in `src/`; sharing keyed on
identity), [[lexic/invariants]] (module/`.pyc` agreement; refuse rather than read
wrong; a memo key is valid only while something holds the object).

---

## Segmentation gains an open model; the emit source stops carrying ids

`IrSegmenter` joins `IrPretoken` and `IrNormalizer` as an open role: the
segmentation MODEL was a two-way branch on `ranks` inside the spine, which
is why families like Unigram and WordPiece could not be expressed at all.
The builders now name the model they already knew, and `with_segmenter`
attaches one declared elsewhere. See [[tokens]].

**Resolution is for matching, not for meaning.** Binding a vocabulary used to
rewrite the canonical AST and each class's `__grammar__`, so `to_grammar()`
emitted ids where the author wrote spellings — lossy on every bound token
grammar, against the canonical-grammar invariant. The engine gets the
resolved form; nothing that carries meaning back to a user does.

Also: `universe` is inclusive everywhere ([[tokens]]); what a vocabulary
cannot carry is skipped at seeding so neighbours merge across the gap; and
`lexic.api` readers refuse settings they cannot honour, judged by whether the
setting changes the result rather than by whether it is set.

## Vendor formats moved out of `ir/`; readers get a home

`ir/encoding.py` had modelled one vendor's tokenizer pipeline directly — a
hand-implemented GPT-2 pattern, its byte table, and node types named after
that vendor's stages. The spine now keeps only `IrPretoken` (the concept);
the format's vocabulary lives in `lexic.api.pretokens` beside its reader.
New invariant in [[invariants]]: **no third-party format, product or model
name appears in `lexic.ir`**, enforceable by grep. Rationale in
[[decisions]].

New package `lexic.api` — readers for third-party formats, taking the
grammar+reducer that parse a document as parameters so they privilege no
formulation. Fetching lives outside the shipped package in `ext/API/`; see
the get / read / model split in [[architecture]].

Also: `IrSelf.ensure` (the boundary narrow, [[ir-shapes]]) and
`CompiledGrammar.bind` + `TokenBinding` ([[public-api]], [[tokens]]).

## 2026-07-25 — Tokens: the encoding family, token terminals, generation masks

An encoding now gives a char class's ordinals their meaning — `IrEncoding`
with `universe`/`resolve`/`spell`/`boundaries`/`ids` and a derived
`tokenize`, in three peers: `IrUnicode` (the default; ordinals ARE code
points), `IrUtf` (UTF-16 code units, owning surrogate-pair combining and the
JSON reducer's unit decode) and `IrTokenizer` (vocab ids; `ranks` stored,
ordered merges derived at emission, exact ranked-merge BPE via a heap
agenda). A tokenizer is a peer of Unicode, not a special case: everything
UTF-specific is an `IrUnicode` property rather than an assumption in the
set-math.

Grammar surface: a token terminal is `IrAlphabet(encoding_name, inner)`
reusing `IrLiteral`/`IrCharClass`/`IrNot`, with negation INSIDE the alphabet
so the encoding governs the complement universe. No token-specific leaf type
exists. `concretize` resolves spellings to ordinals against a registry.

Three capabilities: read/emit with no tokenizer; parse instances
(`TokenKernel` scans id-granular at boundary columns — token terminals island
the PDA by construction, so char grammars' hot path is untouched); and
constrain generation (`TokenMaskCursor`, an ABC over `TokenTermCursor` /
`CharTrieCursor`, holding ONE live chart so `push` grows it instead of
reparsing the prefix).

Two engine constraints found and pinned: run-collapsed tables cannot be
resumed (maximal munch depends on input not yet appended, so a committed run
can never grow — `extend` refuses loudly), and a FRESH empty parse
under-reports viability because its seeds are FIRST-gated on the absent next
char, so it must not be used as a viability oracle.

Boundary: token spans are char-aligned; under a byte-level pipeline a token
may end mid-code-point and so carries no span, though `tokenize()` still
returns its id. A byte-column engine is a separate unmade decision.

New page: [[lexic/tokens]].

## 2026-07-24 — Packing tiers: input-sized origin-bits, tier selection at the parse entries

The packed-item scheme's origin bits are now a per-tables tier instead of a
module constant: `Packing(bits, mask, advance)` rides on
`ParserTables.packing`, every table builder takes a `bits` parameter with a
per-`(identity, bits)` memo, and the parse entries pick the smallest tier of
`TIERS = (28, 40)` covering the input (`tier_for`). Islands inherit the
run's tier (`PdaTables.island_tables(name, bits)`); the model product keys
its cache 3-way `(grammar, fold, bits)`; the reduce product stays tier-free
(its Earley completion picks per parse); the kernel capacity raise remains
the backstop beyond the last tier. The kernel holds no copied tier fields —
hot methods hoist `tables.packing` locals at method top. Also: the per-char
scanning caches (`terms_for`/`char_leaf`) moved from `ParserTables` onto
`TermTables` (they read `terms.atoms`), and `token_model` gained a
per-`(grammar, bits)` tables memo (it had been recompiling per call —
`normalize` mints a fresh IrAst). See [[lexic/architecture]].

## 2026-07-21 — GBNF charclass PDA regression fixed; reduce completion unified; module self-grammar zero fail-islands; per-parse interning

GBNF charclass parsing (`grammars/gbnf.py`) had regressed to superlinear
scaling — its range-tail choice fell back to a full Earley completion on
every hit because no gate could separate the arms with a single-character
FOLLOW set. Fixed two ways: the charclass grammar factors the "is this a
range or a trailing dash" choice into one empty-arm rule (the earlier
`cc-range`/`cc-range-nc` pair deleted), and the PDA analysis gained bounded
FOLLOW-k lookahead windows (`extend_follow` generalized from a single
CharSet to a k≤3 window tuple, computed lazily) that can now separate it.
GBNF self-grammar-text parsing returns to flat µs/char scaling. See
[[lexic/decisions]].

The grammar-text reduce completion (`parsing/products.py`) now always runs
against the SAME lifted/normalized grammar the PDA path compiles against —
the earlier two-route split (an unlifted completion kept only for a
differential comparison) is gone; the differential property tests exercise
the actual product route.

The generated-module self-grammar (`compile/module/selfgrammar.py`) reaches
zero fail-islands: splitting six token rules' trailing whitespace into a
dedicated fold-transparent rule and spelling the grammar-statement's
trailing newline explicitly closes both the last identifier-shaped
fail-island (a bare rule name no longer forces the Earley completion) and
the leading-indent-after-`__binds__` gap noted below. `m-imports` remains a
benign non-failing once-per-file island; the vyx inline-mode self-verify
that motivated this work goes from ~13s to ~0.13s. See
[[lexic/generated-modules]].

Instance parsing gained a per-parse intern memo on the PDA's trusted
construction path (records/leaves built identically more than once within
one parse construct once) plus a fast path for single-item `value_str`
rules. See [[lexic/decisions]] for the measured perf ceiling this and
further micro-optimization run into — reaching well past it needs a
structural (model-count) change, not yet built.

## 2026-07-18 — flavour-layout: width-aware emission + production EBNF

Emission is width-aware end to end: `ir/layout.py` doc nodes double as
action-body templates (`IrLine` identity eval, `IrGroup`/`IrNest`
rebuild-around-interior) and `IrDocConcat`/`IrDocJoin` are the doc-tier sums
of `IrConcat`/`IrJoin` — flavour STRUCTURE actions build docs, atoms stay
str-tier, `IrFlavour.apply(root, width=88)` renders (`width=None` = flat,
byte-identical to the old output). Trailing-pipe/-slash continuations; ABNF's
wrap IS RFC 5234 folding. `to_grammar(flavour, width=88)`. The exporter
docstring wrap moved onto the algebra (per-word fill groups). ABNF gained
`%d`/`%b` dot-sequences, uppercase marker letters, and `ABNF_CORE_RULES` —
the RFC 5234 B.1 prelude injected by dangling-ref resolution only (new
`IrFlavour.core_rules` + `parse_grammar` closure). NEW `grammars/ebnf.py`:
the production ISO-family EBNF flavour (exact `n * x` repetition; classes
expand to quoted alternations; `IrNot`/open-counted refuse), registered with
`.ebnf`; manifests now all generate from shipped singletons; GT corpus gains
`json.ebnf`. Selfgrammar PDA gating fixed (no rule ends on a loop; body lines
FIRST-disjoint) — vyx inline verify 35.7s→13.1s; residual: the notation
`name` fail-island forces the Earley path for every embedded value (backlog).
See [[lexic/flavour-system]], [[lexic/generated-modules]].

## 2026-07-18 — module-selfgrammar complete (whole-file parse-back)

`compile/module/selfgrammar.py`: lexic parses its own exported twin modules —
`module_grammar()`/`parse_module()`/`verify_module()`, the L2 binding
cross-check running per export in `tools/check_generated.py`.
`compile/foldkit.py` (ALT/passthrough) — the build-path unification seed,
shared by notation + selfgrammar. Export renderers publicized
(`field_type`/`value_str_type`/`docstring_lines`) as the exporter↔verifier
contract. See [[lexic/generated-modules]] §module self-grammar. Next:
`260718-flavour-layout` (compile/ restructure = its Task 0).

**When to load:** checking what changed recently; orienting after a gap in the session.

Append-only chronological record. Most recent entry at top.

---

## 2026-07-18 — generated-files: importable twins, IR-native formatting, renames

The 260718-generated-files effort (plan in `zzz_current_work/`), landed on
top of Task 0 below:

- **Defaults-last field order** (`bind_fields`): required fields first,
  `= None` optionals after, each group in item order — the record ctor is
  well-formed; naming/collision numbering unchanged (item order). Zero
  tests pinned the old order; slot-keyed consumers unaffected.
- **`ir/layout.py`** — the layout algebra (Wadler doc combinators on the
  spine; continuation-aware `fits`). **`emit_ir`** — the notation emit
  half in `compile/notation/parse.py` (per-tier `IrTypeMap`; the inverse of
  `load_ir`; spine gained `IrNamedTuple.repr_args`, the shared elision).
  Ruff/subprocess deleted from the compile path.
- **Exported twin modules** ([[generated-modules]]): `export_module`/
  `export_source` (explicit-path-only writes, `inline_tables` option),
  `bind_module` (import-time table attachment), `CompiledGrammar` moved
  to `compile/artifact.py` (+ `flavour`/`stem`), reserved class names
  trimmed to the real header. `tools/check_generated.py` is the corpus
  tool-clean gate (pyright/pylint default configs).
- **Engine fix — island valid-prefix window truncation, made SOUND (two
  passes)**: a 256-window cut mid-token can complete a truncated-but-valid
  island parse short of the edge. Pass 1 (fail-soft): the wrong splice's
  fold error reroutes (`islands.island_value` LexicError→PdaFail;
  `build.finish_delegate` declines). Pass 2 (soundness):
  `Kernel.can_extend_at` — a short-of-edge column's chart is complete
  evidence for its own window char (seeding is FIRST-gated by it), so
  refusal is sighted; delegate-landing columns (derived from
  `Kernel.delegated` handles) and out-of-domain chars answer MAY —
  and `islands._may_extend` grows on no-completion/edge-touch/probe-MAY,
  terminating at window ≥ remaining where truncation is impossible.
  Verified correct with ALL fail-soft guards disabled. Fixpoint-style
  growth is UNSOUND (balanced-paren counterexample) — don't reintroduce.
  Regression: `test_island_valid_prefix.py` (islandhood asserted). The
  notation grammar still refuses trailing commas — now purely a perf
  choice (arglist would island).
- **Renames**: `base.py` → `model.py` (location right — the
  to_grammar→grammars edge pins it out of ir/); `parse.py` DELETED —
  `parse` is the engine's name; the compile one-liners are
  `parse_instance`/`parse_instance_from_path`.
- **Known engine-path divergence (recorded)**: on an ambiguous grammar
  (json's adjacent `ws?` slots) the PDA's greedy choice and Earley's
  `parse_first` can build text-equal but structurally different models
  (noise attachment only). `compare_bench`'s to_text gate is deliberate.

## 2026-07-18 — generated-files Task 0: dead-code sweep

`GrammarAuthoringError` deleted (`exceptions.py` — a never-raised public
stub; CLAUDE.md + [[error-vocabulary]] updated). `refs_in_order` deleted
(`ir/order.py` — production-dead public wrapper; the private
`_refs_in_order` walker stays, `RuleOrder.by_refs` uses it; its contract
re-pinned on `by_refs` in the test mirror). `_child_attrs_of` + the
derive-from-binds branch in `GrammarModel.__init_subclass__` deleted
(`base.py`) — proven dead: `IrNamedTuple.__init_subclass__` always sets
`_child_attrs` from annotations into `cls.__dict__` first, so the branch
never fired; models don't read `_child_attrs` anyway (`children()`/
`rebuild()` are overridden on `__binds__` item order, settled 13). Effort:
`zzz_current_work/260718-generated-files/PLAN.md`.

## 2026-07-18 — ir-native complete: compile/ subsystem, codegen + pydantic gone

The `compile/` package is the whole compilation subsystem. `codegen/` is
deleted; classes are synthesized at runtime via `type(name, bases, ns)`
(`compile/pipeline/synthesis.py`) with `__grammar__` + a `__binds__` table — no
source-emit / import / `model_rebuild`, no file write. pydantic is gone from
`src/` and from `pyproject.toml` (zero runtime deps bar the lazy `ruff`
exporter subprocess). `GrammarModel.model_dump` was renamed to `dump`
(no longer a pydantic override). Both `base.py` shims and the strangler
R0801 suppressions are removed; the schema-joint machinery is gone
(`FastCtor`/`build_validated` proven LIVE and kept). New surfaces landed
across the effort: `load_ir` (IR-constructor notation), `load_flavour`
(manifest → `IrFlavour`), `export_source` (reader `.py` view), the demo
EBNF flavour. Perf: `compile_text` −67…−79% vs baseline; parse +2…+8%.
Full record + commit chain: `zzz_current_work/260716-ir-native/PLAN_v4.md`
OUTCOME + `FOLLOWUP.md` + `NEXT_MILESTONES.md`.

**Wiki drift still to sweep** (flagged, not all fixed this pass):
`codegen.md` describes the deleted module (mark superseded → `compile/`);
`public-api.md` / `architecture.md` retain `codegen()`/`out_dir`/
`_NORM_GRAMMAR_CACHE`/"Pydantic classes" references. The high-traffic
`public-api.md` + `architecture.md` load-bearing entries are corrected in
this pass; a full page-by-page sweep of the remaining pages is a follow-up.

---

## 2026-07-16 — ir-native Task 1: GrammarModel is an IrNamedTuple record

`base.py` rewritten: models live on the record spine (PLAN_v4 ruling 9 —
models ARE IrSelf). Pydantic base, schema joints
(`__get_pydantic_core_schema__`/`_joint_dump`/`__schema_joint__`) and the
licence-refusal machinery are gone from `base.py`; the native
`model_dump()` is runtime-complete (ruling 12 — F-DUMP-1's declared-schema
erasure is gone) with an explicit-stack walk (depth-800 gated);
`semantic_dump()` keeps the top-level-only exclusion; equality is
type-aware + hash-consistent; `models`-mode lists coerce to tuples;
`children()`/`rebuild()` = bound fields in item order; `fast_construct()`
is always granted (one C-level tuple build). Binds channel: explicit
`__binds__` (primary) or one-shot `Annotated` resolution (emitter shim,
dies at the Task-2 flip, as does the no-op `model_rebuild()`). Goldens'
`runtime_dump`/`runtime_semantic_dump` keys are the parity gate (77/77);
`test_pda_parity`'s comparator became an explicit deep-semantic view —
the erasure had been silently hiding a licensed PDA-vs-engine noise-split
difference. Reserved-name window (rules named `eval`/`count`/… unmangled
until Task 3) pinned in `test_binding.py`. Details:
`zzz_current_work/260716-ir-native/TASK1_REPORT.md`.

---

## 2026-07-16 — vyx-parse effort closed: vyx.gbnf is a ground truth

`resources/ground_truth/vyx.gbnf` (92 rules) joins the corpus as a
first-class ground truth: golden-fingerprinted in
`test_gbnf_ir_equivalence`, unambiguous, emit-reparse stable; 130
integration tests in `test_compile_grammar_vyx.py` (compile, recognise +
`is_ambiguous` 0, byte-exact round-trip incl. non-ASCII content, an
enumerated exclusion ledger pinning pre-fix spec lines, and a file-level
`vyx-file` rule that round-trips all 61 vyx spec self.md files —
markdown-as-NL line capture; fence/section semantics live in the vyx-side
assembly layer by design). The vyx language decisions (V16–V25, V20
non-ASCII reversal) are recorded in the effort's FINDINGS; the vyx spec's
fragments were made honest vyx-side with an extractor parity gate
(assembled == pinned). Semantic layer scoped in the vyx repo
(`SEMANTIC_LAYER.vy`). See `zzz_current_work/260713-vyx-parse/PLAN.md`
OUTCOME + FOLLOWUP.md.

---

## 2026-07-16 — Char-class regex escaping: `-` added to `_CLASS_METACHARS`

`ir/nodes.py`: `_escape_regex_point` now escapes `-` inside `[...]`
(`_CLASS_METACHARS = "[]^-"`). Unescaped, a range whose LOW bound is `-`
(e.g. `[!&--.]` from `[A-Za-z0-9_.!&^-]`) reads as **set difference** in
pydantic-core's Rust regex whenever a lower-codepoint member precedes it —
the emitted `StringConstraints` pattern silently dropped members and
`value_str` classes rejected valid text (Python `re` only warns, so tests
built on `re` never caught it). Found by the vyx Task-3 round-trip gate.
Escaping the dash unconditionally is valid and position-independent in both
engines; grammar-text emission is unaffected (flavours spell classes via
their escape codecs, not `pattern()`), and no `CHARCLASS_NAMES` key contains
a literal dash member. Pins: unit (`test_charclass_pattern_dash_range_bound_
is_escaped`) + integration (`test_value_str_charclass_with_dash_range_bound_
validates`).

---

## 2026-07-16 — Schema expansion joints (pydantic depth cliff fixed) + all transformers on IrBottomUp

**Joints (user-ruled: fix, no depth guard).** pydantic inlines a completed
sub-model's core schema into its referrer (def-refs only for recursive
models; unfixed upstream through 2.14.0a1), so long acyclic ref chains built
chain-deep schemas and pydantic's recursive walks overflowed (~450 rules
even after leaf-first rebuild). Fix: `codegen/binding.py` computes each
rule's inlined-schema depth over the ref topology (`_schema_depths` —
cycle edges add nothing, they stay def-refs; `ir/order.refs_in_order` is the
new public edge extractor) and flags every 64th class along a chain
(`_SCHEMA_JOINT_STRIDE`, `RuleBinding.schema_joint`, emitted as
`__schema_joint__` ClassVar). `GrammarModel.__get_pydantic_core_schema__`
(base.py) returns, for a *completed* joint, a shallow
validate-through-the-class schema (`model_validate` + a `_joint_dump`
serializer threading the caller's options), so schema depth — and dump's
Python crossings — are bounded by the stride. Grammars under 64 rules
short-circuit to zero joints; 800-rule chains now compile/parse/round-trip/
dump/semantic_dump end-to-end.

**IrBottomUp everywhere (user directive).** `normalize._Minting`
(FlattenGroups/DesugarQuantifiers) and `passes._HoistTransformer` migrated —
no recursive IR transformer remains. Driver hardening for stateful bodies
and speed: children push reversed (left-to-right visit order — side-effect
order matches the recursive walks, so synthetic-rule numbering stays
compatible; sibling order preserved, nested-group mint order inverts
inner-first — nothing pins it), per-run body-resolution cache (a table miss
on the `IrThis` default skips the eval call), identity-preserving rebuild
(unchanged nodes are reused, compared by child identity — never structural
equality, which would be quadratic), kids carried in the stack frame
(`children()` once per node). Perf gate met: passes+normalize micro-bench
0.479s → 0.520s in isolation, but END-TO-END cold `compile_text` over all
ground truths is *faster* than the pre-change baseline (0.63s → 0.61s; the
identity-preserving rebuild and the joint early-exit dominate). Suite 2255;
gate exit 0.

---

## 2026-07-16 — IrBottomUp: iterative post-order transformer; canonicalize is depth-safe (L7a fixed)

New dispatch preset `IrBottomUp(IrTransformer)` in `ir/walk.py` (re-exported
from `lexic.ir`), the user-ruled fix for L7a (~300 nested inline groups
overflowed `canonicalize`'s recursive walk). `IrDispatch.apply` now routes
through an overridable `_run` strategy (the `IrReturn` catch stays in one
place); `IrBottomUp._run` drives an explicit work stack: children transform
first, the node rebuilds via the `children()`/`rebuild()` protocol, then its
action body runs on a node whose children are already final (they also ride
the `nc` channel). Bodies are pure per-node combiners — NO `d.eval` recursion
— and the table-miss default is `IrThis` (the driver's rebuild IS the
identity). Shared subtrees transform once (id-memo). Trade-off, documented on
the class: every node is visited, so the preset fits whole-tree normal-form
passes, not selective/pruning rewrites (those stay on `IrTransformer`).

`ir/canonical.py`'s `_CANON` and `_RENAME` migrated: `_canon_alternation`/
`_canon_sequence` dropped their child-eval loops; `_canon_not` gained a lift
for a pre-collapsed operand (bottom-up canonicalises the inner class first,
so `[^a]`'s single-member operand arrives as a one-char `IrLiteral` — it
lifts back to a class so rewrite 4 still yields positive spans; without this,
`IrNot` would leak past canonicalization). Byte-compatible output — the full
suite passed unchanged.

Depth math after the change: single-arm nesting collapses inside the
iterative walk (300-deep repro round-trips); multi-arm nesting hoists into
rule chains (verified 450) and so rides the L7b iterative paths; the
remaining wall is pydantic-core's `_schema_gather` on ~500-rule ref chains
(third-party, documented in FINDINGS L7). Repro
`repro_deep_grammar_recursionerror.py` exits 0. Pins: `test_walk.py`
IrBottomUp section (2000-deep), `test_deep_grammar.py` nested-groups
round-trip. Candidates for later migration to the preset: the hoist
transformers (`codegen/passes.py`), `normalize` — none currently
depth-threatened post-canonicalize.

---

## 2026-07-16 — Adversarial sweep round 2: codegen cycles, reserved names, depth bombs, cache keys (L5–L8)

Four findings from the Fable adversarial sweep, three fixed same-day
(FINDINGS L5–L8 in `zzz_current_work/260713-vyx-parse/`):

**L5 — unit-arm cycles** (`codegen/binding.py`): `s ::= s | "a"` emitted
`class S(S):`; mutual unit arms emitted circular inheritance — both died with
NameError at module exec. New `_break_cycles` (over a cycle-tolerant
`_reach_closure`) runs before MRO ordering: intra-cycle parent edges drop
(members become siblings), a cross-cycle edge widens to the target's whole
cycle, so every concrete arm subclasses every cycle member and `isinstance`
holds for fields typed with any of them.

**L6 — reserved rule names** (`codegen/binding.py`): rules named
`import`/`class` emitted SyntaxError modules; `to-text` emitted a field
shadowing the method (TypeError); `annotated` shadowed the header's
`typing.Annotated` and broke every later annotation resolution. Field names
now mangle via `_RESERVED_FIELD_NAMES` (keywords + `BaseModel` surface +
`GrammarModel` methods) and class names via `_RESERVED_CLASS_NAMES` (the
emitted header's bindings), both `_`-suffixed (the `True_` precedent) and
drift-pinned by tests (the pin immediately caught `fast_construct`).

**L7 — deep-grammar depth bombs**: the 300-rule unit-ref chain died twice —
pydantic `model_rebuild` recursing across the model chain (fixed: leaf-first
rebuild order, `codegen/__init__.py::_rebuild_leaf_first`) and the PDA clone
compiler recursing per chained rule (fixed: `_PdaCompiler.ensure_rule`
enqueues and the outermost call drains a work queue — constant stack depth,
callers' fully-compiled-on-return contract unchanged;
`islands`/`fail_islands` became properties over the analysis). Residual:
leaf-first is a marginal bound — pydantic-core's `_schema_gather` still walks
the full nested schema, so depth 320 round-trips but ~500 overflows inside
pydantic (a pydantic-internals fix or a domain depth cap is a user ruling,
same bucket as case A). **Case A —
~300 nested inline groups → RecursionError in `ir/canonical.py`'s
`_canon_alternation` ↔ `_canon_sequence` — is DEFERRED**: every IrDispatch
transformer shares the recursion-by-design shape (action bodies own
recursion), so an iterative driver / ir-level trampoline is a design ruling,
not a sweep patch. `repro_deep_grammar_recursionerror.py` stays as its pin.

**L8 — cache_key staleness** (`compile.py`): an explicit `cache_key` was used
as-is, so one key + different grammar text silently served the first
grammar. The content key is now always folded in
(`(cache_key, stem, flavour, out_dir)`).

Clean bills from the sweep (fuzzes found nothing): derivations/is_ambiguous/
strict-parse consistency (60 grammars × 8 inputs), full-pipeline round-trip
(240 generated samples), PDA-vs-Earley differential, maximal-munch backoff,
ABNF `%i` + `=/`, degenerate grammar texts, deep input on both engine paths.
New adversarial pins: `test_unit_arm_cycles.py`, `test_reserved_rule_names.py`,
`test_deep_grammar.py`, `test_compile_cache.py`. Suite 2236; gate exit 0.

---

## 2026-07-16 — Engine bug sweep: L4 Leo mixed provenance, left-recursion islanding, stack-safe emitter, tests/adversarial/

**L4 (embedded-ambiguity undercount) fixed.** A Leo top can carry *mixed
provenance* — some SPPF families recorded by the normal completer (a later
completion of the same rule found ≥2 waiters), others deferred in `leo_links`.
All three decoders (`Kernel.to_chart`, `FastTree._step`,
`FusedReduce._collect`) gated `expand_leo` on `key not in links`, silently
dropping the deferred families whenever any completer family existed
(`p ::= u u*; u ::= [ab]+` over `"aab"`: 4 derivations at `start=p`, 2 when
embedded under `w ::= p`). Fix: expand on `leo_links` presence, never gate on
`links` — `expand_leo` is idempotent (families dedup); invariant documented on
`expand_leo` itself. Leo stays engaged on every fast path. Probe4 4/4.

**Left recursion now islands structurally** (`pda/analysis/leftrec.py`, new).
A predictive descent cannot run left recursion — it re-enters the rule at the
same position before consuming; no gate family can license it. Previously left
recursion islanded only *by accident* (the recursive arm's FIRST always
overlaps a consuming escape arm's FIRST ⇒ arm conflict), so a nullable-only
escape arm (`root ::= root "a" | ""`) or sole-arm degenerate (`x ::= x "a"`)
compiled to a clone and the PDA descended forever. `left_recursive_names`
(nullable-prefix left-corner transitive closure; leaf module, Any-typed
analysis oracle, open IrTypeMap dispatch) feeds `_classify`, which files a
hard conflict note and skips all other classification for cycle members — the
rule islands, the Earley island sub-parse handles it natively.

**`GrammarModel.to_text()` is stack-safe** (`base.py`): the mutually recursive
`to_text`/`_field_text` descent (RecursionError at nesting ~250) is now an
explicit LIFO work-stack over a new private `_emit_parts()`; byte-identical
output, `_field_text` deleted. `semantic_dump()` probed to depth 1500 — it
rides pydantic-core (Rust), no Python recursion, no fix needed.

**New `tests/adversarial/`** (sibling of `tests/property/`, user ruling):
cross-cutting adversarial edge-case pins graduated from repro scripts —
`test_deep_nesting.py` (round-trip at depth 400/800),
`test_left_recursion.py` (the four recursion/nullability quadrants under a
SIGALRM watchdog, indirect cycles, sole-arm clean rejection). Shared
hand-authored-grammar helpers (`rule_of`/`item_of`/`analysis_of`) moved to
`tests/_ir_fixtures.py` (R0801). Suite 2212 passed; `run_checks.sh` exit 0.

---

## 2026-07-13 — Vyx-parse Tasks 1–2: L1 multi-membership codegen + L2 root arm-choice packing

Fixed both lexic bugs pinned by the probe. **L1 (multiple inheritance):**
`RuleBinding.parent_class_name: str` → `parent_class_names: tuple[str, ...]`;
`codegen/binding.py::_parent_rules` now returns every owning alternation of a
unit-ref arm, ordered most-derived first (`_order_bases` over the transitive
parent closure so a base that is itself an arm of another base precedes it —
C3-linearizable). `model_emitter.py` emits `class Unquoted(BareVal, Value):`,
`GrammarModel` when parentless; `RuleOrder.ordered_parents_first` already walks
all parent edges. A rule that is an arm of ≥2 alternations is now an instance of
all of them, so no field typed with a "losing" alternation class rejects it.
**L2 (per-symbol root packing):** the SPPF's referenced-symbol case already packs
alternative productions (each completion advances the parent waiter, so the
advanced handle collects one family per production); only the **start** symbol —
which has no parent waiter — dropped its alternatives, since `accept_node()`
returned the first accepting item. New `RootNode` (`parsing/earley/forest.py`)
packs every accepting production (`kernel.accept_items()`/`root_ambiguous`);
`RootDerivs` chains their `NodeDerivs`; `DerivationStream.eval` and `BuildTree`
branch on it. Single-production accepts still return the bare `SppfNode` (no
behaviour change). `is_ambiguous` honest, `derivations` complete, strict `parse`
raises; the engine's fast paths (`_single_tree`/`ParseFirst`/`ParseReduced`)
skip `FastTree`/`FusedReduce` when `root_ambiguous`. `RootNode` re-exported from
`lexic.parsing`. Full suite green (2187 passed). Also surfaced a **separate
pre-existing bug L4** (embedded right-recursive/nullable-tail ambiguity
undercount, Leo-deferred family reconstruction) — diagnosed (root cause in
`_leo_resolve`/`_expand_chain` collapsing an ambiguous chain) but NOT yet fixed;
tracked in FINDINGS.md L4.

---

## 2026-07-13 — Vyx-parse probe: two engine-adjacent bugs + vyx defect catalogue

New effort dir `zzz_current_work/260713-vyx-parse/` (FINDINGS.md + probe/).
Pushed the vyx D-layer grammar (assembled from `/home/mika/projects/vyx/spec/`
per-section `grammar:` fragments, mechanically corrected) through the full
pipeline. Compiles (103 classes), recognition 17/18 on realistic packets. Two
lexic bugs pinned with minimal repros: **L1** — `codegen/binding.py::
_parent_rules` is last-writer-wins, so a rule that is an arm of ≥2 alternations
(vyx's norm; never occurs in the existing ground-truth set) gets one parent and
every field typed with a losing alternation class fails at fold-ctor. **L2** —
SPPF forest construction never packs alternative productions of one symbol
(`v ::= a | b`, both arms deriving `"x"` → 1 derivation, `amb=0`); only
within-production split ambiguity (the `sss` fixture shape) is packed, so
`is_ambiguous` under-reports and strict `parse` fails to raise. Fifteen vyx
spec-fragment defects (V1–V15) catalogued in FINDINGS.md. Draft PLAN.md with
six pending user rulings.

---

## 2026-07-13 — Parsing totality-cleanup consolidation

Closed out the effort that made `lexic.parsing` own its public API. Two
product entries (`parse_reduced`/`parse_model`) with the Earley completion
inside the engine, memoised per (grammar, reducer/fold) identity; `compile.py`
imports the root API only; no opt-out (`PdaTables | None` gone — a decision no
gate licenses is a per-rule island); no cross-module `_underscore` imports —
the last two enforced by permanent AST checks in `test_layering_invariants.py`.
`DELEGATES_ENABLED` and "legacy" prose removed (delegation unconditional). The
empty-arm reduce fallback is closed by a structured ARM gate (`struct_arm`
taxonomy channel + `ArmGate`): json_arr/json_ws parse pure-PDA, differential
byte-equal to Earley. The public product API returns honest concrete types —
`parse_reduced -> IrAst`, `ModelFold[M]` → `parse_model -> M` (the engine stays
a leaf w.r.t. `lexic.base`; the model type rides the fold's type parameter). A
new ε-channel reduce differential property test guards the PDA↔Earley
equivalence (no divergence). `src/lexic/parsing/README.md` installed from the
end-state spec. Optimization harvest landed nothing (evidence-gated): every
pinned bench cell at/above the Task-0 baseline except gbnf-self-emit +9% (the
SG_PROBE gate cost, accepted; probe fast-path → FOLLOWUP). Suite 2168;
`run_checks.sh` EXIT 0.

---

## 2026-07-13 — Empty-arm ARM gate (runtime half)

Wired the stored `struct_arm_gates` into the predictive runtime. `specs.py` bundles a body's demotion specs into `ArmGates(windows, peeks, struct_arm)` (one `compile_arms` param) and adds `CloneSpec.struct_arm: ScanGate | None`; `clones.py`'s `compile_arms` resolves the empty-arm `ArmGate` (validating `escape` against the nullable default arm it picks — drift is a hard error) onto the CloneSpec. `flatten.py` gives `FlatClone` a `struct_arm` slot and skips dispatch conversion for a struct-arm clone. `runtime.py`'s `_enter` consults `scanner.scan_gate_take` before the FIRST-gated select — a take admits the gated arms, a refusal selects the escape (nullable default) arm — shared by both the model (`PdaKernel`) and grammar-text (`_ReducePdaKernel`, which reuses `_enter`) paths; the dispatch chase was extracted to `_chase_dispatch` so the inline hot-path select loop stays. **json_arr/json_ws now parse pure-PDA on the reduce path** (byte-equal to Earley); one constructed instance-path grammar exercises SG_SCAN end-to-end. `test_reduce_runtime.py`'s json_arr/json_ws "still PdaFail" pins flipped to pure-PDA; `test_flatten.py` slot pin gains `struct_arm`. Whole GT corpus + both self-emits byte-equal PDA-vs-Earley, both flavours. Bench: instance neutral; reduce self-emit/subset-920 neutral; **gbnf-self-emit product +~8% (184.5→~200ms)** — the SG_PROBE gate runs `scan_gate_take` on every GBNF self-grammar `arm` decision (inherent to closing the fallback with a probe; the reduce path can't dispatch-convert it away). **This one cell's +8% is an accepted, logged deferral to the evidence-gated optimization pass** — the candidate is a probe fast-path (memoise `scan_gate_take` per position, or a cheap first-char pre-check before the full rulename-probe); the cell measures self-grammar parsing, which pays the gate cost with no empty-arm benefit, while the grammars that benefit (json_arr/json_ws) go Earley-fallback → pure-PDA. Suite 2150 green; `run_checks.sh` EXIT 0.

---

## 2026-07-13 — Empty-arm ARM gate (analysis half)

Closed the empty-arm greedy fallback's analysis side. `structured.py` gains `structured_arm_gate(analysis, arms, label)` → an `ArmGate` (a `scanner.ScanGate` plus the escape arm index): for an alternation with a single empty/all-nullable escape arm whose gated arms lead with skippable noise, skip that noise non-consuming and admit the gated arms on a disjoint post-noise content lead (`SG_SCAN`), escalating to `SG_PROBE` when the take/exit overlap is the next construct's header (GBNF `rule`'s `rulename n* "::="`). The skip-then-peek/probe tail is shared with the loop path via a new `_scan_from` helper. `taxonomy.py` gains a sixth gate family `struct_arm` (rule name → `ArmGate`) with `struct_arm_gates` accessor + `store_struct_arm` (same conflicting-re-store tripwire). `analysis.py`'s `arm_conflicts` empty-arm greedy branch routes through `_demote_struct_arm` before falling back to today's greedy soft note (deny = today's behavior). Islands provably unchanged (only the soft branch is touched): GBNF self `arm ::= sequence | empty-seq` demotes `SG_PROBE`, escape=1 — the fix for the json_arr/json_ws grammar-text (reduce) fallbacks. `scanner.py` homes the new `ArmGate` NamedTuple. Runtime wiring (clones/flatten/runtime reading the channel back) is Task 4b. Suite 2150 green; `run_checks.sh` EXIT 0 (pyright + pylint 10.00/10).

---

## 2026-07-13 — Totality cleanup: engine owns its API, no opt-out, no private imports

Landed in atomic sub-steps (parsing owns its public API; no whole-grammar opt-out; no cross-module private imports).

**Sub-step 1 — directive 4 + the runtime C0302 shed.** All 66 cross-module `_name` imports renamed PUBLIC at their defining module (`flatten`'s op-codes/gate-codes/build-modes/mode-codes/reduce-kinds/`FlatArm`/`FlatClone`/`optimize_program`/`all_clones`/`gate_take`/`select_gated`; `runtime`'s `F_*` frame vocabulary + `finish_delegate`; `earley.reduce`'s `*_KIND`/`plan_for`; `tables.expand_atom`; `reduce_pda.reduce_rewrite`/`ReduceCompile`). Cross-module `_name` imports in `src/`: 66 → 0 (AST-enforced permanently). New leaf `pda/build.py` (frame-slot vocabulary + fused model-build tail + `finish_delegate`) shed out of `runtime.py` (946 → 764).

**Sub-step 2 — the product API + no opt-out.** New `parsing/products.py`: the two PRODUCT entries `parse_reduced(grammar, text, reducer)` (grammar-text → IrAst) and `parse_model(grammar, text, fold)` (instance → model), each taking the AUTHORED grammar, PDA-first with the Earley completion INSIDE the engine, memoised per (grammar, reducer/fold) identity; the Earley-completion entries `earley_reduce`/`earley_model` are the completions AND the tests' route-forcing seam. `PdaFail` never surfaces. `compile.py` deleted the route classes (`_ParseRoute`/`_ModelRoute`/`_ReduceRoute`), `_build_pda`, `self_grammar_pda`, and every `PdaTables | None` opt-out (0 remain); `CompiledGrammar` is now `(classes, grammar, codegen_grammar, fold)` and imports `lexic.parsing` root-only. `compile_reduce_pda` is total — an unreconstructable reduce policy compiles to an immediate-PdaFail start (an `IslandRef` over empty clones), never `None`. Totality rests on the existing analysis pre-pass: `arm_conflicts`/`_demote_arms` already islands every un-demotable rule-body AND inline-group overlap, so `compile_arms`' overlap raise is a pure drift hard-error (unreachable on correctly-analysed grammars — the whole real corpus + both self-grammars hit zero opt-out sites). Two permanent AST layering checks added (no cross-module `_name`; runtime imports `lexic.parsing` root only). Differential parity: whole GT corpus + both self-grammar emits byte-equal PDA-route vs Earley-route. Compile-time got faster (PDA/tables now build lazily in the product, not eagerly at compile: json compile_text 73.6 → 51.6 ms); parse perf neutral within noise.

Wiki page-level sweep (public-api.md, architecture.md, decisions.md, flavour-system.md, error-vocabulary.md) deferred to the effort's consolidation task.

---

## 2026-07-12 — Task 7: THE FLIP — `parse_grammar` is PDA-first, gate PASS both flavours

Preceded by the ⚑ pre-Task-7 adversarial pass (`REVIEW_PRE7.md` in the plan dir): 6.2 open-risk #2 discharged (union-FOLLOW conservativeness ⇒ a delegate's filed span is the site parse; the risk collapses into gate soundness), the `_ReduceRoute` landmine narrowed to the ε-channel divergence class (empirically byte-equal corpus-wide), FIRST_k pins verified, one HIGH latent hole found and fixed (soft-gap loop classification, see the 6.6 entry).

`_ReduceRoute` flipped `pda_first=True`. **First gate run: ABNF beat baseline 1.8–2.0×, GBNF MISSED (0.7×)** — profiling attributed it to rule `n`: 404/448 island hits on the GBNF workload (a windowed Earley sub-parse per whitespace run). Lever within the 6.6 design: `_match_gate`'s SG_MATCH licence extended to any **non-semantic** ref atom via `_sem_follow_clear` (the P6 precision clause applied to an *exact-match* gate — rest-of-arm all non-semantic, over-takeable chars ∉ `sem_follow(rule)`), and `nunit` flagged `semantic=False` in gbnf.py (structural noise; `IrRule.__eq__` excludes the flag, so canonical/selfhost fixpoints, GT byte-parity and the emit baseline are all untouched — verified). `n` demotes to an exact-match gate — strictly sounder than a greedy stop-set (an incomplete `comment-line` at a tail comment does not match, so the tail comment keeps its chars). **GBNF-self islands 4→3 (`cc-first`/`cc-item`/`cc-nfirst`).**

**Second gate run: all nine workload×size cells beat the pre-lever Earley baselines 1.7–2.0×.** Differential sweep: whole GT corpus + both self-emits byte-equal IrAst PDA-vs-Earley; multi-copy x2/x4 (IrMerge-heavy incremental rules) byte-equal; subset-920 x1/x2/x4 byte-equal; json_arr/json_ws remain the two known fail-soft Earley fallbacks (the GBNF empty-first-arm residual — `REVIEW_PRE7.md` finding 2). CLAUDE.md pipeline prose updated (PDA-first both paths).

---

## 2026-07-12 — Task 6.6 (unified-parse-engine): P5 probe + structured noise gates land — ABNF PDA exists, GBNF-self 4 islands

The folding-aware structured-noise machinery (`pda/scanner.py`, landed as a slice last session) is now wired end-to-end: analysis (`noise.py` `structured_loop_gate` — SG_MATCH pure-folding / SG_SCAN skip-then-peek / SG_PROBE skip-then-probe), taxonomy channel (`struct_loop_gates`, `store_struct_loop` tripwire), clone compile read-side, flatten/runtime (`_GATE_SCAN` in `_gate_take`).

**P5 probe (generic, grammar-derived):** when a loop's post-noise take/exit content leads overlap, `_probe_candidate` searches every semantic rule for the unique header shape `ref(R) noise* lit(L)` covering the overlap, licensed by refutation — `L`'s lead char must be unreachable in `post_noise_follow(R)` with the header occurrence itself excluded — so a matched `R noise* L` at the peek position refutes the take reading (GBNF `sequence[1]`: `rulename n* "::="`). Demotes GBNF `sequence`; **GBNF-self 7→4** (`n`/`cc-first`/`cc-item`/`cc-nfirst` remain).

**Soft-gap loop classification (latent-unsoundness fix):** `_loop_conflict` guarded only on *hard*-continuation overlap — a loop overlapping only nullable followers silently baked a greedy stop-set (GBNF `grammar`'s `rules-rest*` ate the trailing newline at EOF then demanded a rule). New `_soft_gap_conflict`: P6 licence → demotion cascade → hard note. json `array` joins the demoted set both flavours (P3 peek replaces the silent greedy gate); `_exit_is_noise` extended to optional-noise-only exits (and made stricter: a nullable *semantic* follower now denies SG_MATCH).

**ABNF `rulelist` boundary-shift left-factor** (user-cleared option b): `rulelist = filler* rule rl-cont* c-wsp* c-nl?`, `rl-cont = c-wsp* c-nl filler* rule`, `rule` loses its trailing `c-wsp* c-nl`; `rl-item`/`rl-final`/`endrule` deleted; same language by associativity; reductions mirror (`rl-cont → IrArg(0)`, `IrMerge` intact); rules reordered to canonical. **ABNF-self islands 0; `self_grammar_pda(ABNF)` exists for the first time.** Also `reduce_runtime._reduce_span` now stitches YIELD-with-drop spans (ABNF comment `cchar` over droppable `htab`) instead of PdaFail-ing wholesale.

**Whole-corpus reduce-PDA recognition (byte-equal IrAst vs Earley): ABNF 3/3, GBNF 7/9** (json_arr/json_ws remain — the GBNF empty-first-arm `ws ::= | …` greedy arm commit, fail-soft, not on any bench workload; recorded residual). Delegation evidence (user addendum): all four residual GBNF islands carry 20 delegate clones; corpus reduce runs fired 1855 delegate sub-runs, 1775 successful spans — the reduce twin's island path demonstrably carries delegates. Instance perf neutral vs pre-task (chess 0.091→0.090 ms, json 0.228→0.233 ms, same-sample A/B). `Taxonomy` moved to new leaf `pda/taxonomy.py` (C0302 motion). Oracles: GT parse byte-parity 10/10, canonical + selfhost fixpoints both flavours, emit baseline 21/22 byte-identical (abnf-self refreshed by design). run_checks EXIT 0; 2082 passed / 1 skipped.

---

## 2026-07-11 — Task 6.5 addendum: TOTAL def purge from the grammar modules

Follow-up user escalation to the pure-algebra ruling: the "grandfathered" HEAD-era handlers go too — `gbnf.py`/`abnf.py` now contain **zero** `def`s and zero `IrLambda`s. The logic moved to its architectural homes: `EscapeCodec` (ir/escapes.py) gains the generic `encode_point` (class-member escape cascade: `CLASS_SHORT` → `CLASS_META` backslash → printable glyph → narrowest `HEX_ESCAPES` form) and `spellable` (`QUOTE_SAFE` ranges) algorithms over per-flavour ClassVar data; ir/flavour.py gains the dispatcher-codec leaves `IrEscapePoint` and `IrSpellable` (the `IrEscape` pattern); ir/action.py gains the generic nodes `IrRadix` (emit-side inverse of `IrUnradix`, uppercase digits + zero-pad), `IrOrd` (inverse of `IrGlyph`), `IrLen`, `IrEach` (variadic `IrAt` — maps a body over a tuple-shaped node's elements or a str-leaf's chars, clean channel), and `IrMerge` (the `=/` same-name rule merge, formerly `_merge_rules`). ABNF's literal/charclass emit actions are now `IrCond`/`IrTypeMap`-shaped algebra (`%s"…"` vs dot-joined `%x` via `IrSpellable`; per-element `%x` forms via the `IrChr`/`IrRange` actions + `IrLen`-keyed parenthesisation); `IrRange` endpoint reads go through `IrField` (scalar-payload record — `IrAt` has no children there, caught live). Gates: **emit byte-parity 22/22** (both self-emits + all GT canonical emits, both flavours, vs pre-purge baseline `emit_65b_baseline.json`), GT reduce byte-parity + selfhost unchanged, suite 1990/1 untouched, run_checks EXIT 0. New ir/ surface exported from `lexic.ir`; Sonnet lane owes the mirror tests. See [[decisions]].

---

## 2026-07-11 — Task 6.5 (unified-parse-engine): P4 self-grammar left-factor lands, def-free

Left-factored the two owned self-grammars at author level, grammar + reductions co-edited: GBNF `quantifier` (arms `q-opt|q-star|q-plus|q-counted`; `q-counted -> "{" decits q-tail`, tail rules `"}"` / `",}"` / `"," decits "}"`), ABNF `repeat` (`repeat-num (decits repeat-tail) | repeat-nolo`), `num-val` (per-radix `num-x|num-d|num-b`, each `"%" mark hexits <tail>`), `cvbody` (`cvnac* (cvalpha cvany*)?` — an inline optional group, the first in an authored self-grammar; its synthetic splices case items flat into the channel). Deleted: `q-exact/q-atleast/q-between`, `repeat-exact/repeat-range/lo-bound`, `num-single/num-range/num-seq/dec-*/bin-*`, `cvexp/cvlit`.

**Folds are pure algebra** (user ruling — a first attempt with six `IrLambda` handlers was rejected and rewritten): tail rules reduce to type-distinct markers, parents branch via `IrPipe(IrArg(i), IrTypeMap(...))`; `cvbody` dispatches on `IrArg(-1)` with `IrSequence` coercion lifting the lead `IrLiteral`s to per-char items. See [[decisions]] 2026-07-11 (pure-algebra ruling).

**Gates:** GT `parse_grammar` IrAst **byte-parity vs pre-task HEAD** (all ten GT files; `parity_65.py` + captured baseline in the plan dir); self-host + canonical fixpoints both flavours; islands exactly per coverage map — **GBNF-self 8→7** (`quantifier` out), **ABNF-self 7→4** (`repeat`, `num-val`, `cvbody` out), json/chess 0, no new islands (the factored tails demote via the standing P2 k-window gates); instance perf untouched (structurally: byte-identical canonical grammar; measured: json 0.205 ms, chess 0.059 ms pure-PDA). run_checks EXIT 0; 4 test-pin ports (deleted-rule fixtures + island counts) to the Sonnet lane. Residual ABNF islands (`alternation`/`concatenation`/`rule`/`rulelist`) are exactly the 6.6/P5 targets.

---

## 2026-07-11 — Task 6.4 (unified-parse-engine): P6 + P3 land, json island-free (16×), P2 flag deleted

**Cleanup:** `P2_DEMOTION_ENABLED` deleted entirely (user directive: no legacy staging seams pre-v1) — demotion is unconditional; the flag-OFF A/B tests died with their symbol. `DELEGATES_ENABLED` kept deliberately (the standing delegation A/B gate) and marked for Task-8 consolidation.

**P6 (noise-greedy licence, analysis-only):** new leaf `pda/noise.py` homes `sem_follow_table` — the chars that can follow a rule *as semantic content*, via a semantic-FIRST decomposition (terminals count only inside semantic rules; a ref to a non-semantic rule contributes nothing, since its subtree is excluded from `semantic_dump` wholesale) re-fed through the FOLLOW walk. The licence is SIM_60's two pinned clauses **plus the plan's precision clause** `gap ∩ sem_follow(rule) = ∅` — the two-clause form alone would license a noise loop eating into a *semantic* optional follower (counterexample pinned). Gap is intersected with the loop's own alphabet, which also structurally excludes the EOF sentinel `subtract` exactly retains. json `ws` island→demoted, everything else byte-identical; json 758→279 ms.

**P3 (noise-skip peek gate, json scope):** `noise_alphabet` (W = ⋃FIRST over *nullable* non-semantic rules — grammar-derived: json whitespace, ABNF ws+`;`, GBNF ws+`#`; required noise markers like `dquote` contribute nothing), `ResidualFirst` (post-noise FIRST: pure-W atoms transparent, W-free opaque, a MIXED terminal poisons, refs recurse), `peek_arm_gate`/`peek_loop_gate`. Taxonomy gains `pn_arm_gates`/`pn_loop_gates` (option-(a) keying); cascade = P2 k-window then P3 peek. Runtime: `_GATE_PEEK` loop gate + `pn_selectors` arm selection over a **non-consuming** skip of the maximal W run — the winner re-parses its own noise, so the peek is structurally fail-soft (analysis conditions buy determinism, not bare soundness). **json: zero islands** (`value` selects among 7 arms post-noise; the item loops take on `,`), clone count 1→126, **46 ms — 16× vs the 6.2 state**; chess unchanged. The GBNF/ABNF spine's P3 decisions stay islands: their noise includes comments whose co-finite interiors poison the char-set residual FIRST — the folding-aware scanner is deferred to the 6.6/P5 slot (the P5 probe needs it anyway; grammar-text is unrouted until Task 7).

**Bug caught (F2 class):** the clone compiler consulted stored gates only under its hard-cont overlap guard, so a clone whose hard tail didn't overlap the loop FIRST baked a whitespace-admitting stop-set instead of the stored peek gate (`[ 1 , 2 ,\t3 ]` ate into `" ]"`). Stored gates are now honored in every clone, before any overlap heuristic — the analysis judged the decision against the rule's soft FOLLOW, which covers every clone. Regression input pinned.

Gates: run_checks EXIT 0, 1989/1. See PLAN_v5 ledger + [[decisions]].

---

## 2026-07-11 — Task 6.3 part (c) (unified-parse-engine): P2 k-window demotion LIVE

`kwindow.P2_DEMOTION_ENABLED = True`. The lever that turns k≤3-separable island decisions into runtime k-window gates, built on the **option-(a) gate-spec channel**: `GrammarAnalysis` now exposes its taxonomy as a public attribute (`taxonomy: Taxonomy`, the renamed `_tax` slot — attribute not method, so the R0904/R0902 caps are untouched) carrying two new stores the demotion sites fill — `arm_gates` (rule name → per-arm CharSet-window tuples; **rule bodies only**, an inline group's arm overlap stays a hard note so the rule islands) and `loop_gates` (`id(IrItem)` → taken windows; node identity works because analysis and clone compiler walk the same lifted tree; a conflicting re-store raises → opt-out). Specs are stored cooked via `kwindow.windows_of` (END/MORE/UNK tags dropped — irrelevant to the positionwise runtime test — dedup'd, deterministically sorted). The clone compiler **reads the channel, never recomputes**: `KTupleGate` (loop) sourced from `loop_gates`; `ArmSpec.windows` (arm selection) threaded through `compile_arms`' own arm enumeration so window↔arm alignment can't drift past the empty-FIRST drop; a FIRST-overlapping alternation with no spec raises `UnsupportedConstructError` (the anti-trap drift tripwire). Runtime half (`_GATE_KWIN`, `kwin_selectors`, EOF-exact `_window_admits`) was already validated (task63fix) and is unchanged.

C0302 motions: the superseded 2-char LL(2) prefix machinery (`two_prefix_seq`/`atom_two_prefix`/`group_two_prefix` + `_SINGLE`/`_TWO_PREFIX`/`_LEAD_PREFIX`) moved from `analysis.py` to `kwindow.py` as free fns over the analysis (still the PairGate source via `loop_policy`); `_bake_reduce`/`_reduce_rewrite` moved from `clones.py` to `reduce_pda.py` (tests ported per mirror rule). kwindow #10 LOWs done: never-empty assert → real raise (compile opt-out path, no `-O` strip); dead `forced_once` deleted.

**Results:** island sets moved exactly per the coverage map — GBNF-self 17→8, ABNF-self 9→7, chess 1→0, json unchanged; bonus c.gbnf `multilinecomment` island→demoted. ANTI-TRAP gates held: chess 40/40 pure-PDA **0.0% fallback** with adversarial disambiguation inputs (Nbd2/N1d2/Nb1xd2) driven through `parse_pda` directly; the `lo>k`→k3 **EOF-exact** arm separation live end-to-end (`[0-9]{4,} "x" | "12"`); **chess 8.6× faster** than the 6.2 state (57.5→6.7 ms), json neutral. Criterion-2 chess delivered. Gotcha for test authors: `flatten._all_clones` from the start shell cannot walk past dispatch/ref targets — structural gate pins read the spec table (`pda.clones`). Old `"a"? "a"` island fixtures now *legitimately* demote at k2; the stays-island fixture shape is a shared unbounded prefix (`x ::= n "x" | n "y"; n ::= [0-9]+`). Gates: run_checks EXIT 0, 1974/1. See PLAN_v5 ledger + [[decisions]].

---

## 2026-07-06 — Task 3 (unified-parse-engine): one IR fold type

Replaced the plain-data instance fold's authored form with **one IR-native type**, `ModelFold` (`parsing/fold.py`): its `bodies` is a per-rule `IrMap[IrRuleRef, ModelBody]` (the same shape the grammar-text `Reducer` uses), and it bakes on construction to the flat-runtime `config: dict[str, RuleFold]` (`.baked`) the PDA clone compiler + engine-fallback consume byte-for-byte unchanged. `ModelBody(kind, ctor: IrLambda|IrNone, n_items, fields, fast)` is an `IrNamedTuple` (`_child_attrs=()`); `ModelBody.bake()`/`.of(rf)` are the lower/lift pair; `ModelFold.from_config(dict)` the lowered-form seam. `PositionalFold` absorbed into `ModelFold` (name reclaimed from the retired wrapper-rule fold — unrelated). `compile._fold_config` now returns the `IrMap` body-table; `_build_pda` takes `fold.baked`. Behavior-frozen: a 600-sample × both-parse-path differential is byte-identical before/after; no perf loss (flat clone unchanged). Docs: `CLAUDE.md` fold lines + [[public-api]]/[[architecture]]/[[ir-shapes]]/[[decisions]]. src-only landed; test port (test_fold.py/test_compile.py construction-syntax pins: `PositionalFold(cfg)` → `ModelFold.from_config(cfg)`, `isinstance(cg.fold, ModelFold)`) is a follow-up Sonnet task — full `run_checks.sh` green is the gate after that port. See [[decisions]] 2026-07-06.

---

## 2026-07-04 — Task 5 (cleanup/optimize): consolidation

**Official post-effort baselines saved:** `tools/benchmark/pipeline_bench.py --save` and `tools/benchmark/parse_bench.py --save` re-run on the quiet tree (Tasks 0–4 + depth wave all landed; suite 1568/0, `run_checks.sh` exit 0). `pipeline_baseline.json`: instance parse+fold essentially unmoved from Task 0's pre-fix numbers (arithmetic 88.96/91.07 ms best/median @4800 chars, c 26.70/27.08 ms @3289 chars — Task 1/2 never touched the engine, ±5% gate honoured); compile-time now reflects Task 1's interval-native canonicalize fix — `canonical_grammar` json 28.54/28.72 ms, c 32.36/33.54 ms (both now `parse_grammar`-dominated — canonicalize itself is down to single-digit ms), arithmetic 5.96/6.04 ms; `compile_text` cold json 65.93/67.75 ms, c 80.28/82.65 ms, arithmetic 23.43/23.72 ms (from ~940/946/24 ms pre-fix — the headline win, ~13–14× on json/c). `bench_baseline.json` (`parse_bench.py`, engine vs pure-Lark reference) re-saved unmoved in kind — this round did no engine work (kill-list honoured throughout); its self-emit x4 verdict is engine 303 ms vs lark 235 ms (0.59× on the fused parse+reduce product), consistent with prior rounds. Observed but out of scope: the harness's own diagnostic header line ("ABNF self-host … engine parse+reduce fixpoint: False") compares the *raw* (pre-canonicalize) reduced `IrAst` against the already-canonical `ABNF_FLAVOUR.grammar` constant — a stricter check than the suite's actual golden fixpoint tests (which canonicalize both sides and are green); not a regression from this round's changes, engine/grammar-loading untouched throughout, flagged for whoever next touches that script.

**Wiki consistency pass:** the open-set consumer rework (Task 2) landed generate.py/model_emitter.py/aliases.py's open-table conversion but only logged it — the descriptive wiki pages still said "deferred"/"still carry closed-set ladders". Fixed to reflect completion: [[ir-shapes]]'s "Open-set note" (renamed "rework complete, 2026-07-04"), [[architecture]]'s IR-passed-by-action-table section, [[field-naming]]'s closing "Future" note. `CLAUDE.md`'s matching IR-types blockquote updated the same way (same stale claim, same fix). [[codegen]] and [[public-api]] were already accurate on this front (public-api's `out_dir`/memoisation sections were rewritten in Task 3) — no change needed there. `decisions.md`'s and this log's own historical entries (V2 migration era, "closed-set ladders kept for now") are audit-log entries describing what was true *then* — left untouched, not contradicted by anything since they're dated.

**CLAUDE.md touch-ups:** §Commands suite-count comment `~1360` → `~1568` (current). §Current state's compile/out_dir/memoisation prose and `generated/` git-ignored claim were already accurate (Task 3 landed them correctly) — verified against `compile.py`/`codegen/__init__.py`'s actual signatures, no drift found beyond the open-set note above.

**Examples gate:** getting_started ex01–ex05 all ran clean (exit 0, output inspected). Ran the loop manually rather than `tools/run_examples.sh` directly — that script unconditionally shells out to `tools/auto_fix.sh` (tree-wide) as its last line, which this round's standing constraint forbids running gratuitously; same coverage, one fewer tree-wide side effect. None of the five examples call `generate()`, so Task 2's `_pick_count` lo==0 distribution fix has no pinned-output surface to touch here.

Gates: full suite 1568 green, `run_checks.sh` exit 0.

---

## 2026-07-04 — Task 2 (cleanup/optimize): open-set consumer rework + generate fixes

**Open dispatch tables (Phase 1, byte-identical):** the three remaining closed-set atom-type `isinstance` ladders moved onto open `IrDispatch`/`IrTypeMap` tables with raising defaults, matching `binding.py`'s `_MODE` idiom (dispatch on the atom, the owning `IrItem` riding the argument channel; per-call state — `rng`/`rules`, `class_by_rule`/`aliases` — carried on a plain-`IrNamedTuple` state record passed as the dispatcher `d`, the `_PatternAliasVisitor` precedent). `generate.py`'s `_gen_atom` → `_GEN_ATOM` + `_Generator`; `codegen/model_emitter.py`'s `_base_field_type` → three per-mode tables (`_MODEL_TYPE`/`_GTEXT_TYPE`/`_TEXT_TYPE`) selected by the closed `BIND_MODES` string, `_value_str_type` → `_VALUE_TYPE`; `codegen/aliases.py`'s `_atom_regex_fragment` → `_FRAGMENT`. Each silent fallback (`generate`'s `return ""`) became an explicit `UnsupportedConstructError`. The post-canon-dead `IrNot` branches (in `_gen_atom`, `_atom_regex_fragment`, `_visit_item`) were deleted — the raising default now covers a stray `IrNot` honestly. Emit output for all 10 ground-truth pipelines and seeded `generate` output are byte-identical across Phase 1. No node-intrinsic logic needed moving: the genuinely intrinsic bits (`IrCharClass.pattern()`/`sample()`) already live on the node; everything tabled is consumer policy. `_group_union_type` (a ref-arm *filter*, not a classification ladder) and `_visit_item`'s remaining `isinstance` (essential group-frame control-flow with a *recursing* default) were deliberately left as-is.

**`_pick_count` lo==0 roll (Phase 2, sanctioned behaviour change):** `generate._pick_count` returned 0 unconditionally when `q.lo == 0`, so any `*`/`?`-rooted rule (e.g. c's `root ::= (declaration)*`) always generated `""`. Removing the early return lets `lo == 0` share the existing 0.7/expand roll — c.gbnf root now yields text for ~35% of seeds (was 0%). Stale "root always yields ''" comments in `tests/property/test_roundtrip.py` + `conftest.py` corrected.

**Empty-string round-trip fix (root cause exposed by Phase 2):** the Phase 2 change surfaced a pre-existing round-trip-invariant violation — an empty JSON string `""` is *recognised* but its `String` model failed to construct: `model_emitter._is_optional` only treated `(0,1)` as optional, so a `(0,None)` star pattern field (which matches empty) was required, and the fold emitted no value for an empty run. Fixed to `q.lo == 0` (any absent-able quantifier). Three fields across arithmetic/json_ws/json_arr correctly became `Optional[...] = None` — the only emit-golden divergence in this landing, a deliberate bug fix, not the refactor.

Gates: full suite 1542 green; the three source + three test files ruff/pylint 10.00/typecheck clean. (`run_checks.sh` whole-tree pylint currently trips on `tests/unit/lexic/test_compile.py` — another lane's in-flight Task-3 `_stem_for_text` work, not this lane.)

---

## 2026-07-04 — Task 3 (cleanup/optimize): out_dir API + hygiene sweep

**`out_dir` parameter (USER DECISION 1):** `compile_text`/`compile_from_path`/`codegen` all gained a keyword-only `out_dir: str | Path | None = None` — `None` resolves to today's `_resolve_generated_dir()` default (unchanged), an explicit value redirects the generated module there. `codegen/__init__.py` gained a public `resolve_out_dir(out_dir)` seam (used by both `_write_and_load` and `compile.py`'s memo-key construction, so the two always agree on where a given `out_dir` lands) — no env var, no global config, this is the one way. `compile_text`'s default content key extended to `(sha stem, flavour, resolved out_dir)`, `compile_from_path`'s stat key likewise to `(path, mtime, size, flavour, resolved out_dir)`; an explicit `cache_key=` override is used as-is, not augmented. Module import already worked by absolute file path (`spec_from_file_location`), so threading `out_dir` through was mechanical — no import-machinery changes needed. Six new unit tests in `tests/unit/lexic/test_compile.py` (tmp_path out_dir lands the module + round-trips, default path unaffected, distinct out_dirs don't cross-hit the memo, same out_dir does); `test_compile_and_compile_from_path_share_cache` ported to the 5-tuple key shape.

**`generated/` untracking (USER DECISION 1):** `generated/` added to `.gitignore`; all 33 previously-tracked files `git rm --cached` (staged deletion, files stay on disk — reproducible build products, matches CLAUDE.md's existing "git-ignored" claim which had drifted out of sync with git's actual tracking state).

**`iremit_*` → `emit_<stem>_<flavour>` rename (USER DECISION 3):** `tests/integration/test_codegen_ir.py`'s stem line now derives an explicit `gbnf`/`abnf` flavour segment (`emit_json_gbnf`, `emit_json_abnf`, …) instead of a suffix-or-nothing scheme. Old `generated/iremit_*.py` files deleted from disk; the suite regenerates the new `emit_*` stems on the next run (verified).

**Mechanical residue:** `codegen/__init__.py`'s `except OSError, subprocess.TimeoutExpired:` (a Python-2-shaped bare-tuple-without-parens that happened to still parse) → `except (OSError, subprocess.TimeoutExpired):`; `compile.py`'s pipeline docstring's last `codegen_ir` mention → `codegen`.

**Wiki:** `.wiki/lexic/slice-b-status.md` gained a dated historical-audit-log header note (it still describes the pre-cutover `Flavour` ABC / `MetaGrammarParser`); `.wiki/lexic/public-api.md`'s `compile_text`/`compile_from_path`/`codegen` sections rewritten for `out_dir` and the content-keyed default memoisation (Task 1's rider, previously undocumented).

Gates: full suite green, `run_checks.sh` exit 0, `git status --short` shows exactly the intended tracking changes for this lane.

---

## 2026-07-04 — Task 1 (cleanup/optimize): interval-native canonicalize charclass merge

`canonicalize(parse(json.gbnf))` cost ~930 ms (c.gbnf ~875 ms) because `ir/canonical.py`'s `_merge_arms` fused char-ish alternation arms through `IrCharClass.members()` — a per-point list. A `[^…]` complement (rewrite 4's output) is ~1.1M points, so `flush()` built `IrCharClass(*(IrChr(p) for p in pending))` from ~1.1M constructions and then re-sorted them. All merge math moved to the interval domain:

- `ir/nodes.py`: `IrCharClass` gained a public `intervals()` (the promoted `_intervals` — sorted disjoint `(lo,hi)` cover), a `from_intervals(spans)` classmethod (coalesce + build `IrChr`/`IrRange` directly, result already `normalized()`-form), and a shared static `_coalesce(raw)` — the single home for the sort+merge algorithm, called by `intervals`/`from_intervals` and (transitively) the canonicaliser, so no R0801 duplication. `members()` kept its contract but its docstring now warns against Unicode-scale use.
- `ir/canonical.py`: `_arm_points` → `_arm_intervals` (charclass arm → `atom.intervals()`; single-char literal → `[(c,c)]`); `_merge_arms.flush()` coalesces pending intervals via `IrCharClass.from_intervals` then applies rewrite 1 through the existing `_canon_cc` — byte-identical output because `_canon_cc` depends only on the covered point *set*.

Result: `canonicalize(parse(json.gbnf))` ~3.8 ms (245×), `compile_text` json/c cold ~68/82 ms (from ~945 ms). Canonical output + emitted module source byte-identical across all 10 ground-truth grammars ×flavours; full suite green (1525 passed) and wall-clock ~107 s → ~19 s (the canonicalize fix dominates; the memoisation rider below adds the rest).

**Rider (USER DECISION 2):** `compile_text` now memoises by `(content sha stem, flavour)` by default (was: `cache_key=None` never cached). `cache_key=` stays as explicit override; `reset_cache_for_tests()` is the fresh-objects seam. Two suite tests that asserted the old no-cache default were ported to the new contract (`test_compile.py`, `parsing/test_fold.py`'s identity-memo test now resets between the two compiles).

## 2026-07-04 — Task 7: consolidation — docs/wiki catch up to the IR-native pipeline (IR-native codegen effort)

Task 7 closes the IR-native codegen effort: the code has been IR-native since Task 6; this task brings the user-visible fixpoint test, the examples, and every doc/wiki page describing the old `RuleSpec` shape up to date with disk truth.

- **Fixture fix + headline parity test.** `resources/ground_truth/json.abnf` was missing the `; @non-semantic ws` directive its `json.gbnf` sibling carried (the GBNF file even says in its header comment "both files must lower to the same neutral IR") — added. `tests/integration/test_cross_flavour.py` gained `test_json_gbnf_and_abnf_compile_to_identical_generated_source`: compiles both fixtures through the public `compile_text` entry point and asserts the generated module **source** is byte-identical modulo the one docstring line naming the (content-hashed, therefore necessarily distinct) stem. This is the user-visible form of `canonicalize(parse(json.gbnf)) == canonicalize(parse(json.abnf)) == JSON_GRAMMAR`.
- **`getting_started/`:** all five examples (`ex01`–`ex05`) already ran clean end-to-end against the current API (ported in earlier tasks) — no source changes needed. `getting_started/README.md` still described `MetaGrammarParser`, `model.__grammar__` as a `RuleSpec`, and a `compiled.specs` field that no longer exists — updated to `parse_grammar`/`compiled.grammar`/`__grammar__` as an `IrRule`.
- **CLAUDE.md rewrite** (surgical, structure/voice kept): §Before-you-touch-anything gained a "RuleSpec cutover complete" bullet; §Current-state rewritten (three cutovers now: primitive-node V2, Lark→Earley, RuleSpec→IR-native); §Project-layout rewritten module-by-module against actual disk contents (`ir/bind.py`, `ir/canonical.py`, `ir/order.py`, `ir/meta.py`, `ir/mapping.py`, `codegen/binding.py`, `codegen/passes.py`, `parsing/fold.py` added; `derive.py`/`spec.py`/`emit.py`/`naming.py`/`topo.py`/`utils/`/`ir/regex_portable.py` — the last pre-dating this effort entirely — removed); pipeline diagram redrawn to the Target-pipeline shape verified against `compile.py`; §Layering-rules updated (`lexic.codegen` no longer imports `lexic.grammars` — codegen is IR-native, needs no flavour adapters); §IR-types fixed the known drift (records are `IrNamedTuple`, not `IrComposite` frozen dataclasses — verified against `ir/nodes.py`/`ir/base.py`/`ir/meta.py`) and gained an `IrCachingTuple` mention; new §`kind`-semantics subsection (now `RuleBinding.kind` via `classify_rule`, not `RuleSpec.kind`); §Field-naming re-pointed to `codegen/binding.py`'s `_HINT`/`_TIER2` tables; §GrammarModel rewritten against the actual `base.py` (`__grammar__: IrRule` + per-field `IrBind` metadata, no `to_ir_rule()`); §Directives fixed (`canonical_grammar`, not `compile_grammar`/`derive_specs`); §Import-paths — every listed import verified by actually importing it.
- **README.md:** pipeline diagram redrawn (canonicalize → codegen-grammar passes → binding/codegen/fold, replacing the `derive_specs`/`ModelFold` shape); "action-driven" paragraph's example list (`derive` → `canonicalization`); test-grammar count (seven → eight `.gbnf` + two `.abnf` siblings); Project-status closing line gained the RuleSpec→IR-native cutover mention.
- **Wiki:**
  - `.wiki/lexic/ir-shapes.md` — full rewrite: `IrComposite` → `IrNamedTuple`/`IrCachingTuple` throughout; `IrGroup` removed (never existed post-cutover — an inline group is an `IrAlternation` used as an atom); `IrNot` re-homed to `ir/operators.py`, correctly shown as a variadic-tuple wrapper not a record; new sections for `IrBind`/`BIND_MODES`, `kind` semantics (now on `RuleBinding`), canonicalization (`ir/canonical.py`'s rewrite list + the headline fixpoint), and `codegen/passes.py`'s hoist/relax passes (successors of the retired `ir/derive.py` jobs); dispatch section corrected (`IrDispatch` is an `IrCachingTuple`, no `_resolve_cache` memo — `ir/mapping.py`'s `IrTypeMap.resolve` is a live MRO walk every time); dead `RuleSpec` section removed.
  - `.wiki/lexic/architecture.md` — full rewrite: pipeline diagram redrawn to match `compile.py` exactly; new "positional fold replaces the wrapper-rule bridge" section explaining `kids[i] ↔ items[i]`; layering table/exceptions updated (`lexic.codegen ✗ lexic.grammars`); module ownership + file tree updated to current disk contents; explicit note that `ir/derive.py`/`spec.py`/`emit.py`/`naming.py`/`topo.py`/`parsing/models.py`/`utils/` are gone outright.
  - `.wiki/lexic/new-codegen.md` **renamed to `.wiki/lexic/codegen.md`** and fully rewritten: it described the Tasks-8–14 `new_codegen/` scaffold built against `NewRuleSpec` during the May cutover; the page now documents the current IR-native `lexic.codegen` (`passes.py`'s three grammar→grammar rewrites, `binding.py`'s open-table binding view, `model_emitter.py`'s `Annotated`/`IrBind` field emission, `aliases.py` unchanged in spirit). `.wiki/index.md` re-pointed.
  - `.wiki/lexic/field-naming.md` — full rewrite: source moved from `ir/naming.py`+`ir/derive.py` to `codegen/binding.py`; `_ATOM_HINT`/`_FIELD_BASE` closed dicts → `_HINT`/`_TIER2` open `IrDispatch` tables; `CHARCLASS_NAMES` corrected to 8 entries keyed by canonical (post-`canonicalize`) pattern forms, not the pre-canonical mixed-case spellings; added the fold-mode (`mode_for`/`BIND_MODES`) sibling-table note.
  - `.wiki/lexic/public-api.md` — full rewrite: `compile_grammar`/`RuleSpec`/`build_instance_parser`/`ModelFold` replaced with `canonical_grammar`/`IrBind`/`PositionalFold`; `CompiledGrammar` field table corrected (`grammar` = canonical ast, new `instance_grammar`/`tables` fields, `fold: PositionalFold`); added the `compile_from_path` same-stem-across-flavours caution (`json.gbnf`/`json.abnf` both stem to `json` — use `compile_text` for cross-flavour compilation in one process); golden-gates section extended with the new cross-flavour source-parity test.
  - `.wiki/lexic/invariants.md`, `.wiki/lexic/error-vocabulary.md`, `.wiki/lexic/slice-b-status.md`, `.wiki/lexic/flavour-system.md` — targeted fixes (not full rewrites): dead `compile_grammar`/`IrCallable`/`ir/derive.py` references corrected in place; ground-truth grammar list and stale test count updated.
  - `.wiki/lexic/cutover-plan.md` — a third "Superseded further" note appended (matching the existing convention for the Lark→Earley note) pointing at this cutover, table left as the historical 2026-05-13 record.
  - `.wiki/lexic/decisions.md` left untouched — dated historical decisions, not a living-state page; nothing in it was factually wrong, only superseded (which is expected of a decision log).
- Gates: full suite 1502/0 (was 1501; +1 for the new parity test), `tools/run_checks.sh` exit 0.

---

## 2026-07-04 — Task 6: runtime port + RuleSpec-pipeline deletion (IR-native codegen effort)

The old `RuleSpec`/derive pipeline is gone; the IR-native path is the only one.

- `src/lexic/generate.py` PORTED off `RuleSpec` — `generate(rule_name, rules,
  ...)` now takes a rule-name → `IrRule` mapping (the canonical grammar's
  rules) and walks `rule.body` (alternation of arms) directly. Callers build
  the mapping from `canonical_grammar(text, flavour).rules`.
- `compile.py`: transitional `compile_grammar` and `CompiledGrammar.specs`
  DELETED (the sole `RuleSpec` consumers). `canonical_grammar(text, flavour)`
  is the public front-half seam. `codegen_ir` → `codegen` (the plain name).
- Implementations MOVED HOME (interim Task-3/4 seams closed):
  - `hoist_helpers`'s `_HoistTransformer` machinery moved into
    `codegen/passes.py` (`hoist_groups` no longer wraps derive).
  - the `CHARCLASS_NAMES` / `LITERAL_NAMES` naming tables + `has_ruleref`
    moved into `codegen/binding.py`. **Re-key decision:** the tables are now
    keyed by canonical (post-canonicalize) char-class forms — hex is one
    `[0-9A-Fa-f]` key (the pre-canonical `[0-9a-fA-F]`/`[a-fA-F0-9]` spellings
    are dead), `letter` is `[A-Za-z]`, `alnum` is `[0-9A-Z_a-z]`. The binding
    view reads the post-canon codegen grammar, so only normal-form keys can hit.
  - `bounds_to_quantifier` (regex suffix) moved into `codegen/aliases.py` as
    `_bounds_to_suffix`; the spec-based `collect_aliases(specs)` died and
    `collect_aliases_grammar` took the plain name `collect_aliases`.
  - `codegen/model_emitter.py`: old spec-based emit path DELETED;
    `emit_module_source_ir`/`IrModuleEmitter`/`CANONICAL_IMPORTS_IR` took the
    plain names.
- DELETED: `ir/derive.py`, `ir/spec.py` (`RuleSpec`), `ir/emit.py`
  (`render_specs`), `ir/naming.py`, `ir/topo.py` (`topo_sort` → `ir/order.py`'s
  `RuleOrder`), the whole `utils/` package (`names.py` `to_pascal` absorbed
  into `binding.class_name_for`; `to_snake` had no consumer; `quantifiers.py`),
  and `tests/integration/test_binding_scaffold.py` (its parity job done).
- `ir/__init__.py` export surface trimmed (RuleSpec/derive/emit/naming/topo
  gone). `getting_started/ex05` re-pointed onto `compiled.grammar` +
  `__grammar__`.
- Tests: dead-symbol test files deleted (test_derive/spec/emit/naming/topo,
  utils tests) with assertions re-homed to their successors (binding view,
  `test_order`, `test_aliases`); spec-shaped integration assertions
  (`test_compile_grammar_*`, `test_cross_flavour`, `test_full_round_trip`,
  `test_json`, `test_generate`, property conftest, `test_compile`) re-pointed
  onto the binding view / `canonical_grammar`; `test_model_emitter` and
  `test_aliases` rewritten against the binding-driven emitter + grammar input.
- `tests/integration/test_layering_invariants.py` extended: `lexic.utils`
  package gone and unreferenced; the retired `ir.derive/spec/emit/naming/topo`
  modules gone and unreferenced; one codegen entry / one emit path.
- Gates: suite 1501 green, `run_checks.sh` exit 0 (pylint 10.00/10, no R0801).

---

## 2026-07-04 — Task 5: positional fold + compile.py flip; parsing/models.py deleted (IR-native codegen effort)

The pipeline now runs IR-native end to end; the wrapper-rule instance bridge is gone.

- `src/lexic/parsing/fold.py` (new) — `PositionalFold`: generic positional
  `ParseTree → object` fold over the *real* codegen grammar
  (`kids[i] ↔ items[i]`; no `--f<idx>` wrapper rules). Config is plain data:
  `RuleFold(kind, ctor, n_items, fields)` / `FieldFold(item, mode, name, lo)`;
  modes validated against `lexic.ir.bind.BIND_MODES` (parsing → ir edge only —
  no codegen, no pydantic, no RuleSpec). Also hosts `lift_optional_nullables`
  (now `IrAst → IrAst`), `PositionalFold.run_ok` (run-collapse licence:
  collapse iff no config key among the unit leaves) and
  `collapsed_fold_tables` (memoised per (fold, grammar)).
- `src/lexic/compile.py` FLIPPED: `_compile_core` = `canonical_grammar` (new
  public front half: parse + canonicalize + directive flags → flagged IrAst)
  → `build_codegen_grammar` → `compute_binding` → `codegen_ir` → fold config
  → `instance_grammar = normalize(lift_optional_nullables(codegen_grammar))`.
  `CompiledGrammar` fields now `(classes, specs*, grammar=canonical ast,
  instance_grammar, fold, tables)`; `.parse()` surface unchanged.
  *`compile_grammar` and `CompiledGrammar.specs` are transitional
  (canonical_grammar + derive_specs) feeding `generate.py`/ex05 — die with
  derive in Task 6.
- `src/lexic/base.py` ported (coordinator-sanctioned pull-forward):
  `to_text()` walks the `IrRule` `__grammar__` arm + `IrBind` read from
  `model_fields` metadata (value_str = untagged `value` field; alternation =
  no binds → NotImplementedError; empty-arm rule with all fields None emits
  `""`); `semantic_dump()` excludes `semantic=False` binds; `to_grammar` =
  `flavour.apply(self.__grammar__)`.
- DELETED: `src/lexic/parsing/models.py` + `tests/unit/lexic/parsing/test_models.py`
  (assertions re-homed to `test_fold.py` / `test_compile.py` / `test_binding.py`;
  wrapper-name machinery died with no successor).
- Gates: old-vs-new parity 196/196 outputs identical (fixtures + 40 generate
  seeds × 7 grammars; type/model_dump/to_text/semantic_dump — HEAD oracle);
  the c-statement defect was already fixed by Task 2's canonicalize on the old
  path, so parity covers c statements too. Bench (instance parse+fold, best):
  arithmetic 118.4→72.4 ms (−39%), c 38.2→31.8 ms (−17%). Suite 1631 green,
  run_checks exit 0.
- Layering: new invariants — engine never imports pydantic or `lexic.ir.spec`;
  `parsing/models.py` gone and unreferenced.

---

## 2026-07-04 — Task 3: binding view + IrBind + codegen passes (IR-native codegen effort)

New surfaces, all parallel to the live derive/RuleSpec pipeline (nothing rewired;
Tasks 4/5 consume them, Task 6 deletes derive):

- `src/lexic/ir/bind.py` — `IrBind(item, mode, semantic=True)`, an `IrNamedTuple`
  record generated model fields will carry as `Annotated` metadata; `BIND_MODES =
  (text, gtext, model, models)` with construction-time validation. Exported from
  `lexic.ir`.
- `src/lexic/codegen/passes.py` — grammar→grammar codegen passes:
  `hoist_groups` (wraps `derive.hoist_helpers` until Task 6 moves the
  implementation in), `hoist_arms` (every non-unit-ref alternation arm →
  `<rule>-arm<N>` rule, inserted right after its alternation; empty arms kept;
  name collision raises), `relax_non_semantic` (arm-level refs to
  `semantic=False` rules get `min=0`; group interiors untouched), and the
  composition `build_codegen_grammar = relax(arm_hoist(hoist(ast)))`.
- `src/lexic/codegen/binding.py` — the open-table successor of derive's
  classify/parents/naming: `compute_binding(codegen_grammar) ->
  list[RuleBinding(rule_name, class_name, parent_class_name, kind, fields)]`
  with `fields: dict[str, IrBind]`. Naming cascade and fold-mode derivation are
  `IrDispatch`/`IrTypeMap` tables (raising defaults — `IrNot` deliberately
  unregistered, canonicalize rewrite 4 removes it); `class_name_for` absorbs
  `to_pascal`; the `ir/naming.py` tables are imported until Task 6 moves them.
- `ir/order.py::RuleOrder.ordered_parents_first()` — the parent-edge policy
  replacing `topo_sort` for emission order (start's ancestor chain first, then
  input order, every rule after its inheritance parent).

Parity gate `tests/integration/test_binding_scaffold.py` (TEMPORARY, dies with
derive in Task 6): binding == derive on order/classes/parents/kinds/field
maps/noise sets across all 10 ground truths, plus mode == `models._wrapper_mode`
per bound field. Suite 1549 green, `run_checks.sh` exit 0.

---

## 2026-07-03 — Task 2: canonicalize pass (IR-native codegen effort)

`src/lexic/ir/canonical.py` (`canonicalize`, `fold_name`) — a language-preserving
normal form for a grammar `IrAst`, run as the mandatory second stage of
`compile_grammar` (`parse → canonicalize → semantic flags`). Rewrites: 1 one-member
charclass → literal; 2 single-char/charclass/range alternation arms merge to one
class; 3 adjacent literal items merge; 4 `IrNot(charclass)` → positive Unicode
complement spans; 5 single-arm unquantified group splices into its parent sequence;
6 quantified single-arm single-item group pushes its quantifier onto the inner atom;
7 rule names + refs fold lowercase/`_`→`-` (distinct-rule collision raises
`UnsupportedConstructError`); 8 charclass normal form; 8b empty-literal items drop
(engine precondition); 9 canonical rule order.

Charclass member/complement math is now **intrinsic `IrCharClass` behavior**
(`pattern`/`members`/`sample`/`normalized`/`complement` on `ir/nodes.py`);
`utils/charclass.py` deleted, importers (`derive`, `generate`, `codegen/aliases`)
re-pointed. Rule ordering is `ir/order.py::RuleOrder` (start-first BFS over an edge
relation; `RuleOrder.by_refs`/`order_by_refs` = ref-edge policy) — reborn from
`topo.py` (which still serves derive until Task 6).

Headline fixpoint holds: `canonicalize(parse(json.gbnf)) ==
canonicalize(parse(json.abnf)) == JSON_GRAMMAR`, with `JSON_GRAMMAR` re-authored to
canonical form and `json.abnf`'s `HEXDIG` de-RFC'd to ranges. GBNF emit fixpoint
`canonicalize(parse(emit(canon))) == canon` holds for all ground truths;
`GBNF_GRAMMAR` re-authored to canonical form (all `canonicalize(G)==G`). Proof in
`tests/integration/test_canonical_fixpoint.py`. **Open:** ABNF emit fixpoint and
`canonicalize(ABNF_GRAMMAR)==ABNF_GRAMMAR` need an ABNF `IrLiteral`→num-val emit
change (char-val cannot spell `"`/controls and is case-insensitive) — not attempted
under Task 2.

---

## 2026-07-03 — engine perf round 3 landed (Optimize.md, complete)

Full-grammar product on the disputed corpus (subset-920 self-emit): **25.6 → 17.25 µs/char** (−33%; **0.57× Lark** full-vs-full, was parity). Recognize ~8.0 µs/char. The two engine levers: **seed-layout** (Task 1 — `CodeTables.rule_seeds` stored as primitive seed-pairs, `_seed` dedup-free; kernel −15%, charts byte-identical) and **FIRST-gated prediction** (Task 2 — per-dot-0-arm `(dot0, next_sym, gate)` triples where `gate` is `None`=always-seed or a frozenset FIRST charset with nullable-prefix continuation; `_seed` gates on `text[i:i+1]`; charts deliberately NOT byte-identical, product IR equality + ambiguity counts verified across all suite grammars). Instance path got run collapse (Task 4, separate entry). Task 5 (comment skip-machine) killed — FIRST gating leaves comment noise at 4.8% of items (was 27%).

Consolidation extra: the memoised-collapse skeleton shared by `reduce.collapsed_tables` / `models.collapsed_instance_tables` / `lexruns.recognition_tables` is now **`lexruns.collapse_runs(grammar, run_mode)`** — grammar-side core shared, the licence (`run_mode: (tables, unit_rid) → mode | None`) injected as the policy half; memoisation stays per-caller. Official baseline: `tools/benchmark/bench_baseline.json` (`parse_bench.py --save`, dual workload). Suite 1364/0; `tools/run_checks.sh` (sanity+ruff+pyright+pylint over src+tests+getting_started) is the standing done-gate per user ruling 2026-07-03.

## 2026-07-03 — `IrRule.semantic` flag + repr default-omission + scanner dissolved (Optimize.md Task 6R)

Supersedes Task 6 (the move landed and is subsumed — the module dies from its new location). Three coordinated changes:

1. **Record repr omits trailing default-valued fields** (`IrNamedTuple.__repr__`, `ir/base.py`): walk fields from the end, drop while `self[i] == declared_default` (`==`, so `IrScalar` type-aware eq applies), stop at the first non-default or a field with no default. Still valid codegen. `IrItem(IrLiteral('a'), IrQuantifier(1,1))` → `IrItem(IrLiteral('a'))`. Landed first to absorb the golden churn once.
2. **`IrRule.semantic: bool = True`** (user polarity ruling: no negation in the attribute — a rule IS semantic by default; noise rules declare `semantic=False`). `IrRule.__eq__`/`__ne__`/`__hash__` exclude it (compile-channel metadata; the fixpoint rationale relocated here from IrAst). **`IrAst` dropped its `non_semantic` field and its Task-3 eq/hash override** — back to plain `(rules, start)` tuple equality, which composes `IrRule.__eq__` element-wise. `IrAst.non_semantic` is now a **derived property** (`frozenset(r.name for r in rules if not r.semantic)`), keeping the `@non-semantic` directive vocabulary though the flag polarity is positive. Consumers (`derive_specs`, `GBNF_NOISE`/`ABNF_NOISE`) unchanged. `hoist_helpers` preserves `semantic` through its rebuild.
3. **Scanner dissolved into `compile.py`**: `parse_directives` → private `_scan_directives`; `src/lexic/parsing/directives.py` + its moved test deleted (the Task-6 move subsumed). `compile_grammar` applies a directive by reconstructing each named rule with `semantic=False`. Flavours flag their noise rules `semantic=False` individually (18 ABNF, 2 GBNF); the `non_semantic=frozenset(...)` IrAst kwargs are gone. A directive naming an undefined rule is silently ignored (no rule flagged, so absent from the property — observably identical to before).

Fixpoints green (ABNF+GBNF equivalence 86/0). Expected test breakage (repr goldens + `IrAst(non_semantic=...)` 3-field constructions) enumerated for the Sonnet wave, not fixed by Opus. See [[ir-shapes]], [[flavour-system]].

## 2026-07-03 — `parse_directives` relocated `ir/` → `parsing/` (Optimize.md Task 6)

With the directive *content* now living on `IrAst` (Task 3), `parse_directives` is a pure pre-lexical text scanner — parsing-side machinery (the comment-channel sibling of `parse_grammar`'s Earley half), not node algebra. `src/lexic/ir/directives.py` → `src/lexic/parsing/directives.py` (content unchanged; module docstring reframed off "IR-level"). `compile.py` imports from `lexic.parsing.directives` (the models/normalize/reduce submodule-seam precedent). Dropped from `lexic.ir.__init__` exports. `parsing/__init__.py` deliberately does NOT re-export it — `compile.py` is the only caller. Test mirror: `tests/unit/lexic/ir/test_directives.py` → `tests/unit/lexic/parsing/test_directives.py`; `test_init_ir.py`'s export assertion inverted to `test_directives_not_exported`. Also see [[architecture]].

## 2026-07-03 — instance-path run collapse: `parse_first` gets collapsed tables (Optimize.md Task 4)

`CompiledGrammar.parse` now parses over run-collapsed instance tables. `models.collapsed_instance_tables(grammar, fold)` (memoised per (fold, grammar)) mirrors `reduce.collapsed_tables`, gated by the ModelFold licence `_instance_run_ok`: a proved run collapses iff its unit leaves carry no `RuleSpec` and no field wrapper (`<rule>--f<idx>`) — bare-terminal units always ok, looked-through synthetic layers safe. Kept runs are `RUN_STR` (text-preserving); a collapsed run lands as one multi-char `IrLiteral` leaf (via `FastTree.char_leaf`), which `_subtree_text`/`_direct_models` consume identically to the per-char expansion — so round-trip fidelity holds. `RunTerm.mode` is never read by the tree path (only by `FusedReduce`). `CompiledGrammar` gains a `tables` field (compiled once at build); the public `parse_first` grew an optional `tables=` arg; a fast-path miss re-parses plain, ParseReduced-style. Collapses arithmetic ×2 / json_arr ×1 / json_ws ×1 / c ×3; zero for list/chess/japanese. Bench (arithmetic, charclass-heavy): kernel −78%, end-to-end −69%.

## 2026-07-03 — `IrAst.non_semantic`: structural-noise fact moved into the IR (Optimize.md Task 3)

The "which rules are structural noise" fact now lives on the IR as `IrAst.non_semantic: frozenset[str]` (non-child payload beside `start`), a single declaration feeding `derive_specs`, `semantic_dump`, and the reducer's noise map.

- **`IrAst`** (`ir/nodes.py`) grew `non_semantic: frozenset[str] = frozenset()` (third field; type params now `IrNamedTuple[IrSeq[IrRule], IrStr, frozenset[str]]`). `__eq__`/`__hash__` are **overridden to compare only `(rules, start)`** — `non_semantic` is compile-channel metadata (like a source location), and excluding it is what lets the self-hosting fixpoint `parse_grammar(flavour.apply(GRAMMAR), flavour) == GRAMMAR` survive (a fresh parse carries `frozenset()` while the authored self-grammar declares a non-empty set). `repr` still renders all three fields (valid codegen). See [[ir-shapes]].
- **`Directives` dataclass deleted.** `parse_directives(text, line_comment)` (still in `ir/directives.py`, docstring rewritten off the stale Lark `%ignore` framing) now returns a plain `(start, non_semantic)` tuple. The scan stays **pre-lexical** — settled decision: in-parse capture would make comments load-bearing and block below-chart noise collapse.
- **`compile_grammar`** resolves precedence (explicit arg > directive > fallback) then **rebinds** the resolved `start` / `non_semantic` onto the parsed `IrAst` (frozen record → reconstructed).
- **`derive_specs(ast)`** lost its `non_semantic_rules` parameter; it reads `ast.non_semantic`. `hoist_helpers` preserves `non_semantic` through the rebuild.
- **Flavours:** the private `_NON_SEMANTIC` tuples are gone; `GBNF_GRAMMAR`/`ABNF_GRAMMAR` declare `non_semantic=frozenset({...})`, and `GBNF_NOISE`/`ABNF_NOISE` iterate `<GRAMMAR>.non_semantic` — one source of truth. (`grammars/json.py` needed no change; its `IrAst` defaults `non_semantic=frozenset()`.)
- Not touched: `ir/emit.py` `render_specs` (dead-shim removal flagged separately, out of scope); `src/lexic/parsing/` (owned by concurrent agents — its `normalize.py`/`models.py` `IrAst` construction sites rely on the `frozenset()` default).
- Tests to port (mirror rule): `test_directives.py`, `test_init_ir.py::test_directives_exported`, `test_derive.py::test_derive_marks_non_semantic_field_min_zero`, `test_nodes.py::test_repr_irast_is_codegen`.

## 2026-07-02/03 — Lark→Earley cutover landed (Phases 0–8, `PLAN_cutover_parsing_v2.md`)

`src/lexic/parsing/` (formerly `parsing_2/`) is now the **only** parsing implementation in Lexic — both grammar-text parsing and generated-instance parsing. The old Lark-backed `src/lexic/parsing/` (`meta_parser.py`, `lark_builder.py`, `transformer/`) is deleted outright; no `parsing_legacy`/`parsing_old` shim. `lark` is removed from `pyproject.toml` and `uv.lock`; it survives only as the fixed reference baseline in `tools/benchmark/parse_bench.py` (pure Lark, zero lexic machinery, raced against the native engine).

Key landed shape:

- **`IrFlavour` (`ir/flavour.py`) is R1: zero methods** beyond the inherited `IrEmitter` protocol. `parse_quantifier`/`parse_charclass`/`normalize_literal`/`meta_grammar` are gone, replaced by nothing (not even as free functions) — everything a flavour needs for parsing is IR action algebra + data tables inside a `Reducer`. New ClassVars: `grammar: ClassVar[IrAst]` (the flavour's own self-grammar, authored directly as IR — no meta-grammar string anywhere) and `reducer: ClassVar[IrDispatch]` (a `lexic.parsing.reduce.Reducer` at runtime).
- **`grammars/gbnf.py` and `grammars/abnf.py`** are single flat modules (no `gbnf/`/`abnf/` subpackages) carrying emit `actions`, self-grammar, reductions/noise map, escapes, and the singleton all in one file. GBNF gained a full self-grammar + reducer (Phase 2, previously Lark-only). ABNF's self-grammar was extended to full RFC 5234+7405 parity (Phase 3): `[...]` option, num-sequences (`%x0D.0A`), comments + line-folding, `%s`/`%i` string markers, `%d`/`%b` values, prose-refusal, incremental `name =/ body`.
- **`compile_grammar`** (`compile.py`) now runs `parse_reduced(normalize(flavour.grammar), text, flavour.reducer)` — the same Earley engine instance parsing uses — with a per-flavour-name memo (`_NORM_GRAMMAR_CACHE`) so `normalize(flavour.grammar)`'s object identity stays stable across calls (keeps the engine's `compile_tables` memo hot).
- **`CompiledGrammar`** (`compile.py`) fields are now `classes`, `specs`, `grammar: IrAst`, `fold: ModelFold` — no `parser`/`transformer`. `.parse(text)` runs `fold.apply(parse_first(grammar, text))`; `parse_first` is the engine's deterministic-first-derivation entry (parity with Lark's `ambiguity="resolve"` — some ground-truth instance grammars, e.g. `json_ws`'s `int`, are genuinely ambiguous).
- **`parsing/models.py`** (new): `specs_to_grammar` reconstitutes derived `RuleSpec`s into an instance `IrAst`; `ModelFold` replaces `build_transformer`, folding a `ParseTree` into `GrammarModel` instances via an explicit-stack bottom-up walk (no recursion).
- **Engine gained `IrNot` support** (Phase 0 prerequisite — negated character classes, needed by 4 of the 7 ground-truth GBNF grammars and by GBNF's own self-grammar).
- **`tests/integration/test_{gbnf,abnf}_ir_equivalence.py`** converted from Lark-comparison gates to golden fingerprint tests: every ground-truth/fixture grammar reduces to an `IrAst` with an expected `(start_rule, rule_names)` fingerprint, unambiguously, and stays stable under emit→reparse.
- `utils/names.to_lark_name` deleted. `test_layering_invariants.py` gained `test_engine_package_does_not_import_grammars_or_codegen` and `test_engine_imported_by_runtime_only_via_compile_seam` (the engine is a leaf; `compile.py` is the only sanctioned runtime→`lexic.parsing` seam).

Open items left for the user (not yet resolved as of this entry): whether `gbnf.py`/`abnf.py`'s C0302 (too-many-lines) waiver stands permanently or the modules split; two ABNF parity gaps (`%d`/`%b` value-sequences, uppercase `%X`/`%D`/`%B`/`%S`/`%I` markers) fail as parse errors rather than an explicit `UnsupportedConstructError`. Wiki pages updated: [[architecture]], [[flavour-system]], [[public-api]], [[error-vocabulary]]; a CLAUDE.md refresh was prepared as a proposal (`zzz_current_work/postleo/CLAUDE_md_refresh_proposal.md`) rather than applied directly.

---

## 2026-06-08 — `Field` mutable-default fix + astroid `dataclass_transform` plugin

Two issues found reviewing `Field`/`IrCachingTuple` (`ir/base.py`):

1. **Mutable-default sharing bug.** `Field.build()` returned `self.default` by reference, so a mutable `default` (e.g. `ruleref_frames: list[bool] = Field(default=[False])` in `codegen/aliases.py`) was shared across **every** instance and persisted mutations across constructions (classic mutable-default footgun). Fixed by deep-copying in `build()`: a `default_factory` result is returned as-is; a plain `default` is now `copy.deepcopy`-d, so each instance gets an independent value. Regression tests added to `tests/unit/lexic/ir/test_base.py` (Field isolation + IrCachingTuple field-merge/default resolution — that file had **no** Field/IrCachingTuple coverage before).

2. **pylint false positives on `Field` defaults.** `Field.__new__` is typed (overloads) to return the field's type, which pyright honours but astroid does not — it infers `aliases: dict = Field(...)` as a `Field` instance, raising bogus `no-member`/`unsupported-membership-test` at read sites (`aliases.py` was 8.82/10). Root cause: astroid has no :pep:`681` `dataclass_transform` support for field types declared on a *base* class (`IrNamedTuple`/`IrCachingTuple`). Fixed with a repo astroid brain plugin `tools/pylint_lexic.py` that rebinds each annotated field of an IR field-record class to an instance of its annotation type (reusing astroid's `_infer_instance_from_annotation`). Wired via `[tool.pylint.main] load-plugins`/`init-hook` in `pyproject.toml`. No inline suppressions. Whole-`src` pylint back to clean (only the pre-existing `R0903` on `IrCachingTuple`).

Follow-ups in the same pass: **`Field` now requires exactly one of `default`/`default_factory`** (overloads reject `Field()` statically; `__new__` raises `TypeError` at runtime so a field never silently carries the `_MISSING` sentinel). **`IrCachingTuple.__init_subclass__` now merges every caching base's fields in reverse-MRO order** (the `dataclasses` convention, dedup'd) instead of only the nearest base — well defined under multiple inheritance, not just a linear chain. Note: the `*Ts` type params do **not** track merged fields, so positional *typing* of a subclass is unreliable (use named access / `tuple(inst)`); runtime field layout is correct. Full suite 628 passed; `pyright src/ tests/` = 0.

**astroid gotcha (R0903 root cause).** `IrCachingTuple` tripped `too-few-public-methods` because astroid **cannot resolve a sole base subscripted with a bare `TypeVarTuple`** — `class IrCachingTuple[*Ts](IrNamedTuple[*Ts])` gave astroid *zero* ancestors, so it counted ~0 public methods (the class actually inherits `eval`/`children`/`rebuild`/`bind`/`bound`/…). `IrNamedTuple`/`IrTuple` escape this only because they redundantly list a concrete `IrNode[IrSelf, IrSelf]` second base. Fix: do the same on `IrCachingTuple` (semantic no-op; `IrNode` is already reached via `IrNamedTuple`). Resolving the ancestors then surfaced a *second* astroid quirk: iterating `cls.__mro__[1:]` (a tuple slice) lets pylint infer the element types and emit false `no-member` on `base._fields`/`base._child_attrs`, whereas `reversed(cls.__mro__)` yields uninferable elements and is checked-clean. The two `__init_subclass__` loops were unified into the single `reversed` walk (tracking the nearest field-bearing base via last-write-wins), so no spurious `no-member`. `src/` pylint = 10.00.

---

## 2026-06-05 — Phase-0a algebra expansion (value tier + comparison/conjunction)

Added the value-aware action algebra on top of V2: `IrScalar(IrLeaf)` value-leaf base (hosts `eval` + type-aware `__eq__`/`__ne__`/`__hash__`/`__repr__`, all delegating to the primitive); `IrInt(IrScalar, int)`; `IrStr` re-parented onto `IrScalar` (its `__new__`/`eval` dropped). `IrField` now reads typed attrs via `out: type[IrScalar]` (default `IrStr`), made callable by a forwarding `IrScalar.__new__`. Comparison: `IrOp(IrStr)` operator leaf (the node IS its string — **no `Cmp` enum**) + `IrCompare` + short-circuit `IrAnd(IrTuple[IrSelf])`, all returning `IrInt ∈ {0,1}` (no `IrBool`). `IrTuple.eval` relaxed `-> Self` → `-> IrSelf` so reducers can override (no `[T,R]` generic). `IrCond` generalized `field: str` → `test: IrSelf`. New exports: `IrScalar`/`IrInt`/`IrOp`/`IrCompare`/`IrAnd`.

Deviations from the plan (`docs/superpowers/plans/2026-06-04-phase-0a-algebra-expansion.md`) recorded in [[decisions]] (2026-06-05 entry): no `Cmp` enum (→ `IrOp`), `type[IrScalar]`+`__new__` instead of the `type[IrStr]|type[IrInt]` union, `IrScalar` hosting eq/hash/repr, and `IrTuple.eval -> IrSelf` instead of the two-param generic. Full suite 593 passed; `pyright src/ tests/` = 0. [[ir-shapes]] + `CLAUDE.md` updated.

---

## 2026-06-04 — Primitive-node model (V2) migration complete

The coercion-based node model is gone. Nodes now ARE their payload — three tiers: str-leaves (`IrStr`: `IrLiteral`/`IrCharClass`/`IrRuleRef` subclass `str`), variadic collections (`IrTuple`: `IrSequence`/`IrAlternation` subclass `tuple`), and fixed-arity records (`IrComposite` frozen dataclasses). Removed `IrType`, `coerce`, `_ir_field_types`, the load-bearing `__init__`, `IrStrLeaf`, `IrCollection`/`_items_attr`, and the `_str_name`/`__str__` cascade (now `__repr__`-is-codegen). No `.value`/`.items`/`.arms` accessors. Whole-tree `pyright src/ tests/` = 0 (genuine — the old `*args/**kwargs` init had masked ~174 errors); full suite 572 passed; pylint core 10/10.

New decisions recorded in [[decisions]]: type-aware `IrStr.__eq__` (distinct leaf kinds unequal, plain-`str` compatible — fixes `@cache`/tree-equality poisoning); `IrThis` + lazy `IrReturn` for declarative find-first (no `IrCallable`); two type params `[Iri, Ir_co]` with `_bound` from the **last**; no `cast`/suppressions; **open-set consumer rework deferred** to a separate spec (`derive`/`codegen`/`parsing`/`generate` still carry closed-set `isinstance`/`dict[type,…]` ladders — legacy, not the target). [[ir-shapes]] rewritten to V2; `CLAUDE.md` IR-types section and flavour template updated (flavour dataclasses must NOT use `init=False` — it silently empties `actions`). Plan: `docs/superpowers/plans/2026-06-01-ir-primitive-node-model.md` (Tasks 1–16).

---

## 2026-05-30 — IrNode construction: dataclass-generated `__init__` + `__post_init__` coercion

`IrNode` previously carried one hand-rolled `__init__(*args, **kwargs)` (decorators used `init=False`). Two bugs: type checkers/IDEs saw `(*args, **kwargs)` instead of real per-field signatures, and unknown keyword args were silently dropped (`IrLiteral('x', bogus=1)` constructed fine). Fixed by deleting the custom `__init__`, dropping `init=False` from every `IrNode`-subclass `@dataclass` across `ir/nodes.py`, `ir/action.py`, `ir/walk.py`, `ir/derive.py`, `codegen/aliases.py`, and both `grammars/*/flavour.py`, and moving coercion into a base `__post_init__`. Now signatures are real and unknown kwargs raise `TypeError`. Side effects: `IrReturn.__post_init__` calls `super().__post_init__()`; `_HoistTransformer.parent_name` gained a default (required-after-defaulted ordering); `IrRule.name` is now strictly required. Invariant recorded in [[ir-shapes]]; the flavour template in `CLAUDE.md` no longer prescribes `init=False`.

Collateral: while landing this, the in-progress `derive.py` edit (`_extract_none` → `IrNone`, `_extract_group` filter rework) was left with `_hoist_item` still checking `is None`, which built helper rules with `IrNone` bodies. Resolved by keeping the `has_ruleref` filter in `_extract_group` (returning `IrNone`) and the `_hoist_item` guard on `is IrNone`; two `_EXTRACT_BODY` tests updated from `is None` to `is IrNone`.

## 2026-05-28 — Slice B substrate landed; flavour-as-IrEmitter migration; helpers cleanup

**Substrate landed.** Every IR node now descends from `IrSelf` and is callable: `node(d, n, nc) -> Ir_co`. The action-algebra (`ir/action.py`) and the `IrDispatch[Ir_co]` substrate (`ir/walk.py`) are in. Presets `IrVisitor` / `IrTransformer` / `IrEmitter[IrLiteral]` configure default bodies (`IrWalk`, `IrRebuild`, `IrEmit`). Dispatch is **action-table-driven**, concrete-first MRO resolution, memoised — and crucially, `IrDispatch` does NOT auto-walk children: action bodies own recursion.

**Flavour migration.** `IrFlavour` IS-AN `IrEmitter`. Each flavour is now a single `grammars/<name>/flavour.py` module: `META_GRAMMAR` string, private `_<Name>Escapes` + `<NAME>_ESCAPES` singleton, `<NAME>_ACTIONS: tuple[IrAction, ...]`, private `_<Name>Flavour` + `<NAME>_FLAVOUR` singleton. `grammars/__init__.py` imports and registers the singletons on import. `base.GrammarModel.to_grammar(flavour)` calls `get_flavour(flavour).apply(self.__grammar__.to_ir_rule())`.

**Cleanup.**
- Deleted: `ir/helpers.py` (HelperRuleRegistry), `grammars/gbnf/emitter.py`, `grammars/gbnf/escapes.py`, `grammars/gbnf/meta_grammar.py`, `grammars/abnf/emitter.py`, `grammars/abnf/escapes.py`, `grammars/abnf/meta_grammar.py`.
- `utils/quantifiers.py` survives — consumed by `parsing/lark_builder.py` and `codegen/aliases.py`. GBNF's `parse_quantifier` no longer uses it (uses the local `GBNF_QUANT_SYMBOLS` table). Scheduled for later cleanup.
- `ir/emit.py` ships `render_specs()` as a helper; currently only its own test consumes it.

**Wiki / doc updates.**
- **CLAUDE.md**: test count → 474; file tree rebuilt (added `ir/action.py`, `ir/walk.py` substrate; removed deleted modules; flagged `utils/quantifiers.py`); pipeline diagram updated to `flavour_singleton.apply(node)`; IR-types section expanded with `IrSelf` mixin, `IrNode[Ir_co]` generic, action algebra, dispatch presets; `IrLiteral` dual role documented; layering exception #1 updated to `lexic.grammars.gbnf.flavour.GBNF_FLAVOUR`; import paths refreshed (`IrQuantifier`, action / walk surface, singletons).
- **[[architecture]]**: rewritten — single pipeline (no more two-pipeline section); IR substrate detailed with `IrSelf` / typed bases / dispatch / presets; flavour-as-`IrEmitter` documented; `IrLiteral` dual role section; deleted-modules note.
- **[[flavour-system]]**: rewritten — singleton convention (private class + public instance), action-tuple shape with GBNF example, `IrCallable` vs pure-algebra guidance, `IrFlavour` ABC, new step-by-step.
- **[[ir-shapes]]**: rewritten — substrate first (`IrSelf` / `IrType` / `IrStr` / `IrTuple`), then grammar AST, then action-algebra table, then dual-role note. `IrQuantifier` documented; `_child_attrs` / `_items_attr` convention spelled out.
- **[[decisions]]**: appended **P12–P18** — IR-pass-by-action-table; action bodies AND dispatcher are IR nodes; dispatcher generic in result type with LSP-compatible signature; concrete-first MRO resolution; `IrReturn` short-circuit via `_Return` BaseException; `IrLiteral` dual role; every IR node callable.
- **README.md**: rewritten — concise project intro, supported flavours, quick example, architecture pointer, dev setup, status.

Test suite green at 474 passed.

---

## 2026-05-13 — IrItem cutover complete; document sweep

**Cutover landed.** All 18 parallel-track tasks done. The IrItem-based pipeline is the only pipeline.

Pipeline changes:
- `compile_from_path` now uses `path.stem` as module stem (e.g. `arithmetic.gbnf` → `generated/arithmetic.py`); `compile_text` continues to use `anon_<sha1>.py`.
- `codegen(specs, stem)` in `codegen/__init__.py` ruff-formats generated source via `find_ruff_bin()` before writing.
- `Optional[...]` wrapping for optional sequence fields fixed in `model_emitter.py`.
- `Union[X]` single-arg bug fixed in `_group_type`.
- Layering invariant test fixed to skip its own source file when scanning for forbidden strings.

Wiki / doc updates:
- **CLAUDE.md**: test count corrected (448), "two pipelines" section replaced with "single IrItem pipeline", project layout rewritten, architecture diagram updated, layering exceptions updated, IR types section consolidated (old shape removed), import paths cleaned up, stale constraints removed.
- **[[cutover-plan]]**: rewrote to reflect completion; what-replaced-what table; pointer to Slice B remaining work.
- **[[public-api]]**: `compile_text` / `compile_from_path` / `compile_grammar` / `codegen` / `build_lark` descriptions updated; "Tasks 8–18" language removed.
- **[[index]]**: task routing updated (removed stale Tasks 8–18 rows; added Slice B token reservation row); cutover-plan active work entry updated.
- **[[slice-b-status]]** (new): audit of Slice B Phase 1 (done/obsolete), Phase 2 (entirely obsolete), Phase 3 (token reservation — still required).

Remaining Slice B work: token reservation (Tasks 33–34) — pre-tokenisation scan in GBNF for `<name>`, `<[N]>`, `!<name>` + `tests/integration/test_token_reservation.py`.

---

## 2026-05-10 — Vault reorganization + pipeline canvas
- Deleted empty `related-page.md`
- Moved Lexic pages into [[lexic/]] subfolder (11 pages)
- Split `grammar-theory.md` into [[theory/grammar-formats]] and [[theory/parsing-theory]]
- Created [[pipeline-map.canvas]] showing old and new pipeline flows
- Updated [[index]] — all wikilinks now folder-prefixed, two new theory rows
---

## 2026-05-09 — Ingested parallel-track IR cutover plan (Tasks 9–18)

Pulled concrete API and behaviour details from `docs/superpowers/plans/2026-05-08-parallel-track-ir-cutover.md` into the wiki.
- [[decisions]]: added "Cutover commitments (CQ #1, #2, #4)" entry covering no-FIXME, no `ws` hardcoding, fixed canonical imports.
- [[new-codegen]]: expanded Tasks 9–14 with `CANONICAL_IMPORTS`, `_field_type` rules, `_repr_iritem`, `regex_for_charclass`/`regex_for_group` public surface, `Pattern`/`Pattern2` Tier-3 fallback, `codegen(specs, stem)` signature (no `flavour` parameter).
- [[cutover-plan]]: replaced 8-bullet checklist with the 17 sub-step cutover sequence; added Slice 3 (`parsing/`) table for Tasks 15–17.
- [[public-api]]: added `codegen(specs, stem)` and `build_lark(specs, classes, start_rule)` future signatures.
- [[architecture]]: documented post-cutover `parsing/` directory shape and the layering-invariant test gate.

---

## 2026-05-09 — Wiki improved for agent token efficiency

Rewrote `index.md`: query-answerable page descriptions, quick lookup table, task routing section. Added `When to load:` line to every page. Added new pages: [[testing]], [[new-codegen]]. Updated [[cutover-plan]] to mark Task 8 done. Fixed template name (`note.md.md` → `note.md`).

---

## 2026-05-09 — Task 8 landed (uncommitted)

`new_codegen/aliases.py`: `PatternAlias` frozen dataclass + `collect_aliases`. Walks `IrItem` nodes via `IrVisitor`, dedupes on regex, names via Tier-2 `CHARCLASS_NAMES` (CamelCase) or `"Pattern"` fallback. Tests in `tests/unit/lexic/new_codegen/`.

---

## 2026-05-09 — `public-api` wiki page added

Documented the stable public surface: `parse`, `compile_text`, `compile_from_path`, `compile_grammar`; `CompiledGrammar` fields; `GrammarModel` methods (`to_text`, `to_grammar`, `semantic_dump`); GBNF grammar format and directive precedence rules.

---

## 2026-05-09 — Wiki created

Created initial wiki structure with pages for [[architecture]], [[ir-shapes]], [[flavour-system]], [[field-naming]], [[error-vocabulary]], [[invariants]], [[cutover-plan]], [[decisions]].

Source: CLAUDE.md audit + code reading session. All pages reflect codebase state at this date.

---

## 2026-05-09 — CLAUDE.md updated

Rewrote CLAUDE.md to reflect current codebase state: both pipelines documented, layering rules reproduced in full, flavour system described, error vocabulary table added, `tools/auto_fix.sh` prominently in Commands.

---

## 2026-05-09 — Tasks 6 and 7 completed

**Task 6 (`ir/naming.py`):** `CHARCLASS_NAMES` reduced from ~10 entries to 9 authoritative entries. `[a-zA-Z]` → `"letter"` (was `"alpha"`). Both hex orderings normalise to `"hex"`. All tests updated to match new ground truth.

**Task 7 (`ir/derive.py`):** Replaced 13-branch `if isinstance` chain in `_field_map` with `_FIELD_BASE` dispatch table. `_ATOM_HINT[IrGroup]` bug fixed: was returning `"value"` for ruleref groups; now correctly returns `"kind"` consistent with `_group_field_base`.

---

## 2026-05-08 — Tasks 1, 2, 4 completed

**Task 1:** `grammars/new_gbnf/` skeleton created. Pure-copy of stable modules from `gbnf/`.

**Task 2:** `grammars/new_gbnf/flavour.py` — `GbnfFlavour(Flavour)` class attribute wiring. `emitter = GbnfEmitter` (class ref, not instance). Fixed `type: ignore` by using class reference.

**Task 4:** `grammars/new_gbnf/emitter.py` — IrItem-only `GbnfEmitter`. Fixed pyright error (`Atom` vs `IrItem` in generator guard). Fixed test `_spec()` `kind` parameter annotation.

Tasks 3 and 5 deleted from plan — dead weight, no behaviour without `flavours.py`.

---

## 2026-05-08 — `quantifier_to_bounds("")` fix

`utils/quantifiers.py`: changed `if q is None` to `if not q` so empty string is treated same as `None` (returns `(1,1)`). Needed because GBNF parser emits empty string for bare atoms with no quantifier token.

---

## 2026-05-08 — Plan: parallel-track IR cutover

`docs/superpowers/plans/2026-05-08-parallel-track-ir-cutover.md` created. 18 tasks; builds `new_gbnf/`, `new_codegen/`, `parsing/` against the IrItem shape alongside legacy code, then cuts over atomically in Task 18.
