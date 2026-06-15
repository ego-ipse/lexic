# Handover — codepoint char-ranges, `IrSwitchCase`, kill `EscapeCodec` (2026-06-14)

Reference doc for the locked design of the codepoint/spelling thread. Branch
`more_nodes`. Working tree clean at session start except this file + `HANDOVER.md`.
This supersedes the "live design thread" section of `HANDOVER.md` — that section
posed the open questions; **they are now answered and locked below.**

## The core insight (what unblocked it)

Two operations were being conflated. They are orthogonal and compose by
**structural position**, uniformly within a flavour:

- **Range conversion** — a numeric codepoint ⇄ its surface *spelling*
  (`97 ⇄ %x61` ABNF, `97 ⇄ a` GBNF). Bidirectional, flavour-configured.
- **Escaping** — a special char ⇄ its safe representation (`]` ⇄ `\]`).
  A separate value-dispatch.

Either can occur without the other (a range may or may not need escaping; an
escape may apply to a standalone special char, not a range). So the spelling
table does **not** own escaping and the escape table does **not** know about
ranges. They are composed at the emit site.

## Locked decisions

1. **`IrRadix(base)`, not `IrHex`.** The numeric digit primitive carries a base
   (int) as payload — `IrRadix(16)` for hex, `IrRadix(10)` for a decimal flavour.
   It renders **digits only**; the `%x` / `\x` / `0x` prefix is supplied by the
   surrounding `IrConcat` in the flavour, never by the node. Bidirectional:
   encode `IrInt` codepoint → digit `IrStr`; decode digit `IrStr` → `IrInt`
   (`int(s, base)`). Optional width/pad param if a flavour needs `%x09` vs `%x9`.
   Rationale: every realistic codepoint encoding is base-N; a format-string node
   (rejected) is opaque and not cleanly invertible (breaks the "and back" req).

2. **`IrChr`** — codepoint `IrInt` → 1-char `IrStr` (and `ord` for the inverse).
   Flavour-agnostic; the identity spelling of a printable codepoint.

3. **`IrSwitchCase` — n-ary flattened `IrCond`, a body. NO `IrDispatch` change.**
   `IrSwitchCase(IrSeq[IrTuple[IrSelf, IrSelf]])` — variadic `(guard, body)`
   pairs, evaluated in order; first guard whose `eval(d,n,nc)` is truthy wins,
   that pair's body is evaluated. **Else = a trailing pair whose guard is the
   `IR_MAP_DEFAULT` sentinel** (always matches) — reuses the exact catch-all
   `IrMap` already uses, so one sentinel concept across both tables. No match
   and no `IR_MAP_DEFAULT` pair ⇒ raise `IrKeyError` (consistent with `IrMap`).
   It is used as a **body**, typically as the value of an `IR_MAP_DEFAULT` dyad
   inside an `IrMap`. We deliberately did **not** widen `IrDispatch.actions`
   to a table union / add a `select(d,n,nc)` seam — that was the heavier
   alternative and is unnecessary for now.

4. **Spelling/escape = `IrMap` + `IR_MAP_DEFAULT → IrSwitchCase`.** Exact-value
   specials are `IrMap[IrInt, IrStr]` dyads (O(1) hash key by codepoint); the
   predicate tail (control range → hex, else → `IrChr`) is the `IrSwitchCase`
   under `IR_MAP_DEFAULT`. One spelling table per flavour, built once
   (singleton), held on the flavour. Example (GBNF charclass spelling):

   ```python
   IrMap(
       IrTuple(IrInt(0x5D), IrStr("\\]")),
       IrTuple(IrInt(0x5B), IrStr("\\[")),
       IrTuple(IR_MAP_DEFAULT, IrSwitchCase(
           IrTuple(IrCompare(IrThis(), IrOp("<"), IrInt(0x20)),
                   IrConcat(IrTuple(IrLiteral("\\x"), IrRadix(16)))),  # control → \xNN
           IrTuple(IR_MAP_DEFAULT, IrChr()),                          # else → literal char
       )),
   )
   ```

5. **`IrRange` reshape → codepoints.** Endpoints become `IrInt` codepoint
   **children** (drop the `IrLeaf` mixin and the `_child_attrs = ()` override;
   `lo`/`hi` become dispatchable children). Coercing `__new__`: single-char
   `str` → `ord`, plain `int` → as-is. So `IrRange("a","z")`, `IrRange(97,122)`,
   `IrRange("\x61","\x7a")` all normalise to `IrRange(IrInt(97), IrInt(122))`.
   The emit site reaches an endpoint with `IrAt(0, <spelling>)` / `IrAt(1, …)` —
   `IrAt` rebinds focus to the raw codepoint child and runs the spelling body
   against it. **This is the whole reason endpoints must be children.**
   `IrQuantifier(IrRange)` stays **int counts** (not codepoints), no-arg default
   `(1,1)`.

6. **`IrInt.__str__` → `int.__repr__(self)`.** Latent bug: today `str(IrInt(4))`
   returns `"IrInt(4)"` (int has no `__str__`, so it falls through to the codegen
   `__repr__`). The codepoint flip needs `"4"`. Fix is on `IrInt.__str__` ONLY —
   an `IrScalar.__str__` override recurses (`__format__("")` re-enters `__str__`).

7. **Kill `EscapeCodec`.** `ir/escapes.py` (the `EscapeCodec` ABC, `_GbnfEscapes`,
   `_AbnfEscapes`, `_CanonicalEscapes`, `CANONICAL_ESCAPES`) and `IrEscape`
   (in `grammars/flavour.py`, pulls `d.escapes`) are retired. Their jobs move to
   the per-flavour spelling tables (#4). `flavour.escapes` ClassVar goes away.

## New nodes — where they live

- `IrRadix`, `IrChr`, `IrSwitchCase` → `ir/action.py` (action-algebra bodies).
- Spelling tables → constructed in each flavour module (`gbnf/flavour.py`,
  `abnf/flavour.py`), like `GBNF_QUANTIFIERS` is today. Flavour-local data.

## Build plan (locked order)

1. New nodes: `IrSwitchCase`, `IrRadix(base)`, `IrChr`; `IrInt.__str__` fix.
2. `IrRange` reshape: `IrInt` codepoint children, coercing `__new__`,
   drop `IrLeaf`/`_child_attrs=()`. `IrQuantifier` stays int counts.
3. Kill `EscapeCodec` + `IrEscape`; build per-flavour spelling tables
   (`IrMap` + `IR_MAP_DEFAULT → IrSwitchCase`). Literal + charclass escaping
   route through them. `_abnf_charclass` `IrCallable` → declarative.
4. Parse (`parsing/meta_parser.py`): decode charclass endpoints to codepoints
   (`_build_charclass`/`_read_unit` produce `IrInt`); literals decode through the
   spelling's inverse instead of `f.escapes.decode`.
5. Flat-view re-encode: `utils/charclass.py:charclass_pattern` must re-spell
   codepoints → canonical interior text so the four condemned consumers stay
   untouched: `generate.py`, `parsing/lark_builder.py`, `ir/derive.py`,
   `codegen/aliases.py` (all call `charclass_pattern`; `generate` also
   `parse_charclass_chars`).
6. Quantifier: flatten both flavours' `IR_MAP_DEFAULT` branch from nested
   `IrCond` to `IrSwitchCase` (see ABNF example below).
7. Tests — **Sonnet subagent, ask the user first** (memory:
   `feedback_sonnet_agents_for_tests`). Port, don't delete
   (`feedback_port_tests_never_delete`).

## Blast radius (verified call sites)

`grep` for `EscapeCodec | .escapes | read_escape | .decode | .encode |
CANONICAL_ESCAPES | parse_charclass_chars | charclass_pattern | normalize_literal
| parse_charclass`:

- `ir/escapes.py` — DELETE (whole module).
- `ir/__init__.py` — drops `CANONICAL_ESCAPES`, `EscapeCodec` re-exports.
- `grammars/flavour.py` — `IrEscape` DELETE; `escapes` ClassVar removed;
  `parse_charclass`/`normalize_literal` still load-bearing for the Lark parser
  (parse-side rework deferred — see below).
- `grammars/gbnf/flavour.py`, `grammars/abnf/flavour.py` — `_GbnfEscapes`/
  `_AbnfEscapes` DELETE; build spelling tables; `_abnf_charclass` declarative.
- `parsing/meta_parser.py` — `ir_literal` / `_build_charclass` / `_read_unit`
  rework to codepoints; drop `CANONICAL_ESCAPES`.
- `parsing/lark_builder.py` — `_LarkLiteralEscapes(EscapeCodec)` at line 33 is
  an INDEPENDENT Lark-internal codec (Lark grammar string escaping), not the
  flavour codec. Decide: keep as a private local helper or inline. It is NOT the
  spelling concern.
- `utils/charclass.py` — `charclass_pattern` re-encode (#5); `parse_charclass_chars`
  + `_read_char` use `CANONICAL_ESCAPES` → need a replacement for the canonical
  unit boundary read (these are Lark-era, die with the Lark pipeline).

## Quantifier flattening (target, ABNF)

`ABNF_PREFIX_QUANTIFIER`'s `IR_MAP_DEFAULT` value, today a 3-deep `IrCond`,
becomes:

```python
IrTuple(IR_MAP_DEFAULT, IrSwitchCase(
    IrTuple(IrIsA("hi", IrNoneType),
            IrConcat(IrTuple(IrField("lo", IrStr), IrLiteral("*")))),             # {lo}*
    IrTuple(IrCompare(IrField("lo", IrInt), IrOp("=="), IrField("hi", IrInt)),
            IrField("lo", IrStr)),                                                 # {lo}
    IrTuple(IrCompare(IrField("lo", IrInt), IrOp("=="), IrInt(0)),
            IrConcat(IrTuple(IrLiteral("*"), IrField("hi", IrStr)))),              # *{hi}
    IrTuple(IR_MAP_DEFAULT,
            IrConcat(IrTuple(IrField("lo", IrStr), IrLiteral("*"), IrField("hi", IrStr)))),  # {lo}*{hi}
))
```

The two exact-value specials `(1,1)→""`, `(0,∞)→"*"` stay as `IrMap` dyads.

## Rejected (do not retry)

- `IrHex` baked-in node — use `IrRadix(base)` (flavour may be non-hex).
- Widening `IrDispatch.actions` to `IrMap | IrSwitchCase` + a `select(d,n,nc)`
  seam — heavier; `IrSwitchCase`-as-body under `IR_MAP_DEFAULT` is enough now.
- `IrSwitchCase(IrDispatch)` subclass — inherits a type-keyed `actions` field
  that doesn't fit `(guard, body)`; impedance mismatch.
- A format-string spelling node — opaque, not cleanly invertible.
- `IrScalar.__str__` override — recurses; fix `IrInt.__str__` only.
- `IrVector`/variadic `IrRange` — ranges are fixed arity (`lo`, `hi`).
- A flavour importing an `encode`/`charclass` helper from `utils`
  (`feedback_no_cross_module_util_imports` — instant restore).

## Known-deferred (out of scope for this thread)

- **Parse-side flavour methods** (`parse_quantifier` / `parse_charclass` /
  `normalize_literal`) — load-bearing for the Lark meta-parser; they die with
  the IR-native parser (separate design session). `_build_charclass`/`_read_unit`
  in `meta_parser.py` are Lark-era scaffolding that dies with that file.
- `utils/quantifiers.py:bounds_to_quantifier` — scheduled cleanup, untouched here.
- CLAUDE.md / `.wiki/` are stale; update after the thread lands.

## Workflow reminders (from memory)

- Pin shape before building (done — this doc). Don't multi-file on a guess.
- Tests → Sonnet subagent, **ask first**. Never launch a subagent unasked.
- Never commit autonomously; leave staged. No `Co-Authored-By`.
- No lint/type suppressions without explicit permission — fix root causes.
- Concise Sphinx-style docstrings (`:param:`/`:returns:`/`:raises:`).
- Tasks are done only when the user says so.
