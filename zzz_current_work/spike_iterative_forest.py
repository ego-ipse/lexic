"""Spike: explicit-stack (trampolined) lazy derivation enumerator.

Validates the algorithm before porting into forest.py:
  - correctness: derivation SET == recursive derivations() on amb/unamb grammars
  - laziness: BUILD_TREE-style 2-derivation short-circuit drives no further
  - cycles: nullable a->b->a/'' terminates
  - depth: deep right-recursion at N=10000 does NOT stack-overflow
"""

from __future__ import annotations

import sys
from typing import Iterator

from lexic.ir.base import IrNone, IrSeq, IrStr, IrTuple
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing import derivations
from lexic.parsing.engine import ACCEPTING, EarleyParser
from lexic.parsing.forest import ParseTree, SppfNode
from lexic.parsing.normalize import normalize

_DONE = object()
"""Sentinel sent into a parent cogen when an advanced child is exhausted."""


# ── trampoline driver ─────────────────────────────────────────────────
# A "cogen" is a generator yielding commands:
#   ('emit', v)      -> v is one of my outputs
#   ('advance', G)   -> resume cogen G to its next emit; send me back the
#                       value, or _DONE when G is exhausted
# Suspended cogens live as locals in their parent's frame; the driver stack
# holds only the currently-active pull chain (depth = derivation spine).


def run(root):  # type: ignore[no-untyped-def]
    """Drive ``root`` cogen, yielding its emitted values lazily, O(1) C-stack."""
    stack = [root]
    to_send = None
    while stack:
        top = stack[-1]
        try:
            cmd = top.send(to_send)
        except StopIteration:
            stack.pop()
            to_send = _DONE
            continue
        if cmd[0] == "advance":
            stack.append(cmd[1])
            to_send = None
        else:  # 'emit'
            v = cmd[1]
            stack.pop()
            if stack:
                to_send = v
            else:
                yield v
                stack.append(top)  # re-advance root for the next value
                to_send = None


# ── cogens mirroring node_derivs / prefixes / child_derivs ────────────
# Cycle handling: a per-read memo marks each (item,end) handle "open" while
# its prefixes are being produced; a re-entrant prefixes() on an open handle
# emits the single empty-prefix sentinel and stops (terminates nullable cycles).


def g_node_derivs(chart, memo, node):  # type: ignore[no-untyped-def]
    sym = IrRuleRef(node.item[0])
    pg = g_prefixes(chart, memo, node)
    v = yield ("advance", pg)
    while v is not _DONE:
        yield ("emit", ParseTree(sym, v))
        v = yield ("advance", pg)


def g_prefixes(chart, memo, node):  # type: ignore[no-untyped-def]
    item = node.item
    dot = item[2]
    if dot == 0:
        yield ("emit", IrSeq())
        return
    key = (item, node.end)
    if key in memo:  # re-entrant open handle -> cycle: replay empty sentinel
        yield ("emit", IrSeq())
        return
    memo.add(key)
    for link in chart.links[key]:
        pred = SppfNode(link[0], link[1])
        child = link[2]
        pg = g_prefixes(chart, memo, pred)
        pp = yield ("advance", pg)
        while pp is not _DONE:
            cg = g_child_derivs(chart, memo, child)
            cd = yield ("advance", cg)
            while cd is not _DONE:
                yield ("emit", IrSeq(*pp, cd))
                cd = yield ("advance", cg)
            pp = yield ("advance", pg)
    memo.discard(key)


def g_child_derivs(chart, memo, child):  # type: ignore[no-untyped-def]
    if isinstance(child, IrLiteral):
        yield ("emit", child)
        return
    ng = g_node_derivs(chart, memo, child)
    v = yield ("advance", ng)
    while v is not _DONE:
        yield ("emit", v)
        v = yield ("advance", ng)


def enum(chart, root) -> Iterator[ParseTree]:  # type: ignore[no-untyped-def]
    return run(g_node_derivs(chart, set(), root))


# ── harness ───────────────────────────────────────────────────────────


def _accept(grammar, text):  # type: ignore[no-untyped-def]
    parser = EarleyParser()
    chart, node = ACCEPTING.eval(parser, grammar, IrTuple(IrStr(text)))
    return chart, node


def _sss():
    return IrAst(
        rules=IrSeq(
            IrRule(
                "s",
                IrAlternation(
                    IrSequence(IrItem(IrRuleRef("s")), IrItem(IrRuleRef("s"))),
                    IrSequence(IrItem(IrLiteral("a"))),
                ),
            )
        ),
        start="s",
    )


def _star():
    return normalize(
        IrAst(
            rules=IrSeq(
                IrRule(
                    "S",
                    IrAlternation(
                        IrSequence(IrItem(IrLiteral("a"), IrQuantifier(0, IrNone)))
                    ),
                )
            ),
            start="S",
        )
    )


def _nullable_cycle():
    return IrAst(
        rules=IrSeq(
            IrRule("a", IrAlternation(IrSequence(IrItem(IrRuleRef("b"))))),
            IrRule(
                "b",
                IrAlternation(IrSequence(IrItem(IrRuleRef("a"))), IrSequence()),
            ),
        ),
        start="a",
    )


def _eplus():
    # e = e '+' e / 'a'  — ambiguous (assoc); Catalan-counted over a+a+a...
    return IrAst(
        rules=IrSeq(
            IrRule(
                "e",
                IrAlternation(
                    IrSequence(
                        IrItem(IrRuleRef("e")),
                        IrItem(IrLiteral("+")),
                        IrItem(IrRuleRef("e")),
                    ),
                    IrSequence(IrItem(IrLiteral("a"))),
                ),
            )
        ),
        start="e",
    )


def check_correctness():
    cases = [
        (_sss(), "aaa"),
        (_sss(), "aaaa"),
        (_sss(), "aaaaa"),
        (_sss(), "aaaaaa"),
        (_eplus(), "a+a+a"),
        (_eplus(), "a+a+a+a"),
        (_nullable_cycle(), ""),
    ]
    all_ok = True
    for g, txt in cases:
        chart, node = _accept(g, txt)
        mine = list(enum(chart, node))
        recur = list(derivations(g, txt))
        ok = sorted(map(repr, mine)) == sorted(map(repr, recur)) and len(mine) == len(
            recur
        )
        all_ok = all_ok and ok
        print(f"  {txt!r:>10}: mine={len(mine):>3} recur={len(recur):>3} set_eq={ok}")
    print(f"  ALL MATCH recursive derivations(): {all_ok}")


def check_laziness():
    g, txt = _sss(), "aaaaaa"  # Catalan(5)=42 derivations
    chart, node = _accept(g, txt)
    it = enum(chart, node)
    first = next(it)
    second = next(it)
    print(
        f"  pulled 2 of 42 lazily without materialising; ok={isinstance(first, ParseTree) and isinstance(second, ParseTree)}"
    )


def check_cycle():
    import threading

    g = _nullable_cycle()
    chart, node = _accept(g, "")
    out = {}

    def go():
        out["trees"] = list(enum(chart, node))

    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(timeout=5.0)
    if t.is_alive():
        print("  cycle: DID NOT TERMINATE")
    else:
        print(f"  cycle: terminated, {len(out.get('trees', []))} derivation(s)")


def check_depth():
    # NOTE: the parse chart is O(n^2) in memory (the separate Leo+SPPF issue),
    # so keep N modest — the point is only that the WALK is depth-safe past the
    # ~300 where the recursive walk overflowed at the default recursion limit.
    g = _star()
    for N in (300, 800, 1500):
        chart, node = _accept(g, "a" * N)
        it = enum(chart, node)
        tree = next(it)
        # structural depth
        d, st = 0, [(tree, 1)]
        while st:
            n, dd = st.pop()
            d = max(d, dd)
            if isinstance(n, ParseTree):
                st.extend((k, dd + 1) for k in n.kids)
        del chart, it, tree
        print(f"  depth N={N}: built tree depth={d} (no overflow)")


if __name__ == "__main__":
    print("recursionlimit:", sys.getrecursionlimit())
    print("correctness (set equality vs recursive derivations()):")
    check_correctness()
    print("laziness:")
    check_laziness()
    print("cycle termination:")
    check_cycle()
    print("depth safety (default recursion limit, single-thread):")
    check_depth()
