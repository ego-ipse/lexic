# READING — what the code says (2026-08-09)

The deep-read of lexic ordered before the next design round. Sources: the
spine (`ir/spine/spine.py`, `meta.py`, `records.py`), the compiler
(`compile/__init__.py`, `pipeline/passes.py`, `binding.py`, `synthesis.py`),
the projection surfaces (`payload/codec.py`, `encode.py`, `reader.py`,
`export.py`; `notation/parse.py`, `loader.py`; `module/export.py`,
`selfgrammar.py`), the GBNF flavour whole (`grammars/gbnf.py`, 1314 lines),
the layout algebra (`ir/text/layout.py`), the manifests
(`grammars/*.flavour.ir`), and the artefacts on disk (`generated/`).

These are findings FROM the code, kept separate from design. Design goes in
THINKING once ruled.

## 1. Classes are constructed, not imported — one move, three sites

The compiler never writes source on the runtime path. `synthesis.py` builds
every model class with a bare `type(name, bases, ns)`; `notation/loader.py`
builds a flavour class the same way; `bind_module` re-derives binding and
attaches it to an already-imported module. CPython resolves the metaclass
(`IrMeta`) from the bases, and `IrMeta` injects `__slots__ = ()` — the
physical floor under "a node IS its payload": no `__dict__` exists to hide
state in. The exported `.py` twin is an *emission* of a construction that
happens without it. Compiled files are outward projections, never origins
(confirms §10c independently).

## 2. Sameness is layered, and every layer has its own machine witness

A synthesized class carries three identities at three strengths:

- `__grammar__` — its rule, the actual IR node (the thing itself);
- `__shape__` — the rule-CLOSURE digest (structural sameness across
  compilations; the closure, not the bare rule, because narrowing a
  pass-through alternation changes the language while every named rule
  stays identical);
- `__module__ = generated.<identity>` — the whole grammar's content
  identity ("two different grammars can share a filename, and a consumer
  telling two `Root`s apart has only this").

The same discipline recurs at every seam:

- `repr_args` elides a trailing default only on same-concrete-type AND
  equality — `IrArgs() == IrTuple()` under tuple equality, so equality
  alone reconstructs a *different* object (F-REPR-1).
- The payload codec refuses most-derived-type ties ("an empty
  `IrLiteral()` is a perfectly good fixpoint of a wrong encoder").
- The manifest conformance gate holds `gbnf.py` and `gbnf.flavour.ir`
  equal by a SEVEN-step comparator: identity fields, per-section
  canonical-repr equality, `non_semantic` sets, escape-codec
  **behavioural** parity (synthesized codec classes never `==` — behavior
  is the only available witness), equal `parse_grammar` over the corpus,
  equal emitted text, full register→compile→parse→round-trip.
- `verify_module` re-parses an exported twin WITH LEXIC and recomputes
  every expectation **with the same functions the exporter rendered
  from** (`compute_binding`, `field_type`, `docstring_lines`) — "a
  disagreement means the FILE drifted."

"Different things ensured to be the same" is a family of *checked*
sameness relations. Where repr can witness, repr is used; where classes
cannot be equal, behavior stands in; where nothing at read time could
disagree (a reduction over an ir/plain payload), the claim is RECORDED and
the one party able to check is named (`built_under`).

## 3. The compiler's intermediates are all grammars

`build_codegen_grammar` = `relax_non_semantic(hoist_arms(hoist_groups(ast)))`
— three grammar→grammar rewrites, each `IrAst` in / `IrAst` out, each
language-preserving-for-instances with the proof in its docstring
(nullability read from the INCOMING grammar; relaxing on the output would
be self-fulfilling). The pipeline's every stage is the one object atlas
already renders three ways (text, rails, graph). The parser needed bespoke
instruments; the compiler needs pointing the existing ones at four grammar
snapshots: canonical → groups-hoisted → arms-hoisted → relaxed. Then the
binding view (`RuleBinding`: rule → class/kind/parents/fields) is the
bridge table from the last snapshot to the class world.

## 4. The class hierarchy IS the alternation structure

`binding.py` reads unit-ref arms as subclass edges, breaks unit-arm cycles
by a language-equality argument (cycle members derive the same language →
siblings; outside edges widen to the whole cycle), and orders bases
most-derived-first for C3. Inheritance in a generated module is the
grammar's alternations read as subtyping — not a modeling choice. Field
naming is a three-tier cascade (rule name → pattern library → positional);
field DECLARATION order is required-first and deliberately differs from
item order — the truth of position lives in `IrBind`, never in `_fields`.

## 5. One class mechanism under everything

`IrNamedTuple.__init_subclass__` (annotations → `_fields` → itemgetter
properties) runs identically for hand-written spine nodes, synthesized
model classes, loaded flavour classes, and the selfgrammar's own
`MModule`/`MClass`/`MField`. A generated `Root` and `IrItem` are siblings.
Consequence: everything in the system answers one uniform read protocol —
`_fields` (names), `children()` (structure), `repr_args()` (constructor
spelling). One generic IrSelf viewer covers a grammar node, a model
instance, a reducer, a flavour, a codegen intermediate, and a parsed
compiled file, through the same three calls. IrSelf has never been
represented in atlas; the spine is already shaped for exactly one viewer.

The one named refusal: `IrLambda` — the node whose payload is a callable,
and therefore the one the notation refuses. The boundary of
representability is a single type, by design.

## 6. The generated files are a typed family, not one artefact

Five species in `generated/`:

| species | example | imports | identity carried |
|---|---|---|---|
| twin module | `json.py` | lexic (compile/ir/model) | GRAMMAR spelled twice + import-time self-check |
| ir-target value | `json_grammar.py`, `qwen3_vocab_value.py` (31MB tokenizer) | `lexic.ir` spine only | ORIGINS (SHAPE=0 — spine classes carry no grammar) |
| model-target value | `json_value.py` | the twin (caller-named) | SHAPE (rule-closure digest) + ORIGINS records content identity |
| plain-target value | `json_plain.py` (527B) | nothing | DIGEST only |
| sidecar reader | `payload_reader_<digest>.py` | nothing | its own source digest IS its name |

Load-bearing facts:

- **"There is no target flag."** Which species a value exports to is
  decided by the codomain of the reduction that produced it — the READING
  determines the species of compiled file. One grammar, several readings,
  several artefact types.
- The twin states its grammar twice (classes for humans/pyright, the
  `GRAMMAR = IrAst(...)` constructor spelling for the machine) and
  `bind_module(GRAMMAR, globals())` re-derives and validates the two
  halves agree at every import. Twins come in two modes: bind-mode
  (GRAMMAR + bind_module) and inline-tables mode (per-class
  `__grammar__`/`__shape__`/`__binds__`).
- The model-target value is a two-file molecule: ORIGINS names the content
  identity (`generated.json_<hash>`, which does not import), imports fetch
  from the twin's location, SHAPE proves the fetched classes carry the
  rules the value was built against. The merge-find-set, literal.
- The payload is a **queryable compiled form**: every child index points
  at an earlier record, so `subtree(tables, symbols, index)` materialises
  one record and only its closed reach-set. Partial decode — zoom — is
  native to the format.
- Two sidecar readers coexist in `generated/` right now (July's and
  August's) — version skew impossible by construction, demonstrated live.
- Provenance is three questions asked by three parties: digest (reader:
  are these the written tables), shape (reader: are the supplied symbols
  the ones written against), reduction (producer only, via `built_under`:
  is this cached artefact still current).

## 7. A flavour is five IR values — two of them are programs

`_GbnfFlavour` has zero methods. Its ClassVars: metadata, an `IrAst`
self-grammar, an `EscapeCodec`, and two PROGRAMS in the IR action algebra
— `GBNF_REDUCTIONS` (text→IR) and `GBNF_ACTIONS` (IR→text). No `def`, no
lambda anywhere in either. That is WHY the `.flavour.ir` manifests can
exist: the flavour was always a value, spellable as one notation
expression, loadable by `type()`.

The two halves are twins keyed from opposite sides:

- reducer keyed by RULE NAME (`IrRuleRef("q-counted") → program`) —
  syntax-directed, the text side;
- emitter keyed by NODE TYPE (`IrAction(IrQuantifier, program)`) —
  structure-directed, the value side.

They mirror feature by feature. Escapes: structural on the way in (one
grammar rule per escape kind, constants or `IrUnradix`), codec data on the
way out (`IrEscape`/`IrEscapePoint`). Quantifiers: `GBNF_QUANTIFIERS` is
an `IrMap` whose keys are exact `IrQuantifier` VALUES with the counted
forms in an `IR_DEFAULT` `IrCond` branch — "the data map IS the action
body" — decoded back by `q-*` rules with a mirror sentinel copying `lo`
into `hi`. Round-trip fidelity is the sameness contract between the
halves.

Beyond parsing, in the flavour:

- **The layout algebra**: Wadler pretty-printing as IR data (`IrText`,
  `IrLine`, `IrNest`, `IrGroup`), breaks solved against a width; doc nodes
  double as action-body templates; `width=None` reproduces the flat form
  byte-for-byte. Between IR and emitted text there is a third tree.
- **Token terminals**: `<text>` / `<[id]>` / `<[lo-hi]>` / `!<…>` / `.`
  all reduce to `IrAlphabet("tokens", inner)` — a REGISTRY NAME where the
  tokenizer (itself exportable as a 31MB ir-value artefact) plugs in at
  parse time. Negation lives inside the alphabet: the encoding governs
  the token-universe complement.
- **Engine-aware authoring**: the self-grammar's comments argue k=1/k=2
  FIRST-disjointness for every left-factoring ("stays off the island
  path") and engineer maximal munch structurally. The grammar is written
  in dialogue with the PDA analysis that consumes it.
- `gbnf.py`'s stated end-goal: "completely auto-generated." The .py and
  the manifest are two inscriptions of one flavour; the seven-step gate
  (§2) holds them equal until one derives the other.

## 8. The module self-grammar: composition and the parse of a compiled file

`module_grammar()` EMBEDS the notation grammar wholesale — merging is
concatenation, `m-` prefixes the module rules, and the only rewrite is
`ws → ws-inl` on six token rules so a value-final statement's own newline
is the consuming barrier. Grammar composition is real, simple, and already
practiced: one grammar imported into another as rules.

`parse_module` parses an exported twin INTO SPINE RECORDS
(`MModule`/`MClass`/`MField` are `IrNamedTuple`s) — the compiled file's
parse lands on the same substrate as everything else. `verify_module` then
closes the emit→reparse loop at file granularity: GRAMMAR equals the
compiled canonical AST; per class, name/bases/docstring/fields/inline
tables against a binding recomputed by the exporter's own functions. Even
the docstring check re-renders the rule through the flavour's emit
(`apply(rule, width=None)`) and compares — the class docstring in a twin
is flavour-emitted grammar text, verified as such.

One asymmetry worth holding: flavour reducers are pure IR (manifest-
spellable, no defs — the settled rule), but the module fold is authored
Python ctors over `foldkit` (`ModelBody`/`FieldFold` — the "supplied
class" sugar from binding.py's open-binding contract). Two fold-authoring
tiers exist: the IR-algebra tier (portable, spellable, data) and the
Python-ctor tier (compile-side, not spellable). The boundary between them
is exactly the `IrLambda` boundary of §5.

## 9. Doctrine statements found in the code, relevant to atlas

- "A reduction is a reading, and one grammar must support several"
  (loader.py, on why the reducer is carried, not derived — the manifest
  even refuses a `noise` section with a bespoke error). The Session's
  readings are this sentence, made kinesthetic.
- "There is no target flag" (payload/export.py) — the reading decides the
  artefact species.
- "Regenerate rather than edit: the tables carry a digest, checked on the
  way in, so an edit here is refused rather than read as a wrong value"
  (every value artefact's own docstring).
- Repr-is-codegen: every node's `__repr__` is a valid constructor
  expression; the notation is its strict superset with the no-exec
  SYMBOLS table as the boundary; `compile_ast` memoises on `repr(ast)`;
  manifests are one repr-style expression. One textual form for IR,
  everywhere.

## 10. What atlas does not show (the gap map, from the code's side)

1. **IrSelf itself** — no surface renders an arbitrary node as fields +
   children + repr, though the uniform protocol (§5) makes ONE viewer
   sufficient for all of them. Day-1's question #1, still open.
2. **The compiler** — none of the four grammar snapshots of §3, nor the
   binding view, are visible; atlas shows only the parse's runtime.
3. **The flavour's anatomy** — reducer and emitter are dataflow programs
   (per-rule / per-type trees) that could sit beside the rule or node they
   act on; escapes and quantifier maps are data tables; none rendered.
4. **The artefact family** — the species table of §6 with their different
   imports/identities; the two-file molecule; subtree-decode as native
   zoom. Atlas currently has one "export" rung, typed outward, and
   nothing else.
5. **The doc tree** — between IR and emitted text (§7); rails and text
   views jump over it.

Non-finding, corrected: `except TypeError, ValueError:` in binding.py is
valid PEP 758 syntax (Python 3.14) — not a defect.
