"""Tests for ``lexic.parsing.parallel.discovery.anchors`` — the split-point analysis.

A character is an anchor iff at least one site emits it, no co-finite site
can (opaque interiors: string bodies, comments, token terminals), and no
derived run charset contains it. Multi-site anchors are legitimate — the
site map is the disambiguation hypothesis set; single-site pinning is the
derived property ``len(sites) == 1``, not the definition.
"""

from __future__ import annotations

from lexic.compile import parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrAlphabet, IrAst, IrLiteral, IrRule, IrSeq, IrSequence
from lexic.parsing.parallel import anchor_sites, anchors

JSONISH = """\
root ::= object
object ::= "{" ws member ("," ws member)* "}"
member ::= string ws ":" ws value
value ::= object | string | "true" | "false" | "null"
string ::= quote chars quote
quote ::= "\\""
chars ::= [a-z]*
ws ::= [ \\t\\n]*
"""


def test_structural_characters_anchor_a_jsonish_grammar():
    """Brackets, comma, colon and the quote pass the certificate."""
    got = anchors(parse_grammar(JSONISH, GBNF_FLAVOUR))
    assert got == frozenset('{},:"')


def test_keyword_letters_fall_to_the_run_filter():
    """``t`` (in ``true`` AND ``chars``) and ``b`` (``chars`` only) both land
    inside the derived maximal-munch run — a boundary there is refused."""
    got = anchors(parse_grammar(JSONISH, GBNF_FLAVOUR))
    assert "t" not in got
    assert "b" not in got


def test_a_cofinite_class_decertifies_the_characters_it_covers():
    """``[^}]`` can emit ``{``, so an occurrence of ``{`` may be interior
    text — no anchor; ``}`` is excluded from the class and stays."""
    ast = parse_grammar('root ::= "{" [^}]* "}"', GBNF_FLAVOUR)
    assert anchors(ast) == frozenset("}")


def test_a_char_inside_a_derived_run_is_not_an_anchor():
    """Letters of ``[a-z]+`` land inside the run — only ``=`` survives."""
    ast = parse_grammar('root ::= "=" [a-z]+', GBNF_FLAVOUR)
    assert anchors(ast) == frozenset("=")


def test_a_token_terminal_kills_char_anchors():
    """An ``IrAlphabet`` site matches ids, not chars — conservatively ANY, an
    opaque interior covering everything."""
    rule = IrRule("root", IrSequence(IrAlphabet("tok", IrLiteral("x")), IrLiteral(",")))
    assert anchors(IrAst(IrSeq(rule), "root")) == frozenset()


def test_multi_site_structural_characters_qualify():
    """Two literal sites sharing chars still certify — every occurrence is
    structural; WHICH site is the orchestrator's question, via the site map."""
    ast = parse_grammar('root ::= x y\nx ::= "ab"\ny ::= "ba"', GBNF_FLAVOUR)
    assert anchors(ast) == frozenset("ab")
    sites = anchor_sites(ast)
    assert sites["a"] == ("x", "y")
    assert sites["b"] == ("x", "y")


def test_site_map_names_the_defining_rules():
    """Each anchor maps to the rules whose sites emit it, definition order."""
    sites = anchor_sites(parse_grammar(JSONISH, GBNF_FLAVOUR))
    assert sites['"'] == ("quote",)
    assert sites[","] == ("object",)
    assert sites[":"] == ("member",)


def test_memoised_per_grammar_identity():
    """Repeated calls return the very same objects — one analysis memo."""
    ast = parse_grammar(JSONISH, GBNF_FLAVOUR)
    assert anchors(ast) is anchors(ast)
    assert anchor_sites(ast) is anchor_sites(ast)
