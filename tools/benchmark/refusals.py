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

import json
from collections.abc import Callable
from functools import cache

from lexic.exceptions import LexicError
from lexic.parsing.pda.core.errors import PdaFail

LEXIC_REFUSALS: tuple[type[BaseException], ...] = (
    LexicError,
    PdaFail,
    RecursionError,
)
"""The narrow vocabulary needed by a Lexic-only worker."""


@cache
def refusals() -> tuple[type[BaseException], ...]:
    """Every engine's refusal vocabulary, imported only for competitor rows."""
    import lark
    import msgspec
    import pyparsing as pp
    from parsimonious.exceptions import (
        BadGrammar,
        IncompleteParseError,
        ParseError,
        VisitationError,
    )

    return (
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
        *LEXIC_REFUSALS,
        # The json-format specialists refusing an input: stdlib's decoder error
        # is a narrow ValueError subclass, so our own bugs still crash through.
        json.JSONDecodeError,
        msgspec.DecodeError,
    )


def accepts(
    parse: Callable[[str], object],
    text: str,
    exceptions: tuple[type[BaseException], ...] | None = None,
) -> bool:
    """Whether ``parse`` takes ``text`` whole, however it spells refusal.

    :param parse: An engine's parse entry point.
    :param text: The input to offer it.
    :returns: True if it parsed, False if it refused in a known vocabulary.
    :raises BaseException: Anything outside :func:`refusals`, unchanged — an
        unexpected error is our bug, not the engine's verdict on the grammar.
    """
    return refusal(parse, text, exceptions) is None


def refusal(
    parse: Callable[[str], object],
    text: str,
    exceptions: tuple[type[BaseException], ...] | None = None,
) -> str | None:
    """The engine's OWN words for refusing ``text``, or None if it took it.

    The message is the evidence. "cannot express this grammar" with nothing
    behind it is how emitter bugs survive long enough to be believed — every one
    of them said what was wrong in an exception nobody printed.
    """
    try:
        parse(text)
    except refusals() if exceptions is None else exceptions as exc:
        detail = " ".join(str(exc).split())
        return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
    return None
