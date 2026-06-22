"""Prototype for the code-point-everywhere radix reduce (plan A).

Builds restructured grammar fragments, parses real input via
``parsing_2.engine.parse``, reduces with the proposed table, and asserts
code-point IR. The prototype classes (``IrChr``, ``IrUnradix``, ``IrQuantifier2``,
``IrRange2``, ``IrCharClass2``, ``IrItem2``) live inline: grammar fragments keep
the real ``IrCharClass``/``IrRange`` the engine scans, while the reduce *output*
uses the ``*2`` code-point classes. Docstrings are deliberately terse — this is a
throwaway demonstrator pending plan sign-off.
"""

from __future__ import annotations

from typing import ClassVar, Self, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import (
    IrArg,
    IrArgs,
    IrBuild,
    IrCond,
    IrJoin,
    IrPipe,
)
from lexic.ir.base import (
    IrAtom,
    IrInt,
    IrLeaf,
    IrNamedTuple,
    IrNone,
    IrNoneType,
    IrScalar,
    IrSelf,
    IrSeq,
    IrStr,
    IrTuple,
)
from lexic.ir.mapping import IR_DEFAULT, IrMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing_2.engine import parse
from lexic.parsing_2.normalize import normalize
from lexic.parsing_2.reduce import DROP, KEEP_REDUCED, YIELD, Reducer

# ── Prototype new nodes ───────────────────────────────────────────────


class IrChr(IrInt):
    """A code point. Build from a 1-char glyph or an int; stores the ordinal."""

    def __new__(cls, value: int | str = 0) -> Self:
        if isinstance(value, str):
            if len(value) != 1:
                msg = f"IrChr expects one glyph, got {value!r}"
                raise UnsupportedConstructError(msg)
            value = ord(value)
        return super().__new__(cls, value)

    def __str__(self) -> str:
        return chr(int(self))

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        return IrStr(chr(int(self)))


class IrUnradix(IrNamedTuple[int, type[IrScalar]]):
    """Decode a digit string (the focus ``n``) to ``out(value)`` via ord-arithmetic."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    base: int
    out: type[IrScalar] = IrInt

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrScalar:
        s = str(n)
        if not s:
            raise UnsupportedConstructError("IrUnradix: empty digit string")
        acc = 0
        for c in s:
            v = ord(c) - 0x30 if "0" <= c <= "9" else ord(c.upper()) - 0x41 + 10
            if not 0 <= v < self.base:
                raise UnsupportedConstructError(f"bad digit {c!r} for base {self.base}")
            acc = acc * self.base + v
        return self.out(acc)


class IrBounds(IrLeaf, IrNamedTuple[int, "int | IrNoneType"]):
    """Shared (lo, hi) bounds shape — type-aware eq plus in-bounds membership."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: int
    hi: int | IrNoneType

    def __eq__(self, other: object) -> bool:
        """Equal only to the same bounds subtype with equal endpoints."""
        if type(self) is not type(other):
            return False
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        """Negation of __eq__, kept consistent with the type-aware check."""
        return not self == other

    def __hash__(self) -> int:
        """Hash by endpoint tuple; cross-kind collisions are acceptable."""
        return super().__hash__()

    def __contains__(self, value: object) -> bool:
        """True when value lies within [lo, hi]; hi=IrNone ⇒ unbounded above."""
        if not isinstance(value, int):
            return False
        hi = self.hi
        if isinstance(hi, IrNoneType):
            return self.lo <= value
        return self.lo <= value <= hi


class IrQuantifier2(IrBounds):
    """Repetition bounds — int counts; hi may be IrNone (open)."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: int = 1
    hi: int | IrNoneType = 1


class IrRange2(IrBounds):
    """Char range — IrChr code-point endpoints, always closed; no defaults."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: IrChr
    hi: IrChr


class IrCharClass2(IrSeq["IrRange2 | IrChr"], IrAtom):
    """Char class over code points: IrRange2 spans and single IrChr code points."""


class IrItem2(IrNamedTuple[IrAtom, IrQuantifier2]):
    """Atom + quantifier (mirror of IrItem for the prototype)."""

    atom: IrAtom
    quantifier: IrQuantifier2


# ── repeat grammar (real IrCharClass/IrRange — the engine scans them) ──

REPEAT_GRAMMAR = IrAst(
    rules=IrSeq(
        IrRule("start", IrAlternation(IrSequence(IrItem(IrRuleRef("repeat"))))),
        IrRule(
            "repeat",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("repeat-exact"))),
                IrSequence(IrItem(IrRuleRef("repeat-range"))),
            ),
        ),
        IrRule("repeat-exact", IrAlternation(IrSequence(IrItem(IrRuleRef("decits"))))),
        IrRule(
            "repeat-range",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("lo-bound")),
                    IrItem(IrLiteral("*")),
                    IrItem(IrRuleRef("hi-bound")),
                )
            ),
        ),
        IrRule(
            "lo-bound",
            IrAlternation(IrSequence(IrItem(IrRuleRef("decits"), IrQuantifier(0, 1)))),
        ),
        IrRule(
            "hi-bound",
            IrAlternation(IrSequence(IrItem(IrRuleRef("decits"), IrQuantifier(0, 1)))),
        ),
        IrRule(
            "decits",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("DIGIT"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "DIGIT", IrAlternation(IrSequence(IrItem(IrCharClass(IrRange("0", "9")))))
        ),
    ),
    start="start",
)

# Decode bodies (module-level data, not helpers): a joined digit run, or arg 0.
_dec = IrPipe(IrJoin(IrArgs()), IrUnradix(10, IrInt))
_dec_arg0 = IrPipe(IrArg(0), IrUnradix(10, IrInt))
# Hex code points off args 0 and 1.
_cp0 = IrPipe(IrArg(0), IrUnradix(16, IrChr))
_cp1 = IrPipe(IrArg(1), IrUnradix(16, IrChr))

REPEAT_REDUCTIONS: IrMap[IrRuleRef, IrSelf] = IrMap(
    IrTuple(IrRuleRef("start"), IrArg(0)),
    IrTuple(IrRuleRef("repeat"), IrArg(0)),
    IrTuple(
        IrRuleRef("repeat-exact"), IrBuild(IrQuantifier2, IrTuple(_dec_arg0, _dec_arg0))
    ),
    IrTuple(
        IrRuleRef("repeat-range"), IrBuild(IrQuantifier2, IrTuple(IrArg(0), IrArg(1)))
    ),
    IrTuple(
        IrRuleRef("lo-bound"), IrCond(test=IrArgs(), then_op=_dec, else_op=IrInt(0))
    ),
    IrTuple(IrRuleRef("hi-bound"), IrCond(test=IrArgs(), then_op=_dec, else_op=IrNone)),
    IrTuple(IrRuleRef("decits"), IrJoin(IrArgs())),
    IrTuple(IR_DEFAULT, YIELD),
)

REPEAT_NOISE: IrMap = IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
REPEAT_REDUCER = Reducer(reductions=REPEAT_REDUCTIONS, noise=REPEAT_NOISE, literal=DROP)


# ── num-val grammar ───────────────────────────────────────────────────

NUMVAL_GRAMMAR = IrAst(
    rules=IrSeq(
        IrRule("start", IrAlternation(IrSequence(IrItem(IrRuleRef("num-val"))))),
        IrRule(
            "num-val",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("num-range"))),
                IrSequence(IrItem(IrRuleRef("num-single"))),
            ),
        ),
        IrRule(
            "num-single",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrLiteral("x")),
                    IrItem(IrRuleRef("hexits")),
                )
            ),
        ),
        IrRule(
            "num-range",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrLiteral("x")),
                    IrItem(IrRuleRef("hexits")),
                    IrItem(IrLiteral("-")),
                    IrItem(IrRuleRef("hexits")),
                )
            ),
        ),
        IrRule(
            "hexits",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("HEXDIG"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "HEXDIG",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange("0", "9")))),
                IrSequence(IrItem(IrCharClass(IrRange("A", "F")))),
            ),
        ),
    ),
    start="start",
)

NUMVAL_REDUCTIONS: IrMap[IrRuleRef, IrSelf] = IrMap(
    IrTuple(IrRuleRef("start"), IrArg(0)),
    IrTuple(IrRuleRef("num-val"), IrArg(0)),
    IrTuple(IrRuleRef("num-single"), IrBuild(IrCharClass2, IrTuple(_cp0))),
    IrTuple(
        IrRuleRef("num-range"),
        IrBuild(IrCharClass2, IrTuple(IrBuild(IrRange2, IrTuple(_cp0, _cp1)))),
    ),
    IrTuple(IrRuleRef("hexits"), IrJoin(IrArgs())),
    IrTuple(IR_DEFAULT, YIELD),
)
NUMVAL_NOISE: IrMap = IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
NUMVAL_REDUCER = Reducer(reductions=NUMVAL_REDUCTIONS, noise=NUMVAL_NOISE, literal=DROP)


# ── embedded context: repetition = repeat-opt element (element = num-val) ──
# Pure (no IrLambda): repeat-opt always lands a quantifier, so repetition is a
# positional IrBuild(IrItem2, (atom, quant)). Proves the restructure composes
# inside the real repetition combiner, not just as standalone start rules.

EMBED_GRAMMAR = IrAst(
    rules=IrSeq(
        IrRule("start", IrAlternation(IrSequence(IrItem(IrRuleRef("repetition"))))),
        IrRule(
            "repetition",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("repeat-opt")), IrItem(IrRuleRef("element"))
                )
            ),
        ),
        IrRule(
            "repeat-opt",
            IrAlternation(IrSequence(IrItem(IrRuleRef("repeat"), IrQuantifier(0, 1)))),
        ),
        IrRule("element", IrAlternation(IrSequence(IrItem(IrRuleRef("num-val"))))),
        # repeat sub-tree (from REPEAT_GRAMMAR), minus its own 'start'
        *REPEAT_GRAMMAR.rules[1:],
        # num-val sub-tree (from NUMVAL_GRAMMAR), minus dup 'start' and 'DIGIT'
        *[r for r in NUMVAL_GRAMMAR.rules if r.name not in ("start", "DIGIT")],
    ),
    start="start",
)

EMBED_REDUCTIONS: IrMap[IrRuleRef, IrSelf] = IrMap(
    IrTuple(IrRuleRef("start"), IrArg(0)),
    IrTuple(IrRuleRef("repetition"), IrBuild(IrItem2, IrTuple(IrArg(1), IrArg(0)))),
    IrTuple(
        IrRuleRef("repeat-opt"),
        IrCond(
            test=IrArgs(),
            then_op=IrArg(0),
            else_op=IrBuild(IrQuantifier2, IrTuple()),
        ),
    ),
    IrTuple(IrRuleRef("element"), IrArg(0)),
    # repeat rules (the alternation passthrough `repeat → IrArg(0)` is
    # load-bearing — without it `repeat` falls through IR_DEFAULT→YIELD to text)
    IrTuple(IrRuleRef("repeat"), IrArg(0)),
    IrTuple(
        IrRuleRef("repeat-exact"), IrBuild(IrQuantifier2, IrTuple(_dec_arg0, _dec_arg0))
    ),
    IrTuple(
        IrRuleRef("repeat-range"), IrBuild(IrQuantifier2, IrTuple(IrArg(0), IrArg(1)))
    ),
    IrTuple(
        IrRuleRef("lo-bound"), IrCond(test=IrArgs(), then_op=_dec, else_op=IrInt(0))
    ),
    IrTuple(IrRuleRef("hi-bound"), IrCond(test=IrArgs(), then_op=_dec, else_op=IrNone)),
    IrTuple(IrRuleRef("decits"), IrJoin(IrArgs())),
    # num-val rules
    IrTuple(IrRuleRef("num-val"), IrArg(0)),
    IrTuple(IrRuleRef("num-single"), IrBuild(IrCharClass2, IrTuple(_cp0))),
    IrTuple(
        IrRuleRef("num-range"),
        IrBuild(IrCharClass2, IrTuple(IrBuild(IrRange2, IrTuple(_cp0, _cp1)))),
    ),
    IrTuple(IrRuleRef("hexits"), IrJoin(IrArgs())),
    IrTuple(IR_DEFAULT, YIELD),
)
EMBED_NOISE: IrMap = IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
EMBED_REDUCER = Reducer(reductions=EMBED_REDUCTIONS, noise=EMBED_NOISE, literal=DROP)


# ── Run ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("== repeat ==")
    for text, want in {
        "5": IrQuantifier2(5, 5),
        "1*5": IrQuantifier2(1, 5),
        "*5": IrQuantifier2(0, 5),
        "5*": IrQuantifier2(5, IrNone),
        "*": IrQuantifier2(0, IrNone),
        "12*34": IrQuantifier2(12, 34),
    }.items():
        got = REPEAT_REDUCER.apply(parse(normalize(REPEAT_GRAMMAR), text))
        assert got == want, (text, got, want)
        # the base int range never coerces: a count endpoint stays int, never IrChr.
        assert isinstance(got, IrQuantifier2) and not isinstance(got[0], IrChr)
        print(f"  {text!r:8} -> {got!r}")

    print("== num-val ==")
    for text, want in {
        "%x41": IrCharClass2(IrChr(0x41)),
        "%x41-5A": IrCharClass2(IrRange2(IrChr(0x41), IrChr(0x5A))),
        "%x30-39": IrCharClass2(IrRange2(IrChr(0x30), IrChr(0x39))),
    }.items():
        got = NUMVAL_REDUCER.apply(parse(normalize(NUMVAL_GRAMMAR), text))
        assert got == want, (text, got, want)
        print(f"  {text!r:10} -> {got!r}")

    print("== embedded: repetition = repeat-opt element ==")
    for text, want in {
        "%x41": IrItem2(IrCharClass2(IrChr(0x41)), IrQuantifier2(1, 1)),
        "3%x41": IrItem2(IrCharClass2(IrChr(0x41)), IrQuantifier2(3, 3)),
        "1*2%x41-5A": IrItem2(
            IrCharClass2(IrRange2(IrChr(0x41), IrChr(0x5A))), IrQuantifier2(1, 2)
        ),
    }.items():
        got = EMBED_REDUCER.apply(parse(normalize(EMBED_GRAMMAR), text))
        assert got == want, (text, got, want)
        print(f"  {text!r:12} -> {got!r}")

    print("== IrChr glyph/int equivalence + leaf-kind distinctness ==")
    # The right way to represent IrCharClass(IrRange("A","Z")):
    assert IrCharClass2(IrRange2(IrChr("A"), IrChr("Z"))) == IrCharClass2(
        IrRange2(IrChr(0x41), IrChr(0x5A))
    )
    assert IrChr("A") == IrChr(0x41)  # glyph and ordinal are the same code point
    assert IrChr(0x41) != IrInt(0x41)  # distinct leaf kinds never compare equal
    assert IrChr(0x41) == 0x41  # but a leaf still matches its plain int
    print("  IrCharClass2(IrRange2(IrChr('A'), IrChr('Z'))) holds")

    print("== sibling bounds: disjoint kinds, type-aware eq, membership ==")
    assert not isinstance(IrRange2(IrChr(65), IrChr(90)), IrQuantifier2)
    assert not isinstance(IrQuantifier2(65, 90), IrRange2)
    # counts and code-point ranges with the same numbers never compare equal:
    assert IrQuantifier2(65, 90) != IrRange2(IrChr(65), IrChr(90))
    assert IrQuantifier2(5, 5) == IrQuantifier2(5, 5)
    assert IrRange2(IrChr("A"), IrChr("Z")) == IrRange2(IrChr(0x41), IrChr(0x5A))
    # in-bounds membership (the requested __contains__):
    assert 5 in IrQuantifier2(1, 10) and 11 not in IrQuantifier2(1, 10)
    assert 100 in IrQuantifier2(1, IrNone)  # open upper bound
    assert IrChr(0x42) in IrRange2(IrChr(0x41), IrChr(0x5A))
    assert IrChr(0x60) not in IrRange2(IrChr(0x41), IrChr(0x5A))
    print("  isinstance disjoint; eq type-aware; membership respects bounds")

    print("== IrRange2 requires endpoints (no NUL placeholder) ==")
    no_args: list[IrChr] = []
    try:
        IrRange2(*no_args)
        raise AssertionError("expected required-field error")
    except TypeError as exc:
        print(f"  raises -> {exc}")

    print("== IrChr rejects multi-char glyphs ==")
    try:
        IrChr("AB")
        raise AssertionError("expected glyph-length guard to raise")
    except UnsupportedConstructError as exc:
        print(f"  raises -> {exc}")

    print("== IrUnradix empty-string guard ==")
    try:
        IrUnradix(10, IrInt).eval(IrNone, IrStr(""), ())
        raise AssertionError("expected empty-string guard to raise")
    except UnsupportedConstructError as exc:
        print(f"  raises -> {exc}")

    print("\nALL PASS")
