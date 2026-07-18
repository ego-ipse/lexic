"""Tests for ``lexic.compile.artifact`` — the ``CompiledGrammar`` artefact.

The class moved here from ``compile/__init__`` (260718: ``export`` imports
it cycle-free); the behavioral surface — ``parse`` delegating to the engine
product and the model narrowing — stays pinned via the public
``lexic.compile`` import, plus the artefact's own identity fields.
"""

from __future__ import annotations

import pytest

from lexic.compile import CompiledGrammar, compile_from_path, compile_text
from lexic.compile.artifact import CompiledGrammar as ArtifactCompiledGrammar
from lexic.exceptions import UnsupportedConstructError
from lexic.model import GrammarModel
from tests.paths import GROUND_TRUTH


def test_the_package_root_reexports_the_artifact_class():
    """`lexic.compile.CompiledGrammar` IS the artifact module's class."""
    assert CompiledGrammar is ArtifactCompiledGrammar


def test_parse_returns_a_grammar_model_instance():
    """The artefact's parse drives the engine product to a model."""
    cg = compile_text('root ::= "hi"\n')
    inst = cg.parse("hi")
    assert isinstance(inst, GrammarModel)
    assert inst.to_text() == "hi"


def test_parse_refuses_text_outside_the_grammar():
    """A non-deriving input surfaces the engine's UnsupportedConstructError."""
    cg = compile_text('root ::= "hi"\n')
    with pytest.raises(UnsupportedConstructError):
        cg.parse("nope")


def test_compile_from_path_threads_flavour_and_stem():
    """The artefact records its source flavour and stem (export identity)."""
    cg = compile_from_path(GROUND_TRUTH / "json.gbnf")
    assert cg.flavour == "gbnf"
    assert cg.stem == "json"


def test_compile_text_threads_the_content_stem():
    """compile_text stems by content hash — the anon_<sha> identity."""
    cg = compile_text('root ::= "hi"\n')
    assert cg.stem.startswith("anon_")
