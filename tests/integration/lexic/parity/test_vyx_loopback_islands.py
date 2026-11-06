"""vyx packets the predictive engine declined while a loop met a loopback.

``nl-force``, ``nl-escape`` and ``unquoted`` each run a loop whose FIRST holds a
character only a repetition's next iteration takes after it. Taken longest,
their islands saw two ends that could compose and refused, and the refusal
either declined the packet or, inside a live set's reading, left its boundary
undecided. Islanded whole, they answer as Earley does.
"""

from __future__ import annotations

import pytest

from lexic.compile import Directives, compile_text
from tests.integration.lexic.parity.pda_parity_helpers import pda_and_earley
from tests.paths import GROUND_TRUTH
from tools.benchmark.cases.directives import DIRECTIVES

_LEX, _NS = DIRECTIVES["vyx"]
_VIEWS = {
    "plain": Directives(),
    "lex": Directives(lexical=frozenset(_LEX)),
    "lexns": Directives(lexical=frozenset(_LEX), non_semantic=frozenset(_NS)),
}

PACKETS = [
    "!I %hqPN5 v:_ n:345 # \\nD:{} >\n",
    "T:c=n:6 n:9 n:9\n!X:C D:{}\\nD:{}\\n\\# >\n",
    'T:E=n:3 n:5 n:924\n!H - ""\\nD:{}\\nD:{}\\n#  >\n',
    "S:o={e}\nS:E={s}\nS:S={u}\n!A # \U000d0e3a >\n",
    "T:BP=&Lj ^0\n!X:QH %qe L52<   \U000a1681=\\nD:{} >\n",
]
"""Generated packets (seeds 267, 234, 144, 150, 186) — the smallest of each
refusal the islands removed: an attempt loop's boundary left undecided, and
``nl-escape``, ``nl-force`` and ``unquoted`` refusing their own ends."""


@pytest.mark.parametrize("view", sorted(_VIEWS))
@pytest.mark.parametrize("text", PACKETS)
def test_a_packet_through_a_loopback_run_parses_as_earley_parses_it(
    view: str, text: str
) -> None:
    """Each packet's predictive model is Earley's, on every view."""
    source = (GROUND_TRUTH / "vyx.gbnf").read_text()
    compiled = compile_text(
        source, cache_key=f"vyx-loopback-{view}", directives=_VIEWS[view]
    )
    got, want = pda_and_earley(compiled, text)
    assert got == want


LEXICAL_PACKETS = [
    "!R k=\\na\\n& >",
    "!R k=\\n-:\\nx/y: z >",
]
"""On the lexical views, ``unquoted`` islands too. In ``k=\\na\\n&`` the value's
island ends after ``\\na`` or after ``\\na\\n``: the ends are the whole outcome
of ``value``'s attempt, so they reach ``value?``'s attempted iteration, which
ranks them beside the stop. Kept by the island alone, the longer end died and
``value`` was dropped. In the second, a reading's side settled one attempted
iteration twice, once inherited from the reading and once read off its own
stack, and crashed."""


@pytest.mark.parametrize("view", ["lex", "lexns"])
@pytest.mark.parametrize("text", LEXICAL_PACKETS)
def test_a_value_islanded_whole_is_ranked_by_its_iteration(
    view: str, text: str
) -> None:
    """The predictive model is Earley's."""
    source = (GROUND_TRUTH / "vyx.gbnf").read_text()
    compiled = compile_text(
        source, cache_key=f"vyx-loopback-{view}", directives=_VIEWS[view]
    )
    got, want = pda_and_earley(compiled, text)
    assert got == want
