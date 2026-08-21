# `lexic.grammars` — the flavours

A *flavour* is a grammar notation — GBNF, ABNF, EBNF. The premise here is the
package's whole design: **a flavour is data, not code.** It defines zero
parsing methods and zero emitting methods. It is a bundle of `lexic.ir`
values — a self-grammar, a reducer, an escape codec, and emit actions — that
the engine (`lexic.parsing`) drives from the outside for parsing and that walks
itself for emission. This package reads and writes `lexic.ir` only; it is a
leaf w.r.t. `lexic.parsing` and `lexic.compile`.

Because a flavour is data, the same flavour can be expressed two ways that must
agree: as a flat `grammars/<name>.py` module (the shipped, authored form) or as
a text manifest loaded with `lexic.compile.load_flavour`. The `.ir` /
`.flavour.ir` data files here are the **conformance twins** of the authored
singletons — the same flavour as text, proving the text path.

## 1. The registry (`__init__.py`)

| Callable | Role |
|---|---|
| `get_flavour(name)` | the registered `IrFlavour` singleton by name |
| `flavour_for_extension(path)` | pick a flavour from a file extension (`.gbnf`, `.abnf`, `.ebnf`) |
| `register_flavour(flavour)` | register a new flavour singleton |
| `GBNF_FLAVOUR`, `ABNF_FLAVOUR`, `EBNF_FLAVOUR` | the built-ins, eagerly registered on import |

`lexic.model.to_grammar(flavour)` resolves a singleton through `get_flavour` and
calls `flavour.apply(self.__grammar__)`; `lexic.compile` resolves the flavour
for a compile the same way. These are the only edges into this package.

## 2. Anatomy of a flavour

An `IrFlavour` IS-AN `IrEmitter` (from `lexic.ir`) carrying, as class data:

- **`grammar: IrAst`** — the flavour's **own self-grammar**, authored directly
  as IR (no meta-grammar string). Its structural rules (whitespace, comments,
  delimiters) are flagged `semantic=False` individually.
- **`reducer: Reducer`** — the parse half: `reductions` (an `IrMap` from a
  rule's `IrRuleRef` to an IR body folding its matched children into IR) plus a
  noise map **derived** from the grammar's `semantic=False` flags. `parse_grammar`
  compiles `grammar` and drives the artefact's `reduce` with `reducer` — the same
  engine that later parses generated instances.
- **`escapes: EscapeCodec`** — the escape tables (an instance).
- **`actions: IrTypeMap`** — the emit half: one IR body per IR-AST node type,
  as pure algebra (`IrConcat`, `IrJoin`, `IrField`, `IrChild`, `IrChildren`),
  with `IrLambda` only as the procedural escape hatch. STRUCTURE-level
  actions (item/sequence/alternation/rule/ast) build layout docs
  (`lexic.ir.layout`); `apply(root, width=88)` renders them width-aware —
  long rules wrap at arm/item boundaries (`width=None` = flat) and reparse
  to the identical canonical AST.
- **`core_rules: IrMap`** (optional) — a std-namespace prelude consumed as
  dangling-ref resolution only (ABNF ships the RFC 5234 B.1 core rules; a
  referenced-but-undefined core rule is appended, nothing else ever is).

Each module exposes the class as **private** (`_GbnfFlavour`) and the
constructed singleton as **public** (`GBNF_FLAVOUR`).

## 3. The flavours

```
grammars/
  __init__.py    the registry (§1)
  gbnf.py        GBNF — one flat module: GBNF_GRAMMAR + GBNF_REDUCTIONS +
                 GBNF_REDUCER (parse half, full surface, native — no meta-grammar),
                 GBNF_ESCAPES, GBNF_ACTIONS (emit half), the _GbnfFlavour class +
                 GBNF_FLAVOUR singleton
  abnf.py        ABNF — same shape; full RFC 5234 + 7405 subset (num-seq incl.
                 %d/%b dot-sequences, [...] option, comments/folding, %s/%i and
                 the uppercase markers, prose-refusal, =/); ABNF_CORE_RULES —
                 the B.1 core-rules prelude
  ebnf.py        EBNF — same shape; ISO-family surface (=/; rules, "," concat,
                 {}/[] repetition/option, postfix * + ?, n * x exact repetition,
                 ".." ranges, (* *) comments); no native class/negation syntax —
                 classes expand to quoted alternations, IrNot and open-bounded
                 counted quantifiers refuse declaratively
  json.py        JSON_GRAMMAR — the JSON grammar (RFC 8259) authored directly as
                 IrAst, not derived from either flavour; the flavour-neutral
                 canonical target both front-ends reduce to
  *.ir / *.flavour.ir   data-file conformance twins (loaded via lexic.compile)
```

## 4. The self-hosting fixpoint

The standing proof that a flavour's parse and emit halves agree is
self-hosting: emit a flavour's own self-grammar as text, parse that text with
the flavour itself, reduce, and recover the identical `IrAst`. Because
`IrRule.__eq__` excludes the `semantic` flag, a freshly parsed rule
(`semantic=True`) still equals the authored noise rule (`semantic=False`), and
the fixpoint holds. The manifest twins add a second proof: `load_flavour` of a
flavour's manifest must be conformant with the authored singleton (equal repr
per section, equal `parse_grammar` results across the corpus, equal emitted
text, equal `non_semantic`).

## 5. Adding a flavour

Either write a flat `grammars/<name>.py` (private `_XFlavour` + public
`X_FLAVOUR`, registered via `register_flavour`) or author a text manifest and
load it with `lexic.compile.load_flavour`. Either way you supply only the four
data pieces in §2 — no methods.

**The no-`def` rule.** A flavour module carries **no** `def` / `lambda` /
`IrLambda` in its reduction algebra: reductions are pure IR (branch via an
`IrTypeMap`, flatten channels via inline-group splice). This is what keeps a
flavour purely declarative and manifest-representable (a manifest is a no-`exec`
notation, so an `IrLambda` sentinel is unspellable in one by construction).

## 6. Invariants

- **A flavour is data, zero methods.** Self-grammar + reducer + escapes + emit
  actions; the engine drives parsing, `apply` drives emission.
- **The self-grammar is authored as `IrAst`** — no meta-grammar string, no
  external parser.
- **Noise policy is derived**, not declared — from the grammar's
  `semantic=False` flags — so the reducer and the codegen passes read one
  source of truth.
- **Grammar-neutral target.** `json.py`'s `JSON_GRAMMAR` is the canonical shape
  both front-ends reduce to, proving cross-flavour convergence.
- **Leaf package.** `grammars` imports `lexic.ir` only.

See [`.wiki/lexic/flavour-system.md`](../../../.wiki/lexic/flavour-system.md).
