"""Tests for opsis.praxis.roots — ingress: files becoming roots.

Subrule-level: one test per ``open_path`` kind, the scope guard, and the
listing's shelf-vs-infrastructure filter.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from opsis.opsis.scene import Ring, Space
from opsis.praxis.roots import Workspace, _listable, open_path
from tests.paths import GRAMMARS, GROUND_TRUTH

_SMALL_GRAMMAR = 'root ::= "a" [0-9]\n'


def test_open_path_grammar_kind(tmp_path):
    """A ``.gbnf`` file opens as a grammar root, extension-classified."""
    (tmp_path / "resources" / "ground_truth").mkdir(parents=True)
    text = (GROUND_TRUTH / "list.gbnf").read_text(encoding="utf-8")
    (tmp_path / "resources" / "ground_truth" / "list.gbnf").write_text(
        text, encoding="utf-8"
    )
    ws = Workspace(tmp_path)

    opened = open_path(ws, "resources/ground_truth/list.gbnf")

    assert opened.kind == "grammar"
    assert opened.ladder is not None
    # A freshly opened single rung is both root and terminal, so it carries no
    # reading yet — growth (see test_state.py) is what compiles it.
    assert opened.ladder.rungs[0].text == text


def test_open_path_manifest_kind(tmp_path):
    """A flavour manifest with no grammar extension opens as a manifest root."""
    manifest_text = (GRAMMARS / "gbnf.flavour.ir").read_text(encoding="utf-8")
    (tmp_path / "gbnf.flavour.ir").write_text(manifest_text, encoding="utf-8")
    ws = Workspace(tmp_path)

    opened = open_path(ws, "gbnf.flavour.ir")

    assert opened.kind == "manifest"
    assert opened.ladder is not None


def test_open_path_scene_kind(tmp_path):
    """A saved session file thaws into the ``scene`` kind."""
    scene = Space(Ring("r"))
    (tmp_path / "sess.scene").write_text(repr(scene), encoding="utf-8")
    ws = Workspace(tmp_path)

    opened = open_path(ws, "sess.scene")

    assert opened.kind == "scene"
    assert opened.scene == scene


def test_open_path_notation_kind_falls_through_extension(tmp_path):
    """A notation grammar under an unrecognised extension still classifies right."""
    grammar_repr = repr(compile_text(_SMALL_GRAMMAR).grammar)
    (tmp_path / "grammar.txt").write_text(grammar_repr, encoding="utf-8")
    ws = Workspace(tmp_path)

    opened = open_path(ws, "grammar.txt")

    assert opened.kind == "notation"
    assert opened.ladder is not None
    assert opened.ladder.rungs[0].text == grammar_repr


def test_open_path_refused_kind(tmp_path):
    """A file none of the readings accept refuses with a real message."""
    (tmp_path / "garbage.txt").write_text(
        "not a grammar, not a scene\n", encoding="utf-8"
    )
    ws = Workspace(tmp_path)

    opened = open_path(ws, "garbage.txt")

    assert opened.kind == "refused"
    assert opened.note


def test_open_path_scope_guard(tmp_path):
    """A relative path escaping the workspace root refuses before it is read."""
    ws = Workspace(tmp_path)
    with pytest.raises(UnsupportedConstructError):
        open_path(ws, "../x")


def test_listing_filters_infra_and_includes_shelf_files(tmp_path):
    """Listing sweeps the shelves, excluding pycache/bytecode, plus session files."""
    (tmp_path / "resources" / "ground_truth").mkdir(parents=True)
    (tmp_path / "generated" / "__pycache__").mkdir(parents=True)
    (tmp_path / "resources" / "ground_truth" / "a.gbnf").write_text(
        _SMALL_GRAMMAR, encoding="utf-8"
    )
    (tmp_path / "generated" / "__pycache__" / "x.pyc").write_bytes(b"")
    (tmp_path / "generated" / "twin.py").write_text("# twin\n", encoding="utf-8")
    (tmp_path / "sess.scene").write_text(repr(Space(Ring("r"))), encoding="utf-8")
    ws = Workspace(tmp_path)

    assert ws.listing() == [
        "generated/twin.py",
        "resources/ground_truth/a.gbnf",
        "sess.scene",
    ]


def test_listable_excludes_dunder_modules(tmp_path):
    """``_listable`` refuses dunder-named infrastructure modules."""
    assert not _listable(tmp_path / "generated" / "__init__.py")
    assert _listable(tmp_path / "generated" / "twin.py")
