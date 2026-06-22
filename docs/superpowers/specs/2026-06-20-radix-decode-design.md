# Design — radix decode in the ABNF reduce (task B), code-point model

**Date:** 2026-06-20 (revised 2026-06-22: code-point-everywhere model; sibling
`IrBounds` base replacing the earlier `IrRange(IrQuantifier)` hierarchy flip)
**Scope:** the reduce direction — replace the two procedural calls
`ABNF_FLAVOUR.parse_charclass` / `parse_quantifier` (in `grammars/abnf_2.py`'s
`_num_val` / `_repeat`) with pure `IrSelf` algebra, removing the last `IrLambda`s
from the numeric reductions, **and** move char-class/range storage to code
points. This is item **B** of the
`2026-06-18-flavour-2-reduce-handover.md`, now folded together with the
(previously deferred) code-point storage reshape — "plan A, one plan."

**Status:** the class shapes and the reduce algebra are validated on *shadow
classes* against a real `normalize → parse → reduce` (`_validate_radix.py`: all
cases pass; pyright 0 errors; pylint 10/10). That validates the **IR shapes and
the reduce table only** — *not* the full migration: the real `nodes.py` reshape,
the consumer ladders (`derive` / `codegen` / `generate` / `base`),
`model_emitter` emission, the self-hosting fixpoint, and the GBNF char-class move
are **not yet exercised** (see §Open risks). The doc supersedes the earlier
*char-preserving / `IrGlyph`* design **and** the *`IrRange(IrQuantifier)` flip* —
see §Superseded.

---

## Decided constraints (not re-opened)

- **No `IrCallable`, no `IrLambda`** in the final numeric reductions — including
  `_repetition`, which is now pure (see §Reduce table).
- **A character is a code point everywhere it appears in a char class or range.**
  `IrRange` holds `IrChr` endpoints; `IrCharClass` holds `IrRange | IrChr`;
  `IrQuantifier` holds plain `int` counts. `IrLiteral` stays `IrStr` (string
  literals are not char classes). Spelling (code point → glyph / `%x` / escape)
  happens **only at emit time, per flavour**.
- **`IrQuantifier` and `IrRange` are siblings** under a new abstract `IrBounds`
  base (the shared `(lo, hi)` shape) — neither is-a the other. `IrBounds` hosts
  type-aware `__eq__` / `__ne__` / `__hash__` (a count range and a code-point
  range with the same numbers never compare equal) and `__contains__`
  (`lo <= value <= hi`, `hi=IrNone` ⇒ unbounded above). `IrQuantifier` carries
  int defaults `(1,1)`; `IrRange` carries **required** `IrChr` endpoints — no
  placeholder default. See §The bounds hierarchy.
- **`IrChr`** is a value-carrying `IrInt` subtype: the node IS the code point.
  It is constructible from a 1-char glyph *or* an int (`IrChr("A") == IrChr(0x41)`),
  storing the ordinal; `__str__` → `chr(self)` (the glyph), `eval` →
  `IrStr(chr(self))`. The glyph→code-point conversion lives **in `IrChr`** —
  nowhere else. A multi-char glyph raises `UnsupportedConstructError` (never a
  bare `ord()` `TypeError`). Lives in `ir/base.py`.
- The decided **emit** primitive `IrRadix(base, width)` does the inverse
  (code point → digit string) with hand ord-arithmetic — no `int(s,base)`,
  `format`, table, or `match`.
- **THE ONE PRINCIPLE:** radix (code point ⇄ digit spelling) and escaping
  (special char ⇄ safe form) are orthogonal, composed at the site, never fused.

---

## The bounds hierarchy: `IrQuantifier` and `IrRange` are siblings

`IrQuantifier` and `IrRange` share the `(lo, hi)` shape but **neither is
substitutable for the other** — a char range is not a repetition count, and a
count is not a char span. Shared shape is a reason for a common *base*, not for
one to inherit the other. So:

```
IrBounds          # abstract: the (lo, hi) shape; hosts __eq__/__ne__/__hash__, __contains__
  ├─ IrQuantifier # int counts; lo/hi: int, hi may be IrNone (open); defaults (1,1)
  └─ IrRange      # char span; lo/hi: IrChr code points, always closed; required (no defaults)
```

**Why a sibling base, not either inheritance direction.**

- **`IrRange(IrQuantifier)` (the rejected flip)** would make a char range an
  `IrQuantifier`, so it could flow into any `IrQuantifier` slot (e.g.
  `IrItem.quantifier`). Field-variance is locally sound but answers the wrong
  question: substitutability is exactly what must *not* hold here. It also forced
  a placeholder `IrChr()` (NUL) default on `IrRange` to satisfy the dataclass
  override rule — a silent-wrong footgun.
- **`IrQuantifier(IrRange)` (today's shape)** is worse: it makes `IrRange` the
  base and reintroduces the context-dependent `str`-or-`int` endpoint payload the
  code-point model exists to remove.
- **Siblings under `IrBounds`** make `isinstance(x, IrQuantifier)` and
  `isinstance(x, IrRange)` **disjoint** — the mis-dispatch risk disappears at the
  root rather than relying on every consumer migrating in lockstep — and let
  `IrRange` declare **required** `IrChr` endpoints, so no NUL placeholder can
  ever be constructed.

**`IrBounds` carries the dunders** the shared shape needs:

```python
class IrBounds(IrLeaf, IrNamedTuple[int, "int | IrNoneType"]):
    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: int
    hi: int | IrNoneType

    def __eq__(self, other: object) -> bool:        # type-aware: distinct kinds never equal
        if type(self) is not type(other):
            return False
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:        # tuple supplies its own __ne__ — must override
        return not self == other

    def __hash__(self) -> int:                       # __eq__ nulls __hash__ — restore tuple's
        return super().__hash__()

    def __contains__(self, value: object) -> bool:   # lo <= value <= hi; IrNone hi = unbounded
        if not isinstance(value, int):
            return False
        hi = self.hi
        if isinstance(hi, IrNoneType):
            return self.lo <= value
        return self.lo <= value <= hi
```

`IrBounds` overrides `tuple`'s native `__eq__`/`__ne__`/`__hash__` because the
plain tuple versions compare endpoints element-wise and **ignore the leaf-kind
guard** — without this, `IrQuantifier(65, 90) == IrRange(IrChr(65), IrChr(90))`
would be true (a count silently equal to a code-point span). `__ne__` and
`__hash__` are load-bearing, not redundant: `tuple.__ne__ is not object.__ne__`
(so the "default `__ne__` delegates to `__eq__`" rule does not apply), and
defining `__eq__` sets `__hash__ = None`. This mirrors `IrScalar`'s own
`__eq__`/`__ne__`/`__hash__` for `str`/`int`.

**No coercion node, no `_coerce` flag, no `__new__` override on `IrRange`.**
Endpoints are `IrChr` by construction. The reduce produces `IrChr` directly (via
`IrUnradix(16, IrChr)`); hand-authored ranges write `IrRange(IrChr("A"),
IrChr("Z"))`. Both are `IrChr`, so they compare equal with no normalization pass.

---

## The two new action/value nodes

### `IrChr` (`ir/base.py`)

```python
class IrChr(IrInt):
    """A code point. Build from a 1-char glyph or an int; stores the ordinal."""

    def __new__(cls, value: int | str = 0) -> Self:
        if isinstance(value, str):
            if len(value) != 1:                       # explicit guard, not a bare ord() TypeError
                msg = f"IrChr expects one glyph, got {value!r}"
                raise UnsupportedConstructError(msg)
            value = ord(value)
        return super().__new__(cls, value)

    def __str__(self) -> str:
        return chr(int(self))

    def eval(self, _d, _n, _nc, /) -> IrStr:
        return IrStr(chr(int(self)))
```

`__repr__` is inherited from `IrScalar` (codegen): `repr(IrChr(65)) == "IrChr(65)"`
while `str(IrChr(65)) == "A"`. That split is intended — repr is codegen, str is the
glyph. Because `IrChr` is now **stored** in `IrRange`/`IrCharClass`, it reaches
`RuleSpec` reprs, so **`codegen/model_emitter.py`'s import block must add
`IrChr`.** (This reverses the earlier draft's "never stored, no import change.")

Equality (inherited from `IrScalar`, type-aware on *exact* type): `IrChr(65) ==
IrChr(65)`, `IrChr(65) == 0x41` (matches plain int), but `IrChr(65) != IrInt(65)`
(distinct leaf kinds never compare equal). This is what makes the storage model
honest: a code-point endpoint never silently equals a plain count.

### `IrUnradix(base, out)` (`ir/action.py`)

A record-leaf transform, the inverse of emit `IrRadix`:

```python
class IrUnradix(IrNamedTuple[int, type[IrScalar]]):
    """Decode the focus digit string to out(value) via ord-arithmetic."""
    _child_attrs = ()
    base: int                    # 2 / 10 / 16, scalar payload (per flavour token)
    out: type[IrScalar] = IrInt  # IrChr for code points, IrInt for counts

    def eval(self, _d, n, _nc, /) -> IrScalar:
        s = str(n)
        if not s:                # explicit guard (CLAUDE.md: no silent dispatch path)
            raise UnsupportedConstructError("IrUnradix: empty digit string")
        acc = 0
        for c in s:
            v = ord(c) - 0x30 if "0" <= c <= "9" else ord(c.upper()) - 0x41 + 10
            if not 0 <= v < self.base:
                raise UnsupportedConstructError(f"bad digit {c!r} for base {self.base}")
            acc = acc * self.base + v
        return self.out(acc)
```

- `out` is open, same pattern as `IrField.out` — a new scalar type needs no
  change here. It **reads its focus** `n`, so it composes as
  `IrPipe(<digit source>, IrUnradix(base, out))`.
- `base` is static payload (ABNF is hex/decimal). A future `%d`/`%b` set could
  read `base` off the node; out of scope here.

**No `IrGlyph`.** The earlier design needed it to collapse a decoded code point
back to a stored glyph (char-preserving). With code-point storage, the decode's
`IrChr` *is* the stored value — `IrGlyph` is deleted from the plan entirely.

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
repeat-opt   = [repeat]          ; empty ⇒ a built IrQuantifier() default (1,1)
```

Splitting `num-val` and `repeat` into named arms kills the `5` vs `5*` vs `*5`
ambiguity — the discriminator is the **rule name** the reducer dispatches on, not
the dropped `*`. Wrapping each optional bound in a named rule guarantees the
slot materialises in the parent even when the bound matched empty (see Mechanism).

This is parse-side only; emit is unaffected. The ABNF self-hosting fixpoint must
be re-closed after the change (these rules describe ABNF's own syntax), and any
**hand-authored** char ranges in `ABNF_GRAMMAR` move from glyph strings
(`IrRange("A","Z")`) to code points (`IrRange(IrChr("A"), IrChr("Z"))`). The
*parser's* output is already code points; only hand-authored IR is re-spelled.

---

## Reduce table

Every body builds a final type. `IrUnradix` decodes one clean digit string per
slot. (`IrJoin(IrArgs())` is the established "join the children" body.)

```python
# hex code points off args 0 and 1; joined decimal count.
_cp0 = IrPipe(IrArg(0), IrUnradix(16, IrChr))
_cp1 = IrPipe(IrArg(1), IrUnradix(16, IrChr))
_dec = IrPipe(IrJoin(IrArgs()), IrUnradix(10, IrInt))

# digit-run rules: join scattered single-char args into one string
IrTuple(IrRuleRef("hexits"), IrJoin(IrArgs())),          # ("4","1") → "41"
IrTuple(IrRuleRef("decits"), IrJoin(IrArgs())),          # ("5",)    → "5"

# alternation passthroughs — LOAD-BEARING. Without these, `repeat`/`num-val`
# fall through IR_DEFAULT→YIELD and reduce to TEXT, not the built node.
IrTuple(IrRuleRef("repeat"), IrArg(0)),
IrTuple(IrRuleRef("num-val"), IrArg(0)),

# num-val → IrCharClass over code points (IrChr endpoints)
IrTuple(IrRuleRef("num-single"), IrBuild(IrCharClass, IrTuple(_cp0))),
IrTuple(IrRuleRef("num-range"),
    IrBuild(IrCharClass, IrTuple(IrBuild(IrRange, IrTuple(_cp0, _cp1))))),

# repeat → IrQuantifier (int counts)
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
# (constructed in-branch — never a pre-built composite; IrCond evals the chosen branch)
IrTuple(IrRuleRef("repeat-opt"),
    IrCond(test=IrArgs(), then_op=IrArg(0), else_op=IrBuild(IrQuantifier, IrTuple()))),
IrTuple(IrRuleRef("repetition"),
    IrBuild(IrItem, IrTuple(IrArg(1), IrArg(0)))),   # (atom, quant); repeat-opt is child 0
```

`IrQuantifier(lo, hi)` is built by `repeat-range`; the lo/hi bound rules supply
the `IrInt(0)` / `IrNone` defaults. `_repetition` is pure: `repeat-opt` always
lands a quantifier (decoded or the `(1,1)` default), so `repetition` is a plain
positional `IrBuild(IrItem, (atom, quant))`.

**Decoded endpoints are `IrInt` leaves.** `IrUnradix(10, IrInt)` yields `IrInt`,
so a decoded `IrQuantifier` actually reads `IrQuantifier(IrInt(5), IrInt(5))`,
while a default `(1,1)` (built from `IrTuple()`) reads `IrQuantifier(1, 1)` (plain
int). The two forms compare equal via the leaf-kind-aware `IrScalar.__eq__`
(`IrInt(5) == 5`), so round-trip equality holds. The validation tables below use
the plain-int shorthand `IrQuantifier(5, 5)` for readability.

---

## Mechanism: how empty bounds work (verified)

`[decits]` desugars (in `normalize.py`) to `lo-bound = __opt = "" / decits`. When
the optional matches empty, `__opt` (a synthetic `__`-prefixed rule) takes the
empty arm. `RESOLVE_CHILDREN` splices synthetic children, so an empty `__opt`
contributes nothing — `lo-bound`'s `nc` is empty. But `lo-bound` itself is a
**real** rule, so it always appears as a child of `repeat-range` and always
reduces. Its body `IrCond(test=IrArgs(), ...)` reads the empty `nc` as falsy and
yields the default. The named wrapper is what guarantees the slot.

---

## Empirical validation (`_validate_radix.py`)

Real `normalize` → `parse` → `Reducer.apply`. `IrChr`/`IrUnradix` build on the
**real** bases (`IrInt`/`IrNamedTuple`); `IrBounds` is prototyped inline (it is
new — no real counterpart yet), and `IrQuantifier2`/`IrRange2` are its two shadow
subclasses (`*2` only ever shadows an existing real class — `IrBounds` keeps its
plain name). `IrCharClass2`/`IrItem2` shadow the real collection/record. **All
cases pass with structural `==`; pyright 0 errors; pylint 10/10.**

| input | reduced | input | reduced |
|---|---|---|---|
| `5` | `IrQuantifier(5,5)` | `%x41` | `IrCharClass(IrChr(65))` |
| `1*5` | `IrQuantifier(1,5)` | `%x41-5A` | `IrCharClass(IrRange(IrChr(65),IrChr(90)))` |
| `*5` | `IrQuantifier(0,5)` | `%x30-39` | `IrCharClass(IrRange(IrChr(48),IrChr(57)))` |
| `5*` | `IrQuantifier(5,∞)` | | |
| `*` | `IrQuantifier(0,∞)` | | |
| `12*34` | `IrQuantifier(12,34)` | | |

**Embedded context** (`repetition = repeat-opt element`, `element = num-val` — the
real combiner shape):

| input | reduced |
|---|---|
| `%x41` | `IrItem(IrCharClass(IrChr(65)), IrQuantifier(1,1))` |
| `3%x41` | `IrItem(IrCharClass(IrChr(65)), IrQuantifier(3,3))` |
| `1*2%x41-5A` | `IrItem(IrCharClass(IrRange(IrChr(65),IrChr(90))), IrQuantifier(1,2))` |

**Equality / sibling / membership / guard probes:**

- `IrCharClass(IrRange(IrChr("A"),IrChr("Z"))) == IrCharClass(IrRange(IrChr(0x41),
  IrChr(0x5A)))` (glyph and ordinal construct the same code point); `IrChr(0x41)
  == 0x41`; `IrChr(0x41) != IrInt(0x41)` (distinct leaf kinds).
- **Sibling disjointness:** `not isinstance(IrRange(...), IrQuantifier)` and
  `not isinstance(IrQuantifier(...), IrRange)`.
- **Type-aware bounds equality:** `IrQuantifier(65, 90) != IrRange(IrChr(65),
  IrChr(90))` (a count and a same-numbered code-point span never compare equal —
  the gap the plain tuple `__eq__` would leave open).
- **Membership:** `5 in IrQuantifier(1, 10)`, `100 in IrQuantifier(1, IrNone)`
  (open upper bound), `IrChr(0x42) in IrRange(IrChr(0x41), IrChr(0x5A))`.
- **No NUL placeholder:** `IrRange()` raises (`missing required field 'lo'`).
- **Guards:** `IrChr("AB")` and `IrUnradix` on an empty digit string both raise
  `UnsupportedConstructError`.

`_validate_radix.py` is kept as a regression artifact.

---

## What's new / changes, in total

1. `IrChr` — `ir/base.py` (value-carrying code point; glyph↔ordinal in `__new__`
   with a multi-char guard raising `UnsupportedConstructError`; `__str__` /
   `eval` → glyph `IrStr`).
2. `IrUnradix(base, out)` — `ir/action.py` (radix-decode transform).
3. **Sibling bounds base:** new abstract `IrBounds` (the shared `(lo, hi)` shape)
   in `ir/nodes.py`; `IrQuantifier` and `IrRange` both inherit it, neither the
   other (replaces today's `class IrQuantifier(IrRange)`). `IrBounds` hosts
   type-aware `__eq__` / `__ne__` / `__hash__` and `__contains__`. `IrQuantifier`
   keeps int defaults `(1,1)`; `IrRange` declares **required** `IrChr` endpoints
   (no placeholder default). `isinstance` on the two becomes disjoint.
4. `IrCharClass` element type → `IrRange | IrChr` (was `IrRange | IrStr`).
5. Grammar: `ABNF_GRAMMAR` numeric rules restructured; hand-authored char ranges
   re-spelled to code points; re-close the self-hosting fixpoint.
6. `ABNF_REDUCTIONS`: replace `_num_val`/`_repeat`/`_repetition` `IrLambda`s with
   the pure bodies above (plus the `repeat`/`num-val` passthroughs); delete all
   three functions; `parse_charclass`/`parse_quantifier` lose their reduce-side
   caller.
7. `codegen/model_emitter.py` import block += `IrChr` (now stored, reaches reprs).
8. Emit side (follow-on, same plan): `IrRadix` spells code points back to
   digits/glyphs/escapes per flavour; **GBNF** char-class parsing must also
   produce code points, else `IrCharClass` is origin-polymorphic across flavours.

Everything else is existing algebra (`IrBuild`, `IrPipe`, `IrJoin`, `IrArgs`,
`IrArg`, `IrCond`).

---

## Superseded (the earlier char-preserving design)

The 2026-06-20 draft chose **char-preserving** storage (`IrStr` glyph endpoints)
via an `IrChr → IrGlyph` collapse, to keep the fixpoint holding without touching
storage. That is replaced because:

- It left `IrRange` payload context-dependent (`str` for chars, `int` for
  counts) — not consistent.
- It required a throwaway `IrGlyph` node built only to be deleted later.
- It was only cross-flavour-consistent by accident (both flavours emit glyphs);
  any partial migration broke that.

The code-point model removes `IrGlyph`, makes `IrRange` uniformly int-rooted, and
puts glyph spelling at emit time. Cost paid up front (vs deferred): the fixpoint
re-close, `model_emitter` import, GBNF char-class migration, and hand-authored
grammar re-spelling.

### Superseded (the `IrRange(IrQuantifier)` hierarchy flip)

The 2026-06-22 first revision chose to **flip** the inheritance to
`class IrRange(IrQuantifier)`, defended as the "Liskov-correct" direction via
covariant narrowing of read-only endpoints. Adversarial review replaced it with
the sibling `IrBounds` base because:

- **The substitutability the flip grants is exactly what must not hold.** An
  `IrRange` becomes an `IrQuantifier`, so a char range can flow into any
  quantifier slot (`IrItem.quantifier`). Field variance is sound but answers the
  wrong question — a char range is semantically not a repetition count.
- **It left equality dishonest.** `IrRange`/`IrQuantifier` are tuple subclasses;
  native `tuple.__eq__` compares endpoints element-wise and ignores leaf kind, so
  `IrQuantifier(65, 90) == IrRange(IrChr(65), IrChr(90))` was true. The sibling
  base's type-aware `__eq__`/`__ne__`/`__hash__` close this.
- **It needed a NUL placeholder default** (`IrChr()`) on `IrRange.lo/hi` to
  satisfy the dataclass override rule — a silent-wrong value. Siblings let
  `IrRange` declare required endpoints, removing the footgun.
- **It left mis-dispatch to implementation vigilance.** Siblings make
  `isinstance(x, IrQuantifier)` and `isinstance(x, IrRange)` disjoint, fixing it
  at the root.

---

## Open risks / to verify during implementation

- **Self-hosting fixpoint.** Not yet run against the *real* wiring: the full
  emit→parse→reduce fixpoint over the whole restructured `ABNF_GRAMMAR`
  (`test_self_hosting_fixpoint` + `_idempotent`). Run first after wiring; a red
  localizes the offending rule.
- **Cross-flavour consistency.** ABNF and GBNF char classes must *both* reduce to
  code points, or `IrCharClass` holds `IrChr` from one and `IrStr` from the other.
  GBNF migration is in-scope for "one plan."
- **`acc > 0x10FFFF`** only fails at emit-time `chr()`. Left unguarded: ABNF `%x`
  values are code points by definition; a decode-time cap would be arbitrary policy.
- **Consumer ladders (the largest unvalidated surface).** The shadow-class
  prototype exercises no real consumer. After the `nodes.py` reshape, audit every
  `isinstance(_, IrRange)` / `isinstance(_, IrQuantifier)` and
  `== IrQuantifier(1, 1)` site in `derive` / `codegen` / `generate` / `base` /
  `parsing_2` / `grammars`. The sibling base makes the two `isinstance` sets
  disjoint (so `abnf_2.py`'s `isinstance(c, IrQuantifier)` quantifier-pick is
  correct *by construction*), but the equality sites must still hold under the
  new type-aware bounds `__eq__`. Known scan from review: `parsing_2/engine.py`
  and `utils/charclass.py` scan `IrCharClass` members (stay correct);
  `abnf_2.py:323` is removed by item 6.
- **`IrChr` glyph payload at emit.** `IrCharClass` element payloads shift from raw
  `IrStr` escape-units to `IrChr` glyphs; confirm `_escape_class_text` / the
  flavour char-class renderers re-escape from glyphs correctly (a behaviour shift
  the prototype does not cover).
- **Test ports.** `test_abnf_2.py` num-val/repeat assertions change (rule set +
  bodies change); char-class tests change `IrStr` endpoints → `IrChr`.
