"""The engine-reach grammars — three routes to the gated engine, and the
multi-arm fold that took over the shapes which used to reach it.

**The relay rows reach the engine.** Each is left-recursive INDIRECTLY, through a
relay rule ``more ::= item`` the recursive arms do not consist of entirely. The
left-recursion fold takes DIRECT left recursion only, so the predictive path
cannot run the rule and something else must. Which something else is the
point, and it differs by where the refused rule sits and by what follows it:

* a refused START rule has no enclosing clone to splice into, so the product
  parses the whole document on the gated engine;
* a refused INTERIOR rule becomes an island, whose window is either proved
  exact by the continuation analysis or climbed for;
* and a climbing island either answers or refuses, which is a different event
  again.

That indirection is the property every relay row leans on: a fold that learned
to read through a relay rule would take them all, and the counters pinned in
`tests/integration/lexic/parity/test_engine_reach.py` would fail. It is also
why the relay rows carry no ANTLR seat: ANTLR rewrites direct left recursion
only, and refuses the indirect kind.

**The direct rows are the same three languages, written directly.** They reached
the engine while the fold refused two recursive arms. It now takes several, one
character choosing between them, so they run predictively, and their timings —
same grammars, same corpora, same competitors — price that.

Kept apart from the timing roster's languages because they are not languages
anyone would write: each is the smallest grammar that exercises one route.
The two fold rows' grammars, island-earley and dense-earley, live here for the
same reason. Their rows live beside the rest in `grammars.py`.
"""

from __future__ import annotations

START_FALLBACK = """root ::= root "a" | root "b" | "a"
"""
"""The START rule folded over two recursive arms: the whole document on the
predictive path.

``a`` and ``b`` each begin one β, so the next character says which arm an
iteration takes and the fold builds each through its own arm. This row reached
the whole-parse fallback while the fold refused two arms; its route witness is
now `RELAY_FALLBACK`, and this row prices the fold against the same corpus and
competitors."""


INTERIOR_EXACT = """root ::= item nl
item ::= item "a" | item "b" | "a"
nl ::= "\\n"
"""
"""An INTERIOR rule folded over two recursive arms, followed by a newline.

It was the exact-width island while the fold refused two arms; its route witness
is now `RELAY_EXACT`. The sample matches `interior-climb` unit for unit, so the
two direct rows read against each other with nothing else differing."""


INTERIOR_CLIMB = """root ::= item tail
item ::= item "a" | item "b" | "z"
tail ::= "zz\\n"
"""
"""An INTERIOR rule folded over two recursive arms, whose own alphabet holds
its continuation's first character.

It was the climbing island while the fold refused two arms. Folded, the
predictive descent settles each iteration by the next character and stops at
the ``zz`` the arms cannot start, so no window is climbed at all. Its route
witness is now `RELAY_CLIMB`, which carries the same sample, so the pair prices
the fold against the climb it replaced."""


RELAY_FALLBACK = """root ::= more "a" | more "b" | "a"
more ::= root
"""
"""The WHOLE-PARSE fallback witness: the product's own route to Earley.

Left-recursive through the relay ``more``, so the fold refuses the rule and the
predictive path raises. The refused rule is the START rule, so there is no
enclosing clone to splice into and no island is built: the product catches the
failure and parses the document whole on Earley.

Pinned: ``island_parse`` 0, ``earley_model`` 1. Reaching the gated engine by
the PRODUCT's own decision is a different event from an island splice, and this
is the row that holds the distinction.

The fallback fires on a document of any length, so nothing about the witness
asks for a size. The sample matches the two island rows instead, so the three
routes are priced over the same amount of text and the family's costs can be
read against each other."""


RELAY_EXACT = """root ::= item nl
item ::= more "a" | more "b" | "a"
more ::= item
nl ::= "\\n"
"""
"""The EXACT-width island: the relayed recursion, one sub-parse.

The island's alphabet is ``a`` and ``b``, its continuation a newline, so
`IslandContinuations.bounds` proves the island cannot derive a character of its
own continuation and hands the sub-parse an exact width. One window, no growth,
and the whole-parse fallback never runs.

Pinned: ``island_parse`` 1, one window (``island_run`` 1, no growth), an exact
``policy.window``, ``earley_model`` 0.

One sub-parse at a proved width costs the same however long the island is, so
the witness asks for no particular size either. The sample matches
`relay-climb` unit for unit, because the two exist to be read against each
other and a difference in length would be a second variable."""


RELAY_CLIMB = """root ::= item tail
item ::= more "a" | more "b" | "z"
more ::= item
tail ::= "zz\\n"
"""
"""The CLIMBING island: `island_parse`'s doubling loop, covered.

Identical to `relay-exact` but for one thing: the island's alphabet contains
``z``, which is its continuation's first character, so no exact width is
provable and the window must climb — 256, 512, 1024 … until the chart stops
reaching past the window. The island still ANSWERS rather than falling back,
because every proper prefix is followed by an ``a`` that the tail refuses, so
exactly one end composes.

Pinned: ``island_parse`` 1, ``earley_model`` 0, and windows (the one
``island_run`` opens and each ``WindowKernel.grow``) exactly
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
still exercised after a change to the constant rather than only before it, and
the timing matrix prices a climb that grows one chart (`resume.WindowKernel`).

**This row and `relay-exact` differ in exactly one property: whether the
island's alphabet contains its continuation's first character.** That is what
decides exact against climbing, both carry the same number of units, so the
pair PRICES the climb. A widening of the continuation analysis shows up as this
row turning into that one, which is the shape to look for."""


INTERIOR_DELEGATE = """root ::= item nl
item ::= more "a" | more "b" | word
more ::= item
word ::= [c-z]+
nl ::= "\\n"
"""
"""The DELEGATING island: a sub-parse that hands an interior rule to a clone.

Left-recursive through the relay ``more``, so the fold refuses and ``item`` is
an island. What changes is the BASE arm: it names ``word``, a conflict-free rule
whose ``+`` loop clears the delegation floor, so the island's sub-parse carries
a delegates table and completes ``word`` through the delegated path — the
payload injected and filed as a :class:`PayloadLeaf` family — instead of walking
it on the chart. The relay rows build their islands over a lone ``"a"``, below
that floor, so no roster kernel ever holds a delegate.

``word``'s alphabet stops short of ``a``, ``b`` and the newline, so nothing that
follows a word can be read as more of it and no ambiguity is manufactured.

Pinned: ``island_parse`` 1, ``island_run`` 1 carrying a delegates table of ONE
rule, ``_complete_delegated`` 1, ``earley_model`` 0, and the model round-trips.

Not a benchmark row: whether delegation belongs in the performance matrix is a
separate decision, and a roster row trips every count pin and per-name table
keyed on the roster."""


ISLAND_EARLEY = """root ::= expr nl
expr ::= expr addop term | term
term ::= call | name
call ::= name lparen text rparen
name ::= [a-z] [a-z0-9_]*
text ::= [a-z0-9.,_/]*
addop ::= " + " | " - "
lparen ::= "("
rparen ::= ")"
nl ::= "\\n"
"""
"""A LEFT-RECURSIVE spine over a long deterministic interior — a FOLD row.

``expr``'s recursive arm captures, so the left-recursion fold takes it: the
rule is rewritten to ``(γ)(β)*``, the predictive path runs it, and the
iterations are folded back into the model the original arms build. This is one
of the roster's two ``BUILD_FOLD`` rows, and what it prices is that fold over a
long deterministic interior — each term a call whose arguments are ordinary
character runs, with the left-nested rebuild's depth set by the chain's length.

It does NOT reach the gated engine. Engine reach is held by `relay-fallback`,
`relay-exact` and `relay-climb`, each of which asserts its own counter."""


DENSE_EARLEY = """root ::= line+
line ::= expr nl
expr ::= expr op term | term
term ::= [a-z]
op ::= "+"
nl ::= "\\n"
"""
"""The DENSE Earley control: left-recursive, and one character per unit.

`island-earley` reaches the same engine over a long deterministic interior, so
its terminals collapse into runs and a terminal step crosses many characters at
once — on a 10 KiB input barely 4% of its chart columns ever hold an item. A
per-column change therefore reports a saving there whether or not it taxes the
columns that ARE occupied, and no row on the roster contradicts it.

This row is that contradiction. Every unit is a single character, so essentially
every column is occupied; the grammar is unambiguous and the chain is bounded
per line, so the cost is linear and the row is a control rather than a
pathology.

Its recursion is left and its recursive arm captures, so the fold takes it and
the predictive path runs the row: this is the roster's other ``BUILD_FOLD``
row. The dense CHART is still measured here by the `lexic-earley` seat, which
calls the gated engine directly; what the row does not do is choose that engine
itself. Which engine a shape REACHES is pinned by the three engine-reach rows,
not by this one.

**A control that does not finish reads nothing.** Both arms of an A/B run this
row up to the pair ceiling in fresh processes, and a size that makes the base
arm time out does not produce a cautious verdict — it produces no verdict, on
the one row the others cannot speak for. So the samples are sized against the
roster's other left-recursive row rather than against the largest chart they
could build: a dense column costs far more than a run-collapsed one, and these
two documents put this row's worker processes at or below what
`island-earley`'s already cost. The full sample stays above four workers' worth
of the split floor, so the mt seats still carve it."""
