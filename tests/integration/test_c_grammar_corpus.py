"""Deepened c.gbnf corpus: statement-surface coverage.

Before this file, the suite's only c-language fixture was ``int foo(){}``
(``test_full_round_trip.py``) — a declaration with an empty body that never
exercises a single ``statement`` alternative. A real statement-level defect
in the grammar went unnoticed for months as a result. These fixtures were
built by generating candidate strings with :func:`lexic.generate.generate`
against fixed seeds (over ``declaration``/``statement`` directly — see
``tests/property/test_roundtrip.py``'s ``c_statement_grammar`` fixture for
why ``root`` itself cannot be used), hand-picking readable ones, and pinning
them here as literals so each fixture stays legible and its exact coverage
is visible in the parametrize table.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path
from tests.paths import GROUND_TRUTH

# Each entry documents which statement kind(s)/structural feature it covers.
_FIXTURES = [
    pytest.param("int foo(){}float bar(){}", id="multiple-declarations"),
    pytest.param(
        "int add(int x){int y = 1;return y;}",
        id="parameter+declare-assign+return",
    ),
    pytest.param("int f(){x = 2;}", id="assignment-statement"),
    pytest.param("int f(){foo (1, 2);}", id="function-call-statement"),
    pytest.param("int f(){return x;}", id="return-statement"),
    pytest.param("int f(){while(x<1){return x;}}", id="while-statement"),
    pytest.param(
        "int f(){for(i = 0; i<10; i = i+1){x = x+i;}}",
        id="for-statement-identifier-init",
    ),
    pytest.param(
        "float f(int n){for(int i = 0; i<n; i = i+1){}}",
        id="for-statement-declared-init",
    ),
    pytest.param(
        "int f(){if(x<1){return x;}else{return 0;}}",
        id="if-else-statement",
    ),
    pytest.param("int f(){//comment\n}", id="single-line-comment-statement"),
    pytest.param("int f(){/* comment */}", id="multi-line-comment-statement"),
    pytest.param(
        "int f(){if(x<1){while(y<2){return y;}}foo (1);}",
        id="nested-blocks-if-in-while-plus-call",
    ),
    pytest.param(
        "char f(float p){/* c */if(a<=b){x = 1;}else{//line\n}return x;}",
        id="mixed-comments-if-else-nested-in-declaration",
    ),
    pytest.param(
        "int add(int x, int y){return x;}",
        id="two-parameter-declaration",
    ),
    pytest.param(
        "int add(int x, int y, char z){return x;}",
        id="three-parameter-declaration",
    ),
]


@pytest.mark.parametrize("text", _FIXTURES)
def test_c_grammar_statement_surface_round_trips(text: str) -> None:
    """Each fixture both parses against c.gbnf and round-trips exactly."""
    cg = compile_from_path(GROUND_TRUTH / "c.gbnf")
    model = cg.parse(text)
    assert model.to_text() == text, (
        f"round-trip mismatch.\n  source:  {text!r}\n  to_text: {model.to_text()!r}"
    )
