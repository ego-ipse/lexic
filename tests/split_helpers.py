"""Shared split-path helpers for tests that must not assume engagement.

Faithfulness and concurrency both need the same question answered — *did the
split entry actually take this document?* — and both are worthless if it is
guessed. A suite whose split silently declines still passes every equality it
asserts, having compared a sequential parse against a sequential parse.

One copy, because two would drift: the call reaches into ``split_model``'s
exact signature, and a change there should break one place rather than leave
a stale second answer behind.
"""

from __future__ import annotations

from lexic.compile import CompiledGrammar
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.products import parse_model

WORKERS = 8
"""Worker count engagement is asked at — enough that most shapes can use it."""


def engages(compiled: CompiledGrammar, text: str, cores: int = WORKERS) -> bool:
    """Whether the split entry itself takes ``text``, asked through the real entry.

    Note what this is NOT: a retained pool in ``lexic.parsing.parallel.pool``
    is no evidence of engagement, because the lease is taken before the plan
    settles. A declining grammar leaves a warm pool behind, and discovery may
    already have submitted work to it. Only ``split_model``'s result answers
    whether the split itself produced a model.

    :param compiled: The artefact whose split path is in question.
    :param text: The document to offer it.
    :param cores: The worker count to ask at.
    :returns: Whether the split produced a model rather than declining.
    """
    found = split_model(
        parse_model,
        compiled.codegen_grammar,
        Request(text, compiled.product, None),
        cores,
        analysis=compiled.split_analysis or compiled.grammar,
    )
    return found is not None


LEAD_RULE = (
    "root ::= pair tail*\n"
    "tail ::= comma pair\n"
    'comma ::= "," ws\n'
    'pair ::= [a-z]+ ":" [0-9]+\n'
    'ws ::= " "*\n'
)
"""A SEPARATED repetition: the split re-parses every cut's lead on the driver.

One copy for the same reason as :func:`engages`. Two suites need the shape
whose split does work on the submitting thread — the orchestrator's own tests
and the artefact's document-view regression — and a second spelling of it would
drift into a different shape while both still claimed to be testing this one.
"""


def lead_rule_document(pairs: int) -> str:
    """A ``LEAD_RULE`` document of ``pairs`` items, long enough to divide."""
    return ", ".join(f"key{'x' * (index % 7)}:{index}" for index in range(pairs))
