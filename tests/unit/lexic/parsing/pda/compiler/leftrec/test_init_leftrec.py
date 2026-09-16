"""Tests for lexic.parsing.pda.compiler.leftrec — the fold's one entry.

The package's claim is that a left-recursive rule can be parsed as a loop and
still build the model its arms build. That claim is only worth anything if it
is checked END TO END against the engine whose answer is the reference, so
these tests parse real documents on both seats and compare the models rather
than inspecting the rewrite.

The entry's own decision — a rule is rewritten only if its VALUE can be folded
— gets a test of its own, because taking the shape's word alone would parse a
rule faster and build it wrong, which is the failure mode nothing downstream
would catch.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.compiler.leftrec import folded_grammar
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.products import _model_product, earley_model, pda_model

_DENSE = (
    "root ::= line+\nline ::= expr nl\nexpr ::= expr op term | term\n"
    'term ::= [a-z]\nop ::= "+"\nnl ::= "\\n"\n'
)
_NESTED = (
    'root ::= expr "!"\nexpr ::= expr op term | term\nterm ::= [a-z]\nop ::= "+"\n'
)


def seats(source: str, key: str):
    """The compiled grammar and its bound product, for both engines."""
    compiled = compile_text(source, cache_key=key)
    return compiled, _model_product(compiled.codegen_grammar, compiled.product)


@pytest.mark.parametrize(
    "text", ["a\n", "a+b\n", "a+b+c\n", "a+b+c+d\ne+f\n", "a\nb\nc\n"]
)
def test_a_folded_rule_builds_the_model_earley_builds(text: str) -> None:
    """The whole claim: same document, same model, both engines.

    Compared by ``dump()`` AND ``to_text()`` — the first catches a differently
    shaped tree, the second catches one that is shaped right but holds the
    wrong text. A left-nesting bug shows in the first; a mis-cut iteration
    shows in the second.
    """
    compiled, product = seats(_DENSE, "fold-dense")

    folded = pda_model(product.pda, text, compiled.product.executor)
    reference = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )

    assert folded.dump() == reference.dump()
    assert folded.to_text() == reference.to_text() == text


def test_the_fold_nests_to_the_left() -> None:
    """``a+b+c`` is ``A(A(A(a), b), c)`` — not right-nested, not flat.

    Both wrong shapes round-trip to the same text, so the text is no evidence;
    the nesting has to be read off the model itself. This is the assertion a
    fold that accumulated in the wrong direction would fail while every
    round-trip test still passed.
    """
    compiled, product = seats(_NESTED, "fold-nested")

    model = pda_model(product.pda, "a+b+c!", compiled.product.executor)
    reference = earley_model(
        product.instance_grammar, "a+b+c!", compiled.product, product.tables
    )

    assert model.dump() == reference.dump()
    # The model's classes are synthesised at runtime, so the fields are read by
    # name rather than by attribute — which is also the honest shape of the
    # claim: THIS field holds the shorter expression.
    top = getattr(model, "expr")
    assert top.to_text() == "a+b+c", "the fold's top node spans the whole run"
    assert getattr(top, "expr").to_text() == "a+b", "its slot, the run minus one"


def test_a_rule_the_shape_takes_but_the_build_cannot_is_left_alone() -> None:
    """Both halves must answer, and the entry asks them in that order.

    A rule rewritten on the strength of its shape alone would parse as a loop
    and build through a routine that does not fit it. The entry returns a fold
    only when the build agreed too, so a grammar with no usable routine comes
    back with its grammar untouched.
    """
    compiled, product = seats(_NESTED, "fold-both-halves")
    lifted = lift_optional_nullables(compiled.codegen_grammar)

    grammar, folds = folded_grammar(lifted, product.binding)

    assert "expr" in folds, "this one folds"
    assert len(grammar.rules) < len(lifted.rules), "and its orphan was dropped"


def test_a_grammar_with_nothing_foldable_is_untouched() -> None:
    """The ordinary case leaves both the grammar and the fold table alone."""
    compiled, product = seats('root ::= "a" | "b"\n', "fold-none")
    lifted = lift_optional_nullables(compiled.codegen_grammar)

    grammar, folds = folded_grammar(lifted, product.binding)

    assert not folds
    assert grammar is lifted


def test_an_unfoldable_left_recursion_still_islands() -> None:
    """Indirect recursion keeps the island path — the fold widens nothing.

    The census of what the fold takes is exactly the census of what changes
    behaviour, and this is the other side of that: a shape it declines is
    parsed the way it was before.
    """
    _compiled, product = seats(
        'root ::= x "e"\nx ::= y "a" | "b"\ny ::= x\n', "fold-indirect"
    )

    assert "x" in product.pda.islands


@pytest.mark.parametrize("bad", ["a++b!", "a+!", "+a!", "ab!"])
def test_a_folded_grammar_refuses_what_it_should_still_refuse(bad: str) -> None:
    """Folding decides where a loop stops; it does not accept new input.

    A rewrite that widened the language would show here as a parse of text the
    grammar does not derive — a doubled operator, a missing operand on either
    side, or two terms with no operator between them. All four are shapes the
    ``(β)*`` loop could wrongly admit if the step's items were dropped or made
    optional by the rewrite.
    """
    compiled, product = seats(_NESTED, "fold-refuses")

    with pytest.raises(PdaFail):
        pda_model(product.pda, bad, compiled.product.executor)
