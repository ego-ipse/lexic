"""A text-only run that can hold its follower takes its longest match, and
asks its island only where the span holds that follower.

A text-only rule whose own extent proof declines takes the same check on every
match it makes item by item, and a miss asks the island too: a loop there can
take what the rest of its arm needs, so neither answer stands unchecked.

The island takes the longest completion and refuses only where a shorter end
is followed by a character its reference can continue with. Such an end sits
inside the span, before a character in EXTEND, so a span holding none of the
reference's followers is the island's answer as it stands. These tests pin
both sides: the committed span, with no island asked, and the island route,
each equal to whole-document Earley.
"""

from __future__ import annotations

import itertools
from collections import Counter
from collections.abc import Iterator

import pytest

from lexic.compile import Directives, compile_text
from lexic.exceptions import LexicError
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from lexic.parsing.products import earley_model
from tests.parity_helpers import DECLINED, answers
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

STOLEN = (
    'root ::= w ";"? "!"*\nw ::= x? tail?\nx ::= item+\n'
    'item ::= [a;] | "a"+ "a"\ntail ::= "a;" ";"\n'
)
"""``item``'s arms both open on ``a``, and ``"a"+`` takes the ``a`` its own
arm ends on, so that arm never matches item by item: ``aa`` came back as two
one-character items where the whole-document parse has one."""

SOLE = 'x ::= t* rest\nt ::= "ab" | "a"+ "a"\nrest ::= [a]*\n'
"""At ``aa`` only ``t``'s second arm is admitted. It missed item by item, the
loop read the miss as its end, and ``rest`` took the text ``t`` derives."""

GREEDY_EXACT = 'root ::= v "!"\nv ::= [a]* ("ab")?\n'
"""``v``'s proof declines, yet its greedy match is its longest
(:func:`~lexic.parsing.pda.analysis.conflicts.greedy_exact`): not marked."""

PART = 'doc ::= part+ tail\npart ::= ";" ";"? | [a]* [a;]\ntail ::= [a]*\n'
SECTION = (
    'doc ::= sec+\nsec ::= stmt+ end\nstmt ::= "!" | ";"? [a;]\n'
    'end ::= [a;] | [a]* "a"\n'
)
PART_GROUP = (
    'doc ::= part+ tail\npart ::= ";" ";"? | ("a" | "aa")* [a;]\ntail ::= [a]*\n'
)
PART_OPTIONAL = (
    'doc ::= part+ tail\npart ::= ";" ";"? | ("a" "b"?)* [a;]\ntail ::= [a]*\n'
)
"""``part``'s second arm holds an inline group, so its sub runs framed rather
than as a checked leaf: a miss there must ask the island too."""


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


@pytest.mark.parametrize("text", ["aa", "aaa", "aa;", "aaa;!"])
def test_a_stolen_arm_is_never_a_wrong_model(text: str) -> None:
    """The predictive path answers what the whole-document parse answers, or
    declines; the public parse is whole-document Earley's."""
    predictive, gated = answers(STOLEN, "stolen", text)
    assert predictive in (gated, DECLINED)
    _parity(STOLEN, "stolen", text)


def test_two_admitted_arms_of_a_stealing_rule_ask_its_island(
    islands: Counter[str],
) -> None:
    """At ``aa`` both arms of ``item`` are admitted: no sub-run settles the
    choice, the island does, and the verdict ranks its two followable ends —
    the predictive answer is the gated engine's."""
    predictive, gated = answers(STOLEN, "stolen", "aa")
    assert predictive == gated
    assert islands["item"] >= 1


@pytest.mark.parametrize("text", ["aa", "abaa"])
def test_a_sole_arm_that_misses_by_stealing_asks_the_island(text: str) -> None:
    """The miss is no longer read as the end of ``t*``: the island derives
    ``t``, and the predictive path answers whole-document Earley's model."""
    predictive, gated = answers(SOLE, "sole", text)
    assert predictive == gated


def test_a_sole_arm_with_two_followable_ends_is_ranked() -> None:
    """At ``aaa`` ``t`` ends after two characters or three, and ``rest`` can
    follow either: each end is a candidate iteration of ``t*``, and the
    decider's rank keeps the gated engine's, on the predictive path."""
    predictive, gated = answers(SOLE, "sole", "aaa")
    assert predictive == gated == "X((T('aaa'),), Rest(''))"
    _parity(SOLE, "sole", "aaa")


@pytest.mark.parametrize("text", ["aab!", "ab!", "aaab!"])
def test_a_greedy_exact_rule_keeps_its_answer(text: str, islands: Counter[str]) -> None:
    """``v`` keeps its predictive answer with no island asked."""
    predictive, gated = answers(GREEDY_EXACT, "greedy-exact", text)
    assert predictive == gated
    assert not islands


@pytest.mark.parametrize(
    ("source", "alphabet"),
    [(PART, "a;"), (SECTION, "a;!"), (PART_GROUP, "a;"), (PART_OPTIONAL, "ab;")],
    ids=["part", "section", "part-group", "part-optional"],
)
def test_no_short_document_gets_a_wrong_model(source: str, alphabet: str) -> None:
    """Every document of four characters or fewer: the predictive path answers
    whole-document Earley's model or declines."""
    for size in range(1, 5):
        for chars in itertools.product(alphabet, repeat=size):
            text = "".join(chars)
            predictive, gated = answers(source, f"short-{alphabet}", text)
            assert predictive in (gated, DECLINED), text


HOOK = 'doc ::= c "b"?\nc ::= t tl?\nt ::= [a;] | "a"+ "a"\ntl ::= "a" "b"\n'
"""``t`` is an island whose reference can follow two of its completions at
``aab``: ``a``, leaving ``ab`` to ``tl``, or ``aa``, leaving ``b`` to ``doc``."""


def test_an_islands_two_ends_are_ranked_by_the_parse_not_the_island() -> None:
    """The island's own longest completion is ``aa``, and taking it would be
    the wrong model: ``c`` ends where the shorter one lets ``tl`` end, and
    that is the first boundary the decider ranks. The verdict forks one side
    per completion and keeps the gated engine's."""
    predictive, gated = answers(HOOK, "hook", "aab")
    assert predictive == gated == "Doc(C(T('a'), Tl('ab')), '')"
    assert predictive != "Doc(C(T('aa')), 'b')"
