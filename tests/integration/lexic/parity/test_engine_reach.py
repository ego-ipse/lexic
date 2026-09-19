"""Which engine each shape REACHES — asserted, so a witness cannot go quiet.

Three benchmark rows exist to hold three different routes to the gated engine,
and this file is what makes them witnesses rather than labels:

* ``start-fallback`` — the product's own whole-parse fallback. No island.
* ``interior-exact`` — an island whose width the continuation analysis proves,
  so the sub-parse runs once.
* ``interior-climb`` — an island whose width it cannot prove, so the window
  doubles from :data:`ISLAND_WINDOW` until the chart stops extending.

A row named for an engine it no longer reaches is worse than no row: it reports
green while covering nothing. Every assertion here is therefore on a COUNTER
read at the call site, and every counter is proved non-zero somewhere in the
file — a reach test whose probe never fired would pass for the wrong reason.

The counters are patched where the CALLER binds them (``execution.island_parse``,
``products.earley_model``), not in the module that defines them: the defining
module's name is not the one the running code reads.
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

import lexic.parsing.pda.runtime.islands as islands_mod
import lexic.parsing.pda.runtime.kernel.execution as execution_mod
import lexic.parsing.pda.runtime.kernel.kernel as kernel_mod
import lexic.parsing.pda.runtime.matchers as matchers_mod
import lexic.parsing.products as products_mod
from lexic.compile import compile_text
from lexic.parsing.pda.compiler.program.opcodes import BUILD_DISPATCH
from lexic.parsing.pda.runtime.islands import ISLAND_WINDOW
from lexic.parsing.products import _model_product
from tests.clone_walk import walk_program_clones
from tools.benchmark.cases.grammars import BENCHES


@pytest.fixture(name="reach")
def reach_counts(monkeypatch) -> Counter[str]:
    """Count the engine-reach events of whatever parses inside the test.

    A ``Counter`` rather than a record: the four lanes are all ints with the
    same meaning (how many times this happened), and naming the fixture
    function apart from the fixture keeps the test signatures free of a
    shadowed name.
    """
    counts: Counter[str] = Counter()
    real_parse = execution_mod.island_parse
    real_run = islands_mod.island_run
    real_earley = products_mod.earley_model

    def island_parse(tables, text, pos, name, policy):
        counts["islands"] += 1
        counts["exact"] += policy.window is not None
        return real_parse(tables, text, pos, name, policy)

    def island_run(*args, **kwargs):
        counts["runs"] += 1
        return real_run(*args, **kwargs)

    def earley_model(*args, **kwargs):
        counts["earley"] += 1
        return real_earley(*args, **kwargs)

    monkeypatch.setattr(execution_mod, "island_parse", island_parse)
    monkeypatch.setattr(islands_mod, "island_run", island_run)
    monkeypatch.setattr(products_mod, "earley_model", earley_model)
    return counts


def bench(name: str):
    """One roster row by name."""
    return next(b for b in BENCHES if b.name == name)


def test_the_initial_island_window_is_what_these_pins_assume():
    """``ISLAND_WINDOW`` is 256 — asserted as a LITERAL, beside the formula.

    :func:`climbs` derives its counts from the constant, which documents the
    relationship but CANNOT see the constant change: a wider window makes the
    climb rows climb less, and the derived pin quietly computes the smaller
    number and agrees with it. That is this item's own failure mode — a witness
    going quiet — reappearing inside the fix for it.

    So the constant is pinned here as a bare number. Change it and this fails
    first, at the thing that changed.
    """
    assert ISLAND_WINDOW == 256


def climbs(remaining: int) -> int:
    """Sub-parses a NON-exact island runs over ``remaining`` characters.

    The window starts at :data:`ISLAND_WINDOW` and doubles while the chart is
    still live at the edge, so the count is set by how many doublings it takes
    to cover what is left. Derived from the constant rather than written as an
    integer — with the constant itself pinned literally above, because a
    derived count alone would follow a widened window down in silence.
    """
    if remaining <= ISLAND_WINDOW:
        return 1
    return math.ceil(math.log2(remaining / ISLAND_WINDOW)) + 1


# ── the three rows ─────────────────────────────────────────────────────


def test_start_fallback_reaches_earley_without_an_island(reach):
    """The refused recursion is the START rule, so the whole document falls back.

    There is no enclosing clone to splice an island into, so the product
    catches the predictive failure and parses the document whole on the gated
    engine. This is the route no other row takes.
    """
    row = bench("start-fallback")
    model = row.compiled.parse(row.corpus, cores=1)

    assert reach["earley"] == 1, "the product's fallback did not run"
    assert reach["islands"] == 0, "a fallback is not an island splice"
    assert model.to_text() == row.corpus


def test_interior_exact_islands_once_without_falling_back(reach):
    """A provable width means ONE sub-parse and no whole-document re-parse."""
    row = bench("interior-exact")
    model = row.compiled.parse(row.corpus, cores=1)

    assert reach["islands"] == 1
    assert reach["exact"] == 1, "the continuation analysis did not prove a width"
    assert reach["runs"] == 1, "an exact island must not re-parse at a second width"
    assert reach["earley"] == 0, "an island that answers must not fall back"
    assert model.to_text() == row.corpus


def test_interior_climb_doubles_its_window_and_still_answers(reach):
    """An unprovable width climbs, and the island answers without falling back.

    The island's alphabet contains its continuation's first character, so no
    exact width exists. Every proper prefix is followed by a character the tail
    refuses, so exactly one end composes and the climb terminates on an answer
    rather than on a refusal.
    """
    row = bench("interior-climb")
    model = row.compiled.parse(row.corpus, cores=1)

    assert reach["islands"] == 1
    assert reach["exact"] == 0, "this island must NOT be exact — it is the climb row"
    assert reach["runs"] >= 2, (
        "the sample no longer climbs at all — a corpus at or under "
        f"{ISLAND_WINDOW} chars is covered by the first window, and the count "
        "below would then pin 1 and pass while the row witnesses nothing"
    )
    assert reach["runs"] == climbs(len(row.corpus)), (
        f"{reach['runs']} sub-parses over {len(row.corpus)} chars; "
        f"the doubling from {ISLAND_WINDOW} predicts {climbs(len(row.corpus))}"
    )
    assert reach["earley"] == 0
    assert model.to_text() == row.corpus


def test_the_climb_count_tracks_the_document_not_a_constant(reach):
    """The row's OWN two samples climb different numbers of times.

    One size cannot tell a formula from a coincidence: at the corpus size the
    predicted count is small, and a wrong formula can match it by accident. The
    document-scale sample is the control, and the two must separate — if they
    ever stop separating, the pair has been resized into agreeing and this
    assertion says so before the counts are read.
    """
    row = bench("interior-climb")
    small = climbs(len(row.corpus))
    large = climbs(len(row.full))
    assert large > small, "the two samples do not separate — widen the pair"

    assert row.compiled.parse(row.full, cores=1).to_text() == row.full
    assert reach["runs"] == large, (
        f"{reach['runs']} sub-parses over {len(row.full)} chars, expected {large}"
    )
    assert reach["islands"] == 1
    assert reach["earley"] == 0


def test_every_engine_reach_row_asserts_a_live_counter():
    """The three rows exist on the roster, so the tests above are not vacuous.

    A reach test whose row has been renamed or dropped would otherwise fail as
    a lookup error somewhere less obvious.
    """
    names = {b.name for b in BENCHES}
    assert {"start-fallback", "interior-exact", "interior-climb"} <= names


# ── D: the counter-test, not a row ─────────────────────────────────────


_REFUSAL = """root ::= item tail
item ::= item [a-z] | [a-z]
tail ::= "zz\\n"
"""
"""A climbing island whose first settled window REFUSES, then falls back.

Not a benchmark row, because it is the engine's most expensive single path: a
climb whose sub-parses are all discarded, followed by a whole-document re-parse
on the gated engine. As a timed row it would price one pathological shape; what
matters about it is a COUNT — how many sub-parses run before the refusal — and
a counter reads that exactly where a timer only estimates it.

It is the only cover for the first-window refusal RAISING rather than silently
taking the shorter end.
"""


def test_refusal_after_a_climb_falls_back_and_round_trips(reach):
    """The island refuses an arm choice spanning two ends, then the product falls back.

    The island's alphabet includes the tail's own characters, so two different
    ends compose and the settle step refuses rather than picking one. The
    product then parses the document whole on the gated engine, and the result
    still round-trips — a refusal inside an island is not a parse failure.
    """
    # Sized like `interior-climb`: several doublings, so the row keeps
    # climbing even if the initial window widens once.
    text = "q" * 2400 + "zz\n"
    compiled = compile_text(_REFUSAL, cache_key="engine-reach-refusal")
    model = compiled.parse(text, cores=1)

    assert reach["islands"] == 1
    assert reach["runs"] == climbs(len(text)), (
        f"{reach['runs']} sub-parses before the refusal over {len(text)} chars, "
        f"expected {climbs(len(text))}"
    )
    assert reach["earley"] == 1, "the refusal did not reach the product's fallback"
    assert model.to_text() == text


# ── the window-gated pass-through dispatch ──────────────────────────────


WIDE_ROWS = {"gbnf-meta": 16, "abnf-meta": 6, "markdown": 2}
"""Roster rows converting a wide alternation, and how many clones each does.

Counted in the FINAL program. The same rows count the same at convert time;
`vyx` converts 48 there and **none here**, because those clones are not
reachable in the program that ships — a count is a fact about a moment in the
pipeline, and this one names its moment.
"""

WIDE_HOPS = {"markdown": 2_088, "abnf-meta": 1_552, "gbnf-meta": 984}
"""Wide dispatch hops each row takes on its full sample, at cores=1.

A hop is one CHASE STEP, not one entry, and ONE parse at cores=1 is the
measurement — a counter left installed across a second parse doubles these
without saying so.
"""


def wide_dispatch_clones(compiled) -> int:
    """Wide-selecting dispatch clones reachable in the final program."""
    product = _model_product(compiled.codegen_grammar, compiled.product)
    return sum(
        1
        for one in walk_program_clones(product.pda.program.start).values()
        if one.wide_selectors is not None and one.mode == BUILD_DISPATCH
    )


def wide_hops(row, text: str) -> int:
    """Wide dispatch hops one parse takes, counted at BOTH call-site bindings."""
    real = matchers_mod.chase_dispatch
    seen = [0]

    def counted(clone, text_, pos):
        if clone.mode == BUILD_DISPATCH and clone.wide_selectors is not None:
            seen[0] += 1
        return real(clone, text_, pos)

    matchers_mod.chase_dispatch = counted
    kernel_mod.chase_dispatch = counted
    try:
        row.compiled.parse(text, cores=1)
    finally:
        matchers_mod.chase_dispatch = real
        kernel_mod.chase_dispatch = real
    return seen[0]


@pytest.mark.parametrize("name", sorted(WIDE_ROWS))
def test_the_rows_that_convert_a_wide_alternation_convert_the_same_number(name):
    """The clone pin, with its moment named in `WIDE_ROWS`."""
    assert wide_dispatch_clones(bench(name).compiled) == WIDE_ROWS[name]


def test_no_row_outside_those_three_converts_a_wide_clone():
    """The other sixteen rows' programs carry no wide dispatch at all.

    Asserted rather than assumed: the rewrite's blast radius IS this set, and
    a grammar drifting into it would change a program nobody was watching.
    """
    strayed = {
        row.name: wide_dispatch_clones(row.compiled)
        for row in BENCHES
        if row.name not in WIDE_ROWS and wide_dispatch_clones(row.compiled)
    }

    assert not strayed, f"a row outside the three now converts: {strayed}"


@pytest.mark.parametrize("name", sorted(WIDE_HOPS))
def test_each_converting_row_takes_the_hops_it_takes(name):
    """The firing pin, read at the hop — a different event from an entry."""
    assert wide_hops(bench(name), bench(name).full) == WIDE_HOPS[name]


def test_vyx_takes_no_wide_hop_on_either_of_its_documents():
    """A fact about vyx's DOCUMENTS, not a property of its grammar.

    vyx converts wide clones at bake that its shipped program does not reach,
    so nothing it parses takes a wide hop. Said as a document fact because
    another document under the same grammar need not agree.
    """
    row = bench("vyx")

    assert wide_hops(row, row.corpus) == 0
    assert wide_hops(row, row.full) == 0
