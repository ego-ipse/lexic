# Handover — IR-native parsing (`parsing_2/`) + `abnf_2.py`

**Date:** 2026-06-17
**Status:** prototype / shape. Recognizer + parser + reduction seam work end-to-end on
unambiguous, quantifier-free grammars. Self-hosting ABNF fixpoint is *not* yet runnable
(blocked on normalize increments — see Next steps).

---

## 1. Goal

Drop Lark. An `IrAst` *is already a grammar*, so it can drive a parser directly instead of
being produced by one. Target end-state:

```
grammar text ──(IR-native Earley parse)──► ParseTree ──(reduction table)──► IrAst
```

The proof is **self-hosting**: `parse(ABNF_GRAMMAR, abnf_source)` reduced through
`ABNF_REDUCTIONS` should reproduce `ABNF_GRAMMAR`. Once that holds, the meta-grammars
(`META_GRAMMAR` strings, `MetaGrammarParser`, `lark_builder`, the transformer) can be
retired. The *same* engine also generalises to runtime input parsing (replacing
`build_lark`), since a user grammar like `JSON_GRAMMAR` drives it the same way.

This is the materialisation of the design discussed before implementation: the Earley
operations are a dispatch table on the symbol after the dot — the same `IrTypeMap`
substrate the emit flavours use, run the other direction.

---

## 2. What was built

### `src/lexic/parsing_2/` — the engine (everything IS-AN `IrSelf`)

| File | Contents | Status |
|---|---|---|
| `item.py` | `EarleyItem(IrNamedTuple)` — dotted-arm state `(rule_name, arm, dot, origin)`. `is_complete`, `next_symbol()` (returns `IrNone` when complete), `advance()`. | done |
| `chart.py` | `Column` / `Chart` — mutable `IrLeaf`s (the one mutability concession). `Chart.links` holds provenance: `(item, end) → (predecessor, predecessor_end, child)`. | done |
| `ops.py` | `Predict` / `Scan` / `Complete` as `IrLeaf` bodies; `EARLEY_OPS: IrTypeMap` keyed on the symbol-after-dot type. `ParseCtx` carries per-dispatch state via `nc`. | done |
| `engine.py` | `EarleyParser(IrDispatch)` — the Scott/Earley loop. `recognize()`, `parse()`, module-level `recognize`/`parse`. | recognize+parse done |
| `forest.py` | `ParseTree(IrNamedTuple)` (field is `kids`, not `children` — see gotchas) + `build_tree()` reconstructing a derivation from `Chart.links`. | done |
| `reduce.py` | `Reducer(IrDispatch)` — bottom-up fold of a `ParseTree` into IR via a `reductions: IrMap[IrRuleRef, body]`. | done |
| `normalize.py` | `split_literals()` (multi-char literal → per-char items) done; `desugar_quantifiers()` / `flatten_groups()` raise — sketched only. | partial |

### `src/lexic/grammars/abnf_2.py` — the text→IR half of an ABNF flavour

- `ABNF_GRAMMAR` — ABNF-of-ABNF (RFC 5234 §4 subset) as a fully explicit `IrAst`, same
  style as `grammars/json.py` (no construction helpers). 23 rules.
- `ABNF_REDUCTIONS: IrMap[IrRuleRef, IrSelf]` — the "meta notation": per-rule parse-tree →
  IR. The mirror of the emit table `abnf.ABNF_ACTIONS` (`IrTypeMap[type, body]`, IR→text),
  pointed the other way (`IrMap[IrRuleRef, body]`, tree→IR).

---

## 3. Verified working (commands below)

- **Recognizer** on a recursive grammar `expr = "(" expr ")" / digit ; digit = [0-9]`:
  accepts `5`, `(7)`, `((3))`; rejects `(8`, ``, `(())`.
- **`split_literals`** turns `"true"` into 4 single-char items; recognizes `true`, rejects `tru`.
- **`parse()`** builds the correct nested `ParseTree` for `((7))`.
- **`Reducer`** round-trip: parse `((7))` → tree → reduce (join) → `"((7))"`.
- **`ABNF_GRAMMAR`** emits as well-formed ABNF through `ABNF_FLAVOUR.apply(...)` (well-formedness check).
- **`ABNF_REDUCTIONS`** leaf reductions on synthetic trees: `rulename → IrRuleRef('ab')`,
  `char_val → IrLiteral('ab')`, `num_val %x41-5A → IrCharClass(IrRange('A','Z'))`,
  `%x41 → IrCharClass(IrStr('A'))`.
- **pyright**: 0 errors on both `parsing_2/` and `abnf_2.py`. **ruff**: clean.

```bash
uv run pyright src/lexic/parsing_2/ src/lexic/grammars/abnf_2.py
uv run ruff check src/lexic/parsing_2/ src/lexic/grammars/abnf_2.py
```

---

## 4. Key design decisions (and why)

- **Earley ops = dispatch on the symbol after the dot.** `EARLEY_OPS` maps
  `IrRuleRef→Predict`, `IrLiteral/IrCharClass→Scan`, **`IrNoneType→Complete`**. Completion
  keys on the absence sentinel `IrNone` (what `next_symbol()` returns when the dot is at the
  end) — the same property that makes `IrNone` fit every dispatch slot.
- **`IrDispatch` is immutable** (a tuple value), so the parser holds no per-parse state.
  All mutable state lives in `Chart`/`Column`; it reaches the ops through a `ParseCtx` on the
  `nc` argument channel.
- **Provenance over SPPF.** For unambiguous grammars each `(item, end)` is reached one way,
  so a single back-link per advanced item suffices; `build_tree` walks them. Full SPPF
  (shared packed forest) binarisation/disambiguation is the ambiguous-grammar generalisation,
  not built.
- **Reduction is the symmetric twin of emission.** Emit = `IrTypeMap[type, body]` (IR→text);
  reduce = `IrMap[IrRuleRef, body]` (tree→IR). Both ride the same action algebra and dispatch
  substrate. `abnf_2.ABNF_REDUCTIONS` is exactly the inverse of `abnf.ABNF_ACTIONS`.

---

## 5. Gotchas (substrate traps already navigated — keep in mind)

1. **Type-aware equality.** `IrScalar` makes `IrStr("x") != IrRuleRef("x")` (distinct leaf
   kinds never compare equal). The engine standardises on **`IrRuleRef` for all rule
   identity** so `Complete`'s match and `rules` lookups compare like-for-like. Comparing a
   rule name as a bare `IrStr` will silently never match.
2. **`IrMap[K, V].__getitem__` returns `IrSelf`, not `V`** for an `IrSelf`/`type` key. Use
   `.resolve(key) → V` when you need the typed value (e.g. to iterate an `IrAlternation`).
3. **`ParseTree` field is `kids`, not `children`.** A field named `children` shadows the
   `IrNamedTuple.children()` protocol method (pyright `reportIncompatibleMethodOverride`,
   and it breaks walking). `_child_attrs = ("kids",)` still routes the walk correctly.
4. **`IrTuple` is invariant** (`TypeVarTuple`). A heterogeneous-value `IrMap` (bodies of
   different types) won't unify when constructed from bare `IrTuple(...)` rows — `IrMap`
   solves one `V` jointly. Fix: pin the element type **once** on a container
   (`_REDUCTIONS: tuple[IrTuple[IrRuleRef, IrSelf], ...] = (...)`), then `IrMap(*_REDUCTIONS)`.
   See the comment in `abnf_2.py`. (Homogeneous maps like GBNF's don't need this.)
5. **The action algebra is an *emission* DSL** — its nodes produce strings (`IrStr`). It has
   no node that *constructs* a typed structural IR node (`IrSequence`/`IrAlternation`/`IrItem`
   /`IrRule`/`IrAst`) or *filters* children by type. So in `abnf_2`:
   - the 10 character/terminal rules reduce with one shared declarative `_YIELD`
     (`IrJoin` over `IrArgs`), **no `IrCallable`**;
   - the 13 structural/constructing rules use `IrCallable` (its documented purpose).
   Making the structural ones declarative would mean adding a construction-algebra family
   (`IrFilter` / `IrCollect` / `IrMake`). Deliberately *not* invented here — open question.

---

## 6. Known gaps (documented at each site, never silently passed)

- `engine.parse()` works; the full `parse → reduce → IrAst` pipeline for ABNF does **not**
  run yet because:
- `normalize.desugar_quantifiers()` and `flatten_groups()` **raise** `NotImplementedError`.
  ABNF/JSON grammars use `*`, `1*`, `[...]`, and `(...)` groups; classic Earley needs them
  desugared to synthetic rules first.
- **Nullable-rule completion** (Aycock-Horspool held-completions) is not implemented;
  `Complete` notes it. Quantifier desugaring *introduces* nullable rules (`*x` → nullable),
  so this is coupled to the previous item.
- **Synthetic-rule-aware reduction.** Desugaring wraps repetitions/groups in synthetic
  rules, so the parse tree will contain synthetic nodes. The `abnf_2` structural reductions
  currently describe the *conceptual* (pre-desugar) tree; they'll need a flattening step that
  collapses synthetic nodes before/within reduction.

---

## 7. Next steps (ordered, to reach the self-hosting fixpoint)

1. **`desugar_quantifiers`** in `normalize.py`: `*x → X' = "" / x X'`, `1*x → X' = x / x X'`,
   `[x] → X' = "" / x`, `{m,n}` unrolled. Emits synthetic rules with stable names.
2. **`flatten_groups`**: hoist inline `IrAlternation` atoms to synthetic rules so every
   post-dot atom is a ruleref or terminal.
3. **Nullable completer**: add held-completions to `Complete` so empty productions complete
   within their own column.
4. **Synthetic-node flattening** in reduction (or record original structure during desugar so
   `build_tree`/`Reducer` can re-expose the conceptual children).
5. **Fixpoint test**: `parse(ABNF_GRAMMAR, <abnf source of ABNF>)` reduced via
   `ABNF_REDUCTIONS` `==` `ABNF_GRAMMAR`. Then the same against `JSON_GRAMMAR`.
6. **Tests.** None written yet (these are sandbox/shape files). Per workflow, hand test
   authoring to a Sonnet subagent against this doc + the module docstrings once the shape is
   accepted. Mirror structure: `tests/unit/lexic/parsing_2/test_*.py`.
7. Eventually: generalise the engine to replace `build_lark` for runtime input parsing, and
   wire `parse → reduce` into a flavour so `compile_*` can drop Lark.

---

## 8. Open design questions

- **Construction algebra?** Should the action algebra gain `IrFilter`/`IrCollect`/`IrMake`
  so reductions are fully declarative (no `IrCallable`)? This aligns with the open-classes
  direction but is a real addition. Current call: keep `IrCallable` for genuine construction.
- **PEG vs CFG semantics.** Earley is a CFG parser (handles ambiguity); the current
  recognizer assumes unambiguous grammars for single-derivation extraction. Decide whether to
  build full SPPF or constrain to unambiguous grammars.
- **Where the reduction table lives.** `ABNF_REDUCTIONS` sits in `abnf_2.py` beside the
  grammar. Long-term it likely becomes a second table on the flavour, symmetric to `actions`
  (emit) — i.e. a flavour carries both `actions` (IR→text) and `reductions` (text→IR).

---

## Quick reference — imports

```python
from lexic.parsing_2 import recognize, parse, EarleyParser, ParseTree, Reducer
from lexic.parsing_2.normalize import split_literals
from lexic.grammars.abnf_2 import ABNF_GRAMMAR, ABNF_REDUCTIONS
from lexic.grammars.json import JSON_GRAMMAR
```
