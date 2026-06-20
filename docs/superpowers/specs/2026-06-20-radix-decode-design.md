# Design — radix decode in the ABNF reduce (task B)

**Date:** 2026-06-20
**Scope:** the reduce direction only — replace the two procedural calls
`ABNF_FLAVOUR.parse_charclass` / `parse_quantifier` (in `grammars/abnf_2.py`'s
`_num_val` / `_repeat`) with pure `IrSelf` algebra, removing the last `IrLambda`s
from the numeric reductions. This is item **B** of the
`2026-06-18-flavour-2-reduce-handover.md`.

**Status:** design validated end-to-end against a real parse + real reduce
(`_validate_radix.py`, all cases pass) and adversarially reviewed. **Decided:**
char-preserving endpoint storage (`IrChr` + `IrGlyph` collapse) and a **pure**
`_repetition` (no `IrLambda`). Implementing.

---

## Decided constraints (not re-opened)

- **No `IrCallable`, no `IrLambda`** in the final numeric reductions.
- **`IrChr`** is a value-carrying `IrInt` subtype: the node IS the code point;
  `__str__` → `chr(self)` (the glyph), `eval` → `IrStr(chr(self))`. Lives in
  `ir/base.py`. (Locked in the codepoint thread; reaffirmed in the
  `decided_means_decided` memory.)
- The decided **emit** primitive `IrRadix(base, width)` does the inverse
  (code point → digit string) with hand ord-arithmetic — no `int(s,base)`,
  `format`, table, or `match`.
- **THE ONE PRINCIPLE:** radix (code point ⇄ digit spelling) and escaping
  (special char ⇄ safe form) are orthogonal, composed at the site, never fused.
  This design touches radix only; ABNF has no escaping.

---

## The core idea

`IrQuantifier(lo, hi)` and `IrRange(lo, hi)` **already are the structure.** The
only thing un-decoded is the *number sitting in a slot*. So the reduce builds the
final IR types directly and the only new pieces are:

1. **`IrChr`** (`ir/base.py`) — the value-carrying code point (above).
2. **`IrUnradix`** (`ir/action.py`) — the radix-decode body (digits → code point).
3. **`IrGlyph`** (`ir/action.py`) — collapse a code-point focus to its 1-char
   `IrStr` glyph. The char-preserving bridge (see Axis 2): the decode yields a
   code point, `IrGlyph` lands it as the char today's `IrRange`/`IrCharClass`
   already store. Throwaway — removed when the code-point storage reshape lands.

No intermediate node types (an earlier `IrNumVal`/`IrRepeatExact`/`IrRepeatRange`
sketch was scrapped — those merely re-encoded `IrCharClass`/`IrQuantifier`). No
extra normalize pass.

### `IrUnradix` — the one new action node

A record-leaf, the inverse of emit `IrRadix`:

```python
class IrUnradix(IrNamedTuple[int, type[IrScalar]]):
    """Decode the focus digit string to out(value) via ord-arithmetic."""
    _child_attrs = ()
    base: int                    # 2 / 10 / 16, scalar payload (per flavour token)
    out: type[IrScalar] = IrInt  # IrChr for code points, IrInt for counts

    def eval(self, _d, n, _nc, /):
        s = str(n)               # focus is a digit IrStr, fed via IrPipe(<digits>, IrUnradix(...))
        if not s:                # explicit guard (CLAUDE.md: no silent dispatch path)
            raise UnsupportedConstructError("IrUnradix: empty digit string")
        acc = 0
        for c in s:
            v = ord(c) - 0x30 if "0" <= c <= "9" else ord(c.upper()) - 0x41 + 10
            if not (0 <= v < self.base):
                raise UnsupportedConstructError(...)
            acc = acc * self.base + v
        return self.out(acc)
```

`__repr__` is **not** overridden: it inherits `IrScalar`'s codegen repr, so
`repr(IrChr(65)) == "IrChr(65)"` (reconstructs from the code point) while
`str(IrChr(65)) == "A"` (the glyph). That split is intended — repr is codegen,
str is the surface. `codegen/model_emitter.py`'s import block must add `IrChr`.

- `out` is open, same pattern as `IrField.out` — a new scalar type needs no
  change here.
- It **reads its focus** `n` (a transform body, like `IrField`/`IrJoin`), so it
  composes as `IrPipe(<digit source>, IrUnradix(base, out))`. This is distinct
  from the value-carrying `IrChr`/emit-`IrRadix` — `IrUnradix` is the decode
  transform, not a value carrier.
- `base` is static payload (ABNF is hex/decimal). A future `%d`/`%b`/`bin-val`
  set could read `base` off the node; out of scope here.
- Naming alternative considered: make `IrRadix` bidirectional (eval dispatches
  encode vs decode on focus type). Rejected — keeps each eval single-branch,
  matching the decided "no mode flag, no match" style.

---

## Grammar restructure

The grammar carries the structure (which slot a digit run feeds). Wrap each
digit run in its own rule, and give every optional bound its own **named** rule
so the structural slot always exists:

```
hexits     = 1*HEXDIG
num-val    = num-single / num-range
num-single = "%" "x" hexits
num-range  = "%" "x" hexits "-" hexits

decits       = 1*DIGIT
repeat       = repeat-exact / repeat-range
repeat-exact = decits
repeat-range = lo-bound "*" hi-bound
lo-bound     = [decits]          ; empty ⇒ 0
hi-bound     = [decits]          ; empty ⇒ ∞ (IrNone)

; pure _repetition: the optional repeat becomes a named rule too
repetition   = repeat-opt element
repeat-opt   = [repeat]          ; empty ⇒ IrQuantifier() default (1,1)
```

Splitting `num-val` and `repeat` into named arms kills the `5` vs `5*` vs `*5`
ambiguity — the discriminator is the **rule name** the reducer dispatches on, not
the dropped `*`. Wrapping each optional bound in a named rule guarantees the
slot materialises in the parent even when the bound matched empty (see Mechanism).

This is parse-side only; emit is unaffected (it renders the final
`IrCharClass`/`IrQuantifier`, never these rules). The ABNF self-hosting fixpoint
must be re-closed after the change (these rules describe ABNF's own syntax).

---

## Reduce table

Every body builds a final type. `IrUnradix` decodes one clean digit string per
slot. (`IrJoin(IrArgs())` is the established "join the children" body — already
used as `_YIELD` in `test_reduce.py`.)

```python
# char-preserving: decode digits → code point (IrChr) → glyph IrStr (IrGlyph)
_cp  = lambda i: IrPipe(IrArg(i), IrPipe(IrUnradix(16, IrChr), IrGlyph()))
_dec = IrPipe(IrJoin(IrArgs()), IrUnradix(10, IrInt))     # joined digits → count

# digit-run rules: join scattered single-char args into one string
IrTuple(IrRuleRef("hexits"), IrJoin(IrArgs())),          # ("4","1") → "41"
IrTuple(IrRuleRef("decits"), IrJoin(IrArgs())),          # ("5",)    → "5"

# alternation passthroughs — LOAD-BEARING. Without these, `repeat`/`num-val`
# fall through IR_DEFAULT→YIELD and reduce to TEXT, not the built node.
# (The embedded-context test caught this omission.)
IrTuple(IrRuleRef("repeat"), IrArg(0)),
IrTuple(IrRuleRef("num-val"), IrArg(0)),

# num-val → IrCharClass directly (IrStr glyph endpoints, today's shape)
IrTuple(IrRuleRef("num-single"), IrBuild(IrCharClass, IrTuple(_cp(0)))),
IrTuple(IrRuleRef("num-range"),
    IrBuild(IrCharClass, IrTuple(IrBuild(IrRange, IrTuple(_cp(0), _cp(1)))))),

# repeat → IrQuantifier directly
IrTuple(IrRuleRef("repeat-exact"),
    IrBuild(IrQuantifier, IrTuple(IrPipe(IrArg(0), IrUnradix(10, IrInt)),
                                  IrPipe(IrArg(0), IrUnradix(10, IrInt))))),
IrTuple(IrRuleRef("repeat-range"),
    IrBuild(IrQuantifier, IrTuple(IrArg(0), IrArg(1)))),

# the bounds own their own emptiness — IrArgs() is falsy when the rule matched empty
IrTuple(IrRuleRef("lo-bound"),
    IrCond(test=IrArgs(), then_op=_dec, else_op=IrInt(0))),
IrTuple(IrRuleRef("hi-bound"),
    IrCond(test=IrArgs(), then_op=_dec, else_op=IrNone)),   # ∞

# pure _repetition (no IrLambda): repeat-opt defaults to a BUILT IrQuantifier()
# (not IrNone — IrNone is truthy; and a branch value must be constructed in-branch,
# never a pre-built composite, since IrCond evals the chosen branch).
IrTuple(IrRuleRef("repeat-opt"),
    IrCond(test=IrArgs(), then_op=IrArg(0), else_op=IrBuild(IrQuantifier, IrTuple()))),
IrTuple(IrRuleRef("repetition"),
    IrBuild(IrItem, IrTuple(IrArg(1), IrArg(0)))),   # (atom, quant)
```

`IrQuantifier(lo, hi)` is built once, by `repeat-range`; the lo/hi bound rules
supply the `IrInt(0)` / `IrNone` defaults. No parallel "repeat" type. `_repetition`
is now pure: `repeat-opt` always lands a quantifier (decoded or the `(1,1)`
default), so `repetition` is a plain positional `IrBuild(IrItem, (atom, quant))`.

---

## Mechanism: how empty bounds work (verified)

`[decits]` desugars (in `normalize.py`) to `lo-bound = __opt = "" / decits`. When
the optional matches empty, `__opt` (a synthetic `__`-prefixed rule) takes the
empty arm. `RESOLVE_CHILDREN` splices synthetic children, so an empty `__opt`
contributes nothing — `lo-bound`'s `nc` is empty. But `lo-bound` itself is a
**real** (non-synthetic) rule, so it always appears as a child of `repeat-range`
and always reduces. Its body `IrCond(test=IrArgs(), ...)` reads the empty `nc`
as falsy and yields the default. The named wrapper is what guarantees the slot.

---

## Empirical validation (`_validate_radix.py`)

Real `normalize` → `parse` → `Reducer.apply`, `IrChr`/`IrUnradix` prototyped
inline (the prototype `IrChr` subclasses the **real** `IrInt`, so its equality is
production-accurate). **All cases pass with structural `==`:**

| input | reduced | input | reduced |
|---|---|---|---|
| `5` | `IrQuantifier(5,5)` | `%x41` | `IrCharClass(IrChr(65))` → glyph `A` |
| `1*5` | `IrQuantifier(1,5)` | `%x41-5A` | `IrCharClass(IrRange(IrChr(65),IrChr(90)))` → `A`-`Z` |
| `*5` | `IrQuantifier(0,5)` | `%x30-39` | `IrCharClass(IrRange(IrChr(48),IrChr(57)))` → `0`-`9` |
| `5*` | `IrQuantifier(5,∞)` | | |
| `*` | `IrQuantifier(0,∞)` | | |
| `12*34` | `IrQuantifier(12,34)` | | |

**Embedded context** (`repetition = repeat? element`, `element = num-val` — the
real combiner shape, not isolated start rules):

| input | reduced |
|---|---|
| `%x41` | `IrItem(IrCharClass(IrChr(65)), IrQuantifier(1,1))` |
| `3%x41` | `IrItem(IrCharClass(IrChr(65)), IrQuantifier(3,3))` |
| `1*2%x41-5A` | `IrItem(IrCharClass(IrRange(IrChr(65),IrChr(90))), IrQuantifier(1,2))` |

Covered: leading-empty optional (`*5`, `*`); multi-digit runs (`12*34`); code
points; the embedded combiner; `IrUnradix` empty-string guard raises.

**Equality semantics** (probed against the real `IrInt`): `IrChr(65)==IrChr(65)`
is `True`, `IrChr(65)!=IrChr(90)`, `IrChr(65)!=IrStr("A")` (distinct leaf kinds —
this is why the old `IrStr`-shaped tests must port), `hash` stable,
`IrCharClass(IrRange(IrChr,IrChr))` compares structurally. The earlier draft
compared num-val by `repr`; now it uses real `==`.

`_validate_radix.py` is kept as a regression artifact.

---

## Axis 2 — endpoint storage: DECIDED = char-preserving

Reduce produces **today's shape** — `IrStr` glyph endpoints (`IrRange("A","Z")`,
`IrCharClass(IrStr("A"))`) — via the `IrChr` → `IrGlyph` collapse. Chosen because
the self-hosting fixpoint compares reduced output **structurally** to the
char-authored `ABNF_GRAMMAR`:

- `IrRange(IrStr("A"),IrStr("Z")) == IrRange("A","Z")` → **True** (probed); single
  `IrCharClass(IrStr(chr(13))) == IrCharClass(IrStr("\r"))` → **True**.
- Code-point endpoints **without** `IrRange` coercion: `IrRange(IrChr(65),IrChr(90))
  != IrRange("A","Z")` → fixpoint **breaks** (probed).

So char-preserving is the only path that keeps B truly surgical: **fixpoint holds
unchanged, no `IrRange`/`IrCharClass` reshape, no grammar re-authoring, no
char-class test ports.** `IrChr` appears only transiently inside the reduce
algebra (never stored), so it never reaches a `RuleSpec` repr — **no
`codegen/model_emitter.py` import change needed.**

**Deferred (separate thread):** the locked code-point storage reshape — `IrRange`
coercing `__new__` (endpoints → `IrChr`), `IrQuantifier` opting out, the emit-side
spelling algebra, GBNF, and `EscapeCodec` removal. When it lands, `IrGlyph` and the
char storage are removed and endpoints become `IrChr`.

---

## What's new, in total

1. `IrChr` — `ir/base.py` (value-carrying code point; `__str__`/`eval` → glyph).
2. `IrUnradix(base, out)` — `ir/action.py` (radix-decode transform).
3. `IrGlyph` — `ir/action.py` (code-point focus → 1-char `IrStr` glyph; the
   char-preserving collapse, throwaway against the reshape).
4. Grammar: `ABNF_GRAMMAR` numeric rules restructured (wrap digit runs, split
   arms, named optional bounds, `repeat-opt`); re-close the self-hosting fixpoint.
5. `ABNF_REDUCTIONS`: replace the `_num_val`/`_repeat`/`_repetition` `IrLambda`s
   with the pure bodies above (plus the `repeat`/`num-val` passthroughs); delete
   all three `IrLambda` functions; `parse_charclass`/`parse_quantifier` lose their
   reduce-side caller.

Everything else is existing algebra (`IrBuild`, `IrPipe`, `IrJoin`, `IrArgs`,
`IrArg`, `IrCond`).

**Scope of the "no `IrLambda`" claim — now complete.** The restructure removes the
reason `_repetition` was parked: with `repeat-opt` a named rule, `repetition`'s
`nc` is fixed `(quant, atom)` and `repeat` reliably yields an `IrQuantifier`, so
`_repetition` becomes a plain `IrBuild`. All three numeric-area `IrLambda`s
(`_num_val`, `_repeat`, `_repetition`) are removed.

---

## Adversarial review — fixed vs. not

**Fixed in this design + demonstrator:**
- *Missing alternation passthroughs* (`repeat`/`num-val` → `IrArg(0)`). Caught by
  the embedded test; without them the node reduced to text. Added to the table.
- *`IrUnradix` empty-string* now raises (explicit dispatch path) rather than
  returning `IrInt(0)`/`IrChr(0)`.
- *Validation rigor*: num-val now compared with real `==`; embedded-context cases
  added; equality semantics probed against the real `IrInt`.
- *Scope overclaim*: the "no `IrLambda`" statement is now scoped to the two
  numeric token reductions; `_repetition` is documented as staying.

**Not fixed — and why:**
- *`IrUnradix` stores `int`/`type` in tuple slots that lack `.eval`.* Identical
  shape to the shipped `IrField` (`str` + `type[IrScalar]`); nothing dispatches an
  action body as a data node, so the "AttributeError if walked as data" path is
  unreachable. No change — it would diverge from existing precedent.
- *`IrChr.__repr__` shows `IrChr(65)`, not the glyph.* Intended: repr is codegen
  (must reconstruct from the code point); `str` is the glyph. Documented, not
  changed.
- *`acc > 0x10FFFF` only fails at emit-time `chr()`.* Left as-is: ABNF `%x` values
  are code points by definition; a decode-time cap would be an arbitrary policy
  not required by the grammar. Flagged, not guarded.
- *`test_abnf_2.py` num-val/repeat assertions* — char-preserving keeps the old
  `IrCharClass(IrStr(...))` / `IrRange(...)` shape, so the charclass assertions do
  **not** need porting. The two numeric reductions' tests change because the rule
  set and bodies change (`_num_val`/`_repeat` gone; new `num-single`/`num-range`/
  `repeat-exact`/`repeat-range`/bound rules). Test work waits for the parallel A
  agent to finish `test_abnf_2.py`, then is handed to a Sonnet subagent.

## Implementation gotchas (validated, fold into the code)

- **`IrNone` is truthy.** A default-via-`IrCond(test=IrArg(0))` mis-branches when
  the arg is `IrNone`. So `repeat-opt` defaults to a *built* `IrQuantifier()`, not
  `IrNone`, and `repetition` reads it positionally with no conditional.
- **Never hand a pre-built composite as an `IrCond` branch value.** `IrCond` calls
  `.eval()` on the chosen branch; `IrQuantifier().eval()` recurses into its int
  children and raises `AttributeError`. Construct it in-branch:
  `IrBuild(IrQuantifier, IrTuple())`. (Scalar literals like `IrInt(0)` are fine —
  they self-evaluate.)

## The remaining gate

**Self-hosting fixpoint.** Validated: the numeric rules in isolation, the embedded
`repetition` combiner, and that char-preserving output equals the authored
shapes. Not yet run (needs the real wiring): the full emit→parse→reduce fixpoint
over the whole restructured `ABNF_GRAMMAR` (`test_self_hosting_fixpoint` +
`_idempotent`). Run these first after wiring `abnf_2.py`; a red is a structural
diff that localizes the offending rule.
