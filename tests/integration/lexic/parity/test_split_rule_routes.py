"""What each route answers when the start symbol derives the input twice over.

A key's families are carvings of the span it covers. Where they name one arm
over different spans the grammar has not said which slot owns the text, so the
split rule does — the FIRST slot takes as much as it can — and that answer is
never a refusal. Where they name different arms the grammar said two things and
only a resolver or a refusal settles it.

The two questions meet at a ROOT-ambiguous span, where the start symbol
completes the whole input through more than one production. Those productions
are not families of one key — they live in separate accepting items — so the
reader has to be asked about each in turn. A route that gives up at the first
sight of root ambiguity and takes the enumeration's first instead is answering
by CHART ORDER, and it answers the span's splits that way too: the caller
supplied a resolver to settle the choice of ARM, and got a carving nobody
chose.

``ROOT_AMBIGUOUS`` is built so the two questions are separable. Its first
production carves ``"xxxxxx"`` three ways with two slots trading against each
other, where left-to-right gives ``(3, 1, 2)`` and right-to-left gives
``(2, 3, 1)``; its second production takes the same span as one run. So the arm
choice is real, the split under it has a defined answer, and the two readings
of that split are different tuples — which is what makes the wrong answer
visible instead of merely unproven. With the reader skipped, this grammar
reports ``(2, 3, 1)``: chart order here IS the right-to-left reading.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing import parse
from lexic.parsing.earley.kernel.forest.fasttree import ParseTree
from lexic.parsing.products import _model_product, earley_model
from tests.unit.lexic.parsing.parsing_helpers import engines_agree_or_both_refuse

PURE_SPLIT = 'doc ::= a b c\na ::= "xx" "x"?\nb ::= "x" "xx"?\nc ::= "x"+\n'
"""One production, carved two ways — a split, with an answer and no ambiguity."""

ROOT_AMBIGUOUS = (
    'doc ::= a b c | r\na ::= "xx" "x"?\nb ::= "x" "xx"?\nc ::= "x"+\nr ::= "x" "x"+\n'
)
"""The same carving, plus a second production of the START rule over the span.

A first attempt used a fixed six-character literal for the second production
and proved nothing: with the reader skipped, chart order happened to give the
rule's own answer there, so reinstating the defect left every assertion
passing. This shape separates them.
"""


def _product(source: str, key: str):
    """Compile ``source``; return the compiled grammar and its model product."""
    compiled = compile_text(source, cache_key=key)
    return compiled, _model_product(compiled.codegen_grammar, compiled.product)


def _model(source: str, key: str, text: str, resolve=None):
    """``text``'s model through the Earley model route."""
    compiled, product = _product(source, key)
    return earley_model(
        product.instance_grammar, text, compiled.product, product.tables, resolve
    )


def _take_the_other(_first: ParseTree, other: ParseTree) -> ParseTree:
    """The resolver that keeps the derivation it is offered as the ALTERNATIVE.

    ``Resolver`` is handed the derivation in hand and one that means something
    else, and either choice is legitimate — what matters is that both are the
    readings the rule produces. Deterministic, so both engines answer alike.
    """
    return other


def _take_the_first(first: ParseTree, _other: ParseTree) -> ParseTree:
    """The degenerate resolver from ``Resolver``'s own docstring."""
    return first


def _widths(model) -> tuple[int, ...]:
    """How many characters each of the model's fields covers."""
    return tuple(len(part.to_text()) for part in model)


def test_a_resolver_settles_the_arm_and_the_rule_settles_the_split() -> None:
    """The row the defect is found on: widths, not merely a value.

    ``"xxxxxx"`` derives through both productions, so the caller supplies a
    resolver about ARMS — and the carving under the arm it gets is the split
    rule's, ``(3, 1, 2)``. With the reader skipped on a root-ambiguous chart
    the route takes the enumeration's first instead, and on this grammar that
    is ``R('xxxxxx')``: the caller's resolver never sees the carved production
    at all.
    """
    model = _model(ROOT_AMBIGUOUS, "routes-root", "xxxxxx", _take_the_other)

    assert repr(model) == "DocArm1(A('xxx'), B('x'), C('xx'))"
    assert _widths(model) == (3, 1, 2)
    assert model.to_text() == "xxxxxx"


def test_the_other_resolver_gets_the_other_production_and_not_a_carving() -> None:
    """The same span from the other side, which is where ``(2, 3, 1)`` shows up.

    Keeping the derivation in hand gives the uncarved production. With the
    reader skipped the two answers TRADE: this resolver gets a carving, and it
    is ``(2, 3, 1)`` — the right-to-left reading the module docstring names as
    the wrong one. So the pair of rows pins the fix from both ends.
    """
    model = _model(ROOT_AMBIGUOUS, "routes-root", "xxxxxx", _take_the_first)

    assert repr(model) == "R('xxxxxx')"


def test_the_arm_choice_itself_still_refuses_without_a_resolver() -> None:
    """Deciding the split may not decide the arm.

    Two productions of the start symbol derive the span and mean different
    things. Nothing about lengths settles that, so with no resolver the span
    refuses — the fix is not "refuse less".
    """
    with pytest.raises(UnsupportedConstructError, match="ambiguous"):
        _model(ROOT_AMBIGUOUS, "routes-root", "xxxxxx")


@pytest.mark.parametrize(
    ("text", "widths"),
    [("xxxxxxx", (3, 3, 1)), ("xxxxxxxx", (3, 3, 2))],
)
def test_the_neighbouring_lengths_answer_without_any_resolver(
    text: str, widths: tuple[int, ...]
) -> None:
    """Longer spans, where the carving moves and the rule still governs it.

    Kept beside the rows above so the ``(3, 1, 2)`` is not mistaken for a
    constant: ``a`` takes as much as it can, then ``b``, and ``c`` keeps the
    remainder. Each of these is derived by hand from that sentence.
    """
    model = _model(ROOT_AMBIGUOUS, "routes-root", text, _take_the_other)

    assert _widths(model) == widths
    assert model.to_text() == text


def test_the_model_route_answers_a_pure_split_with_no_resolver() -> None:
    """Without the second production the same span is not ambiguous at all.

    This is the control for the row above: the carving is identical, and the
    only difference is that no second ARM exists. A split has an answer, so the
    model route gives it and asks nobody.
    """
    model = _model(PURE_SPLIT, "routes-pure", "xxxxxx")

    assert _widths(model) == (3, 1, 2)


def test_parse_still_refuses_that_pure_split() -> None:
    """And the RAW family still refuses it — the two families differ by design.

    ``parse`` answers about derivations, not values: it is asked for THE single
    derivation and there are two, so it refuses. The split rule governs the
    model route, which is asked a different question. Nothing in this change
    may quietly make the raw reader take a policy's answer.
    """
    _compiled, product = _product(PURE_SPLIT, "routes-pure")
    with pytest.raises(UnsupportedConstructError):
        parse(product.instance_grammar, "xxxxxx")


@pytest.mark.parametrize("text", ["xxxxx", "xxxxxx", "xxxxxxx"])
def test_the_engines_answer_these_spans_the_same_way(text: str) -> None:
    """Both engines, or both refusals, or the composed entry equals the gated one.

    The predictive path DECLINES every one of these — its loop gate will not
    settle two slots that trade against each other — so what this row actually
    asserts is the third branch: the route a caller uses, PDA first with Earley
    completion, answers exactly what the gated engine answers. That is stated
    here rather than left implicit, because a row that silently compared
    nothing would pass for the wrong reason.
    """
    compiled, _unused = _product(ROOT_AMBIGUOUS, "routes-root")
    verdict = engines_agree_or_both_refuse(compiled, text, _take_the_other)

    assert verdict == "declined", (
        f"{text!r}: the predictive path answered ({verdict}) — this row now "
        f"compares two engines and its docstring is out of date"
    )


# ── `X Y+` with a NON-nullable item — still a split ────────────────────


X_Y_PLUS = 'root ::= "x" y+\ny ::= "a" "a"?\n'
"""A repetition whose item cannot be empty, and which still carves.

`y` derives `a` or `aa`, so `xaaa` is two items either way — `(2, 1)` or
`(1, 2)` — and the grammar does not say which. Nullability is what the
split-greedy licence's exchange argument needs; it is NOT what makes a
repetition carve. A non-nullable item with a variable extent carves too, and
the split rule is what answers.
"""


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("xa", ("a",)),
        ("xaa", ("aa",)),
        ("xaaa", ("aa", "a")),  # the first slot takes as much as it can
        ("xaaaa", ("aa", "aa")),
    ],
)
def test_a_non_nullable_item_still_carves_and_the_first_slot_wins(
    text: str, expected: tuple[str, ...]
) -> None:
    """Both routes give the split rule's answer, and it is first-slot-maximal.

    `xaaa` is the witness: `(2, 1)` and `(1, 2)` are both legal readings, so
    the decision is a SPLIT rather than a lookahead conflict, and both engines
    must give the same carving — the one where the first slot takes what it can.
    """
    compiled = compile_text(X_Y_PLUS, cache_key="xy-plus-split")
    product = _model_product(compiled.codegen_grammar, compiled.product)
    gated = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    verdict = engines_agree_or_both_refuse(compiled, text)

    assert verdict != "declined", "both routes should answer this shape"
    assert tuple(one.to_text() for one in gated[0]) == expected
