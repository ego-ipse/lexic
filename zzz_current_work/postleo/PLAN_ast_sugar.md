# Plan: IR authoring sugar — constructor coercion to canonical shape

Date: 2026-07-02. Produced by plan-ast agent; unreviewed by user.

## TL;DR

**Recommendation: option (a), constructor coercion in `ir/nodes.py`.** `IrRule("CR", IrCharClass(IrChr("\r")))` becomes legal and constructs *exactly* the canonical `IrRule("CR", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("\r"))))))` object, so the self-hosting fixpoint (`test_self_hosting_fixpoint`) keeps comparing equal. Feasibility is **spike-verified end to end** against the live repo: runtime coercion, keyword calls, narrow accessor types, and pyright all pass. Every consumer (normalize, tables, reduce, emit, derive) only ever sees canonical instances, so nothing outside `nodes.py` + the two authoring files needs to change — plus a one-line kwarg absorption in `ir/meta.py`.

Correction to the task framing: `nodes.py` today has **no `IrGroup`** (groups are `IrAlternation`-as-atom; `IrAlternation` IS-A `IrAtom`), and records are `IrNamedTuple` named tuples, not frozen dataclasses. CLAUDE.md §IR types is stale on both points.

## 1. Where the canonical shape is assumed (the map)

All read-side — they consume already-constructed nodes, so construction-time coercion cannot break them:

| Site | What it assumes | Impact |
|---|---|---|
| `ir/nodes.py:199` `IrRule.body: IrAlternation` | body always `IrAlternation` | preserved — coercion guarantees it |
| `parsing_2/normalize.py` (`HoistItem`, `DesugarItem`, `Expand`) | walks `ast → body arms → items`; builds `IrAlternation(IrSequence(...))` internally | builders pass canonical args → coercion no-op |
| `parsing_2/tables.py` `_compile_rule`/`_symbol_of` | arms of `IrItem`s; raises `UnsupportedConstructError` on unnormalised atoms | unchanged; downstream validation intact |
| `parsing_2/reduce.py` + `abnf_2.py` `ABNF_REDUCTIONS` | reducer builds via `IrBuild(IrAlternation)`/`IrBuild(IrSequence)`/`IrBuild(IrItem,…)` splatting `nc` | `nc` elements already canonical → no-op. **Fixpoint holds: sugar and reducer converge on identical canonical objects** |
| Emit tables (`abnf.py` `ABNF_ACTIONS`, `gbnf.py`) | type-dispatched over instances; `IrIsA("atom", IrAlternation)` parenthesises groups | unchanged |
| `ir/derive.py`, `ir/spec.py`, `generate.py` | read canonical `IrAst`/`RuleSpec.items` | unchanged |
| `IrTuple.eval`/`rebuild` (`ir/base.py:603–625`) | rebuild via `type(self)(*children)`; children may be **non-item values** mid-transform (e.g. emitter mapping items to `IrStr`) | constraint: coercion must **pass unknown types through unchanged**, wrapping only `IrAtom` — see §3 |
| repr-is-codegen | repr is a constructor expression yielding an equal node | holds: repr prints canonical; coercion is idempotent. Authored sugar isn't what repr prints — invariant is validity + equality, not source identity |
| Equality/hash (`IrScalar.__eq__`, tuple equality, `IrBounds`) | structural | untouched — coercion runs before tuple construction |

## 2. Options evaluated

**(a) Constructor coercion — recommended.** Behavior on the node type (matches the standing "behavior belongs on the type" rule; it's the constructor's accepted-input contract, not a shim). Canonicalizes at construction → fixpoint, repr, and all consumers automatically safe. One construction path.

**(b) Authoring-helper layer outside `ir/`.** Also yields canonical objects, but introduces a second construction vocabulary ("one way per task" violation) and the authoring files would read in a different language than every repr, test, and reduction table. Buys nothing (a) doesn't. Rejected.

**(c) Relax the canonical shape.** Every consumer grows acceptance branches; worse, `parse(emit(G))` reduces to canonical while an authored non-canonical `G` stays sugared — **fixpoint equality breaks by construction**. Contradicts "grammar is canonical". Rejected.

## 3. Coercion cascade (exact semantics)

Each constructor lifts its arguments one level; the cascade composes:

- **`IrSequence(*items)`** accepts `IrItem | IrAtom`. `IrAtom` wraps to `IrItem(atom)` (includes `IrAlternation` = unquantified inline group). `IrItem` passes. **Unknown types pass through unchanged** (preserves today's permissiveness for `RunTerm` items and `IrTuple.eval` rebuilds; wrap-or-raise would break transformer flows).
- **`IrAlternation(*arms)`** accepts `IrSequence | IrItem | IrAtom`. Non-`IrSequence` known types wrap via `IrSequence(arm)` (its coercion handles atom→item). `IrAlternation`/`IrSequence` are sibling `IrSeq`s, so a nested alternation arm coerces to a single-item group arm — semantically identical language. Unknowns pass.
- **`IrRule(name, body)`** accepts `IrAlternation | IrSequence | IrItem | IrAtom`. `IrAlternation` check runs **first** (it IS-A `IrAtom`): alternation body taken as-is, everything else wraps via `IrAlternation(body)`. Unknowns pass.
- **`IrItem`, `IrAst`, `IrCharClass`** — no change (decision points D2–D4).

Idempotent by construction: canonical input hits the pass-through branch everywhere, so sugar == reducer-built == canonical-authored (spike-verified: headline CR example, multi-arm wsp, quantified decits, group-in-sequence, keyword calls, idempotence).

## 4. Mechanism (spike-verified — this was the hard part)

1. **`IrSequence`/`IrAlternation`** (tuple tier, no `dataclass_transform`): plain widened `__new__` override — statically and runtime clean. No tricks.
2. **`IrRule`** (an `IrNamedTuple` record): pyright validates construction against the **synthesized `dataclass_transform` `__init__`**, so a widened `__new__` alone fails statically. A dummy explicit `__init__` passes pyright but trips pylint W0613 (unused args); suppressions forbidden.
3. **Clean mechanism:** declare `class IrRule(IrNamedTuple[IrStr, IrAlternation], init=False):` — the spec'd dataclass parameter as class keyword — and have **`IrMeta.__new__` pop `"init"` from `**kw`** before forwarding (one line at `ir/meta.py:35`; static-only class kwargs have precedent — the `@final` note on `IrNoneType`). Pyright then validates against the declared `__new__`: positional calls, keyword calls (`IrRule(name=…, body=…)` — 2 live src sites at `parsing/meta_parser.py:201`, `ir/derive.py:180` keep working), and the narrow `rule.body: IrAlternation` accessor all pass, 0 errors, no pylint issue. Important: the kwarg must be absorbed in the **metaclass**, not `__init_subclass__` — spiking the latter changed pyright's interpretation and broke constructor checking.

One wart: `super().__new__(cls, name, body)` from `IrRule.__new__` hits pyright's unsolvable ParamSpec on `IrNamedTuple.__new__[**P]`; needs a single `cast` at that call (established idiom; no `# type: ignore`).

Costs: one `isinstance` per element per construction on hot paths (`FusedReduce`'s `IrBuild`, normalize expansion, `IrTuple.eval` rebuilds) — negligible next to eval dispatch, but real. Silent wrapping can mask a malformed `nc` (stray atom where an item was intended becomes legal structure); `tables.py` validation still catches genuinely un-normalisable shapes.

## 5. What it buys

`json.py`: 38 `IrAlternation` → ~5 remain (true multi-arm), 48 `IrSequence` → ~15, 83 `IrItem` → 14 (only quantified items keep it). `abnf_2.py` similar. Roughly **250 wrapper constructor calls deleted**; both grammar blocks shrink to ~half their lines. Target form:

```python
IrRule("CR", IrCharClass(IrChr("\r")))
IrRule("wsp", IrAlternation(IrRuleRef("SP"), IrRuleRef("HTAB")))
IrRule("rule", IrSequence(
    IrRuleRef("rulename"),
    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
    IrLiteral("="),
    ...
))
```

## 6. Step-by-step plan

1. **`src/lexic/ir/meta.py`** — `IrMeta.__new__` pops `"init"` from `**kw` (docstring: static-only `dataclass_transform` parameter, mirroring the `@final` precedent). Test mirror: `tests/unit/lexic/ir/test_meta.py` — class creation with `init=False` succeeds; kwarg doesn't leak to `__init_subclass__`.
2. **`src/lexic/ir/nodes.py`** — widened `__new__` on `IrSequence` and `IrAlternation`; `init=False` + widened `__new__` (with the one `cast`) on `IrRule`. Concise Sphinx docstrings stating the coercion contract. Test mirror: `tests/unit/lexic/ir/test_nodes.py` — **add, never delete**: four `IrRule` body coercions, sequence element coercion, alternation arm coercion (incl. nested-alternation→group arm), idempotence on canonical input, equality with hand-built canonical, repr prints canonical, keyword construction, unknown-type pass-through.
3. **Migrate `src/lexic/grammars/json.py` and `abnf_2.py`** to sugared form. Purely mechanical; `test_json.py`/`test_abnf_2.py` stay untouched and **are** the proof — especially `test_self_hosting_fixpoint`.
4. **Gates:** `tools/auto_fix.sh`, then `uv run pytest tests/ -q` (baseline 1188 green), `uv run ruff check src/ tests/`, `uv run pyright src/`, `uv run pylint` on the three touched src files.
5. **Wiki:** update `.wiki/lexic/ir-shapes.md` (coercion contract + `init=False` mechanism) and `log.md`. Flag: CLAUDE.md §IR types is stale independent of this change (`IrGroup` gone, `IrComposite`→`IrNamedTuple`) — worth fixing in the same pass.

Workflow note: src first; the test additions and mechanical grammar-file migration are Sonnet-subagent candidates — ask per task, don't dispatch unilaterally.

## 7. Flagged decision points

- **D1 — pass-through vs. raise for unknown element types.** Recommended: pass through (matches today; required by `IrTuple.eval` rebuild flows and `RunTerm`). Strict raising needs a full transformer audit.
- **D2 — extend coercion to `IrItem.atom`** (`IrSequence` → `IrAlternation(seq)` for quantified groups, e.g. json.py object/array bodies). Cheap under the `init=False` mechanism (its 41 keyword call sites keep working). Lean **yes** for cascade consistency, but it's the most heavily-constructed record; fine to defer.
- **D3 — plain `str` → leaf coercion** (`IrSequence("=")`): **no** — ambiguous between `IrLiteral` and `IrRuleRef`; explicit leaf kinds are load-bearing.
- **D4 — `IrChr`/`IrAst` sugar:** **no**. `IrChr` isn't an atom, and single-char-as-`IrCharClass(IrChr(…))` vs `IrLiteral` is a *semantic* canonical-form choice (abnf_2 deliberately uses char classes where ABNF `char-val` can't express the code point) — sugar must not decide it.

## Sequencing vs the cutover plan (added by team lead)

`PLAN_cutover_parsing.md` Phase 2c merges `abnf_2.py` into `abnf.py` and Phase 1 renames `parsing_2` → `parsing`. Step 3's migration targets whichever file holds `ABNF_GRAMMAR` at execution time; keyword-call site `parsing/meta_parser.py:201` becomes `parsing_legacy/meta_parser.py` after the rename. Run this plan either fully before or fully after the cutover, not interleaved.
