"""Shared fixtures for the ``lexic.parsing.pda.compiler`` unit tests."""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.delegate_compile import DelegateSource
from tests.unit.lexic.parsing.parsing_helpers import prod

# An alternation island (``item``: both arms share FIRST ``[0-9]``) with a long
# island-free interior run (``digits``); ``wrapped`` references the ``item``
# island (an island-referencing rule the floor must exclude); ``short`` is a
# below-floor bounded literal.
G = """root ::= item wrapped
item ::= a | b
a ::= digits "x"
b ::= digits "y"
digits ::= [0-9]+
wrapped ::= "<" item ">"
short ::= "z"
"""


def compiled():
    """Compile ``G`` and return its (analysis, DelegateSource, CompiledGrammar)."""
    cg = compile_text(G, cache_key="delegate-compile-unit")
    assert prod(cg).pda is not None
    source = prod(cg).pda.program.delegates
    assert isinstance(source, DelegateSource)
    lifted = source.lifted
    return GrammarAnalysis(lifted), source, cg
