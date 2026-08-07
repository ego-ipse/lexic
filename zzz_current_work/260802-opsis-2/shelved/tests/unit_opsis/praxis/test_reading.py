"""Reading/Reader/Params contract — product narrowing, ``reads``, ``as_reader``."""

from __future__ import annotations

from opsis.praxis.reading import Outcome, Reading, refusal_of

from lexic.compile import compile_text
from lexic.grammars import GBNF_FLAVOUR

_TOY = 'root ::= "x"+\n'


def test_reading_with_no_reader_has_no_product_and_no_error() -> None:
    """A fresh reading has produced nothing and refused nothing."""
    reading = Reading("r1", "loose text")
    assert reading.product is None
    assert reading.error == ""


def test_compiled_narrows_only_when_product_is_a_compiled_grammar() -> None:
    """``compiled`` returns the product only when it IS a ``CompiledGrammar``."""
    reading = Reading("r1", "grammar")
    reading.outcome = Outcome(product=compile_text(_TOY))
    assert reading.compiled is not None
    assert reading.tokenizer is None
    assert reading.flavour is None


def test_flavour_narrows_only_when_product_is_a_flavour() -> None:
    """``flavour`` returns the product only when it IS an ``IrFlavour``."""
    reading = Reading("r2", "manifest")
    reading.outcome = Outcome(product=GBNF_FLAVOUR)
    assert reading.flavour is not None
    assert reading.compiled is None
    assert reading.tokenizer is None


def test_neither_property_narrows_an_unrelated_product() -> None:
    """A product of some other type satisfies none of the three narrowings."""
    reading = Reading("r3", "text")
    reading.outcome = Outcome(product=object())
    assert reading.compiled is None
    assert reading.tokenizer is None
    assert reading.flavour is None


def test_reads_is_true_exactly_when_compiled_or_flavour_is_not_none() -> None:
    """``reads`` tracks the product's own capability, not a stored mode."""
    loose = Reading("r1", "loose")
    assert loose.reads is False

    grammar = Reading("r2", "grammar")
    grammar.outcome = Outcome(product=compile_text(_TOY))
    assert grammar.reads is True

    manifest = Reading("r3", "manifest")
    manifest.outcome = Outcome(product=GBNF_FLAVOUR)
    assert manifest.reads is True

    plain = Reading("r4", "text")
    plain.outcome = Outcome(product=object())
    assert plain.reads is False


def test_as_reader_returns_a_reader_for_a_compiled_grammar() -> None:
    """A compiled grammar's reading offers a reader that parses texts."""
    reading = Reading("r1", "grammar")
    reading.outcome = Outcome(product=compile_text(_TOY))
    reader = reading.as_reader()
    assert reader is not None
    assert reader.kind == "grammar"


def test_as_reader_returns_a_reader_for_a_flavour() -> None:
    """A flavour's reading offers a reader that reads grammar texts."""
    reading = Reading("r1", "manifest")
    reading.outcome = Outcome(product=GBNF_FLAVOUR)
    reader = reading.as_reader()
    assert reader is not None
    assert reader.kind == "flavour"


def test_as_reader_returns_none_for_anything_else() -> None:
    """A reading whose product cannot read others offers no reader."""
    reading = Reading("r1", "text")
    reading.outcome = Outcome(product=object())
    assert reading.as_reader() is None

    empty = Reading("r2", "loose")
    assert empty.as_reader() is None


def test_refusal_of_states_the_exception_type_and_message() -> None:
    """A refusal reads as its class name and message, not a traceback."""
    try:
        raise ValueError("boom")
    except ValueError as exc:
        assert refusal_of(exc) == "ValueError: boom"
