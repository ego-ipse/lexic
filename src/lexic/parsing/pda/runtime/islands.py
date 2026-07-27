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
from typing import NamedTuple

from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.ir import IrTuple
from lexic.parsing.earley.engine import EarleyParser
from lexic.parsing.earley.kernel.fasttree import FastTree
from lexic.parsing.earley.kernel.forest import DERIVATION_STREAM, ParseTree, SppfNode
from lexic.parsing.earley.kernel.kernel import Delegate, Kernel
from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.fold import ModelFold
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
through :data:`~lexic.parsing.earley.kernel.forest.DERIVATION_STREAM`'s ``eval`` (stateless)."""


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
      (:meth:`~lexic.parsing.earley.kernel.kernel.Kernel.can_extend_at`) — a
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


class IslandPolicy[M](NamedTuple):
    """How an island's interior is run, and what may come out of it.

    ``fold`` is here for the ambiguity question alone: whether two derivations
    are a real ambiguity is a question about the VALUES they build, and only
    the fold can answer it.
    """

    delegates: dict[int, Delegate] | None = None
    ambiguous: bool = False
    fold: ModelFold[M] | None = None


def island_parse(
    tables: ParserTables,
    text: str,
    pos: int,
    name: str,
    policy: IslandPolicy = IslandPolicy(),
) -> tuple[ParseTree, int]:
    """Longest completion of island ``name`` over a doubling window from ``pos``.

    Grows the window while the best completion still touches its edge and input
    remains (the ambiguous-longest-match risk), then decodes the winning
    completion to a :class:`~lexic.parsing.earley.kernel.forest.ParseTree`.

    :param tables: The island rule's :class:`~lexic.parsing.earley.kernel.tables.ParserTables`.
    :param text: The full input.
    :param pos: The cursor position the window opens at.
    :param name: The island rule name (for the failure message).
    :param policy: The interior delegate table, and whether more than one
        derivation is allowed. An island is the ONE place the model path chooses
        between derivations — everywhere else it is predictive and produces one
        by construction — so it is where the setting is enforced.
    :returns: ``(tree, end)`` — the derivation and its consumed length.
    :raises PdaFail: When the island completes over no window.
    :raises UnsupportedConstructError: On an ambiguous island under the default
        setting. The round-trip invariant cannot catch a wrong choice here:
        ``to_text()`` reproduces the input for whichever derivation was taken.
    """
    remaining = len(text) - pos
    window = ISLAND_WINDOW
    best = island_run(tables, text[pos : pos + window], policy.delegates)
    while window < remaining and _may_extend(best, text, pos, window, remaining):
        window *= 2
        best = island_run(tables, text[pos : pos + window], policy.delegates)
    if best is None:
        raise PdaFail(f"island {name!r}: no match at {pos}")
    kern, item, end = best
    tree = FastTree(kern).build((item << kern.tables.packing.bits) | end)
    if not isinstance(tree, ParseTree):
        # The fast path declining is NOT ambiguity — it also declines when a key
        # packs more than one family or the root has many productions.
        tree = island_derivation(kern, item, end, name, policy=policy)
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


def island_derivation(
    kern: Kernel,
    item: int,
    end: int,
    name: str,
    *,
    policy: IslandPolicy = IslandPolicy(),
) -> ParseTree:
    """First derivation of an island completion the fast path did not build.

    Under the default setting a SECOND derivation is refused — but only when it
    builds a DIFFERENT value. A grammar routinely derives one text several ways
    without meaning anything by it: an inline group like
    ``([0-9] | [1-9] [0-9]*)`` carves a single digit two ways and folds to the
    same model both times, because the arms never materialise a class. Refusing
    that refuses ``{"a":1}`` for a difference no consumer can observe. What is
    worth refusing is a second derivation that means something ELSE, which is a
    question about values, not about trees.

    The stream is lazy, so this costs one extra derivation and one fold, and
    only where the fast path already declined.

    :param kern: The island's Earley kernel.
    :param item: The accepting item.
    :param end: The completion's consumed length.
    :param name: The island rule name (for the failure message).
    :param policy: Carries the ambiguity setting and the fold that answers it.
    :returns: The first derivation tree.
    :raises PdaFail: When the completion decodes to no derivation.
    :raises UnsupportedConstructError: When a second derivation builds a
        different value and the setting refuses it.
    """
    node = SppfNode(kern.decode_item(item), end)
    stream = DERIVATION_STREAM.eval(_DERIV_PARSER, node, IrTuple(kern.to_chart()))
    walk = iter(stream)
    tree = next(walk, None)
    if not isinstance(tree, ParseTree):
        raise PdaFail(f"island {name!r}: no derivation")
    if policy.ambiguous or policy.fold is None:
        return tree
    second = next(walk, None)
    if isinstance(second, ParseTree) and _differs(policy.fold.apply, tree, second):
        raise UnsupportedConstructError(
            f"parsing: island {name!r} derives the same text two ways that mean "
            "different things — pass ambiguous=True to take the first"
        )
    return tree


def _differs(
    apply: Callable[[ParseTree], object], one: ParseTree, other: ParseTree
) -> bool:
    """Do two derivations of one span build different values?

    Compares the VALUES, not their spelling: two dicts of the same content in
    different key orders are one value and two reprs, and refusing a document
    over that refuses it for a difference no consumer can observe.

    Takes the fold's ``apply`` rather than the fold, so the question it answers
    is exactly "what do these two build" — a fold that had no ``apply`` used to
    answer "no difference" to everything, which is a refusal that never fires.

    A fold that refuses either tree answers nothing about ambiguity — that is a
    fold failure, and the caller's own completion will report it — so it counts
    as "no observable difference" here rather than masquerading as one.
    """
    try:
        return apply(one) != apply(other)
    except LexicError:
        return False
