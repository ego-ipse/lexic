"""Island sub-parse + splice — the cold-path Earley escape for a PDA clone.

Shed from :class:`~lexic.parsing.pda.runtime.runtime.PdaKernel` as free functions,
for the reason every leaf in this package is shed: these take only plain values
and :mod:`earley <lexic.parsing.earley>` types, never the ``PdaKernel`` cursor,
so the module is a leaf — ``runtime`` imports it, not the reverse — and the
contract between the halves is the argument list rather than an implicit
``self`` nothing checks. The thin ``PdaKernel._island`` dispatcher (which owns
the cursor state — fold, tables, position) calls :func:`island_parse` here.

**Not for speed.** Neither shape costs anything measurable: CPython's inline
``LOAD_ATTR_METHOD_NO_DICT`` cache makes an extra MRO hop free on a ``__slots__``
class with a stable type version, so a mixin split and a free-function split
measure the same. Where a group *does* reach back for a private method, the
method stays — see ``PdaKernel._island`` and ``Kernel._try_leo``, both kept
because their groups write the cursor's own state.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.ir import IrTuple
from lexic.parsing.earley.engine import EarleyParser
from lexic.parsing.earley.kernel.forest.ambiguity import (
    Resolver,
    another_meaning,
    same_value,
)
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import (
    DERIVATION_STREAM,
    ParseTree,
    SppfNode,
)
from lexic.parsing.earley.kernel.forest.readout import (
    can_extend_at,
    decode_item,
    to_chart,
)
from lexic.parsing.earley.kernel.loop.kernel import Delegate, Kernel
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
through :data:`~lexic.parsing.earley.kernel.forest.forest.DERIVATION_STREAM`'s
``eval`` (stateless)."""


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
      (:func:`~lexic.parsing.earley.kernel.forest.readout.can_extend_at`) — a
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
    return can_extend_at(kern, end, text[nxt])


class IslandPolicy[M](NamedTuple):
    """How an island's interior is run, and what may come out of it.

    ``fold`` is here for the ambiguity question alone: whether two derivations
    are a real ambiguity is a question about the VALUES they build, and only
    the fold can answer it.
    """

    delegates: dict[int, Delegate] | None = None
    resolve: Resolver | None = None
    fold: ModelFold[M] | None = None

    def for_island(self, delegates: dict[int, Delegate] | None) -> IslandPolicy[M]:
        """This policy with ``delegates`` filled in — what one island reference
        hands to its sub-parse. The delegates are the only per-island part; the
        fold and the resolver belong to the whole parse."""
        return IslandPolicy(delegates, self.resolve, self.fold)


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
    completion to a :class:`~lexic.parsing.earley.kernel.forest.forest.ParseTree`.

    :param tables: The island rule's :class:`~lexic.parsing.earley.kernel.tables.ParserTables`.
    :param text: The full input.
    :param pos: The cursor position the window opens at.
    :param name: The island rule name (for the failure message).
    :param policy: The interior delegate table, and the caller's resolver, if
        any. An island is the ONE place the model path chooses between
        derivations — everywhere else it is predictive and produces one by
        construction — so it is where the refusal (or the resolver) applies.
    :returns: ``(tree, end)`` — the derivation and its consumed length.
    :raises PdaFail: When the island completes over no window.
    :raises UnsupportedConstructError: On an ambiguous island with no resolver.
        The round-trip invariant cannot catch a wrong choice here:
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
    handle = (item << kern.tables.packing.bits) | end
    tree = FastTree(kern).build(handle)
    if not isinstance(tree, ParseTree):
        # The fast path declining is NOT ambiguity — it also declines when a key
        # packs more than one family or the root has many productions.
        return island_derivation(kern, item, end, name, policy=policy), end
    # ...and the fast path SUCCEEDING is not proof of unambiguity either, which
    # is what this used to assume. Measured: `FastTree` builds a tree for a
    # completion whose arms mean different things, so trusting it here answered
    # an ambiguous input instead of refusing it. The reduce path never relied on
    # the fast path as an oracle — `_one_meaning` asks this question separately —
    # and the model path must ask it too.
    return _settle_two_meanings(kern, handle, tree, name, policy), end


def _settle_two_meanings(
    kern: Kernel, handle: int, tree: ParseTree, name: str, policy: IslandPolicy
) -> ParseTree:
    """The derivation to keep when this completion may mean a second thing.

    :param kern: The island's Earley kernel.
    :param handle: The packed accepting item and end.
    :param tree: The derivation already in hand.
    :param name: The island rule name (for the failure message).
    :param policy: Carries the fold that answers the question, and the caller's
        resolver.
    :returns: ``tree`` when every derivation means the same thing, else what
        the resolver chooses.
    :raises UnsupportedConstructError: When the span means two things and no
        resolver was supplied.
    """
    if policy.fold is None:
        return tree
    witness = another_meaning(kern, handle, policy.fold.apply, tree)
    if witness is None:
        return tree
    if policy.resolve is None:
        raise UnsupportedConstructError(
            f"parsing: island {name!r} derives the same text two ways that mean "
            "different things — supply a resolver to choose between them"
        )
    return policy.resolve(tree, witness)


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
    :param policy: Carries the fold that answers the question, and the caller's
        resolver.
    :returns: The first derivation tree, or what the resolver chooses.
    :raises PdaFail: When the completion decodes to no derivation.
    :raises UnsupportedConstructError: When a second derivation builds a
        different value and no resolver was supplied.
    """
    handle = (item << kern.tables.packing.bits) | end
    if policy.fold is None:
        return _one_derivation(kern, handle, name)
    tree = _one_derivation(kern, handle, name, {})
    return _settle_two_meanings(kern, handle, tree, name, policy)


def _one_derivation(
    kern: Kernel, handle: int, name: str, choices: dict[int, int] | None = None
) -> ParseTree:
    """The derivation ``choices`` names, or the fast path's when it is ``None``."""
    tree = FastTree(kern, choices).build(handle)
    if isinstance(tree, ParseTree):
        return tree
    node = SppfNode(
        decode_item(kern.tables, handle >> kern.tables.packing.bits),
        handle & kern.tables.packing.mask,
    )
    stream = DERIVATION_STREAM.eval(_DERIV_PARSER, node, IrTuple(to_chart(kern)))
    got = next(iter(stream), None)
    if not isinstance(got, ParseTree):
        raise PdaFail(f"island {name!r}: no derivation")
    return got


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
        return not same_value(apply(one), apply(other))
    except LexicError:
        return False
