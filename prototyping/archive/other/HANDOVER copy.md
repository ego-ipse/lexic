# Handover — codepoint char-classes + escaping-as-algebra (2026-06-15)

**STATUS: NOTHING IMPLEMENTED.** Tree clean at `d664b9e`. Design settled through
dialogue this session (no code kept — every attempt was `git restore`d). This
doc is the contract. Branch `more_nodes`.

The previous handover (`HANDOVER_CODEPOINT_V2.md`) and a verbose spec doc were
**rejected and deleted** — they fused escaping with range and contradicted
existing test assertions. Do not resurrect them.

---

## THE ONE PRINCIPLE

**Escaping and range are two separate operations that may or may not intersect.**
They meet only at range endpoints. Do not fuse them.

- **Range** = structural: `(lo, hi)` of neutral code points. Escaping-agnostic.
- **Escaping** = a per-flavour **algebra** body `code point → IrStr` that owns the
  char-vs-escape decision. Applies wherever a char is emitted — char-class
  members, range endpoints, **and literals**.

---

## DECIDED (non-negotiable — user stated these explicitly)

1. **Escaping is IR-node algebra.** "B. Non negotiable."
2. **`IrChr` is an `IrInt` subtype** (value-carrying — the node IS the code point).
   - `IrChr.__str__` → `IrStr(chr(self))` (the glyph).
   - `IrChr.eval` → `str(self)` (so it composes in a join — produces a string).
   - Lives in `base.py` beside `IrInt` (so `IrRange` in `nodes.py` coerces to it
     with no import cycle).
3. **NO `IrCallable`** anywhere in this work.
4. **`EscapeCodec` is deleted.** All escaping goes through the algebra. Literal
   escaping included — `IrEscape` is **reimplemented** to dispatch each char of
   the literal through the flavour's `IrChr` action (no codec).
5. **`IrQuantifier` remains an `IrRange` subclass** — `__new__` bypasses the
   `IrChr` coercion (`return IrNamedTuple.__new__(cls, lo, hi)`), keeps plain int
   counts, `_child_attrs = ()`, defaults `(1, 1)`.
6. **Rename `IR_MAP_DEFAULT` → `IR_DEFAULT`** (value + repr in `ir/mapping.py`;
   consumers `meta.py` docstring, `abnf/flavour.py`, `ir/__init__.py`,
   `tests/unit/lexic/ir/test_mapping.py`).
7. **No verbose spec docs.** Build it.

## PROPOSED (agreed in dialogue, not individually re-confirmed — treat as the plan)

- **`IrRadix(base, width)`** in `action.py` — n-reading digits render. Record,
  scalar payload `base`/`width` (`_child_attrs=()`); `eval` reads `int(n)` →
  `IrStr` of **uppercase**, **zero-padded-to-`width`** base-`base` digits
  (arithmetic from `ord("0")`/`ord("A")`, no table, no `match`). Serves `%xNN` /
  `\xNN` (16,2), `\uNNNN` (16,4). Uppercase + zero-pad chosen to satisfy existing
  `%x41-5A` / `\x7F` assertions.
- **NO `IrSwitchCase`.** (Was proposed; dropped 2026-06-15.) The GBNF escape
  cascade is built from existing nodes: `IrMap[IrChr, …]` for the equality
  specials + `IR_MAP_DEFAULT → IrCond` for the control-range/glyph fallback —
  the exact shape `ABNF_PREFIX_QUANTIFIER` already uses. A dedicated guarded
  switch would be a third way to do what `IrMap`+`IrCond` already do.

## ALGEBRA ALREADY LANDED (this doc predated it)

The action algebra is richer than the body of this handover assumes. Already in
`ir/action.py` / `ir/mapping.py` / `ir/operators.py`: `IrMap` / `IrTypeMap`
(with `IR_MAP_DEFAULT`), `IrCond`, `IrAt`, `IrApply`, `IrArgs`, `IrIsA`,
`IrCompare`, `IrOp`, `IrCallable`. Only `IrChr` (`ir/base.py`) and `IrRadix`
(`action.py`) are genuinely new nodes; plus the `IR_MAP_DEFAULT → IR_DEFAULT`
rename.

---

## STORAGE RESHAPE

- `IrRange(IrNamedTuple[IrChr, "IrChr | IrNoneType"])` — drop `IrLeaf`, the
  `_child_attrs=()` override, the `[T:(str,int)]` generic. `lo`/`hi` become
  **dispatchable `IrChr` children**. Coercing `__new__`: `"a"`→`IrChr(97)`,
  `97`→`IrChr(97)`, an `IrChr`/`IrInt` kept. Inline, no helper.
- `IrCharClass = IrSeq[IrChr | IrRange]` — **runs dropped**; each single member is
  one `IrChr`. Escaping applies per code point uniformly.
- `IrQuantifier(IrRange)` — see DECIDED #5.

---

## ESCAPING ALGEBRA (emit)

One per-flavour char-escape body, dispatched on `IrChr`, reused by char-class
members (direct `IrChr` dispatch) and literals (via the reimplemented `IrEscape`,
which dispatches each char as `IrChr(ord(c))` through `d`). Union of specials —
over-escaping across contexts is **harmless** (e.g. `\]` in a literal decodes
back to `]`).

### GBNF — glyph, with escapes (`IrChr` action = `IrMap[IrChr, …]`)
The action is an `IrMap` keyed on `IrChr`; equality specials are exact keys,
everything else falls to `IR_MAP_DEFAULT → IrCond`. Mirrors
`ABNF_PREFIX_QUANTIFIER`.
- Equality specials (exact `IrChr` keys): `\n`→`\n`, `\t`→`\t`, `\r`→`\r`,
  `"`→`\"`, `\`→`\\`, `]`→`\]`. A dispatched `IrChr(10)` resolves to the
  `IrChr('\n')` key by value (type-aware eq; same `IrChr` type, same int).
- `IR_DEFAULT` → `IrCond`: `cp < 0x20` **or** `cp == 0x7F` → `<hex>`, else glyph.
  - `<hex>` = `IrConcat(IrLiteral("\\x"), IrRadix(16, 2))`
  - glyph = `IrEmit()` (via `str(n)` → the `IrChr.__str__` glyph)
  - control test = `IrCompare(IrThis(), IrOp("<"), IrChr(0x20))` (or `==` for `0x7F`)

The control tests work because `IrChr` **is** an `int`, so `operator.lt`/`eq`
compare numerically even though `IrChr.eval` is `str`.

- GBNF `IrRange` action: `IrJoin(IrChildren(), separator=IrLiteral("-"))` — each
  endpoint dispatched through the same `IrChr` action → `0-9`.
- GBNF literal: `IrConcat(IrLiteral('"'), IrEscape(), IrLiteral('"'))`.

### ABNF — always hex
- `IrChr` action: `IrConcat(IrLiteral("%x"), IrRadix(16, 2))`.
- `IrRange` action: `IrConcat(IrLiteral("%x"), IrAt(0, IrRadix(16,2)),
  IrLiteral("-"), IrAt(1, IrRadix(16,2)))` → `%x41-5A`.
- `IrCharClass` action: one element bare; many → `"(" + join(" / ") + ")"`.
  `_abnf_charclass` `IrCallable` removed (declarative).
- ABNF literal: **verbatim** — `IrConcat(IrLiteral('"'), IrEmit(), IrLiteral('"'))`
  (ABNF escape is identity; do NOT route through `IrEscape`/hex).

---

## LARK-ERA, PLAIN PYTHON (dies with the IR-native parser)

- **Parse-decode** (`parsing/meta_parser.py`): source escape unit → code point →
  `IrChr`; build `IrChr` singles / `IrRange(IrChr, IrChr)`.
  **RESOLVED (2026-06-15):** decode stays plain Python, NOT algebra (it scans raw
  text, with no IR node to dispatch on). Each flavour declares plain-data escape
  tables as attributes (the `EscapeCodec` ABC is deleted; its `SHORT_ESCAPES` /
  `HEX_ESCAPES` data survives as bare flavour attrs). A free function in
  `parsing/` consumes them to decode literal content and char-class units →
  code points. Emit = algebra, decode = plain data — two separate operations,
  one flavour home, honouring THE ONE PRINCIPLE.
- **Flat-view** (`utils/charclass.py:charclass_pattern`): re-spell `IrChr`/
  `IrRange` code points → canonical interior text (printable→char, special→`\`,
  control→`\xNN`) so the four condemned consumers (`generate`, `lark_builder`,
  `codegen/aliases`, `derive`) stay byte-compatible. The naming keys
  `0-9`/`a-z`/`a-fA-F0-9` (`ir/naming.py:CHARCLASS_NAMES`) MUST reproduce exactly.
  `parse_charclass_chars` reads it back.

---

## CODEGEN

Generated modules embed `RuleSpec` reprs now containing `IrChr(...)` /
`IrRange(IrChr(...), IrChr(...))`. `codegen/model_emitter.py` import block must
import `IrChr` (and any node type now in a repr). Fix the template, never a
generated file.

---

## BUILD ORDER

Step 1 is independently green. Steps 2–6 are one src push (the reshape breaks
every IR-constructing test + the flat-view consumers; no green between them — the
integration/round-trip/property suite returns to green once parse + flat-view are
mutually consistent; IR-constructing unit tests + flavour emit tests go green
after porting).

1. **Nodes** — `IrChr` (`base.py`), `IrRadix` (`action.py`);
   `IR_MAP_DEFAULT`→`IR_DEFAULT`; export. Verify suite stays green.
2. **Reshape** — `IrRange`, `IrCharClass`, `IrQuantifier`.
3. **Parse → code points** (decode-home resolved: plain-data flavour attrs +
   a free function in `parsing/` — see Lark-era section).
4. **Flat-view re-spell** + codegen import block.
5. **Emit algebra** — ABNF, then GBNF (glyph + specials).
6. **GBNF control-escaping** — the `IrMap` + `IR_DEFAULT → IrCond` cascade
   ("at the end" per user).
7. **Tests** — port (Sonnet subagent, **ask first**). GBNF test porting IS in
   scope. Update construction syntax (`IrStr` runs → `IrChr`, str endpoints →
   coerced); **preserve assertions**.

---

## TEST FACTS (verified this session)

- No test compares `to_grammar` to byte-exact ground-truth source. Emit-escape is
  asserted only in small flavour unit tests: `[a-z]`, `[0-9]`, `[abc0-9]`,
  `%x41-5A`, `%x61`, `%x62`, `%x63`, `(%x61 / %x62 / %x63)`.
- Round-trip fidelity rides on `to_text` + the flat-view (`generate`→`parse`), not
  flavour emit. Linchpin = `charclass_pattern` reproducing canonical text.
- The meta-grammar idempotent parse test is parse-only (two parses equal),
  insensitive to decode spelling.
- Full suite is **765 tests** at baseline.
- ABNF tests asserting hex want **uppercase, 2-digit** (`%x41-5A`, `%x09`).
- Ground-truth char-classes exercising escapes: `[\x00-\x1F]`, `\x7F`, `\x0b`,
  `\x0c`, `\x85`, ``, ``, `["\\bfnrt]`, direct Unicode ranges
  (`ぁ-ゟ`, `一-鿿`, `ァ-ヿ`, `、-〾`).

---

## PROCESS NOTES FOR THE NEXT AGENT (read these)

- **Do not write code until the user explicitly says to start AND agrees the bite
  size.** This session burned trust by charging into implementation
  (multi-file rename + node additions) unprompted. Confirm: "first concrete change
  = X, I stop and show you after." Then wait.
- User is terse and decisive. Wrong design guesses, re-opening decided points, and
  verbose docs all draw sharp correction. Keep output tight and high-signal.
- "Decided means decided." Record decisions as settled; never re-frame as open.
- Src first, then a **Sonnet** subagent for tests — **ask before** dispatching any
  subagent.
- Never commit autonomously. No `Co-Authored-By` lines.
- `tools/auto_fix.sh` before manual lint fixes. Commands prefixed `uv run`.
