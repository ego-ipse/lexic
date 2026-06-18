# Lark as a full-coverage flavour — umbrella scoping design

**Status:** umbrella scoping spec. Defines the *arc*, the *principles*, and the
*phase decomposition* for admitting Lark as a first-class input/output flavour
with **full coverage** of the Lark grammar surface. This document authorizes
**nothing** to be built — each phase below gets its own spec. Its job is to pin
the architecture and dependencies once, so every phase-spec has a stable
contract to reference.

> **V2 substrate note (2026-06-04).** The primitive node model
> (`2026-06-01-ir-primitive-node-model.md`) landed after this umbrella was
> written: `IrType`/`coerce`/`IrCollection`/`_items_attr` are gone, nodes now
> subclass their payload. The **arc, principles, and phase decomposition below
> are unchanged** — they describe Layer-2 growth, which V2 did not alter. Only
> Phase-0's concrete node shapes are re-derived (see
> `2026-06-04-phase-0-v2-realignment-design.md`). Inline `path:line` references
> below are indicative, not pinned.

**Relationship to prior notes:**
- Builds on `2026-05-29-charclass-quantifier-and-lark.md` (working notes). That
  note's §3 sequence (`IrInt` → generalized `IrCond`/`IrCompare` → honest
  `IrQuantifier` → structured `IrCharClass`) **is Phase 0 here** — a hard
  prerequisite, not a parallel effort.
- Inherits the deferred-work ledger and the canonical-nine constraint from the
  `2026-05-14` and `2026-05-17` specs. The canonical-nine **amendment** that the
  working notes flagged (ledger item #8) is on this program's critical path.

**Decision of record (2026-05-29):** honest but ambitious. Pursue **full
coverage of Lark first**, then iterate to deepen fidelity. "Full coverage" means
every construct expressible in a `.lark` grammar can be parsed into the IR and
re-emitted as `.lark` text. Iteration means progressively replacing the
transitional frontier node (below) with structured composites.

---

## 1. What "backend" means (the three pipeline layers)

The pipeline has three layers, and a Lark *input/output* flavour touches them
very differently. Naming them removes the ambiguity in "without changing the
backend." (This is orthogonal to the *IR-internal* level model in §4 — that one
is about how the IR stratifies; this one is about pipeline seams.)

- **Layer 1 — execution backend.** `derive_specs` → `codegen` → `build_lark`
  (`parsing/lark_builder.py`) + the internal Lark parser and transformer. Turns
  `RuleSpec` into Pydantic classes that parse user text. It is **flavour-blind**:
  it begins at `IrAst`/`RuleSpec` and never asks which flavour produced them. A
  new flavour cannot touch it. *(Note: `build_lark` already emits an internal
  Lark grammar; that is unrelated to a Lark **input** flavour — two different
  Lark grammars. Note also that both the meta-parser and `build_lark` already run
  `parser="earley"`, so the pre-spec's LALR-vs-Earley "parser-class commitment"
  worry is largely moot against current code.)*
- **Layer 2 — IR node shapes** (`ir/nodes.py`). The denatured nodes
  (`IrCharClass(value:str)`, `IrQuantifier(min,max)`) and the structural
  skeleton. **This is the layer full coverage grows.**
- **Layer 3 — the flavour-input contract** (`grammars/flavour.py` ABC + the
  generic `MetaGrammarParser`). Today `parse_charclass` returns
  `(pattern:str, negated:bool)` and `parse_quantifier` returns an
  `IrQuantifier`. Full Lark coverage stretches this contract (regex bodies are
  not char classes); the stretch is designed in Phase 1.

**Consequence:** full Lark fidelity is *not* achievable "without changing the
backend" if "backend" means Layer 2 — it provably requires new IR nodes (see
§2). It *is* achievable without touching Layer 1. The execution backend stays
untouched throughout this program.

---

## 2. The core diagnosis — what the IR cannot cover today

The structural IR is exactly 11 node types in a rigid skeleton (`Ast → Rule →
Alternation → Sequence → Item(atom, quantifier)`, atom ∈ {`IrLiteral`,
`IrCharClass`, `IrRuleRef`, `IrGroup`, `IrNot`}). It models **normalized EBNF
core**. Measured against the full Lark surface, the gaps fall into three tiers
distinguished by *how* they fail:

**Tier 0 — cannot be represented at all (no node).**
1. **Arbitrary regex terminals** — the headline gap. The only pattern primitive
   is `IrCharClass` = the interior of *one* bracket (`ir/nodes.py`). It cannot
   hold `.` any-char, in-token alternation `/foo|bar/`, a mixed sequence that
   must stay one token (`/[0-9]+\.[0-9]+/`), quantified sub-groups inside a
   terminal, anchors, lookaround, backreferences, non-greedy, or inline flags.
   *The `regex_portable.py` / `PORTABLE_FEATURES` machinery describes a
   `PatternAtom.regex` contract for a node that **does not exist** in the IrItem
   pipeline — orphaned/aspirational infrastructure. Today the IR cannot hold a
   regex at all; the only regex in the system is synthesized transiently inside
   `lark_builder._regex_terminal` and immediately discarded.*
2. **Template / parameterized rules** (`separated{x, sep}: ...`).
3. **Grammar directives** (`%import`, `%ignore`, `%declare`, `%override`,
   `%extend`).
4. **Tree-shaping modifiers** (`?rule`, `_rule`/`_TERM`, `!rule`, `-> alias`,
   Lark's `[item]` maybe-placeholder semantics).
5. **Priorities** (`TERMINAL.2:`, `rule.5:`).

**Tier 1 — representable semantically, surface round-trip lossy.** Terminal-vs-
rule kind (today collapses to `IrRule`/`IrRuleRef`); `"a".."z"` string-range
surface; `"foo"i` case-insensitive; `~n`/`~n..m` (cross-flavour lossy).

> **Correction (this revision).** The earlier draft listed "`%ignore` vs.
> `@non-semantic` whitespace model mismatch" here as a *lossy translation*. That
> was wrong by our own principle (§4). Non-semantic is **one Lexic-level
> concept** with per-flavour *emissions*: `%ignore` is how Lark emits it,
> `@non-semantic` is a Lexic shim parked in GBNF's comment space (not GBNF
> itself). There is no surface-to-surface translation and no inherent loss — both
> flavour parsers feed the one `IrNonSemantic`.

**Tier 2 — representable, but emit is broken/partial (the denatured tax).**
General bounds `{n,m}` (IR holds it; GBNF `_gbnf_quantifier` *raises* —
`gbnf/flavour.py` — the latent parse-but-can't-emit bug); negation across
flavours (`_gbnf_not` partial, `_abnf_not` raises); ABNF char-class
re-derivation from the blob on every emit.

---

## 3. Keystone principle — one compositional algebra

**A regex and a grammar rule are the same algebra at different levels.**
`/[0-9]+\.[0-9]+/` is structurally `sequence(charclass+, ".", charclass+)` —
identical shape to an `IrRule` body. The terminal/rule distinction Lark draws is
intrinsic structure (a node *kind*, see §4), not a parsing accident. So the
existing IR skeleton already covers the *context-free core* of regex. Regex adds
only a small closed set beyond the grammar IR: any-char, anchors, and the
genuinely non-CFG features (lookaround, backreferences, non-greedy).

This yields a single design, not a fork:

- **One open algebra.** Trivial atoms (`IrLiteral`, `IrCharClass`, `IrAnyChar`,
  `IrAnchor`, `IrRuleRef`) plus irreducible leaves (`IrBackref` references a
  capture — a leaf, still a trivial atom). *Note `\d`/`\w`/`\s` are **not** a
  separate atom — they are `IrCharClass` NamedSet members; `"a".."z"` is a Range
  member. `IrShorthand` is struck.*
- **Complex constructs are composites over that algebra.** `IrLookaround(body:
  IrSequence)`, greed as a quantifier variant, groups, negation — all built from
  trivial nodes. "Fully structured" is "the algebra with more composite types
  defined," **not** a different representation.
- **`IrRawRegex` is the typed frontier, not a rival philosophy.** It holds
  exactly the constructs for which a structured composite has not been written
  *yet*. When every Lark construct has a node, the parser stops emitting it.
  This is honest where `IrCharClass(value:str)` is not: the blob is the
  *permanent* state of something that *should* be structured; `IrRawRegex` is the
  *transitional* state with a known destination. It is the seam that delivers
  "full coverage now" and the lever for "iterate later."

**Cross-flavour emit honesty falls out for free.** Emit is per-flavour open-table
dispatch (policy on tables, intrinsic logic on nodes). The Lark table defines
actions for `IrAnyChar`/`IrAnchor`/`IrLookaround`/`IrRawRegex`; the GBNF/ABNF
tables do not, so they raise `UnsupportedConstructError` exactly as `_abnf_not`
does today (or render a deliberately lossy form where one is defined). Transpile
works for the CFG-portable subset and refuses, loudly, beyond it. No generic code
needs to know — cross-flavour lossiness is *correct* when the target formalism is
weaker.

---

## 4. The IR-internal model — levels of `IrSelf` related by dispatch

Everything in the IR is, in the end, an `IrSelf`. The IR is therefore not "nodes
+ fields + sidecar metadata"; it is **`IrSelf` stratified into levels, where a
higher level *dispatches on* the level below.** This is not a new mechanism — a
**flavour is already an `IrEmitter`**, i.e. a higher-level `IrSelf` (an
`IrDispatch`) that dispatches on the grammar to produce text. Three levels:

### 4.1 Grammar level — the language itself (intrinsics are *types/structure*)

A flavour-neutral distinction that changes the accepted language or its structure
is a **type or structure**, never a property read off a field. (An enum field is
a closed alternation smuggled in as data; the codebase dispatches on type instead
— working notes §2.3.)

- **Productions:** `IrProduction` base → `IrRule` | `IrTerminal`. **`kind` is a
  type distinction, not a property.**
- **Skeleton:** `IrAst`, `IrAlternation`, `IrSequence`, `IrItem`.
- **Quantifier:** `IrQuantifier` with **greed (greedy/lazy/possessive) as a
  variant**, not a field.
- **Composites:** `IrGroup`, `IrNot`.
- **Atoms:** `IrLiteral` (**case-insensitivity dissolves to structure** — a set
  of strings, à la ABNF's existing expansion; the surface `i` is emit-table
  recognition, not a field or node), structured `IrCharClass`
  (Char/Range/NamedSet + negation; absorbs `\d\w\s` and `"a".."z"`), `IrAnyChar`,
  `IrAnchor`, `IrRuleRef`.
- **Frontier:** `IrRawRegex` (transitional only).
- **Deferred-structure (Phase 4):** `IrLookaround`, `IrBackref` (non-CFG).

### 4.2 Lexic level — rules *about* the grammar (`IrDispatch`-derived)

A distinction that does **not** change the accepted language — it changes how the
grammar projects to a model, or how the parser disambiguates — is a **Lexic-level
`IrSelf` that dispatches on the grammar level.** It is its own node, holding a
dispatch edge down onto the grammar; it is *not* a property on a grammar node.

- **`IrNonSemantic(IrDispatch)`** — the worked example. A dispatch over the
  grammar that marks its named targets as structural. `@non-semantic`
  (Lexic-shim emission into GBNF comment space) and Lark `%ignore` (native
  emission) both **parse into the one `IrNonSemantic`**; each flavour's emit
  table renders it back to its own surface (or raises/loses where it cannot).
- **`inline`, `alias`, `priority`** follow the *same shape* — Lexic-level
  `IrDispatch`-derived rules over the grammar, **not** node fields. (`alias` is
  open-valued data carried by such a rule; `priority` likewise.)

This retires the earlier "carrier properties" idea and the retracted "promote
non-semantic to a property on `IrRule`."

### 4.3 Emit level — flavours (`IrEmitter`, already `IrDispatch`)

`GBNF_FLAVOUR`, `ABNF_FLAVOUR`, and the new `LARK_FLAVOUR` are `IrEmitter`s that
dispatch on the grammar and Lexic levels to produce text. Already the shape in
the codebase; the program adds a third table, it does not add a mechanism.

---

## 5. Destination IR inventory (the upper bound)

The complete target vocabulary, so early phases build toward it rather than
toward flavour-specific encodings that get rewritten later.

| Level | Element | Notes |
|---|---|---|
| Grammar | `IrAst, IrAlternation, IrSequence, IrItem` | skeleton (exists) |
| Grammar | `IrProduction → IrRule \| IrTerminal` | kind as **type** |
| Grammar | `IrQuantifier` (+ greed variant) | honest bounds (Phase 0); greed (Phase 4) |
| Grammar | `IrGroup`, `IrNot` | composites (exist) |
| Grammar | `IrLiteral` | case-fold → structure, not a field |
| Grammar | `IrCharClass` (Char/Range/NamedSet + neg) | absorbs `\d\w\s`, `"a".."z"` |
| Grammar | `IrAnyChar`, `IrAnchor`, `IrRuleRef` | atoms |
| Grammar | `IrRawRegex` | **transitional frontier** — empty at destination |
| Grammar | `IrLookaround`, `IrBackref` | non-CFG; Phase 4 |
| Lexic | `IrNonSemantic(IrDispatch)` | worked example |
| Lexic | `inline`, `alias`, `priority` rules | same `IrDispatch` shape |
| Module | `IrImport, IrDeclare, IrOverride, IrExtend, IrTemplate/IrTemplateRef` | `IrAst` children; Lark↔Lark |
| Emit | `LARK_FLAVOUR` (`IrEmitter`) | third action table |

`IrRawRegex` non-emptiness in a parsed Lark grammar *measures* remaining Phase-4
work. `%ignore` is **not** a module node — it is Lark's *emission* of
`IrNonSemantic` (§4.2).

---

## 6. Phase decomposition

Each phase is its own spec. Ordering encodes hard dependencies.

| Phase | Scope | Delivers | Depends on |
|---|---|---|---|
| **0 — Honest-IR foundation** | Working-notes §3 sequence: `IrInt`; generalize `IrCond` + add `IrCompare`; honest `IrQuantifier`; structured `IrCharClass`. **Plus the reference Lexic-level dispatch:** migrate `@non-semantic` from directive-frozenset to **`IrNonSemantic(IrDispatch)`** as the worked example of §4.2. | Fixes Tier 2; fixes latent GBNF `{n,m}` bug; establishes the Lexic-level dispatch pattern. | **Canonical-nine amendment** (ledger #8). |
| **1 — Regex/grammar unification** | `IrProduction → IrRule \| IrTerminal` (kind as type); regex atoms `IrAnyChar`, `IrAnchor`; `IrRawRegex` frontier; case-fold → structure; `LARK_FLAVOUR` (meta-grammar, escapes, `IrEmitter` table) parsing regex bodies into the algebra, parking the tail in the frontier. | **Full *syntactic* coverage of Lark terminals.** The novel architectural piece. | Phase 0. |
| **2 — Lexic-level rules** | `inline`, `alias`, `priority` as `IrDispatch` rules following the `IrNonSemantic` pattern; their per-flavour emission and their mapping into Lexic model generation (`_rule`/`?rule` ↔ non-semantic/inline, `-> alias` ↔ field naming). | Faithful tree-shape and Pydantic-model fidelity. | Phases 0–1. |
| **3 — Module-level constructs** | `%import`, `%declare`, `%override`, `%extend`, templates — `IrAst` children. Lark↔Lark; dropped/translated for GBNF/ABNF. *(`%ignore` is **not** here — it ships with the Lark flavour in Phase 1 as the emission of `IrNonSemantic`.)* | Full *grammar-file* coverage. | Phase 1 (templates may want Phase 2). |
| **4 — Structure the frontier (iterate)** | Replace `IrRawRegex` with `IrLookaround`/`IrBackref` and consume greed-variant quantifiers as cross-flavour or generation value justifies. | Deepening fidelity. Coverage already complete after Phase 3. | Phases 1–3. |

---

## 7. Open sub-decisions (deferred to phase specs)

- **Greed encoding** — `IrQuantifier` *subtypes* vs. a typed variant member.
  (Phase 0 readies the quantifier; Phase 4 consumes.)
- **Templates: monomorphize (lose template structure) vs. dedicated
  `IrTemplate`/`IrTemplateRef` nodes (true round-trip).** Full coverage argues
  for nodes. (Phase 3.)
- **`%ignore` scope** — Lark `%ignore` is global; once it parses into
  `IrNonSemantic`, decide whether global-vs-per-target scope needs carrying.
  (Phase 1/3.)
- **Parser class** — already Earley everywhere; record explicitly that no LALR
  commitment is implied. (Phase 1.)

*(Settled this revision, no longer open: kind → types; greed → variant; case-fold
→ structure; `IrShorthand` struck; non-semantic → `IrDispatch`, not a property.)*

---

## 8. Invariants preserved

From `1_NORTH_STAR.md`, unchanged by this program:

- **Grammar is canonical.** Every class keeps a lossless `to_grammar(flavour)`
  path *for flavours that can express its nodes*; cross-flavour emit raises
  honestly (or renders a declared lossy form) when it cannot.
- **Round-trip fidelity.** `parse(text, grammar).to_text() == text` on every
  valid input, per flavour.
- **Arrows go one way.** No new runtime→codegen edges; the two sanctioned edges
  are untouched. The `ir ← grammars` arrow is preserved (see §9).
- **One way per task.** One parse function, one emit method per flavour, one
  round-trip method. The frontier node does not add an alternate API — it is one
  atom in the single algebra.
- **No regression.** Full suite green after every phase.

---

## 9. Explicitly out of scope for this umbrella

- Any code. This is a map; each phase is separately specced and authorized.
- **`IrTokenConstr` / flavour-defined *structural* self-dispatching nodes**, and
  the **protocol-only generic-seam** commitment they would require (`derive`,
  `codegen`, `build_lark` touching such nodes purely via the `IrSelf`/`IrDispatch`
  protocol so the `ir ← grammars` arrow is not inverted). Powerful, but a large
  reversal of the current "policy on external tables" split. Demo placeholder at
  most this pass; cross-flavour an unsupported flavour-local node **raises or is
  defined lossily**, like any other unsupported node.
- Re-opening deferred ledger items not on the phase critical path.
- The longer-arc "meta-grammar-as-IR / self-describing flavour" vision (working
  notes §5) — further out than Phase 4; aspiration, not roadmap.
