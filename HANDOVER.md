# Handover — branch `more_nodes`, 2026-06-12

Session ended mid-step-3 (test porting pending). Read `NEXT_STEPS_V2.md` for
the plan, but see **§Direction change** below — it invalidates parts of it.

## Git state

- Committed: steps 1–2 (`ff5c27f more`, `7a2e933 wip` on top of `54cb164`).
- **Uncommitted working tree: all of step 3 src** (list under §Step 3).
- `generated/` churn is expected and deliberate.

## Where things stand

- **Integration + property: 69/69 green.** All seven ground truths compile,
  parse, and round-trip byte-exact through the new structured pipeline
  (`[^\n]`, `[\x00-\x1F]`-style classes included).
- src is ruff + pyright clean.
- **Unit: 634 pass / 39 fail + 1 collection error — ALL test-porting debt,
  no src bugs known.** The failures construct the old str-leaf
  `IrCharClass("a-z")` or import the deleted `lexic.ir.charclass`.

## Completed this session

**Step 1 — IrRange + IrQuantifier retier** (committed): `IrRange[T: (str,int)]`
record (`lo`/`hi` scalar payload, `_child_attrs = ()`); `IrQuantifier(IrRange)`;
`min/max` → `lo/hi` everywhere; open bound is `IrNone` (the `int | None` union
is gone); `IrNoneType.__repr__` → `"IrNone"`; generated-module template imports it.

**Step 2 — argument channel + delegation** (committed): `nc` formalized as THE
argument channel; `IrChild`/`IrIndex`/`IrChildren` de-hybridized (children come
from `n`, never `nc`); new nodes `IrAt(selector, body)` (binder, raw-child
focus shift), `IrArgs()` (args reader), `IrApply(args)` (re-dispatch focus with
args). GBNF `IrNot` action = `IrAt(0, IrTypeMap(IrCharClass → IrApply("^"),
IrSelf → IrRaise))` — zero `IrCallable`s in the GBNF table; `_gbnf_not` gone.

**Step 3 — structured IrCharClass** (UNCOMMITTED):

- `ir/nodes.py`: `IrCharClass(IrSeq[IrRange | IrStr], IrAtom)` — pure
  structure, NO methods. Runs of singles are one bare `IrStr` leaf; explicit
  `x-y` are `IrRange`. Negation stays outside (`IrNot(IrCharClass(...))`).
  Element payloads are **encoded escape units** (`"\x1F"` = one 4-char unit)
  so emission is byte-exact; decoding happens only at enumeration.
- `parsing/meta_parser.py`: the interior splitter lives in
  `_build_charclass` + `_read_unit` — deliberately, as Lark-era scaffolding
  that dies with this file. `parse_charclass` flavour methods survive
  until the metagrammars die.
- `ir/charclass.py` **deleted** → `utils/charclass.py` (`charclass_pattern`
  flat view + relocated `parse_charclass_chars`). Shims live OUTSIDE ir/.
- `grammars/gbnf/flavour.py`: class action = `"[" + IrJoin(IrArgs()) +
  IrJoin(IrChildren()) + "]"`; `IrRange → IrJoin(parts=(IrField lo, hi),
  sep="-")`; `IrStr → IrEmit` (run leaf; wide-MRO key accepted by user).
- `grammars/abnf/flavour.py`: `_abnf_charclass` renders elements
  (`%xNN-MM` per range, `%xNN` per run char, parens when >1 atom);
  `_split_charclass_segments`/`_hex_range_segment`/`_abnf_not` deleted;
  `IrNot → IrRaise`; `normalize_literal` wraps runs in `IrStr`.
- Consumers (`ir/derive.py` `_bracketed`, `codegen/aliases.py` ×4,
  `parsing/lark_builder.py` ×4, `generate.py`) read via `charclass_pattern`.
- `codegen/model_emitter.py` `CANONICAL_IMPORTS`: + `IrRange`, `IrStr`.

## Next task: port the 39 failing unit tests (Sonnet job, per workflow)

Files: `test_nodes.py` (4), `test_derive.py` (13), `test_model_emitter.py`
(14), `test_aliases.py` (5), `test_action.py` (1),
`test_init_new_codegen.py` (1), `test_meta_parser.py` (1), plus
`tests/unit/lexic/ir/test_charclass.py` (imports deleted module).

- Constructions: `IrCharClass("a-z")` → `IrCharClass(IrRange("a","z"))`;
  `IrCharClass("abc")` → `IrCharClass(IrStr("abc"))`; mixed
  `IrCharClass("a-z0-9_")` → `IrCharClass(IrRange("a","z"),
  IrRange("0","9"), IrStr("_"))`.
- `test_charclass.py` moves to `tests/unit/lexic/utils/test_charclass.py`
  (mirror rule), imports from `lexic.utils.charclass`; add
  `charclass_pattern` coverage.
- Flavour `parse_charclass` tests: unchanged API (method survives).
- New coverage to add: `_build_charclass` shapes (ranges, runs, hex units
  `\x00-\x1F`, negation wrap, `[-+]`-style literal dashes), GBNF emission of
  structured classes, ABNF range/run rendering, ABNF `IrNot` raise.
- Port, never delete; user commits, agent doesn't.

## Direction change — READ BEFORE PLANNING FURTHER WORK

User decisions (enforced via three rejected implementations, see memory
`project_ir_purity_lark_temporary.md`):

1. **`ir/` stays pure.** No shims, scanners, helpers, or convenience methods
   in `src/lexic/ir/` — not as functions, not as codec methods, not as node
   methods. Temp shims go in `parsing/`/`utils/`/`codegen/` only.
2. **No new Lark infrastructure, ever.** A mini Lark meta-grammar for
   charclass interiors was rejected. **The metagrammars themselves are
   slated for removal**; parsing will be rebuilt strictly within the IR.
3. Consequence: **NEXT_STEPS_V2.md steps 4–5 are stale** — step 4 (quantifier
   /charclass meta-grammar productions) is MORE Lark and contradicts (2).
   The real step 4 is the IR-native parser design. Do not start it without
   the user; revise the doc with them first.

Other settled-this-session decisions: rendering ownership (an action renders
only its own node's tokens; cross-node marks travel as `nc` arguments; the
receiving action places them — surface position is flavour data, e.g. a
flavour could render negation `[foo]!`); guards are `IrTypeMap`s with
`IrSelf → IrRaise` catch-all, not cond-chains; `lo`/`hi` stay scalar payload
read via `IrField` ("keep as is for now" — the flip to value-leaf children
that would enable `IrJoin(IrChildren(), "-")` was discussed and deferred).

## Loose ends

- User hand-moved `literal_to_regex_pattern` into `parsing/lark_builder.py`
  (out of `ir/regex_portable.py`) — part of the same ir/-purge; check what
  remains of `regex_portable.py`.
- `src/lexic/ir/meta.py` appeared during the session (user WIP, not touched
  or read by the assistant).
- CLAUDE.md and `.wiki/` are badly stale (predate `base.py` spine,
  `operators.py`, `mapping.py`, IrRange, argument channel, structured
  charclass). V2 doc's Housekeeping section lists the refresh items.
- `escapes.py` docstring updated to point at `utils/charclass.py`.
