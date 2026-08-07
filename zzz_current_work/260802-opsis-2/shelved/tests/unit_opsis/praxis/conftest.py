"""Shared fixtures for tests/unit/opsis/praxis/."""

from __future__ import annotations

from typing import Callable

import pytest
from opsis.praxis.reading import Reading, Source
from opsis.praxis.session import Session

_VOCAB_DOC = '{"model": {"vocab": {"a": 0}, "merges": []}}'

BindVocab = Callable[[Session, Reading, str], Reading]


@pytest.fixture(name="bind_vocab")
def _bind_vocab() -> BindVocab:
    """A factory adding a one-token vocabulary reading, bound to a grammar."""

    def make(session: Session, grammar: Reading, vname: str) -> Reading:
        vocab = session.add("vocab", "vocabulary", vname, Source(_VOCAB_DOC))
        session.bind(grammar.ident, vocab.ident)
        return vocab

    return make
