"""Adversarial codegen tests — unit-arm cycles must produce loadable classes.

A rule that is a unit arm of itself (``s ::= s | "a"``), or rules that are
unit arms of each other, are valid CFGs; the multiple-inheritance codegen
used to emit ``class S(S):`` / circularly inheriting classes and die with
``NameError`` at module exec. Cycle members all derive the same language, so
the parent graph breaks the cycle (members become siblings) and every
concrete arm carries every cycle member as a base — ``isinstance`` keeps
working for fields typed with any member.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.model import GrammarModel
from lexic.parsing import ParseConfig
from lexic.parsing.products import earley_model, model_product
from tests.adversarial.lexic.adversarial_helpers import watchdog


def test_self_unit_arm_compiles_and_round_trips() -> None:
    """s ::= s | "a" — the self-arm shape that emitted ``class S(S):``."""
    compiled = compile_text('s ::= s | "a"\n', cache_key="adv-cyc-self")
    model = compiled.parse("a")
    assert model.to_text() == "a"


def test_self_arm_with_left_recursion_round_trips() -> None:
    """s ::= s "b" | s | "a" — self arm mixed with a left-recursive arm."""
    compiled = compile_text('s ::= s "b" | s | "a"\n', cache_key="adv-cyc-mix")
    model = compiled.parse("ab")
    assert model.to_text() == "ab"


def test_mutual_unit_arms_compile_and_round_trip() -> None:
    """a ::= b | "x" / b ::= a | "y" — mutually inheriting alternations."""
    compiled = compile_text(
        'a ::= b | "x"\nb ::= a | "y"\n', cache_key="adv-cyc-mutual"
    )
    for text in ("x", "y"):
        assert compiled.parse(text).to_text() == text


def test_cycle_arm_instances_carry_every_cycle_member() -> None:
    """A concrete arm of either cycle member is an instance of BOTH classes.

    ``a`` and ``b`` derive the same language, so a field typed with either
    alternation class must accept a parse that went through the other.
    """
    compiled = compile_text('a ::= b | "x"\nb ::= a | "y"\n', cache_key="adv-cyc-iso")
    a_cls = compiled.classes["A"]
    b_cls = compiled.classes["B"]
    for text in ("x", "y"):
        model = compiled.parse(text)
        assert isinstance(model, a_cls)
        assert isinstance(model, b_cls)


KEEP_FIRST = ParseConfig(resolve=lambda first, _other: first)
"""A resolver that settles any two meanings by keeping the derivation in hand."""

CYCLES = {
    "self-unit": ('root ::= s\ns ::= s | "a"\n', "a"),
    "mutual-unit": ('root ::= s\ns ::= t | "a"\nt ::= s\n', "a"),
    "mutual-pair": ('a ::= b | "x"\nb ::= a | "y"\n', "y"),
    "nullable-unit": (
        'root ::= "<" e mid ">"\ne ::= f | ""\nf ::= e\n'
        'mid ::= p | q\np ::= "n"\nq ::= "n"\n',
        "<n>",
    ),
    "no-way-out": ('root ::= "<" e ">"\ne ::= f | g\nf ::= e\ng ::= e | ""\n', "<>"),
}
"""Cycles the value route's first-derivation build walks into: a self arm, two
rules that are each other's unit arm (one with the comparison's flip leading
back into the cycle), the same through an empty span beside an arm choice whose
two arms build different values, and a key whose every family leads back into
a handle still being built."""


def _earley(label: str, config: ParseConfig) -> object:
    """``label``'s document through the Earley value route, under a budget."""
    source, text = CYCLES[label]
    compiled = compile_text(source, cache_key=f"adv-cyc-earley-{label}")
    product = model_product(compiled.codegen_grammar, compiled.product)
    with watchdog(10):
        return earley_model(
            product.instance_grammar, text, compiled.product, product.tables, config
        )


def _complete(model: object, label: str) -> str:
    """The model's repr, once it is shown to cover its document exactly: a
    node over a span it does not fill — the truncated cut a cycle's stream
    emits — reads back short of the text."""
    assert isinstance(model, GrammarModel)
    assert model.to_text() == CYCLES[label][1]
    return repr(model)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("self-unit", "Root(SArm2('a'))"),
        ("mutual-pair", "BArm2('y')"),
    ],
)
@pytest.mark.parametrize("config", [ParseConfig(), KEEP_FIRST])
def test_a_cycle_of_one_meaning_answers_it(
    label: str, expected: str, config: ParseConfig
) -> None:
    """Every derivation through the cycle builds the same value, so the span
    answers it, resolver or no resolver. ``b ::= a`` over "y" is compared by
    unrolling the cycle once — the flip's inner ``a`` builds under the default
    choices in the untracked first try — not refused for re-entering it."""
    assert _complete(_earley(label, config), label) == expected


@pytest.mark.parametrize("label", ["mutual-unit", "nullable-unit"])
def test_a_cycle_with_two_meanings_refuses_promptly(label: str) -> None:
    """The build never loops on a cycle: the span's two meanings are found and,
    with no resolver, refused — the nullable one once ran without end."""
    with pytest.raises(UnsupportedConstructError, match="ambiguous"):
        _earley(label, ParseConfig())


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("mutual-unit", "Root(SArm2('a'))"),
        ("nullable-unit", "Root(E(F(E())), P('n'))"),
    ],
)
def test_a_cycle_with_two_meanings_takes_the_resolvers_answer(
    label: str, expected: str
) -> None:
    """The same spans settle under a resolver, on a complete derivation: the
    nullable one's ``e ⇄ f`` turn leaves through ``e ::= ""``, the family the
    handle still being built does not close."""
    assert _complete(_earley(label, KEEP_FIRST), label) == expected


@pytest.mark.parametrize("config", [ParseConfig(), KEEP_FIRST])
def test_a_key_with_no_way_out_refuses_explicitly(config: ParseConfig) -> None:
    """``e`` takes ``f``, and ``f``'s only family re-enters the ``e`` still being
    built: no complete derivation follows that choice, so the span refuses as
    one that cannot be compared — resolver or not — rather than fold a cut."""
    with pytest.raises(UnsupportedConstructError, match="cannot be compared"):
        _earley("no-way-out", config)
