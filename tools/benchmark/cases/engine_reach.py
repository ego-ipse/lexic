"""The engine-reach grammars — three shapes, three routes to the gated engine.

Each of these is left-recursive in a way the left-recursion fold REFUSES, so
the predictive path cannot run the rule and something else must. Which
something else is the point, and it differs by where the refused rule sits and
by what follows it:

* a refused START rule has no enclosing clone to splice into, so the product
  parses the whole document on the gated engine;
* a refused INTERIOR rule becomes an island, whose window is either proved
  exact by the continuation analysis or climbed for;
* and a climbing island either answers or refuses, which is a different event
  again.

Kept apart from the timing roster's languages because they are not languages
anyone would write: each is the smallest grammar that exercises one route.
Their rows live beside the rest in `grammars.py`, and
`tests/integration/lexic/parity/test_engine_reach.py` asserts the counter each
one exists to hold.
"""

from __future__ import annotations

START_FALLBACK = """root ::= root "a" | "a"
"""
"""The WHOLE-PARSE fallback witness: the product's own route to Earley.

The recursive arm captures nothing, so the left-recursion fold refuses the rule
— a bare-literal arm leaves no values in the sink, so the iteration depth
cannot be recovered — and the predictive path raises. The refused rule is the
START rule, so there is no enclosing clone to splice into and no island is
built: the product catches the failure and parses the document whole on Earley.

Pinned: ``island_parse`` 0, ``earley_model`` 1. Reaching the gated engine by
the PRODUCT's own decision is a different event from an island splice, and this
is the row that holds the distinction.

The fallback fires on a document of any length, so nothing about the witness
asks for a size. The sample matches the two island rows instead, so the three
routes are priced over the same amount of text and the family's costs can be
read against each other."""


INTERIOR_EXACT = """root ::= item nl
item ::= item "a" | "a"
nl ::= "\\n"
"""
"""The EXACT-width island: the same refused recursion, one sub-parse.

The island's alphabet is ``a`` and its continuation begins with a newline, so
`IslandContinuations.bounds` proves the island cannot derive a character of its
own continuation and hands the sub-parse an exact width. One
``island_run``, no doubling, and the whole-parse fallback never runs.

Pinned: ``island_parse`` 1, ``island_run`` 1, an exact ``policy.window``,
``earley_model`` 0.

One sub-parse at a proved width costs the same however long the island is, so
the witness asks for no particular size either. The sample matches
`interior-climb` unit for unit, because the two exist to be read against each
other and a difference in length would be a second variable."""


INTERIOR_CLIMB = """root ::= item tail
item ::= item "a" | "z"
tail ::= "zz\\n"
"""
"""The CLIMBING island: `island_parse`'s doubling loop, covered.

Identical to `interior-exact` but for one thing: the island's alphabet contains
``z``, which is its continuation's first character, so no exact width is
provable and the window must climb — 256, 512, 1024 … until the chart stops
extending at the edge. The island still ANSWERS rather than falling back,
because every proper prefix is followed by an ``a`` that the tail refuses, so
exactly one end composes.

Pinned: ``island_parse`` 1, ``earley_model`` 0, and ``island_run`` exactly
``ceil(log2(remaining / ISLAND_WINDOW)) + 1``. The formula documents the
relationship; it CANNOT catch a change to ``ISLAND_WINDOW`` itself, because a
wider window makes the row climb less and the formula obligingly computes the
smaller number. A literal pin on the constant is what catches that, and it sits
beside this one in the test.

**The sample is sized for MARGIN in doublings, not for minimality.** A shorter
document still climbs — the window only stops doubling once it covers what is
left — but it climbs fewer times, and a row one doubling away from covering its
document stops witnessing the moment the initial window widens. This sample
climbs five times as shipped and four if that window doubles, so the loop is
still exercised after a change to the constant rather than only before it.

A climb re-parses its characters at every width, so this is the roster's most
expensive row per character — more so than either row beside it. That cost IS
the price of the witness: a document that climbs must be re-scanned to climb.

**This row and `interior-exact` differ in exactly one property: whether the
island's alphabet contains its continuation's first character.** That is what
decides exact against climbing, both carry the same number of units, so the
pair PRICES the climb. A widening of the continuation analysis shows up as this
row turning into that one, which is the shape to look for."""


INTERIOR_DELEGATE = """root ::= item nl
item ::= item "a" | word
word ::= [b-z]+
nl ::= "\\n"
"""
"""The DELEGATING island: a sub-parse that hands an interior rule to a clone.

The recursive arm is still bare, so the fold still refuses and ``item`` is an
island. What changes is the BASE arm: it names ``word``, a conflict-free rule
whose ``+`` loop clears the delegation floor, so the island's sub-parse carries
a delegates table and completes ``word`` through the delegated path — the
payload injected and filed as a :class:`PayloadLeaf` family — instead of
walking it on the chart. The witnesses above build their islands over a lone
``"a"``, below that floor, so no roster kernel ever holds a delegate.

``word``'s alphabet stops short of ``a`` and of the newline, so nothing that
follows a word can be read as more of it and no ambiguity is manufactured.

Pinned: ``island_parse`` 1, ``island_run`` 1 carrying a delegates table of ONE
rule, ``_complete_delegated`` 1, ``earley_model`` 0, and the model round-trips.

Not a benchmark row: whether delegation belongs in the performance matrix is a
separate decision, and a roster row trips every count pin and per-name table
keyed on the roster."""
