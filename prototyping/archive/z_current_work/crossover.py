"""Apples-to-apples crossover: left vs right `*` desugaring, ONE process.

Builds the normalized shapes of `S = unit*` by hand (no normalize edit, no
cross-run noise) and times recognize at small N (suite-like) and large N, for a
TERMINAL unit and a NON-TERMINAL (ruleref) unit.

  right:  S = R ;  R = "" / unit R     (current)
  left:   S = R ;  R = "" / R unit     (F1)

R is nullable in both, so predicting R fires the Aycock-Horspool branch; the
left shape self-predicts R, firing that expensive branch more often per element.
"""

from __future__ import annotations

import gc
import statistics
import time

from lexic.ir.base import IrSeq, IrStr, IrTuple
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing_2.engine import RECOGNIZE, EarleyParser

PARSER = EarleyParser()
A = IrItem(IrLiteral("a"))
R = IrItem(IrRuleRef("R"))
U = IrItem(IrRuleRef("U"))


def grammar(left: bool, nonterminal: bool) -> IrAst:
    unit = U if nonterminal else A
    rec = IrSequence(R, unit) if left else IrSequence(unit, R)
    rrule = IrRule("R", IrAlternation(IrSequence(), rec))  # "" / (unit R | R unit)
    srule = IrRule("S", IrAlternation(IrSequence(R)))
    rules = [srule, rrule]
    if nonterminal:
        rules.append(IrRule("U", IrAlternation(IrSequence(A))))  # U = a
    return IrAst(rules=IrSeq(*rules), start="S")


RIGHT = grammar(left=False, nonterminal=False)
LEFT = grammar(left=True, nonterminal=False)
RIGHT_NT = grammar(left=False, nonterminal=True)
LEFT_NT = grammar(left=True, nonterminal=True)


def best(grammar: IrAst, text: str, iters: int) -> float:
    samples = []
    nc = IrTuple(IrStr(text))
    for _ in range(iters):
        gc.disable()
        t0 = time.perf_counter()
        RECOGNIZE.eval(PARSER, grammar, nc)
        samples.append(time.perf_counter() - t0)
        gc.enable()
    return statistics.median(samples) * 1e6  # microseconds


def table(title: str, right: IrAst, left: IrAst) -> None:
    print(f"\n== {title} ==")
    print(f"{'N':>6} {'right(us)':>12} {'left(us)':>12} {'left/right':>11}")
    for n, iters in ((0, 6000), (1, 6000), (2, 5000), (3, 5000), (4, 4000), (8, 3000)):
        text = "a" * n
        r = min(best(right, text, iters), best(right, text, iters))
        ln = min(best(left, text, iters), best(left, text, iters))
        print(f"{n:>6} {r:>12.2f} {ln:>12.2f} {ln / r:>10.2f}x")


def main() -> None:
    table("TERMINAL unit  (R = unit R | R unit, unit = 'a')", RIGHT, LEFT)
    table("NON-TERMINAL unit  (unit = U, U = 'a')", RIGHT_NT, LEFT_NT)


if __name__ == "__main__":
    main()
