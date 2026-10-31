"""A loop decided where its run ends: the predictive engine against Earley.

The witness language — entries of ``e ";"`` each followed by ``"," e`` tails,
``e`` a run of letters — puts a tail's run directly against the next entry's
run of the same class. Taking the run whole leaves the next entry nothing; the
leftmost answer leaves it exactly what it needs before its ``;``. Every
spelling below derives on the predictive engine, at document scale, with
Earley's model.

The closure counterexamples are followers where stopping at the fewest the
follower needs would prune the only reading that parses: they keep the
longest take and, where it cannot complete, the gated engine answers — never
a different model.
"""

from __future__ import annotations

import pytest

from lexic.compile import CompiledGrammar, compile_from_path, compile_text
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.runtime.kernel.kernel import PdaFail, pda_model
from lexic.parsing.products import earley_model, model_product
from tests.paths import GROUND_TRUTH

_ENTRY = 'root ::= entry+\nentry ::= e ";" tail*\ntail ::= "," e\n'
SPELLINGS = {
    "rules": _ENTRY + "e ::= [a-z]+\n",
    "inline": 'root ::= ([a-z]+ ";" ("," [a-z]+)*)+\n',
    "group-tail": 'root ::= entry+\nentry ::= e ";" ("," e)*\ne ::= [a-z]+\n',
    "one-then-star": _ENTRY + "e ::= [a-z] [a-z]*\n",
    "tail-inline": 'root ::= entry+\nentry ::= e ";" tail*\ntail ::= "," [a-z]+\ne ::= [a-z]+\n',
    "tail-recursion": (
        'root ::= entry+\nentry ::= e ";" tails\n'
        'tails ::= "," e tails | ""\ne ::= [a-z]+\n'
    ),
    "entries-recursion": (
        'root ::= e ";" rest\nrest ::= "," e rest | e ";" rest | ""\ne ::= [a-z]+\n'
    ),
    "head-then-star": (
        'root ::= entry entry*\nentry ::= e ";" tail*\ntail ::= "," e\ne ::= [a-z]+\n'
    ),
}
UNIT = "abc;,de,fgh"
DOCUMENT = UNIT * (8 * 1024 // len(UNIT))
COMPARED = UNIT * (1024 // len(UNIT))

_ITEM = 'root ::= item+\nitem ::= head tail*\ntail ::= "," e\n'


def _earley(compiled: CompiledGrammar, text: str) -> str:
    """Whole-document Earley's model dump."""
    product = model_product(compiled.codegen_grammar, compiled.product)
    model = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    return str(model.dump())


@pytest.mark.parametrize("grammar", SPELLINGS.values(), ids=SPELLINGS.keys())
def test_every_spelling_derives_on_the_predictive_engine_with_earleys_model(
    grammar: str,
) -> None:
    """8 KiB, which on the gated engine alone took seconds and gigabytes: the
    predictive engine derives it, and at 1 KiB its model is Earley's."""
    compiled = compile_text(grammar)
    tables = compiled.pda_tables()
    assert pda_model(tables, DOCUMENT, compiled.executor).to_text() == DOCUMENT
    built = pda_model(tables, COMPARED, compiled.executor)
    assert str(built.dump()) == _earley(compiled, COMPARED)


def test_the_tail_leaves_the_next_entry_exactly_one_letter() -> None:
    """``,fghabc;`` — the tail's run stops one letter short of ``;``: the
    second entry is ``c;``, read on the predictive engine as Earley reads it."""
    compiled = compile_text(SPELLINGS["rules"])
    text = "abc;,de,fghabc;"
    built = pda_model(compiled.pda_tables(), text, compiled.executor)
    entries = getattr(built, "entry")
    assert len(entries) == 2
    assert entries[1].to_text() == "c;"
    assert str(built.dump()) == _earley(compiled, text)


@pytest.mark.parametrize(
    ("head", "e", "text"),
    [
        ('[0-9] [a-z]* ";"', "[a-z0-9]+", "5ab;,q5ab;"),
        ('[0-9] ";" | [a-z] [a-z] ";"', "[a-z0-9]+", "ab;,qab;"),
        ('[a-z] ";" "!" | [a-z] [a-z] ";" "?"', "[a-z]+", "a;!,qab;?"),
        ('[a-z]* "x" ";"', "[a-z]+", "x;,qabx;"),
    ],
    ids=["digit-then-star", "two-lengths", "two-tails", "star-then-x"],
)
def test_an_unclosed_follower_never_takes_a_different_reading(
    head: str, e: str, text: str
) -> None:
    """Leaving the follower's minimum would prune the reading that parses; the
    public parse gives Earley's model, and the predictive engine either gives
    it too or refuses."""
    compiled = compile_text(_ITEM + f"e ::= {e}\nhead ::= {head}\n")
    expected = _earley(compiled, text)
    assert str(compiled.parse(text).dump()) == expected
    try:
        built = pda_model(compiled.pda_tables(), text, compiled.executor)
    except PdaFail:
        return
    assert str(built.dump()) == expected


def test_the_digit_led_follower_refuses_rather_than_stopping_short() -> None:
    """``q5ab;``: stopping one short of ``;`` would hand the follower ``b``;
    the loop keeps its longest take and the predictive engine refuses."""
    compiled = compile_text(_ITEM + 'e ::= [a-z0-9]+\nhead ::= [0-9] [a-z]* ";"\n')
    with pytest.raises(PdaFail):
        pda_model(compiled.pda_tables(), "5ab;,q5ab;", compiled.executor)


def test_an_optional_follower_leaves_its_letter_empty() -> None:
    """``x? ";"``: ``;`` may follow at once, so the tail's run is taken whole
    and the next head is a bare ``;``."""
    compiled = compile_text(_ITEM + 'e ::= [a-z]+\nhead ::= x? ";"\nx ::= [a-z]\n')
    text = "a;,bc;"
    built = pda_model(compiled.pda_tables(), text, compiled.executor)
    assert [item.to_text() for item in getattr(built, "item")] == ["a;,bc", ";"]
    assert str(built.dump()) == _earley(compiled, text)


def test_an_escaping_stop_set_over_an_optional_tail_gives_the_right_model() -> None:
    """``x ::= [a-c]*`` before ``"ab"?`` still answers through the gated engine."""
    compiled = compile_text('root ::= x "ab"?\nx ::= [a-c]*\n')
    for text in ("", "ab", "cab", "abab", "ca"):
        assert str(compiled.parse(text).dump()) == _earley(compiled, text)


def test_a_loop_its_own_arm_still_needs_text_after_keeps_its_island() -> None:
    """``[a-z]* [a-z]`` keeps its route: ``e`` is an island, models unchanged."""
    compiled = compile_text(_ENTRY + "e ::= [a-z]* [a-z]\n")
    assert "e" in compiled.pda_tables().islands
    text = UNIT * 8
    assert str(compiled.parse(text).dump()) == _earley(compiled, text)


@pytest.mark.xfail(
    strict=True,
    raises=RecursionError,
    reason="deep right recursion exhausts the stack, on either engine",
)
def test_a_right_recursive_spelling_at_document_scale() -> None:
    """``root ::= entry root | entry`` over 4 KiB: the same outcome as without
    the run-end gate — a recursion as deep as the document."""
    compiled = compile_text(
        "root ::= entry root | entry\n" + _ENTRY.split("\n", 1)[1] + "e ::= [a-z]+\n"
    )
    compiled.parse(UNIT * (4 * 1024 // len(UNIT)))


def test_vyx_keeps_every_route_it_had() -> None:
    """No vyx loop is decided at its run's end: the ones that reach the step
    have no context that needs any of their run, so the program is unchanged."""
    compiled = compile_from_path(GROUND_TRUTH / "vyx.gbnf")
    analysis = GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))
    assert not analysis.taxonomy.loops.run
