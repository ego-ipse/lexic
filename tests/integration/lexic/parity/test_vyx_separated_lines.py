"""vyx bodies whose lines a `\\n` separates, read by the predictive engine as
Earley reads them.

A line's run that can take the separator's `\\` asks whether stopping there
goes on. Inside a later line, the stop goes on into ``inline-content``'s next
iteration, which the frame the line stands in repeats. And where readings that
came through later splits meet, what each built before those splits is part of
what they are compared by.
"""

from __future__ import annotations

import pytest

from lexic.parsing.pda.core.errors import PdaFail
from tests.integration.lexic.parity.pda_parity_helpers import (
    VYX_VIEWS,
    pda_and_earley,
    vyx_view,
)

LATER_LINES = [
    "!R -:\\na\\nk= >",
    "!R %a -:\\na\\nk= >",
    "!R %a D:{}\\n&\\nk= >",
]
"""A second line's ``nl-head`` before a third line. It stands inside
``inline-content``'s repeated ``("\\\\" "n" body-line)``, whose next iteration
takes the `\\`. Read as a dead stop, the run took the separator and the third
line's ``k`` (a decline), and under a budget the reading without it survived
(a wrong model). On the lexical views ``nl-head`` is a stop-set that runs
longest, through the separator, and the packet declines."""

CROSS_WAY = [
    "!R k=\\n-:\\n# c >",
    "!X:A k=\\nD:{}\\n# x >",
]
"""``k``'s value may run on through the separator. Its boundary's readings
meet past a later split, one keeping the value and one settling ``value?``
without it. Compared only by what each built since that later split, they read
as equal, the merge kept the reading without the value, and the set decided
for the way it came by: a wrong model."""


@pytest.mark.parametrize("text", LATER_LINES)
def test_a_later_line_stops_at_its_separator(text: str) -> None:
    """On plain the line's attempt loop asks the stop, and the model is Earley's."""
    got, want = pda_and_earley(vyx_view("plain", "vyx-separated"), text)
    assert got == want


@pytest.mark.xfail(raises=PdaFail, strict=True, reason="nl-head runs longest")
@pytest.mark.parametrize("view", ["lex", "lexns"])
@pytest.mark.parametrize("text", LATER_LINES)
def test_a_later_line_on_a_lexical_view_runs_through_its_separator(
    view: str, text: str
) -> None:
    """Open on the lexical views: the run takes the separator and declines."""
    got, want = pda_and_earley(vyx_view(view, "vyx-separated"), text)
    assert got == want


@pytest.mark.parametrize("view", VYX_VIEWS)
@pytest.mark.parametrize("text", CROSS_WAY)
def test_readings_that_met_are_compared_by_what_they_built(
    view: str, text: str
) -> None:
    """Each packet's predictive model is Earley's, on every view."""
    got, want = pda_and_earley(vyx_view(view, "vyx-separated"), text)
    assert got == want


SEPARATED_ENDS = "!X:Y }\\n# n\\\\n\\#\\n\\n\\n\\n >"
"""Escaped lines run on through every separator after them, so a set holds two
readings at each one: the line read as ``nl-escape`` and as ``nl-force``.
They stand at one place without meeting until a character on, and the readings
behind keep adding pairs ahead; the set passed its bound and the packet
declined."""


def test_readings_crowded_ahead_meet_before_the_set_forks() -> None:
    """The packet's predictive model is Earley's, on plain."""
    got, want = pda_and_earley(vyx_view("plain", "vyx-separated"), SEPARATED_ENDS)
    assert got == want


RELIEVED_AGAIN = '!X:Q o:"" L7716< a\\n# \\n# \\n# \\n\\#\\n\\#\\n}\\n\\n# \\n >'
"""More lines that run on through the separators after them: one round of
relief meets the pairs that stood together, but the readings it drives on split
into pairs of their own further ahead, and the set was still past its bound."""


def test_relief_goes_on_while_the_set_is_past_its_bound() -> None:
    """The packet's predictive model is Earley's, on plain."""
    got, want = pda_and_earley(vyx_view("plain", "vyx-separated"), RELIEVED_AGAIN)
    assert got == want
