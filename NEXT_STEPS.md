# Next steps — flavour rework (branch `more_nodes`)

State as of 2026-06-11: 693 tests green, pyright/ruff/pylint clean. `GBNF_ACTIONS`
is declarative except `_gbnf_not`. New algebra this session: fold-mode
`IrCallable(fn, out)`, `IrIsA(name, target)`, `IrEscape()` (reads `d.escapes`),
`IrChild(IrStr)` / `IrIndex(IrInt)` value-leaves, `IrMap` as action body
(`GBNF_QUANTIFIERS`). `IrScalar.eval` static return widened `Self` → `IrSelf`.

## Decisions (settled, do not relitigate)

- **No `IrNegCharClass`.** `IrNot` is *generic* negation; it will apply beyond
  charclasses. Negation never lives in a node type.
- Brackets belong to the charclass; `^` belongs to the negation. Therefore
  negation sits **inside** the bracket construct.
- Lark consumers (`derive`, `naming`, `lark_builder`, `aliases`, `generate`,
  `charclass.py`, `model_emitter`) are condemned — adapt them mechanically to
  keep the suite green, design nothing around them.
- Action leaves are value-leaves, not records: the node IS its payload
  (`IrChild` IS the field name, `IrIndex` IS the position, `IrOp` IS the
  operator string).

## 1. IrCharClass restructure (Q2) — next up

Tree shape:

```
[a-z]   →  IrCharClass(IrStr("a-z"))            # brackets: the class's
[^a-z]  →  IrCharClass(IrNot(IrStr("a-z")))     # ^: the negation's
```

- `IrCharClass` changes tier: str-leaf → monadic container (`IrTuple[IrSelf]`
  wrapper, same shape as `MonadicOp`). Interior stays a plain `IrStr` leaf for
  now (structured ranges come in step 3).
- GBNF actions: `IrCharClass → IrConcat("[", IrIndex(0), "]")`,
  `IrNot → IrConcat("^", IrIndex(0))`, interior `IrStr → IrEmit`.
  Kills `_gbnf_not` → zero `IrCallable`s in the GBNF table.
- ABNF binds `IrNot → IrRaise(...)` (pre-kills `_abnf_not`).
- `meta_parser._build_charclass` builds the new nesting.
- Legacy consumers get one flattening helper (canonical `(pattern, negated)`
  view) instead of per-site surgery.

## 2. Quantifier meta-grammar (Q3a)

`parse_quantifier` dies: replace the opaque `QUANTIFIER` regex token with a
canonical meta-grammar production carrying INT tokens; `MetaGrammarParser`
builds `IrQuantifier(lo, hi)` generically. Flavour contributes only grammar
text + a symbol `IrMap` (`GBNF_QUANTIFIERS` exists; ABNF needs its prefix
equivalent).

## 3. parse_charclass shrink (Q3b)

Negation detection becomes grammar structure (`"[" "^"? interior "]"`) feeding
`IrCharClass(IrNot(...))` directly. Residue: ABNF `%xNN-MM` hex→char is
*decoding*, not flavour logic — one shared decoder beside `EscapeCodec`.
`normalize_literal` (ABNF case-folding) folds the same way later. End state: a
flavour is meta-grammar text + action table + escape/symbol data, no methods
(the "completely auto-generated" promise in the flavour docstrings).


# Note from human: I think one good way to solve multiple issues at once is to
abstract both quantifiers and char ranges into a single `IrRange`, that is,
a range from `lo` to `hi` (inclusive). If this is an int, like in a quantifier,
then it's a range from `lo` to `lo`. If it's a char class, then it's a range
from the first char to the last char- or a sequence thereof... which 0-9 is the
range from `0` to `9` as strings.

## 4. ABNF port

After 1–3 land: `_abnf_encode_literal` → same `IrEscape` body as GBNF;
`_abnf_item` → GBNF's item body with cond/quantifier order flipped (prefix);
`_abnf_ast` → identical to GBNF's. Then extend ABNF coverage (fuller quantifier
forms, literal forms) on the structured base.
s
## Housekeeping

- CLAUDE.md and `.wiki/` are stale: `IrMap`/`IrTypeMap`/`mapping.py`,
  `IrCallable` in spine (`base.py`), `operators.py`, fold-mode `IrCallable`,
  `IrIsA`/`IrEscape`/`IrIndex`/`IrChild` reshape, declarative `GBNF_ACTIONS`,
  actions-as-IrTypeMap. Refresh once the restructure settles.
- `generated/` files churn in the working tree; deliberately uncommitted.
- Workflow: src by hand/Fable/sOpus, tests always via Sonnet subagents.
