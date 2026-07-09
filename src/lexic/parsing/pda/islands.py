"""Island sub-parse + splice — the cold-path Earley escape for a PDA clone.

Shed from :class:`~lexic.parsing.pda.runtime.PdaKernel` as free functions: an
island reference already pays a full windowed Earley sub-parse, so the
call-convention change is off the hot path (unlike the fold-build methods, which
stay on ``PdaKernel`` for speed — a mixin split there costs ~6%). These take
only plain values and :mod:`earley <lexic.parsing.earley>` types, never the
``PdaKernel`` cursor, so this module is a leaf: ``runtime`` imports it, not the
reverse. The thin ``PdaKernel._island`` dispatcher (which owns the cursor state
— fold, tables, position) calls :func:`island_parse` here.
"""

from __future__ import annotations

from lexic.ir.base import IrTuple
from lexic.parsing.earley.engine import EarleyParser
from lexic.parsing.earley.forest import DERIVATION_STREAM, ParseTree, SppfNode
from lexic.parsing.earley.kernel import FastTree, Kernel
from lexic.parsing.earley.tables import ORIGIN_BITS, ParserTables
from lexic.parsing.pda.errors import PdaFail

__all__ = ["ISLAND_WINDOW", "island_derivation", "island_parse", "island_run"]

ISLAND_WINDOW = 256
"""Initial character window for an island Earley sub-parse; doubles on demand
while the best completion still touches the window edge and input remains."""

_DERIV_PARSER = EarleyParser()
"""The shared façade dispatcher the island derivation-stream fallback threads
through :data:`~lexic.parsing.earley.forest.DERIVATION_STREAM`'s ``eval`` (stateless)."""


def island_parse(
    tables: ParserTables, text: str, pos: int, name: str
) -> tuple[ParseTree, int]:
    """Longest completion of island ``name`` over a doubling window from ``pos``.

    Grows the window while the best completion still touches its edge and input
    remains (the ambiguous-longest-match risk), then decodes the winning
    completion to a :class:`~lexic.parsing.earley.forest.ParseTree`.

    :param tables: The island rule's :class:`~lexic.parsing.earley.tables.ParserTables`.
    :param text: The full input.
    :param pos: The cursor position the window opens at.
    :param name: The island rule name (for the failure message).
    :returns: ``(tree, end)`` — the derivation and its consumed length.
    :raises PdaFail: When the island completes over no window.
    """
    remaining = len(text) - pos
    window = ISLAND_WINDOW
    best = island_run(tables, text[pos : pos + window])
    while window < remaining and (best is None or best[2] == min(window, remaining)):
        window *= 2
        best = island_run(tables, text[pos : pos + window])
    if best is None:
        raise PdaFail(f"island {name!r}: no match at {pos}")
    kern, item, end = best
    tree = FastTree(kern).build((item << ORIGIN_BITS) | end)
    if not isinstance(tree, ParseTree):  # ambiguous — take the first derivation
        tree = island_derivation(kern, item, end, name)
    return tree, end


def island_run(tables: ParserTables, window: str) -> tuple[Kernel, int, int] | None:
    """Run the island start rule over ``window``, longest origin-0 completion.

    :param tables: The island rule's compiled tables.
    :param window: The candidate window text.
    :returns: ``(kernel, accepting_item, end)`` for the longest completion, or
        ``None`` when the rule never completes in the window.
    """
    kern = Kernel(tables, window)
    result = kern.longest_start_completion()
    if result is None:
        return None
    item, end = result
    return kern, item, end


def island_derivation(kern: Kernel, item: int, end: int, name: str) -> ParseTree:
    """First derivation of an ambiguous island completion (engine policy).

    :param kern: The island's Earley kernel.
    :param item: The accepting item.
    :param end: The completion's consumed length.
    :param name: The island rule name (for the failure message).
    :returns: The first derivation tree.
    :raises PdaFail: When the completion decodes to no derivation.
    """
    node = SppfNode(kern.decode_item(item), end)
    stream = DERIVATION_STREAM.eval(_DERIV_PARSER, node, IrTuple(kern.to_chart()))
    tree = next(iter(stream), None)
    if not isinstance(tree, ParseTree):
        raise PdaFail(f"island {name!r}: no derivation")
    return tree
