# Design — radix decode in the ABNF reduce (task B)

**Date:** 2026-06-20
**Scope:** the reduce direction only — replace the two procedural calls
`ABNF_FLAVOUR.parse_charclass` / `parse_quantifier` (in `grammars/abnf_2.py`'s
`_num_val` / `_repeat`) with pure `IrSelf` algebra, removing the last `IrLambda`s
from the numeric reductions. This is item **B** of the
`2026-06-18-flavour-2-reduce-handover.md`.

**Status:** design validated end-to-end against a real parse + real reduce
(`_validate_radix.py`, all cases pass). Up for adversarial review before
implementation.

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
2. **`IrUnradix`** (`ir/action.py`) — the radix-decode body.

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
        acc = 0
        for c in s:
            v = ord(c) - 0x30 if "0" <= c <= "9" else ord(c.upper()) - 0x41 + 10
            if not (0 <= v < self.base):
                raise UnsupportedConstructError(...)
            acc = acc * self.base + v
        return self.out(acc)
```

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
_cp  = lambda i: IrPipe(IrArg(i), IrUnradix(16, IrChr))   # arg i → code point
_dec = IrPipe(IrJoin(IrArgs()), IrUnradix(10, IrInt))     # joined digits → count

# digit-run rules: join scattered single-char args into one string
IrTuple(IrRuleRef("hexits"), IrJoin(IrArgs())),          # ("4","1") → "41"
IrTuple(IrRuleRef("decits"), IrJoin(IrArgs())),          # ("5",)    → "5"

# num-val → IrCharClass directly
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
```

`IrQuantifier(lo, hi)` is built once, by `repeat-range`; the lo/hi bound rules
supply the `IrInt(0)` / `IrNone` defaults. No parallel "repeat" type.

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
inline. **All cases pass:**

| input | reduced | input | reduced |
|---|---|---|---|
| `5` | `IrQuantifier(5,5)` | `%x41` | `IrCharClass(IrChr(65))` → glyph `A` |
| `1*5` | `IrQuantifier(1,5)` | `%x41-5A` | `IrCharClass(IrRange(IrChr(65),IrChr(90)))` → `A`-`Z` |
| `*5` | `IrQuantifier(0,5)` | `%x30-39` | `IrCharClass(IrRange(IrChr(48),IrChr(57)))` → `0`-`9` |
| `5*` | `IrQuantifier(5,∞)` | | |
| `*` | `IrQuantifier(0,∞)` | | |
| `12*34` | `IrQuantifier(12,34)` | | |

The leading-empty optional (`*5`, `*`), multi-digit runs (`12*34`), and code-point
endpoints all work. `_validate_radix.py` is kept as a regression artifact.

---

## Axis 2 — endpoint storage (recommend: code points)

The design lands `IrChr` **code points** in `IrRange`/`IrCharClass`. The concern
was that this breaks char-expecting consumers. **Tested, it does not (for ABNF):**

- `utils/charclass.py:charclass_pattern` stringifies endpoints (`f"{el.lo}-{el.hi}"`,
  `str(el)`); `IrChr.__str__` is the glyph, so `IrCharClass(IrRange(IrChr(65),
  IrChr(90)))` → `"A-Z"`, identical to char endpoints.
- The real ABNF emit (`_abnf_charclass`, `ord(str(el.lo))`) produces byte-identical
  output for code-point and char endpoints: `%x41-5A`, `%x41`.
- No consumer does `isinstance(el, IrStr)` on a class member, so single members
  becoming `IrChr` (an `IrInt`) instead of `IrStr` does not trip a type ladder.

This contradicts the adversary's earlier "silent corruption" claim, which assumed
`str(IrChr(65)) == "65"` — false under the decided glyph `__str__`.

**Not yet exercised** (flagged, not assumed safe): GBNF emit; `derive` naming
keys; `generate`; `codegen/aliases`; and equality/hash — a test pinning the old
`IrCharClass(IrStr("A"))` shape will not equal `IrCharClass(IrChr(65))` (distinct
leaf kinds), so those are **test ports**, not consumer breaks. The
`IrCharClass`/`IrRange` element-type annotations would widen to admit `IrChr`.

---

## What's new, in total

1. `IrChr` — `ir/base.py` (value-carrying code point).
2. `IrUnradix(base, out)` — `ir/action.py` (radix-decode transform).
3. Grammar: `ABNF_GRAMMAR` numeric rules restructured (wrap digit runs, split
   arms, named optional bounds); re-close the self-hosting fixpoint.
4. `ABNF_REDUCTIONS`: replace `_num_val`/`_repeat` `IrLambda`s with the bodies
   above; delete the two `IrLambda` functions; `parse_charclass`/`parse_quantifier`
   lose their reduce-side caller.

Everything else is existing algebra (`IrBuild`, `IrPipe`, `IrJoin`, `IrArgs`,
`IrArg`, `IrCond`).

---

## Open questions / risks for review

1. **Edge cases in `IrUnradix`:** empty digit string → `acc = 0` silently
   (cannot occur for `1*HEXDIG`/`1*DIGIT`, but reachable if a wrapper is misused);
   `acc > 0x10FFFF` is accepted at decode and only fails when `IrChr.__str__`
   calls `chr()` at emit (no early guard).
2. **Self-hosting fixpoint:** restructuring `ABNF_GRAMMAR` must still reduce back
   to itself. Validated for the numeric rules in isolation; the full
   emit→parse→reduce fixpoint over the whole grammar is the real gate.
3. **`out=IrChr` vs char storage:** if Axis-2 review prefers char-preserving
   output instead of code points, `_cp` would need a glyph-collapse
   (`IrChr` → `IrStr` glyph) step; the rest is unchanged.
4. **Scope of `IrChr` introduction:** this is the first node to actually build the
   locked `IrChr`; it lands in `base.py` ahead of the full emit-side codepoint
   reshape (which stays out of scope).
