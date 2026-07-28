"""What each engine raises when it declines a grammar or an input.

Every competitor refuses in its own unrelated exception hierarchy, which invites
a bare `except Exception` at each call site. That is wrong twice over: it
swallows OUR bugs and prints them as "cannot express this grammar" — the failure
mode that has misled this benchmark repeatedly — and it duplicates the same
block between the runner and its differential test.

So the vocabulary is named, once, here. An exception outside it is not a refusal
and must CRASH: a benchmark that reports an unexpected error as a capability
limit is worse than one that stops.
"""

from __future__ import annotations

from collections.abc import Callable

import lark
import pyparsing as pp
from parsimonious.exceptions import (
    BadGrammar,
    IncompleteParseError,
    ParseError,
    VisitationError,
)

from lexic.exceptions import LexicError
from lexic.parsing.pda.core.errors import PdaFail

REFUSALS: tuple[type[BaseException], ...] = (
    lark.exceptions.LarkError,
    ParseError,
    IncompleteParseError,
    VisitationError,
    BadGrammar,
    pp.ParseBaseException,
    # ANTLR: the strict error listener turns its recover-and-continue default
    # into a raise, and the Java bridge reports a refused parse the same way.
    SyntaxError,
    # The ANTLR toolchain itself declining to build a grammar.
    RuntimeError,
    # lexic's own refusals, for the rows lexic parses. `PdaFail` is the
    # predictive engine declining a grammar (an island start rule, say) — a
    # real result about that engine, and the Earley column still answers.
    LexicError,
    PdaFail,
    RecursionError,
)
"""Every way an engine here says no. Anything else is a bug and should surface."""


def accepts(parse: Callable[[str], object], text: str) -> bool:
    """Whether ``parse`` takes ``text`` whole, however it spells refusal.

    :param parse: An engine's parse entry point.
    :param text: The input to offer it.
    :returns: True if it parsed, False if it refused in a known vocabulary.
    :raises BaseException: Anything outside :data:`REFUSALS`, unchanged — an
        unexpected error is our bug, not the engine's verdict on the grammar.
    """
    return refusal(parse, text) is None


def refusal(parse: Callable[[str], object], text: str) -> str | None:
    """The engine's OWN words for refusing ``text``, or None if it took it.

    The message is the evidence. "cannot express this grammar" with nothing
    behind it is how emitter bugs survive long enough to be believed — every one
    of them said what was wrong in an exception nobody printed.
    """
    try:
        parse(text)
    except REFUSALS as exc:
        detail = " ".join(str(exc).split())
        return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
    return None
