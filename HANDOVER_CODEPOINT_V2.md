# Handover V2 — codepoint char-ranges, spelling, new nodes (2026-06-15)

Supersedes `HANDOVER_CODEPOINT.md`. That doc locked a design under a
**parse-time spelling** assumption ("model B"). This session built the new
nodes, started the `IrRange` reshape, then discovered model B breaks
flavour-neutrality. The design was corrected to **emit-time per-flavour
spelling**. Working tree was `git restore`-d to commit `992f8ab` (clean, 765
green) — **none of the code below is in the tree**; this is the spec to
re-implement against. Branch `more_nodes`.

The original handover's mechanics (decisions #1–#5, the spelling-table example,
the build-plan ordering) are still the right starting point. The **deltas this
session established** are what follow — read them as overrides.

---

## HARD CONSTRAINTS (enforced this session — violating these got work deleted)

These are non-negotiable. The user deleted agent work / session data over each.

1. **No new node classes without express approval.** The approved set is exactly
   `IrSwitchCase`, `IrRadix`, `IrChr`. Nothing else without asking.
2. **No methods beyond `eval` on action nodes without permission.** Dunders
   (`__new__`, `__repr__`, `__str__`) are acceptable **only when justified** (e.g.
   to carry/round-trip payload). No helper methods, no nested data tables.
3. **No dicts added to `action.py`.** Data/lookup tables do not belong in the
   action algebra. (An agent was deleted for adding one.)
4. **No `match`/`case`** for data mapping or base conversion. Don't reach for it.
5. **No hardcoded digit alphabets, no magic numbers.** Derive digit characters
   arithmetically from `ord("0")` / `ord("a")` (see IrRadix below).
6. **Grammar is canonical; round-trip must stay lossless; suite stays green per
   logical unit.** Tests are ported, never deleted (memory:
   `feedback_port_tests_never_delete`). Src first, then a **Sonnet** subagent for
   tests — **ask first** (`feedback_sonnet_agents_for_tests`,
   `feedback_never_launch_subagent_without_asking`).
7. **Never commit autonomously; no `Co-Authored-By`.** Tasks are done only when
   the user says so. Pause and ask before each task / subagent.

---

## THE ONE OPEN BLOCKER — resolve this FIRST

**`IrChr`/`IrRadix` shape conflicts with the chosen spelling model.** Resolve
before writing any flavour spelling code.

- This session reshaped `IrChr`/`IrRadix` to **carry** their codepoint at
  construction (`IrChr(97)`, `IrRadix(IrInt(97), 16)`).
- Then the user chose **emit-time per-flavour spelling** (see below). Emit-time
  spelling hands the codepoint to a spelling **body as the runtime `n`**, and the
  body must render it. A value-carrying node can't render a runtime `n`: a static
  `IrChr()` is just `IrChr(0)`; `IrRadix.eval` reads `self.codepoint`, not `n`.
- The handover's own spelling-table example (decision #4) **requires** the bodies
  to read `n`: `IrChr()` → `chr(int(n))`, `IrRadix(16)` → hex of `int(n)`.

**Recommended resolution (a):** make `IrChr`/`IrRadix` **read the dispatched
codepoint `n`** (operation shape, matching the handover's tables). `IrChr()` →
`IrStr`/char of `int(n)`; `IrRadix(base)` → digit `IrStr` of `int(n)`. This adds
no nodes and is what emit-time spelling needs. **The user did not confirm (a)
before reverting — get a yes/no on it first.** Alternative (b) keeps them
value-carrying and adds a separate `n`-reading spelling op (a new node → needs
approval, see constraint 1).

---

## LOCKED DECISIONS (built and verified green this session, except where noted)

### New nodes — all live in `ir/action.py`

1. **`IrSwitchCase[Ir_co]`** — n-ary flattened `IrCond`. An `IrSeq[IrTuple[IrSelf,
   IrSelf]]` of `(guard, body)` dyads. `eval` returns the first dyad's body whose
   `guard` is truthy; a guard that **is** `IR_MAP_DEFAULT` (imported from
   `lexic.ir.mapping`) always matches (trailing catch-all); no match ⇒
   `IrKeyError`. Re-declare `_bound = tuple` (the `IrSeq` move). `eval`-only.
   *(Built, green. Also needed for Step 6 quantifier flattening.)*

2. **`IrChr(IrInt)`** — locked as "an `IrInt` subtype whose `__str__` is the
   operation": `str(IrChr(97)) == "a"`, `int(IrChr(97)) == 97`. **BUT see the
   open blocker** — emit-time spelling likely needs it to read `n` instead.
   *(Built green in the value-carrying form; may need reshape per blocker.)*

3. **`IrRadix`** — spell a codepoint as base-N digits. Final built form was a
   `(codepoint, base)` record (`IrNamedTuple[IrInt, int]`, `_child_attrs =
   ("codepoint",)`, `base: int = 16`) whose **`eval` IS the encode** → digit
   `IrStr`. **BUT see the open blocker** — likely needs to read `n`.
   - **Base-N rendering (this part is locked regardless of shape):** any base
     2–36, no table/dict/match. Digit char is arithmetic:
     ```python
     digit = rem + ord("0") if rem < 10 else rem - 10 + ord("a")
     digits.append(chr(digit))
     ```
     in a `divmod` loop (`while True: value, rem = divmod(value, base); ...; if
     not value: return`). Zero handled naturally → `"0"`.
   - Prefix (`%x` / `\x` / `0x`) is supplied by the surrounding `IrConcat`, never
     by `IrRadix`.

4. **`IrInt.__str__` fix** (in `ir/base.py`): `return int.__repr__(self)`.
   Confirmed bug: `int` has no own `__str__`, so `str(IrInt(4))` falls through
   `object.__str__` → codegen `IrScalar.__repr__` → `"IrInt(4)"`. Fix on `IrInt`
   ONLY (an `IrScalar.__str__` override recurses via `__format__`). *(Built, green.)*

All four were exported from `ir/__init__.py`.

### `IrRange` reshape (Step 2) — built, correct at node level

In `ir/nodes.py`:
- `class IrRange(IrNamedTuple[IrInt, "IrInt | IrNoneType"])` — drop the `IrLeaf`
  mixin and the `_child_attrs = ()` override, drop the `[T: (str,int)]` generic.
  `lo`/`hi` become **dispatchable `IrInt` codepoint children**.
- **Coercing `__new__`:** single-char `str` → `ord`; plain `int` → as-is; an
  endpoint that already IS an `IrInt` (incl. subtypes like `IrChr`) is kept. So
  `IrRange("a","z")`, `IrRange(97,122)`, `IrRange("\x61","\x7a")` all normalise to
  `IrRange(IrInt(97), IrInt(122))`. Inline both coercions (no helper method):
  ```python
  def __new__(cls, lo, hi):
      lo = lo if isinstance(lo, IrInt) else IrInt(ord(lo) if isinstance(lo, str) else lo)
      if hi is not IrNone and not isinstance(hi, IrInt):
          hi = IrInt(ord(hi) if isinstance(hi, str) else hi)
      return super().__new__(cls, lo, hi)
  ```
- **`IrQuantifier(IrRange)` stays plain int counts** — override `__new__` to
  bypass the codepoint coercion (`return IrNamedTuple.__new__(cls, lo, hi)`),
  keep `_child_attrs = ()`, defaults `(1,1)`. Every quantifier consumer
  (`generate`, `build_transformer`, `codegen`, `lark_builder`, `derive`) reads
  `q.lo`/`q.hi` as **plain ints** — do not disturb them.

### Spelling location — DECIDED: emit-time, per-flavour (was "option 1")

Endpoints stay **neutral `IrInt` codepoints**. Each flavour spells them **at
emit**: one parsed `IrRange(IrInt(48), IrInt(57))` must emit `0-9` under GBNF and
`%x30-39` under ABNF — same neutral codepoint, two surface spellings. This is the
`to_grammar(flavour)` seam in `base.py` and is why parse-time leaf typing
("model B") was rejected: it freezes the spelling and breaks cross-flavour.

So the handover's **Step 3 spelling tables** are the mechanism, applied at emit:
per-flavour `IrMap[IrInt, body]` (specials by codepoint key) + `IR_MAP_DEFAULT →
IrSwitchCase` (control → hex, else → char). `IrChr`/`IrRadix` are the spelling
**operations** invoked inside those bodies — which is exactly why the open
blocker (they must read `n`) must be resolved first.

---

## BLAST RADIUS (measured this session — the reshape breaks ~105 tests)

Steps 2–5 are **one inseparable unit**: there is **no green checkpoint between
them**. The `IrRange` reshape alone breaks ~105 tests; every failure traces to a
consumer that still assumes the old (escape-unit-string) endpoint representation:

| Failure | Cause | Fix lands in |
|---|---|---|
| `^[48-57]+$` not `^[0-9]+$` | flat-view `charclass_pattern` emits codepoints | **Step 5** `utils/charclass.py` |
| `ord() … string of length 4` | parser feeds raw multi-char escape units to `IrRange.__new__` | **Step 4** `parsing/meta_parser.py` |
| `ord(str(element.lo))` | abnf charclass emit reads old str endpoints | **Step 3** `grammars/abnf/flavour.py` |
| `NameError: IrInt` in `generated/*.py` | codegen embeds the `RuleSpec` repr (now contains `IrInt(...)`) without importing `IrInt` | **Step 3** codegen import block (`codegen/model_emitter.py`) |
| pydantic `SchemaError`, gbnf emit | downstream of the above | resolved by the above |

---

## REMAINING BUILD PLAN (Steps 3–6; do as one coherent src push, then Sonnet tests)

**Resolve the open blocker first.** Then:

- **Step 3 — Kill `EscapeCodec` + `IrEscape`; build emit-time per-flavour spelling.**
  - `IrRange` action (per flavour) spells each codepoint endpoint via the
    resolved `IrChr`/`IrRadix` ops. GBNF → char (with `]`→`\]`, `[`→`\[`,
    `\`→`\\`, control→`\xNN`); ABNF → `%xNN`.
  - GBNF/ABNF `IrLiteral` action escaping routes through the same per-flavour
    spelling instead of `IrEscape()` (`d.escapes`).
  - `_abnf_charclass` `IrCallable` → declarative (read `int(element.lo)`, not
    `ord(str(...))`).
  - Codegen: generated modules must import `IrInt` (and any other node type now
    appearing in `RuleSpec` reprs). Fix the template/import collection, not the
    generated files.
  - Delete `ir/escapes.py` (whole module: `EscapeCodec`, `_GbnfEscapes`,
    `_AbnfEscapes`, `_CanonicalEscapes`, `CANONICAL_ESCAPES`); drop `IrEscape`
    from `grammars/flavour.py` and its `escapes` ClassVar; drop re-exports from
    `ir/__init__.py`. NOTE: `parsing/lark_builder.py`'s `_LarkLiteralEscapes` is
    an **independent** Lark-internal codec — not the flavour codec; leave or
    inline locally, it is NOT the spelling concern.
- **Step 4 — Parser → codepoints.** `parsing/meta_parser.py`
  `_build_charclass`/`_read_unit`: decode each escape unit to its **codepoint
  int** before constructing `IrRange`. Literals decode through the spelling's
  inverse instead of `f.escapes.decode`. (Decide treatment of bare `IrStr` runs
  inside `IrCharClass` — they were NOT reshaped; keep consistent with the
  re-encode in Step 5.)
- **Step 5 — Flat-view re-encode.** `utils/charclass.py:charclass_pattern` must
  re-spell codepoints → canonical interior text so the four condemned consumers
  (`generate`, `parsing/lark_builder`, `ir/derive`, `codegen/aliases`) stay
  untouched. `parse_charclass_chars`/`_read_char` use `CANONICAL_ESCAPES` →
  need a replacement for the canonical-unit boundary read (Lark-era; dies with
  the Lark pipeline).
- **Step 6 — Quantifier flattening.** Flatten both flavours' `IR_MAP_DEFAULT`
  quantifier branch from nested `IrCond` to `IrSwitchCase` (see the ABNF example
  in the original handover). Keep the two exact-value specials (`(1,1)→""`,
  `(0,∞)→"*"`) as `IrMap` dyads.
- **Step 7 — Tests.** Sonnet subagent, **ask first**. Port, don't delete.

---

## REJECTED (do not retry)

- **Parse-time / leaf-typed spelling ("model B")** — breaks flavour-neutrality
  (one IR, two flavour emits). Spelling is emit-time, per-flavour.
- Hardcoded digit alphabet string; `match`/`case` base→spec mapping; base→char
  lookup dict in `action.py`; magic `48`/`87` — all rejected. Arithmetic from
  `ord("0")`/`ord("a")` only.
- `IrHex` baked-in node — `IrRadix(base)` (flavour may be non-hex).
- A format-string spelling node — opaque, not cleanly invertible.
- `IrScalar.__str__` override — recurses; `IrInt.__str__` only.
- Widening `IrDispatch.actions` / a `select(d,n,nc)` seam — unnecessary;
  `IrSwitchCase`-as-body under `IR_MAP_DEFAULT` is enough.

---

## KNOWN-DEFERRED (out of scope)

- Parse-side flavour methods (`parse_quantifier`/`parse_charclass`/
  `normalize_literal`) and `meta_parser` `_build_charclass`/`_read_unit` are
  Lark-era; they die with the IR-native parser (separate session).
- `utils/quantifiers.py:bounds_to_quantifier` — scheduled cleanup, untouched.
- CLAUDE.md / `.wiki/` are stale; update after the thread lands.
