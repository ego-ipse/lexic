"""A text-only run that can hold its follower takes its longest match, and
asks its island only where the span holds that follower.

The island takes the longest completion and refuses only where a shorter end
is followed by a character its reference can continue with. Such an end sits
inside the span, before a character in EXTEND, so a span holding none of the
reference's followers is the island's answer as it stands. These tests pin
both sides: the committed span, with no island asked, and the island route,
each equal to whole-document Earley.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator

import pytest

from lexic.compile import Directives, compile_text
from lexic.exceptions import LexicError
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from lexic.parsing.products import earley_model
from tests.unit.lexic.parsing.parsing_helpers import prod
from tools.benchmark.cases.grammars import BENCHES

CLOSED = 's ::= x ("}" | ";") y\nx ::= "v" [a-z}]*\ny ::= [a-z]*\n'
"""``x`` can hold ``}``, which may also close it, and letters go on either
way past it, so no two characters decide where ``x`` ends."""

LED = 's ::= x ("}" | ";") y\nx ::= "}" [a-z}]*\ny ::= [a-z]*\n'
"""``x`` opens with the follower it can hold: its first character is not a
shorter end, since ``x`` is not nullable."""

TWO_SITES = (
    's ::= a | b\na ::= "AA" x ";" y\nb ::= "B" x "}" y\n'
    'x ::= "v" [a-z}]*\ny ::= [a-z]*\n'
)
"""``x`` referenced where ``;`` follows and where ``}`` follows, at positions
that cannot meet: each reference checks its own followers."""


def _island_owner() -> type:
    """The kernel class that defines the island splice."""
    for one in PdaKernel.__mro__:
        if "_island" in one.__dict__:
            return one
    raise AssertionError("no class defines _island")


@pytest.fixture(name="islands")
def fixture_islands(monkeypatch: pytest.MonkeyPatch) -> Iterator[Counter[str]]:
    """Count the island sub-parses a test's parses run, by island rule."""
    owner = _island_owner()
    real = owner.__dict__["_island"]
    calls: Counter[str] = Counter()

    def counting(kernel, ref, sink):
        calls[ref[0]] += 1
        return real(kernel, ref, sink)

    monkeypatch.setattr(owner, "_island", counting)
    yield calls


def answer(run) -> str:
    """A parse's model dump, or the refusal it raised."""
    try:
        return str(run().dump())
    except LexicError as refused:  # the refusal IS the answer being compared
        return f"refused: {type(refused).__name__}"


def _parity(source: str, key: str, text: str) -> None:
    """The public parse of ``text`` is whole-document Earley's answer."""
    compiled = compile_text(source, cache_key=key)
    product = prod(compiled)
    want = answer(
        lambda: earley_model(
            product.instance_grammar, text, compiled.product, product.tables
        )
    )
    assert answer(lambda: compiled.parse(text, cores=1)) == want


@pytest.mark.parametrize("text", ["vab;c", "v;", "vab;"])
def test_a_span_without_its_follower_commits_with_no_island(
    text: str, islands: Counter[str]
) -> None:
    """The greedy match stands, and no island is asked."""
    _parity(CLOSED, "longest-closed", text)
    assert not islands


@pytest.mark.parametrize("text", ["va}b}c", "v}}", "va}b;c", "v}a}}", "vab}c", "v}"])
def test_a_span_holding_its_follower_asks_the_island(
    text: str, islands: Counter[str]
) -> None:
    """A ``}`` inside the span may end ``x`` short, even the one the greedy
    match ran over: the island answers."""
    _parity(CLOSED, "longest-closed", text)
    assert islands["x"] >= 1


def test_the_first_character_is_not_a_shorter_end(islands: Counter[str]) -> None:
    """``x`` cannot be empty, so its opening ``}`` ends nothing: committed."""
    _parity(LED, "longest-led", "}ab;c")
    assert not islands


def test_each_reference_checks_its_own_followers(islands: Counter[str]) -> None:
    """Where ``;`` follows, a ``}`` in the span is text: committed. Where
    ``}`` follows, the same span asks the island."""
    _parity(TWO_SITES, "longest-two-sites", "AAvx}y;z")
    assert not islands
    _parity(TWO_SITES, "longest-two-sites", "Bvx}y}z")
    assert islands["x"] >= 1


def test_the_vyx_lexical_seat_takes_every_unquoted_value_longest(
    islands: Counter[str],
) -> None:
    """vyx's ``@lexical`` compile inlines ``unquoted`` into one text-only rule
    whose run can hold ``/``, ``\\`` and ``}``. Its bench corpus holds none of
    them, so every value is committed on the predictive path."""
    bench = next(one for one in BENCHES if one.name == "vyx")
    compiled = compile_text(
        bench.source,
        cache_key="longest-vyx-lex",
        flavour=bench.flavour,
        directives=Directives(lexical=frozenset(bench.lexical)),
    )
    product = prod(compiled)
    want = earley_model(
        product.instance_grammar, bench.corpus, compiled.product, product.tables
    )
    assert compiled.parse(bench.corpus, cores=1) == want
    assert not islands
