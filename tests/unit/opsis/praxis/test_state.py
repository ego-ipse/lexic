"""Tests for opsis.praxis.state — the ladder cursor.

Subrule-level: one meta-ladder walk exercising both reading kinds, then the
cascade/growth mechanics and each root constructor's own path.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.grammars import get_flavour
from opsis.praxis.state import Ladder, root_flavour, root_manifest, root_notation
from tests.paths import GRAMMARS

_SMALL_GRAMMAR = 'root ::= "a" [0-9]\n'
_OTHER_GRAMMAR = 'root ::= "b" [0-9]\n'


def _meta_ladder() -> Ladder:
    """A 3-rung flavour ladder: self-grammar text, a small grammar, an instance."""
    text0 = str(get_flavour("gbnf").apply(get_flavour("gbnf").grammar))
    ladder = Ladder(root_flavour("gbnf"))
    ladder.edit(0, text0)
    ladder.edit(1, _SMALL_GRAMMAR)
    ladder.edit(2, "a7")
    return ladder


def test_meta_ladder_readings():
    """Rungs 0 and 1 carry both readings; the terminal rung is instance-only."""
    ladder = _meta_ladder()
    rung0, rung1, rung2 = ladder.rungs
    assert rung0.compiled is not None
    assert rung0.instance is not None
    assert rung1.compiled is not None
    assert rung1.instance is not None
    assert rung2.compiled is None
    assert rung2.instance is not None
    assert not rung0.errors
    assert not rung1.errors
    assert not rung2.errors


def test_edit_cascades_downward_and_preserves_untouched_rungs():
    """Editing rung 1 leaves rung 0's compiled object untouched, and re-reads rung 2."""
    ladder = _meta_ladder()
    compiled0 = ladder.rungs[0].compiled
    assert not ladder.rungs[2].errors

    ladder.edit(1, _OTHER_GRAMMAR)

    assert ladder.rungs[0].compiled is compiled0
    assert ladder.rungs[2].instance is None
    assert "instance" in ladder.rungs[2].errors


def test_growth_flips_previously_terminal_rung():
    """Appending a new terminal rung gives the old terminal rung a compiled reading."""
    text0 = str(get_flavour("gbnf").apply(get_flavour("gbnf").grammar))
    ladder = Ladder(root_flavour("gbnf"))
    ladder.edit(0, text0)
    ladder.edit(1, _SMALL_GRAMMAR)
    assert ladder.rungs[1].compiled is None
    assert ladder.rungs[1].instance is not None

    ladder.edit(2, "a7")

    assert ladder.rungs[1].compiled is not None
    assert not ladder.rungs[1].errors


def test_manifest_root_compiles_without_touching_registry():
    """A loaded manifest root compiles rung 0, leaving the shipped singleton alone.

    A single rung is both root and terminal, so it carries no reading until a
    second rung makes it non-terminal — the same growth mechanic as above.
    """
    manifest_text = (GRAMMARS / "gbnf.flavour.ir").read_text(encoding="utf-8")
    before = get_flavour("gbnf")

    ladder = Ladder(root_manifest(manifest_text))
    ladder.edit(0, _SMALL_GRAMMAR)
    ladder.edit(1, "a7")

    assert ladder.rungs[0].compiled is not None
    assert not ladder.rungs[0].errors
    assert get_flavour("gbnf") is before


def test_notation_root_reads_ir_constructor_text():
    """A notation root compiles its own repr and parses an instance below it."""
    grammar_repr = repr(compile_text(_SMALL_GRAMMAR).grammar)
    ladder = Ladder(root_notation())
    ladder.edit(0, grammar_repr)
    ladder.edit(1, "a7")

    assert ladder.rungs[0].compiled is not None
    assert ladder.rungs[0].compiled.flavour == "ir"
    assert ladder.rungs[1].instance is not None
    assert not ladder.rungs[1].errors
