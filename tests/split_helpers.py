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


def assert_parallel_matches_sequential(
    compiled: CompiledGrammar, text: str, workers: int
):
    """The parallel answer IS the sequential one — class, model and text.

    One copy for the same reason as :func:`engages`: every suite that divides
    a document owes exactly these three, and a second spelling would drift
    into asserting less while still reading like this one. Equality alone is
    not enough — two models of different classes can compare equal field for
    field — and the round-trip is what catches a stitch that reassembled the
    right values in the wrong order.

    :param compiled: The artefact to parse with.
    :param text: The document, long enough that the split takes it.
    :param workers: The worker count to parse at.
    :returns: The sequential model, for a caller with more to ask of it.
    """
    sequential = compiled.parse(text, cores=1)
    parallel = compiled.parse(text, cores=workers)
    assert type(parallel) is type(sequential)
    assert parallel == sequential
    assert parallel.to_text() == text
    return sequential


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
