"""Island sub-parse + splice — the cold-path Earley escape for a PDA clone.

Shed from :class:`~lexic.parsing.pda.runtime.runtime.PdaKernel` as free functions: an
island reference already pays a full windowed Earley sub-parse, so the
call-convention change is off the hot path (unlike the fold-build methods, which
stay on ``PdaKernel`` for speed — a mixin split there costs ~6%). These take
only plain values and :mod:`earley <lexic.parsing.earley>` types, never the
``PdaKernel`` cursor, so this module is a leaf: ``runtime`` imports it, not the
reverse. The thin ``PdaKernel._island`` dispatcher (which owns the cursor state
— fold, tables, position) calls :func:`island_parse` here.
"""

from __future__ import annotations

from collections.abc import Callable

from lexic.exceptions import LexicError
from lexic.ir.base import IrTuple
from lexic.parsing.earley.engine import EarleyParser
from lexic.parsing.earley.forest import DERIVATION_STREAM, ParseTree, SppfNode
from lexic.parsing.earley.kernel import Delegate, FastTree, Kernel
from lexic.parsing.earley.tables import ORIGIN_BITS, ParserTables
from lexic.parsing.pda.core.errors import PdaFail

__all__ = [
    "ISLAND_WINDOW",
    "island_derivation",
    "island_parse",
    "island_run",
    "island_value",
]

ISLAND_WINDOW = 256
"""Initial character window for an island Earley sub-parse; doubles on demand
while the best completion still touches the window edge and input remains."""


def island_value[T](compute: Callable[[], T], name: str, pos: int) -> T:
    """Run an island's fold/reduce step, failing SOFT on a library error.

    The window-growth heuristic is a heuristic: a language with the
    valid-prefix property (e.g. bare identifiers) can complete a TRUNCATED
    parse strictly inside a window that cut a token, without touching the
    edge — the spliced sub-model is then wrong, and its fold/reduce step is
    the first thing to notice (an unknown symbol, a refused field). Such a
    :class:`~lexic.exceptions.LexicError` reroutes to :class:`PdaFail`, so
    the Earley completion — which parses the WHOLE input and re-runs the
    same fold — becomes the authority; a genuine fold error reproduces there
    identically. Non-library exceptions (authored-constructor bugs) still
    surface loudly.

    :param compute: The deferred fold/reduce application.
    :param name: The island rule name (for the failure message).
    :param pos: The cursor position (for the failure message).
    :returns: The computed sub-model / IR value.
    :raises PdaFail: When ``compute`` raises a :class:`LexicError`.
    """
    try:
        return compute()
    except LexicError as exc:
        raise PdaFail(f"island {name!r} at {pos}: fold refused the completion") from exc


_DERIV_PARSER = EarleyParser()
"""The shared façade dispatcher the island derivation-stream fallback threads
through :data:`~lexic.parsing.earley.forest.DERIVATION_STREAM`'s ``eval`` (stateless)."""


def _may_extend(
    best: tuple[Kernel, int, int] | None,
    text: str,
    pos: int,
    window: int,
    remaining: int,
) -> bool:
    """Whether a windowed island result may extend with more input — grow.

    Three grow signals, each an over-approximation (growing is always safe;
    it can only ever add genuine longest-match input):

    - no completion in the window at all (more context may produce one);
    - the best completion touches the window edge (the original heuristic —
      a token cut exactly at the edge);
    - the **valid-prefix probe**: the FULL text's next character after the
      completion is scannable at the completion column
      (:meth:`~lexic.parsing.earley.kernel.Kernel.can_extend_at`) — a
      language with the valid-prefix property (bare identifiers, call heads)
      can complete a TRUNCATED parse strictly inside a cut window; if the
      real next character could extend the island, the stop is not to be
      trusted. This is the longest-match semantics the window was hiding —
      not merely a safety net for the fail-soft path.

    :param best: The windowed ``island_run`` result.
    :param text: The FULL input.
    :param pos: The island's start position in ``text``.
    :param window: The current window size.
    :param remaining: ``len(text) - pos``.
    :returns: ``True`` when the window must grow before trusting ``best``.
    """
    if best is None:
        return True
    kern, _item, end = best
    if end == min(window, remaining):
        return True
    nxt = pos + end
    if nxt >= len(text):
        return False
    return kern.can_extend_at(end, text[nxt])


def island_parse(
    tables: ParserTables,
    text: str,
    pos: int,
    name: str,
    delegates: dict[int, Delegate] | None = None,
) -> tuple[ParseTree, int]:
    """Longest completion of island ``name`` over a doubling window from ``pos``.

    Grows the window while the best completion still touches its edge and input
    remains (the ambiguous-longest-match risk), then decodes the winning
    completion to a :class:`~lexic.parsing.earley.forest.ParseTree`.

    :param tables: The island rule's :class:`~lexic.parsing.earley.tables.ParserTables`.
    :param text: The full input.
    :param pos: The cursor position the window opens at.
    :param name: The island rule name (for the failure message).
    :param delegates: The island-interior delegate table (rule_id → callable),
        or ``None`` (pure-Earley interior — the pre-delegation behaviour).
    :returns: ``(tree, end)`` — the derivation and its consumed length.
    :raises PdaFail: When the island completes over no window.
    """
    remaining = len(text) - pos
    window = ISLAND_WINDOW
    best = island_run(tables, text[pos : pos + window], delegates)
    while window < remaining and _may_extend(best, text, pos, window, remaining):
        window *= 2
        best = island_run(tables, text[pos : pos + window], delegates)
    if best is None:
        raise PdaFail(f"island {name!r}: no match at {pos}")
    kern, item, end = best
    tree = FastTree(kern).build((item << ORIGIN_BITS) | end)
    if not isinstance(tree, ParseTree):  # ambiguous — take the first derivation
        tree = island_derivation(kern, item, end, name)
    return tree, end


def island_run(
    tables: ParserTables,
    window: str,
    delegates: dict[int, Delegate] | None = None,
) -> tuple[Kernel, int, int] | None:
    """Run the island start rule over ``window``, longest origin-0 completion.

    :param tables: The island rule's compiled tables.
    :param window: The candidate window text.
    :param delegates: The island-interior delegate table, or ``None``.
    :returns: ``(kernel, accepting_item, end)`` for the longest completion, or
        ``None`` when the rule never completes in the window.
    """
    kern = Kernel(tables, window, delegates=delegates)
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
