"""A noise-skip peek reads its loop's exit past the noise, as it reads the take.

At ``root ::= "!" tag? " " content end?`` with ``tag ::= " %" [a-z]+``, both
the take and the exit start with a noise character. Past it the take reads
the tag's ``%``, and so does the exit when the content is prose. The gate read
the exit as its continuation less the noise alphabet, which left nothing of
the required ``" "``, so it took the tag where the exit had to stop, and the
PDA declined where Earley parses. An item that can derive only noise is read
through the same way, whatever its FIRST.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.descent.leftrec import folded_grammar
from tests.parity_helpers import DECLINED, REFUSED, answers

D3 = (
    'root ::= "!" tag? " " content end?\ntag ::= " %" [a-z]+\n'
    "content ::= list | prose\nlist ::= item (sep item)*\n"
    'item ::= [a-z]+ ws\nws ::= [ \\n]*\nsep ::= "\\n" "-"\n'
    'prose ::= "%" [a-z %\\n-]*\nend ::= " " "!"\n'
)

D3_VIEWS = {
    "plain": "",
    "lex": "# @lexical item\n",
    "lex-ns": "# @lexical item\n# @non-semantic ws sep end\n",
}

D3_TEXTS = {
    "word": "! a",
    "two-letters": "! ab",
    "prose": "! %a",
    "list": "! a\n-b",
    "word-end": "! a !",
    "tagged-list": "! %a a\n-b",
}

PURE_NOISE = {
    "group": 'root ::= "a" (ws "b")* ws x "b"\nws ::= " "*\nx ::= "dd" | " "\n',
    "pair": 'root ::= "a" pair* ws x "b"\npair ::= ws "b"\nws ::= " "*\nx ::= "dd" | " "\n',
}
"""``x`` can be noise (its ``" "`` arm) though its FIRST is not within the
noise alphabet; past the exit's noise, the next character can be the ``b``
the take reads."""

PURE_VIEWS = {
    "plain": "",
    "lex": "# @lexical x\n",
    "lex-ns": "# @lexical x\n# @non-semantic ws\n",
}


def _analysis(source: str, key: str) -> GrammarAnalysis:
    compiled = compile_text(source, cache_key=key)
    lifted = lift_optional_nullables(compiled.codegen_grammar)
    return GrammarAnalysis(folded_grammar(lifted, compiled.product)[0])


@pytest.mark.parametrize("view", D3_VIEWS)
@pytest.mark.parametrize("case", D3_TEXTS)
def test_the_pda_answers_as_earley(view: str, case: str) -> None:
    """Every D3 witness is parsed on the PDA to Earley's model, not declined."""
    predictive, gated = answers(D3_VIEWS[view] + D3, f"pes-{view}", D3_TEXTS[case])
    assert gated not in {REFUSED, DECLINED}
    assert predictive == gated


def test_the_tag_keeps_no_noise_skip_gate() -> None:
    """The premise, asserted: on the noise view ``tag?`` holds no peek gate."""
    analysis = _analysis(D3_VIEWS["lex-ns"] + D3, "pes-gates")
    root = list(analysis.rules["root"].body[0])
    assert str(root[1].atom) == "tag"
    assert id(root[1]) not in analysis.taxonomy.pn_loop_gates


@pytest.mark.parametrize("view", PURE_VIEWS)
@pytest.mark.parametrize("shape", PURE_NOISE)
@pytest.mark.parametrize("text", ["a b", "a    b", "a b  b"])
def test_an_item_that_can_be_only_noise_is_read_through(
    shape: str, view: str, text: str
) -> None:
    """The exit side walks past ``x`` as the skip can, so the loop keeps no
    noise-skip gate, and the predictive engine agrees with Earley or
    declines."""
    source = PURE_VIEWS[view] + PURE_NOISE[shape]
    key = f"pes-pure-{shape}-{view}"
    assert not _analysis(source, key).taxonomy.pn_loop_gates
    predictive, gated = answers(source, key, text)
    assert gated not in {REFUSED, DECLINED}
    assert predictive in (gated, DECLINED)
