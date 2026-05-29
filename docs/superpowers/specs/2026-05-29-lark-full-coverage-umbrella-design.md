# Lark as a full-coverage flavour — umbrella scoping design

**Status:** umbrella scoping spec. Defines the *arc*, the *principles*, and the
*phase decomposition* for admitting Lark as a first-class input/output flavour
with **full coverage** of the Lark grammar surface. This document authorizes
**nothing** to be built — each phase below gets its own spec. Its job is to pin
the architecture and dependencies once, so every phase-spec has a stable
contract to reference.

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

## 1. What "backend" means (the three layers)

The pipeline has three layers, and a Lark *input/output* flavour touches them
very differently. Naming them removes the ambiguity in "without changing the
backend."

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
   is `IrCharClass` = the interior of *one* bracket (`nodes.py:505`). It cannot
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
   `%extend`). `%ignore` is Lark's primary whitespace mechanism; Lexic models
   non-semantic content by a *different* mechanism (`@non-semantic` + `min=0`).
4. **Tree-shaping modifiers** (`?rule`, `_rule`/`_TERM`, `!rule`, `-> alias`,
   Lark's `[item]` maybe-placeholder semantics).
5. **Priorities** (`TERMINAL.2:`, `rule.5:`).

**Tier 1 — representable semantically, surface round-trip lossy.** Terminal-vs-
rule kind (collapses to `IrRule`/`IrRuleRef`); `"a".."z"` string-range surface;
`"foo"i` case-insensitive; `~n`/`~n..m` (cross-flavour lossy); `%ignore`-vs-
`@non-semantic` whitespace model mismatch.

**Tier 2 — representable, but emit is broken/partial (the denatured tax).**
General bounds `{n,m}` (IR holds it; GBNF `_gbnf_quantifier` *raises* —
`gbnf/flavour.py:117` — the latent parse-but-can't-emit bug); negation across
flavours (`_gbnf_not` partial, `_abnf_not` raises); ABNF char-class
re-derivation from the blob on every emit.

---

## 3. The keystone principle — one compositional algebra

**A regex and a grammar rule are the same algebra at different levels.**
`/[0-9]+\.[0-9]+/` is structurally `sequence(charclass+, ".", charclass+)` —
identical shape to an `IrRule` body. The terminal/rule distinction Lark draws is
a **kind marker**, not a structural difference. So the existing IR skeleton
already covers the *context-free core* of regex. Regex adds only a small closed
set beyond the grammar IR: any-char, shorthands, anchors, and the genuinely
non-CFG features (lookaround, backreferences, non-greedy).

This yields a single design, not a fork:

- **One open algebra.** Trivial atoms (`IrLiteral`, `IrCharClass`, `IrAnyChar`,
  `IrShorthand`, `IrAnchor`, `IrRuleRef`) plus irreducible leaves (`IrBackref`
  references a capture — a leaf, still a trivial atom).
- **Complex constructs are composites over that algebra.**
  `IrLookahead(body: IrSequence)`, greed (lazy/possessive) as *data on*
  `IrQuantifier`, groups, negation — all built from trivial nodes. "Fully
  structured" is "the algebra with more composite types defined," **not** a
  different representation.
- **`IrRawRegex` is the typed frontier, not a rival philosophy.** It holds
  exactly the constructs for which a structured composite has not been written
  *yet*. When every Lark construct has a node, the parser stops emitting it.
  This is honest where `IrCharClass(value:str)` is not: the blob is the
  *permanent* state of something that *should* be structured; `IrRawRegex` is the
  *transitional* state with a known destination. It is the seam that delivers
  "full coverage now" and the lever for "iterate later."

**Cross-flavour emit honesty falls out for free.** Emit is per-flavour open-table
dispatch (the open-classes principle: policy on tables, intrinsic logic on
nodes). The Lark table defines actions for `IrAnyChar`/`IrAnchor`/`IrLookahead`/
`IrRawRegex`; the GBNF/ABNF tables do not, so they raise
`UnsupportedConstructError` exactly as `_abnf_not` does today. Transpile works
for the CFG-portable subset and refuses, loudly, beyond it. No generic code needs
to know — cross-flavour lossiness is *correct* when the target formalism is
weaker.

---

## 4. Phase decomposition

Each phase is its own spec. Ordering encodes hard dependencies.

| Phase | Scope | Delivers | Depends on |
|---|---|---|---|
| **0 — Honest-IR foundation** | The working-notes §3 sequence: `IrInt`; generalize `IrCond` + add `IrCompare`; honest `IrQuantifier` (bounds, greed-ready); structured `IrCharClass` (composite of `Char`/`Range`/`NamedSet`). | Fixes Tier 2; unifies the three flavours' shared shapes; fixes the latent GBNF `{n,m}` bug. New atoms in later phases inherit a clean substrate, not the denatured tax. | **Canonical-nine amendment** (ledger #8). |
| **1 — Regex/grammar unification** | Terminal/rule **kind**; trivial regex atoms (`IrAnyChar`, `IrShorthand`, `IrAnchor`); the `IrRawRegex` frontier node; a Lark flavour that parses regex bodies into the algebra and parks the undecomposed tail in the frontier; Lark `actions` table + meta-grammar + escapes. | **Full *syntactic* coverage of Lark terminals** — common cases structured, frontier catches the rest. The novel architectural piece. | Phase 0. |
| **2 — Carrier metadata** | Priorities; tree-shaping (`?`, `_`, `!`, `-> alias`, `[maybe]`); case-insensitive flag — additive node fields **plus** their mapping into Lexic model generation (`_rule` ↔ non-semantic, `-> alias` ↔ field naming, `?rule` ↔ inlining). | Faithful tree-shape and Pydantic-model fidelity. | Phase 1. |
| **3 — Module-level constructs** | `%import`, `%ignore`, `%declare`, `%override`, `%extend`, templates — nodes hanging off `IrAst`. Lark↔Lark; dropped/translated for GBNF/ABNF. | Full *grammar-file* coverage. | Phase 1 (templates may want Phase 2). |
| **4 — Structure the frontier (iterate)** | Replace `IrRawRegex` occurrences with `IrLookahead`/`IrLookbehind`/`IrBackref`/greed-on-quantifier as cross-flavour or generation value justifies. | Deepening fidelity. Coverage is already complete after Phase 3. | Phases 1–3. |

---

## 5. Open sub-decisions (deferred to phase specs, recorded here)

- **Terminal/rule: `IrTerminal` type vs. `kind` marker on a shared node.**
  (Phase 1.) Leaning toward a kind marker to keep one rule-shaped node; revisit
  if terminal-only fields (priority, regex-only atoms) make a distinct type
  cleaner.
- **Greed representation** — lazy/possessive as an enum field on `IrQuantifier`
  vs. wrapper nodes. (Phase 0 readies the quantifier; Phase 4 may consume it.)
- **`%ignore` ↔ `@non-semantic` mapping** — structural translation in both
  directions, lossy. (Phase 3.)
- **Templates: monomorphize (lose template structure) vs. dedicated
  `IrTemplate`/`IrTemplateRef` nodes (true round-trip).** Full coverage argues
  for nodes. (Phase 3.)
- **`IrShorthand` vs. `IrCharClass`** — whether `\d`/`\w`/`\s` are their own atom
  or a named char-class form. (Phase 1, informed by Phase 0's structured
  charclass.)
- **Parser class** — already Earley everywhere; record explicitly that no LALR
  commitment is implied. (Phase 1.)

---

## 6. Invariants preserved

From `1_NORTH_STAR.md`, unchanged by this program:

- **Grammar is canonical.** Every class keeps a lossless `to_grammar(flavour)`
  path *for flavours that can express its nodes*; cross-flavour emit raises
  honestly when it cannot.
- **Round-trip fidelity.** `parse(text, grammar).to_text() == text` on every
  valid input, per flavour.
- **Arrows go one way.** No new runtime→codegen edges. The two sanctioned edges
  are untouched.
- **One way per task.** One parse function, one emit method per flavour, one
  round-trip method. The frontier node does not add an alternate API — it is one
  atom in the single algebra.
- **No regression.** Full suite green after every phase.

---

## 7. Explicitly out of scope for this umbrella

- Any code. This is a map; each phase is separately specced and separately
  authorized.
- Re-opening deferred ledger items not on the phase critical path.
- The longer-arc "meta-grammar-as-IR / self-describing flavour" vision (working
  notes §5) — further out than Phase 4; aspiration, not roadmap.
