# Handover V2 — codepoint char-ranges, spelling, new nodes (2026-06-15)

Supersedes `HANDOVER_CODEPOINT.md`. This session prototyped the new nodes and
the `IrRange` reshape, corrected the spelling model, then **`git restore`-d
everything**.

**STATUS: NOTHING IS IMPLEMENTED.** Tree clean at `992f8ab`, 765 green.
Everything below is a **spec to build from scratch** — prototyped this session
(known-feasible), not in the tree. Branch `more_nodes`.

The original handover's spelling-table example, build-plan ordering, and rejected
list remain the starting point. What follows are the **deltas this session
established** — read them as overrides.

---

## HARD CONSTRAINTS (enforced this session — violating these got work deleted)

1. **No new node classes without express approval.** Approved set: exactly
   `IrSwitchCase`, `IrRadix`, `IrChr`.
2. **No methods beyond `eval` on action nodes without permission.** Dunders
   (`__new__`/`__repr__`/`__str__`) only when justified (carry/round-trip
   payload). No helper methods, no nested data tables.
3. **No dicts added to `action.py`.**
4. **No `match`/`case`** for data mapping or base conversion.
5. **No hardcoded digit alphabets, no magic numbers.** Digit chars come from
   `ord("0")` / `ord("a")` (see `IrRadix`).
6. **Grammar canonical; round-trip lossless; suite green per logical unit.** Tests
   ported, never deleted. Src first, then a **Sonnet** subagent for tests — ask first.
7. **Never commit autonomously; no `Co-Authored-By`.** Tasks done only when the
   user says. Ask before each task / subagent.

---

## NODE DESIGNS — `IrChr`/`IrRadix` CARRY their codepoint (never read `n`)

All three new nodes live in `ir/action.py`.

1. **`IrChr(IrInt)`** — value-carrying codepoint leaf whose `__str__` IS the char
   spelling. The node *is* the codepoint (`int(IrChr(97)) == 97`, neutral);
   `str(IrChr(97)) == "a"`. Inverse is the plain `int` (`ord`). Justified dunder:
   `__str__` only. It is constructed with its codepoint — it does **not** read
   the dispatched `n`.

2. **`IrRadix`** — value-carrying codepoint leaf whose spelling is base-`base`
   digits. Carries `(codepoint, base)`; renders digits only (the `%x`/`\x`/`0x`
   prefix comes from the surrounding `IrConcat`). Prototyped as
   `IrNamedTuple[IrInt, int]` (`codepoint` child, scalar `base: int = 16`) whose
   `eval` IS the encode → digit `IrStr`. **Base-N rendering:** any base 2–36, no
   table/dict/match — digit char is arithmetic:
   ```python
   digit = rem + ord("0") if rem < 10 else rem - 10 + ord("a")
   digits.append(chr(digit))
   ```
   in a `divmod` loop (`while True: value, rem = divmod(value, base); ...; if not
   value: return`). Zero → `"0"`.

3. **`IrSwitchCase[Ir_co]`** — n-ary flattened `IrCond`. `IrSeq[IrTuple[IrSelf,
   IrSelf]]` of `(guard, body)` dyads. `eval` runs the first dyad whose `guard`
   is truthy; a guard that **is** `IR_MAP_DEFAULT` (from `lexic.ir.mapping`)
   always matches (trailing catch-all); no match ⇒ `IrKeyError`. Re-declare
   `_bound = tuple`. `eval`-only. Also used for Step 6 quantifier flattening.

4. **`IrInt.__str__` fix** (`ir/base.py`): `return int.__repr__(self)`. `int` has
   no own `__str__`, so `str(IrInt(4))` falls through `object.__str__` → codegen
   `IrScalar.__repr__` → `"IrInt(4)"`. Fix on `IrInt` ONLY (an `IrScalar.__str__`
   override recurses via `__format__`).

Export all four from `ir/__init__.py`.

---

## `IrRange` reshape (Step 2)

In `ir/nodes.py`:
- `class IrRange(IrNamedTuple[IrInt, "IrInt | IrNoneType"])` — drop `IrLeaf`, the
  `_child_attrs = ()` override, and the `[T: (str,int)]` generic. `lo`/`hi`
  become **dispatchable `IrInt` codepoint children**.
- **Coercing `__new__`:** single-char `str` → `ord`; plain `int` → as-is; an
  endpoint already an `IrInt` (incl. `IrChr`) kept. `IrRange("a","z")`,
  `IrRange(97,122)`, `IrRange("\x61","\x7a")` → `IrRange(IrInt(97), IrInt(122))`.
  Inline both coercions (no helper):
  ```python
  def __new__(cls, lo, hi):
      lo = lo if isinstance(lo, IrInt) else IrInt(ord(lo) if isinstance(lo, str) else lo)
      if hi is not IrNone and not isinstance(hi, IrInt):
          hi = IrInt(ord(hi) if isinstance(hi, str) else hi)
      return super().__new__(cls, lo, hi)
  ```
- **`IrQuantifier(IrRange)` stays plain int counts** — override `__new__` to
  bypass the coercion (`return IrNamedTuple.__new__(cls, lo, hi)`), keep
  `_child_attrs = ()`, defaults `(1,1)`. Every quantifier consumer (`generate`,
  `build_transformer`, `codegen`, `lark_builder`, `derive`) reads `q.lo`/`q.hi`
  as plain ints — do not disturb them.

---

## SPELLING MODEL — emit-time, per-flavour (DECIDED)

- Endpoints are **neutral `IrInt` codepoints**. One parsed `IrRange(IrInt(48),
  IrInt(57))` emits `0-9` under GBNF and `%x30-39` under ABNF — same neutral
  codepoint, two surface spellings (the `to_grammar(flavour)` seam in `base.py`).
- Each flavour's emit actions **do the spelling via the value-carrying
  `IrChr`/`IrRadix` leaves, constructed from the endpoint codepoint** — e.g.
  `IrField("lo", IrChr)` reads `n.lo` and wraps it as `IrChr(codepoint)`, which
  renders as the char (GBNF); ABNF reads `int(endpoint)` and renders `%xNN`.
- Per-flavour `IrMap[IrInt, body]` (specials keyed by codepoint) +
  `IR_MAP_DEFAULT → IrSwitchCase` (control → hex, else → char) handle escaping —
  the Step 3 spelling tables. `IrChr`/`IrRadix` are the value-carrying leaves
  those bodies build and render.

---

## BLAST RADIUS (measured — the reshape breaks ~105 tests)

Steps 2–5 are **one inseparable unit** — no green checkpoint between them. Every
failure traces to a consumer still assuming the old escape-unit-string endpoints:

| Failure | Cause | Fix lands in |
|---|---|---|
| `^[48-57]+$` not `^[0-9]+$` | flat-view `charclass_pattern` emits codepoints | **Step 5** `utils/charclass.py` |
| `ord() … string of length 4` | parser feeds raw multi-char escape units to `IrRange.__new__` | **Step 4** `parsing/meta_parser.py` |
| `ord(str(element.lo))` | abnf charclass emit reads old str endpoints | **Step 3** `grammars/abnf/flavour.py` |
| `NameError: IrInt` in `generated/*.py` | codegen embeds the `RuleSpec` repr (now `IrInt(...)`) without importing `IrInt` | **Step 3** `codegen/model_emitter.py` import block |
| pydantic `SchemaError`, gbnf emit | downstream of the above | resolved by the above |

---

## BUILD PLAN (one coherent src push, then Sonnet tests)

- **Step 1 — New nodes:** `IrSwitchCase`, `IrRadix`, `IrChr`, `IrInt.__str__`;
  export them.
- **Step 2 — `IrRange` reshape** (above). `IrQuantifier` stays int.
- **Step 3 — Kill `EscapeCodec` + `IrEscape`; build emit-time per-flavour spelling.**
  - Per-flavour `IrRange`/charclass actions spell each codepoint endpoint via the
    value-carrying `IrChr`/`IrRadix` leaves (GBNF → char, `]`→`\]`, `[`→`\[`,
    `\`→`\\`, control→`\xNN`; ABNF → `%xNN`).
  - GBNF/ABNF `IrLiteral` escaping routes through the same per-flavour spelling
    instead of `IrEscape()` (`d.escapes`).
  - `_abnf_charclass` `IrCallable` → declarative (read `int(element.lo)`).
  - Codegen: generated modules must import `IrInt` (and any node type now in
    `RuleSpec` reprs). Fix the template / import collection, not generated files.
  - Delete `ir/escapes.py` (`EscapeCodec`, `_GbnfEscapes`, `_AbnfEscapes`,
    `_CanonicalEscapes`, `CANONICAL_ESCAPES`); drop `IrEscape` from
    `grammars/flavour.py` and its `escapes` ClassVar; drop `ir/__init__.py`
    re-exports. NOTE: `parsing/lark_builder.py`'s `_LarkLiteralEscapes` is an
    independent Lark-internal codec — leave/inline, not the spelling concern.
- **Step 4 — Parser → codepoints.** `parsing/meta_parser.py`
  `_build_charclass`/`_read_unit`: decode each escape unit to its codepoint int
  before constructing `IrRange`. Literals decode through the spelling's inverse
  instead of `f.escapes.decode`. Decide bare `IrStr` runs inside `IrCharClass`
  (not reshaped) — keep consistent with Step 5.
- **Step 5 — Flat-view re-encode.** `utils/charclass.py:charclass_pattern`
  re-spells codepoints → canonical interior text so the four condemned consumers
  (`generate`, `lark_builder`, `derive`, `codegen/aliases`) stay untouched.
  `parse_charclass_chars`/`_read_char` use `CANONICAL_ESCAPES` → need a
  replacement for the canonical-unit boundary read (Lark-era).
- **Step 6 — Quantifier flattening.** Both flavours' `IR_MAP_DEFAULT` quantifier
  branch: nested `IrCond` → `IrSwitchCase`. Keep the two exact-value specials
  (`(1,1)→""`, `(0,∞)→"*"`) as `IrMap` dyads.
- **Step 7 — Tests.** Sonnet subagent, ask first. Port, don't delete.

---

## REJECTED (do not retry)

- **`IrChr()` / `IrRadix(base)` as `n`-reading ops** — they are value-carrying;
  the codepoint is supplied to them (e.g. via `IrField`), not read from `n`.
- **Parse-time / leaf-typed spelling ("model B")** — breaks flavour-neutrality.
- Hardcoded digit alphabet; `match`/`case` base→spec; base→char dict in
  `action.py`; magic `48`/`87`. Arithmetic from `ord("0")`/`ord("a")` only.
- `IrHex` baked-in node — use `IrRadix(base)`.
- Format-string spelling node — opaque, not cleanly invertible.
- `IrScalar.__str__` override — recurses; `IrInt.__str__` only.
- Widening `IrDispatch.actions` / a `select(d,n,nc)` seam — `IrSwitchCase`-as-body
  under `IR_MAP_DEFAULT` is enough.

---

## KNOWN-DEFERRED

- Parse-side flavour methods (`parse_quantifier`/`parse_charclass`/
  `normalize_literal`) and `meta_parser` `_build_charclass`/`_read_unit` are
  Lark-era; die with the IR-native parser.
- `utils/quantifiers.py:bounds_to_quantifier` — scheduled cleanup, untouched.
- CLAUDE.md / `.wiki/` stale; update after the thread lands.
