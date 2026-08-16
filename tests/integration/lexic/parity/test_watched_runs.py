"""The watched run over the corpus: the account agrees with the parse.

What this defends is the trace's reference fidelity across every formulation
the repo ships, not one hand-picked document. A trace whose spans drift from
the text, or whose rule names do not exist in the grammar it claims to
describe, is worse than no trace: it is a confident wrong answer, and a room
drawing it would co-select the wrong thing with no way to tell.

The documents come from ``lexic.generate`` at fixed seeds, so every grammar is
exercised through the standard pipeline rather than through samples chosen to
suit the watcher.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path
from lexic.parsing import TRACE_KINDS, parse_model, watch
from tests.corpus import documents
from tests.paths import GBNF_GRAMMARS, GROUND_TRUTH

APART = frozenset({"think.gbnf", "vyx.gbnf"})
"""Token-terminal grammars: their input is a token segmentation rather than
characters, so a character span means something else there."""

CORPUS = tuple(name for name in GBNF_GRAMMARS if name not in APART)


@pytest.mark.parametrize("name", CORPUS)
def test_the_scans_account_for_every_character(name: str) -> None:
    """The account tiles the document — no gap, no overlap, no shortfall."""
    compiled = compile_from_path(GROUND_TRUTH / name)
    for text in documents(name):
        run = watch(compiled.pda_tables(), text, compiled.fold)
        if not run.derived:  # the predictive route bailed; the engine owns it
            continue
        at = 0
        for event in run.events.of_kind("scan"):
            assert event.span.start == at, f"{name}: gap at {at}"
            at = event.span.end
        assert at == len(text), f"{name}: account stops at {at} of {len(text)}"


@pytest.mark.parametrize("name", CORPUS)
def test_every_event_references_the_document_and_the_grammar(name: str) -> None:
    """Spans lie inside the text; rule names are the compiled grammar's own."""
    compiled = compile_from_path(GROUND_TRUTH / name)
    known = {str(rule.name) for rule in compiled.codegen_grammar.rules} | {""}
    for text in documents(name):
        run = watch(compiled.pda_tables(), text, compiled.fold)
        for event in run.events:
            assert event.kind in TRACE_KINDS
            assert 0 <= event.span.start <= event.span.end <= len(text)
            assert event.rule in known, f"{name}: unknown rule {event.rule!r}"


@pytest.mark.parametrize("name", CORPUS)
def test_two_watched_runs_agree_across_the_corpus(name: str) -> None:
    """Determinism, per grammar and per document."""
    compiled = compile_from_path(GROUND_TRUTH / name)
    for text in documents(name):
        first = watch(compiled.pda_tables(), text, compiled.fold)
        assert first == watch(compiled.pda_tables(), text, compiled.fold)


@pytest.mark.parametrize("name", CORPUS)
def test_watching_does_not_change_what_the_parse_says(name: str) -> None:
    """The watched re-run derives exactly when the unwatched parse does.

    The account is of the SAME machine: if watching moved a decision, this is
    where it would show, because the two runs would disagree about the input.
    """
    compiled = compile_from_path(GROUND_TRUTH / name)
    for text in documents(name):
        model = parse_model(compiled.codegen_grammar, text, compiled.fold)
        run = watch(compiled.pda_tables(), text, compiled.fold)
        if run.derived:
            assert model.to_text() == text, name
