"""Deterministic op/alloc counts on the REAL normalized ABNF grammar.

Run with the current normalize.py state (right or F1/left). Counts are
deterministic, so two runs (edit normalize, rerun) are directly comparable with
zero noise. Separates recognition work (chart items/links) from forest+reduce
work (ParseTree nodes, ResolveChildren element-copies, IrTuple allocs in reduce).
"""

from __future__ import annotations

from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.abnf_2 import ABNF_GRAMMAR
from lexic.ir.base import IrStr, IrTuple
from lexic.parsing_2 import parse as earley_parse
from lexic.parsing_2.engine import BUILD_CHART, NULLABLE, EarleyParser
from lexic.parsing_2.forest import ParseTree
from lexic.parsing_2.normalize import (
    desugar_quantifiers,
    flatten_groups,
    split_literals,
)

PARSER = EarleyParser()
BASE = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
NORM = split_literals(desugar_quantifiers(flatten_groups(ABNF_GRAMMAR)))


def chart_counts(text: str):
    chart = BUILD_CHART.eval(PARSER, NORM, IrTuple(IrStr(text)))
    nullable = NULLABLE.eval(PARSER, NORM, ())
    items = 0
    completed = 0  # dot==len  → a Complete call (snapshot alloc each)
    predict = 0  # dot faces ruleref → a Predict call
    nullpred = 0  # dot faces a NULLABLE ruleref → expensive AH branch fires
    for i in range(len(chart)):
        col = chart[i]
        items += len(col)
        for it in col:
            if it.dot >= len(it.arm):
                completed += 1
            elif type(it.arm[it.dot].atom).__name__ == "IrRuleRef":
                predict += 1
                if it.arm[it.dot].atom in nullable:
                    nullpred += 1
    links = sum(len(chart.links[k]) for k in chart.links._table)
    return len(chart), items, links, completed, predict, nullpred


def tree_counts(tree) -> tuple[int, int]:
    """(#ParseTree nodes, total kids across all nodes) in the single derivation."""
    nodes = 0
    kids = 0
    stack = [tree]
    while stack:
        t = stack.pop()
        if isinstance(t, ParseTree):
            nodes += 1
            kids += len(t.kids)
            stack.extend(t.kids)
    return nodes, kids


def main() -> None:
    print(f"rules in NORM: {len(list(NORM.rules))}")
    print(
        f"\n{'mult':>4} {'items':>8} {'links':>8} "
        f"{'compl':>8} {'predict':>8} {'nullpred':>9} {'ptkids':>8}"
    )
    for mult in (1, 2, 4):
        text = BASE * mult
        _cols, items, links, completed, predict, nullpred = chart_counts(text)
        tree = earley_parse(NORM, text)
        _nodes, kids = tree_counts(tree)
        print(
            f"{mult:>4} {items:>8} {links:>8} "
            f"{completed:>8} {predict:>8} {nullpred:>9} {kids:>8}"
        )


if __name__ == "__main__":
    main()
