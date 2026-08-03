"""Frozen contract — freeze/thaw, the fixpoint, and refusal on junk."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexic.compile import Directives
from lexic.exceptions import UnsupportedConstructError
from opsis.praxis.ingress.frozen import freeze, thaw
from opsis.praxis.reading import Source
from opsis.praxis.session import Session


def _populated(tmp_path: Path) -> Session:
    """A session with a few readings, naming and binding each other."""
    session = Session(tmp_path)
    root = session.add("root", "text", source=Source("hello"))
    child = session.add(
        "child", "grammar", reader=root.ident, source=Source("something")
    )
    child.params = child.params._replace(
        directives=Directives(start="root", non_semantic=frozenset({"ws"}))
    )
    session.bind(child.ident, root.ident)
    return session


def test_freeze_thaw_freeze_is_a_fixpoint(tmp_path: Path) -> None:
    """Thawing what was frozen and re-freezing it reproduces the same text."""
    session = _populated(tmp_path)
    once = freeze(session)

    restored = Session(tmp_path)
    thaw(restored, once)
    twice = freeze(restored)

    assert once == twice


def test_thaw_restores_idents_titles_kinds_readers_and_bindings(
    tmp_path: Path,
) -> None:
    """Every reading's identity, kind, reader and binding comes back exactly."""
    session = _populated(tmp_path)
    text = freeze(session)

    restored = Session(tmp_path)
    thaw(restored, text)

    for ident, original in session.readings.items():
        again = restored.readings[ident]
        assert again.ident == original.ident
        assert again.title == original.title
        assert again.kind == original.kind
        assert again.reader == original.reader
        assert again.params.bound == original.params.bound


@pytest.mark.parametrize("junk", ["", "Held()", "IrStr('x')"])
def test_thaw_on_junk_raises_construct_error(tmp_path: Path, junk: str) -> None:
    """Malformed session text is a refusal, never a bare Type/ValueError."""
    session = Session(tmp_path)
    with pytest.raises(UnsupportedConstructError):
        thaw(session, junk)


def test_saved_empty_thaws_to_zero_readings(tmp_path: Path) -> None:
    """An empty saved session leaves nothing to restore."""
    session = _populated(tmp_path)
    count = thaw(session, "Saved()")
    assert count == 0
    assert not session.readings
