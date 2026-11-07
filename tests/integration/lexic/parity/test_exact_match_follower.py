"""An exact-match noise gate must not take the text of its loop's follower.

``ws*`` before a required ``nl``: where a complete ``ws`` unit is the whole of
``nl``'s text, or a proper prefix of it, the gate took it as one more
iteration, ``nl`` found nothing, and the PDA declined where Earley parses. The
follower reads past a required item that can vanish and, where the arm ends,
into the caller. Such a loop takes the attempt licence instead.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.gates import structured
from lexic.parsing.pda.compiler.descent.leftrec import folded_grammar
from lexic.parsing.pda.core.scanner import SG_MATCH, ScanGate
from tests.parity_helpers import DECLINED, REFUSED, answers
from tests.unit.lexic.parsing.ir_fixtures import body_items

LOOP = 'root ::= "a" ws* nl "b"\n'
COMMENT = 'ws ::= " " | cl\ncl ::= "#" [a-z]* "\\n"\n'
PREFIX = 'ws ::= " " | cm\ncm ::= "#" [a-z]*\n'

GRAMMARS = {
    "whole": LOOP + COMMENT + "nl ::= cl\n",
    "whole-spelled": LOOP + COMMENT + 'nl ::= "#" [a-z]* "\\n"\n',
    "whole-in-a-reading": (
        'root ::= "!" tag? " " content\ntag ::= " %" [a-z]+\ncontent ::= line | prose\n'
        'line ::= "a" ws* nl "b"\nprose ::= "%" [a-z %#\\n]*\n'
        + COMMENT
        + "nl ::= cl\n"
    ),
    "prefix": LOOP + PREFIX + 'nl ::= cm "\\n"\n',
    "prefix-spelled": LOOP + PREFIX + 'nl ::= "#" [a-z]* "\\n"\n',
    "prefix-dashed": LOOP + 'ws ::= " " | cm\ncm ::= "--" [a-z]*\nnl ::= cm ";"\n',
    "past-vanishing": 'root ::= "a" ws* e nl "b"\ne ::= "!"?\n'
    + PREFIX
    + 'nl ::= cm "\\n"\n',
    "past-vanishing-run": 'root ::= "a" ws* e nl "b"\ne ::= "!"*\n'
    + COMMENT
    + "nl ::= cl\n",
    "into-the-caller": 'root ::= x nl "b"\nx ::= "a" ws*\n'
    + PREFIX
    + 'nl ::= cm "\\n"\n',
    "into-the-caller-whole": 'root ::= x nl "b"\nx ::= "a" ws*\n'
    + COMMENT
    + "nl ::= cl\n",
    "one-char": LOOP + 'ws ::= " " | "\\n"\nnl ::= "\\n"\n',
}

TEXTS = {
    "whole": ["a#\nb", "a#x\nb", "a #x\nb", "a#x\n#y\nb"],
    "whole-spelled": ["a#x\nb", "a #x\nb"],
    "whole-in-a-reading": ["! %a a#x\nb", "! a#x\nb"],
    "prefix": ["a#x\nb", "a#\nb", "a #x\nb", "a#x #y\nb", "a#xy\nb"],
    "prefix-spelled": ["a#x\nb", "a#x #y\nb"],
    "prefix-dashed": ["a--x;b", "a --x;b", "a--x --y;b"],
    "past-vanishing": ["a#x\nb", "a!#x\nb", "a #x\nb"],
    "past-vanishing-run": ["a#x\nb"],
    "into-the-caller": ["a#x\nb", "a #x\nb"],
    "into-the-caller-whole": ["a#x\nb", "a #x\nb"],
    "one-char": ["a\nb", "a \n\nb"],
}

VIEWS = {
    "plain": "",
    "lex": "# @lexical cl cm\n",
    "lex-ns": "# @lexical cl cm\n# @non-semantic ws nl cl cm e\n",
}

ROWS = [(name, text) for name, texts in TEXTS.items() for text in texts]


@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize(("grammar", "text"), ROWS)
def test_the_pda_answers_as_earley(view: str, grammar: str, text: str) -> None:
    """Every witness, and the one-character control, is parsed on the PDA to
    Earley's model, not declined."""
    predictive, gated = answers(
        VIEWS[view] + GRAMMARS[grammar], f"emf-{view}-{grammar}", text
    )
    assert gated not in {REFUSED, DECLINED}
    assert predictive == gated


def _analysis(source: str, key: str) -> GrammarAnalysis:
    compiled = compile_text(source, cache_key=key)
    lifted = lift_optional_nullables(compiled.codegen_grammar)
    return GrammarAnalysis(folded_grammar(lifted, compiled.product)[0])


@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize("grammar", [name for name in GRAMMARS if name != "one-char"])
def test_every_refused_loop_lands_on_the_attempt_licence(
    view: str, grammar: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cascade still asks its later tiers before the attempt licence, so
    a refusal is no route by construction: every loop the check refuses must
    carry the attempt licence. On the noise view it refuses at least once."""
    check = structured.exact_against_follower
    refused: dict[int, object] = {}

    def recorded(analysis, unit, rest, scope):
        exact = check(analysis, unit, rest, scope)
        if not exact:
            refused[id(unit)] = unit
        return exact

    monkeypatch.setattr(structured, "exact_against_follower", recorded)
    analysis = _analysis(VIEWS[view] + GRAMMARS[grammar], f"emf-land-{view}-{grammar}")
    loops = [item for item in body_items(analysis) if id(item.atom) in refused]
    assert len(loops) == len(refused)
    assert all(id(item) in analysis.taxonomy.loops.attempt for item in loops)
    assert refused or view != "lex-ns", "no refusal on the noise view — nothing tested"


def test_only_the_follower_check_takes_the_gate_away(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The premise: the whole-unit loop reaches the exact-match gate."""

    def match_gates(key: str) -> list[str]:
        analysis = _analysis(VIEWS["lex-ns"] + GRAMMARS["whole"], key)
        gates = analysis.taxonomy.ready_loop_gates
        return [
            f"{rule}: {item.atom}"
            for rule, body in analysis.rules.items()
            for arm in body.body
            for item in arm
            if isinstance(gate := gates.get(id(item)), ScanGate) and gate[0] == SG_MATCH
        ]

    assert match_gates("emf-head") == []
    monkeypatch.setattr(structured, "exact_against_follower", lambda *_a: True)
    assert match_gates("emf-stub") == ["root: ws"]
