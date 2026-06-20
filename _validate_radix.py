"""Throwaway validation for the Option-4-restart radix reduce design.

Builds the restructured grammar fragments as real IrAst, parses real input via
parsing_2.engine.parse, reduces with the proposed reduction table, and asserts
the final IrQuantifier / IrCharClass. IrChr + IrUnradix are prototyped inline.
"""

from __future__ import annotations

from typing import ClassVar, Sequence

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
    IrLambda,
    IrNamedTuple,
    IrNone,
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
    """Value-carrying code point; glyph is its str form."""

    def __str__(self) -> str:
        return chr(int(self))

    def eval(self, _d, _n, _nc, /):
        return IrStr(chr(int(self)))


class IrUnradix(IrNamedTuple[int, type]):
    """Decode a digit string (the focus n) to out(value) via ord-arithmetic."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    base: int
    out: type = IrInt

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /):
        s = str(n)
        if not s:
            raise ValueError("IrUnradix: empty digit string")
        acc = 0
        for c in s:
            v = ord(c) - 0x30 if "0" <= c <= "9" else ord(c.upper()) - 0x41 + 10
            if not (0 <= v < self.base):
                raise ValueError(f"bad digit {c!r} for base {self.base}")
            acc = acc * self.base + v
        return self.out(acc)


# ── Shared rule fragments ─────────────────────────────────────────────


def _digit_rule() -> IrRule:
    return IrRule(
        "DIGIT", IrAlternation(IrSequence(IrItem(IrCharClass(IrRange("0", "9")))))
    )


def _hexdig_rule() -> IrRule:
    # subset: 0-9 plus A-F (single ranges so the engine scans them)
    return IrRule(
        "HEXDIG",
        IrAlternation(
            IrSequence(IrItem(IrCharClass(IrRange("0", "9")))),
            IrSequence(IrItem(IrCharClass(IrRange("A", "F")))),
        ),
    )


# ── repeat grammar ────────────────────────────────────────────────────

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
        _digit_rule(),
    ),
    start="start",
)

_dec = IrPipe(IrJoin(IrArgs()), IrUnradix(10, IrInt))
_dec_arg0 = IrPipe(IrArg(0), IrUnradix(10, IrInt))

REPEAT_REDUCTIONS = IrMap(
    IrTuple(IrRuleRef("start"), IrArg(0)),
    IrTuple(IrRuleRef("repeat"), IrArg(0)),
    IrTuple(
        IrRuleRef("repeat-exact"), IrBuild(IrQuantifier, IrTuple(_dec_arg0, _dec_arg0))
    ),
    IrTuple(
        IrRuleRef("repeat-range"), IrBuild(IrQuantifier, IrTuple(IrArg(0), IrArg(1)))
    ),
    IrTuple(
        IrRuleRef("lo-bound"), IrCond(test=IrArgs(), then_op=_dec, else_op=IrInt(0))
    ),
    IrTuple(IrRuleRef("hi-bound"), IrCond(test=IrArgs(), then_op=_dec, else_op=IrNone)),
    IrTuple(IrRuleRef("decits"), IrJoin(IrArgs())),
    IrTuple(IR_DEFAULT, YIELD),
)

REPEAT_NOISE = IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
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
        _hexdig_rule(),
    ),
    start="start",
)


def _cp(i: int) -> IrPipe:
    """Return a pipe that unradixes its argument"""
    return IrPipe(IrArg(i), IrUnradix(16, IrChr))


NUMVAL_REDUCTIONS = IrMap(
    IrTuple(IrRuleRef("start"), IrArg(0)),
    IrTuple(IrRuleRef("num-val"), IrArg(0)),
    IrTuple(IrRuleRef("num-single"), IrBuild(IrCharClass, IrTuple(_cp(0)))),
    IrTuple(
        IrRuleRef("num-range"),
        IrBuild(IrCharClass, IrTuple(IrBuild(IrRange, IrTuple(_cp(0), _cp(1))))),
    ),
    IrTuple(IrRuleRef("hexits"), IrJoin(IrArgs())),
    IrTuple(IR_DEFAULT, YIELD),
)
NUMVAL_NOISE = IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
NUMVAL_REDUCER = Reducer(reductions=NUMVAL_REDUCTIONS, noise=NUMVAL_NOISE, literal=DROP)


# ── embedded context: repetition = repeat? element (element = num-val) ──
# Proves the restructure composes when num-val/repeat sit inside the real
# repetition combiner, not just as standalone start rules.


def _repetition(_d, _n, nc):
    """The existing combiner: pick atom + quantifier by type from clean nc."""
    atom = next(c for c in nc if isinstance(c, IrAtom))
    quant = next((c for c in nc if isinstance(c, IrQuantifier)), IrQuantifier())
    return IrItem(atom, quant)


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
        # repeat sub-tree (from REPEAT_GRAMMAR)
        *REPEAT_GRAMMAR.rules[1:],  # drop its own 'start'
        # num-val sub-tree (from NUMVAL_GRAMMAR), minus dup 'start' and 'DIGIT/HEXDIG'
        *[r for r in NUMVAL_GRAMMAR.rules if r.name not in ("start", "DIGIT")],
    ),
    start="start",
)

EMBED_REDUCTIONS = IrMap(
    IrTuple(IrRuleRef("start"), IrArg(0)),
    IrTuple(IrRuleRef("repetition"), IrLambda(_repetition)),
    IrTuple(
        IrRuleRef("repeat-opt"),
        IrCond(test=IrArgs(), then_op=IrArg(0), else_op=IrNone),
    ),
    IrTuple(IrRuleRef("element"), IrArg(0)),
    # repeat rules (NOTE: the alternation passthrough `repeat → IrArg(0)` is
    # load-bearing — without it `repeat` falls through IR_DEFAULT→YIELD to text)
    IrTuple(IrRuleRef("repeat"), IrArg(0)),
    IrTuple(
        IrRuleRef("repeat-exact"), IrBuild(IrQuantifier, IrTuple(_dec_arg0, _dec_arg0))
    ),
    IrTuple(
        IrRuleRef("repeat-range"), IrBuild(IrQuantifier, IrTuple(IrArg(0), IrArg(1)))
    ),
    IrTuple(
        IrRuleRef("lo-bound"), IrCond(test=IrArgs(), then_op=_dec, else_op=IrInt(0))
    ),
    IrTuple(IrRuleRef("hi-bound"), IrCond(test=IrArgs(), then_op=_dec, else_op=IrNone)),
    IrTuple(IrRuleRef("decits"), IrJoin(IrArgs())),
    # num-val rules
    IrTuple(IrRuleRef("num-val"), IrArg(0)),
    IrTuple(IrRuleRef("num-single"), IrBuild(IrCharClass, IrTuple(_cp(0)))),
    IrTuple(
        IrRuleRef("num-range"),
        IrBuild(IrCharClass, IrTuple(IrBuild(IrRange, IrTuple(_cp(0), _cp(1))))),
    ),
    IrTuple(IrRuleRef("hexits"), IrJoin(IrArgs())),
    IrTuple(IR_DEFAULT, YIELD),
)
EMBED_NOISE = IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
EMBED_REDUCER = Reducer(reductions=EMBED_REDUCTIONS, noise=EMBED_NOISE, literal=DROP)


# ── Run ───────────────────────────────────────────────────────────────


def red(reducer, grammar, text):
    return reducer.apply(parse(normalize(grammar), text))


def main() -> None:
    repeat_cases = {
        "5": IrQuantifier(5, 5),
        "1*5": IrQuantifier(1, 5),
        "*5": IrQuantifier(0, 5),
        "5*": IrQuantifier(5, IrNone),
        "*": IrQuantifier(0, IrNone),
        "12*34": IrQuantifier(12, 34),
    }
    print("== repeat ==")
    for text, want in repeat_cases.items():
        got = red(REPEAT_REDUCER, REPEAT_GRAMMAR, text)
        ok = got == want
        print(f"  {text!r:8} -> {got!r:32} want {want!r:32} {'OK' if ok else 'FAIL'}")
        assert ok, (text, got, want)

    numval_cases = {
        "%x41": IrCharClass(IrChr(0x41)),
        "%x41-5A": IrCharClass(IrRange(IrChr(0x41), IrChr(0x5A))),
        "%x30-39": IrCharClass(IrRange(IrChr(0x30), IrChr(0x39))),
    }
    print("== num-val ==")
    for text, want in numval_cases.items():
        got = red(NUMVAL_REDUCER, NUMVAL_GRAMMAR, text)
        ok = got == want  # real structural equality (prototype IrChr ⊂ real IrInt)
        print(f"  {text!r:10} -> {got!r:40} {'OK' if ok else 'FAIL'}")
        assert ok, (text, got, want)

    embed_cases = {
        "%x41": IrItem(IrCharClass(IrChr(0x41)), IrQuantifier(1, 1)),
        "3%x41": IrItem(IrCharClass(IrChr(0x41)), IrQuantifier(3, 3)),
        "1*2%x41-5A": IrItem(
            IrCharClass(IrRange(IrChr(0x41), IrChr(0x5A))), IrQuantifier(1, 2)
        ),
    }
    print("== embedded: repetition = repeat? element ==")
    for text, want in embed_cases.items():
        got = red(EMBED_REDUCER, EMBED_GRAMMAR, text)
        ok = got == want
        print(f"  {text!r:12} -> {got!r:52} {'OK' if ok else 'FAIL'}")
        assert ok, (text, got, want)

    print("== IrUnradix empty-string guard ==")
    try:
        IrUnradix(10, IrInt).eval(None, IrStr(""), ())
        raise AssertionError("expected empty-string guard to raise")
    except ValueError as exc:
        print(f"  raises -> {exc}")

    print("\nALL PASS")


if __name__ == "__main__":
    main()
