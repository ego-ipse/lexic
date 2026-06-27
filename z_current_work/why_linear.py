"""Why does left-recursion (F1) carry a higher LINEAR coefficient than right?

Builds the rep grammar in BOTH shapes (already Earley-normalised: single-char
terminal, (1,1) quantifiers, no groups), runs the real Earley driver, and counts
per-column items + total links + a per-op tally. Reports the marginal cost per
input element so the extra linear term is visible, not the asymptotics.

  right:  list = elem list / elem     (current)
  left:   list = list elem / elem     (F1)
"""

from __future__ import annotations

from lexic.ir.base import IrSeq, IrStr, IrTuple
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing_2.engine import BUILD_CHART, EarleyParser

PARSER = EarleyParser()

ELEM = IrRule(
    "elem",
    IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
)


def right_grammar() -> IrAst:
    rule = IrRule(
        "list",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("elem")), IrItem(IrRuleRef("list"))),
            IrSequence(IrItem(IrRuleRef("elem"))),
        ),
    )
    return IrAst(rules=IrSeq(rule, ELEM), start="list")


def left_grammar() -> IrAst:
    rule = IrRule(
        "list",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("list")), IrItem(IrRuleRef("elem"))),
            IrSequence(IrItem(IrRuleRef("elem"))),
        ),
    )
    return IrAst(rules=IrSeq(rule, ELEM), start="list")


def build(grammar: IrAst, text: str):
    return BUILD_CHART.eval(PARSER, grammar, IrTuple(IrStr(text)))


def stats(grammar: IrAst, n: int) -> dict:
    text = "a" * n
    chart = build(grammar, text)
    ncols = len(chart)
    items = [len(chart[i]) for i in range(ncols)]
    total_items = sum(items)
    total_links = sum(len(chart.links[k]) for k in chart.links._table)
    nkeys = len(chart.links._table)
    return {
        "n": n,
        "cols": ncols,
        "items": total_items,
        "links": total_links,
        "link_keys": nkeys,
        "per_col_tail": items[-4:],
    }


def slope(label: str, grammar) -> None:
    print(f"\n== {label} ==")
    rows = [stats(grammar, n) for n in (20, 40, 80, 160)]
    print(
        f"  {'n':>4} {'items':>8} {'links':>8} {'keys':>8} {'items/n':>9} {'links/n':>9}"
    )
    for r in rows:
        print(
            f"  {r['n']:>4} {r['items']:>8} {r['links']:>8} {r['link_keys']:>8} "
            f"{r['items'] / r['n']:>9.2f} {r['links'] / r['n']:>9.2f}"
        )
    # marginal per-element cost between the two largest sizes
    a, b = rows[-2], rows[-1]
    d_items = (b["items"] - a["items"]) / (b["n"] - a["n"])
    d_links = (b["links"] - a["links"]) / (b["n"] - a["n"])
    print(f"  marginal items/elem = {d_items:.2f}   links/elem = {d_links:.2f}")
    print(f"  tail column sizes (last 4): {rows[-1]['per_col_tail']}")


def main() -> None:
    slope("RIGHT  list = elem list / elem", right_grammar())
    slope("LEFT   list = list elem / elem  (F1)", left_grammar())


if __name__ == "__main__":
    main()
