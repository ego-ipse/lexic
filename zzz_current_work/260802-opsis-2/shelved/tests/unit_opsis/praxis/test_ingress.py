"""Ingress contract — resolve, open_file's inference, browse, manifests."""

from __future__ import annotations

from pathlib import Path

import pytest
from opsis.praxis.ingress.ingress import browse, manifests, open_file, resolve

from lexic.compile import compile_text
from lexic.compile.module.export import export_module
from lexic.compile.notation.loader import load_flavour
from lexic.compile.payload.export import export_value
from lexic.exceptions import UnsupportedConstructError
from tests.paths import PROJECT_ROOT

_TOY = 'root ::= "x"+\n'


def test_resolve_refuses_a_path_outside_the_workspace(tmp_path: Path) -> None:
    """Escaping the workspace is refused, not silently clamped."""
    with pytest.raises(UnsupportedConstructError, match="outside the workspace"):
        resolve(tmp_path, "../etc/passwd")


def test_open_file_infers_a_grammar_extension(tmp_path: Path) -> None:
    """A ``.gbnf`` file opens as a grammar, read by its flavour."""
    path = tmp_path / "toy.gbnf"
    path.write_text(_TOY, encoding="utf-8")
    opened = open_file(tmp_path, "toy.gbnf")
    assert opened.kind == "grammar"
    assert opened.reader is not None
    assert opened.reader.kind == "flavour"


def test_open_file_infers_a_manifest(tmp_path: Path) -> None:
    """A ``*.flavour.ir`` manifest opens as a manifest, read by the notation."""
    _, text = manifests()[0]
    path = tmp_path / "some.flavour.ir"
    path.write_text(text, encoding="utf-8")
    opened = open_file(tmp_path, "some.flavour.ir")
    assert opened.kind == "manifest"
    assert opened.reader is not None
    assert opened.reader.kind == "notation"


def test_open_file_infers_an_exported_twin(tmp_path: Path) -> None:
    """An exported twin module opens as a grammar, read by the module grammar."""
    compiled = compile_text(_TOY)
    export_module(compiled, tmp_path / "generated" / "toy.py", stem="toy")
    opened = open_file(tmp_path, "generated/toy.py")
    assert opened.kind == "grammar"
    assert opened.reader is not None
    assert opened.reader.kind == "module"
    assert "twin" in opened.note


def test_open_file_infers_a_compiled_value(tmp_path: Path) -> None:
    """A compiled value's module opens as a value, read by importing it."""
    compiled = compile_text(_TOY)
    export_module(compiled, tmp_path / "generated" / "toy.py", stem="toy")
    value = compiled.parse("xx")
    export_value(value, tmp_path / "generated" / "toy_value.py", module="generated.toy")
    opened = open_file(tmp_path, "generated/toy_value.py")
    assert opened.kind == "value"
    assert opened.reader is not None
    assert opened.reader.kind == "python"


def test_a_file_no_reader_claims_opens_as_a_text() -> None:
    """Everything is text; what it MEANS is whatever ends up reading it.

    Not a refusal: a source file, a README or a log may be the document
    somebody wants to parse, or carry the grammar for a level below.
    Deciding in advance that it could not be would be opsis choosing
    what a text is allowed to mean.
    """
    opened = open_file(PROJECT_ROOT, "src/lexic/model.py")
    assert opened.kind == "text"
    assert opened.reader is None
    assert opened.text
    assert "model.py" in opened.note


def test_a_text_no_reader_claims_still_says_what_was_tried() -> None:
    """The attempts are named, so the answer is informative either way."""
    opened = open_file(PROJECT_ROOT, "CLAUDE.md")
    assert opened.kind == "text"
    assert "IR notation" in opened.note
    assert "drop a reader on it" in opened.note


def test_open_file_on_a_missing_path_raises_construct_error(tmp_path: Path) -> None:
    """A vanished file is a construct refusal, never a bare OSError."""
    with pytest.raises(UnsupportedConstructError):
        open_file(tmp_path, "does_not_exist.gbnf")


def test_browse_lists_directories_first(tmp_path: Path) -> None:
    """A directory always sorts ahead of the files beside it."""
    (tmp_path / "b_dir").mkdir()
    (tmp_path / "a_file.txt").write_text("x", encoding="utf-8")
    rows = browse(tmp_path)
    kinds = [row.kind for row in rows]
    assert kinds.index("dir") < kinds.index("file")


def test_browse_includes_a_parent_row_when_not_at_the_root(tmp_path: Path) -> None:
    """A subdirectory's listing carries a way back up; the root's does not."""
    (tmp_path / "sub").mkdir()
    at_root = browse(tmp_path)
    at_sub = browse(tmp_path, "sub")
    assert not any(row.name == ".." for row in at_root)
    assert any(row.name == ".." for row in at_sub)


def test_browse_never_leaves_the_workspace(tmp_path: Path) -> None:
    """Browsing outside the workspace root refuses exactly like resolving one."""
    with pytest.raises(UnsupportedConstructError):
        browse(tmp_path, "..")


def test_manifests_finds_shipped_flavours_and_each_loads() -> None:
    """Every shipped ``*.flavour.ir`` text folds into a live flavour."""
    found = manifests()
    assert found
    names = [name for name, _ in found]
    assert all(name.endswith(".flavour.ir") for name in names)
    for _, text in found:
        load_flavour(text)
