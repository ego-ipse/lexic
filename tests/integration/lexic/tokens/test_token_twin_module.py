"""F9: token grammars are full citizens of the notation + twin-module surfaces.

A grammar using every token-terminal form (``<text>`` / ``<[id]>`` /
``<[lo-hi]>`` / ``!<…>`` / ``.``) goes through the same machinery every char
grammar does: the notation repr-fixpoint holds on its IR (``IrAlphabet`` and
friends ride the SYMBOLS whitelist), a fresh export parses back and
cross-checks (``parse_module`` / ``verify_module``), ``export_module``
reproduces ``export_source`` byte-for-byte, and the written twin IMPORTS with
the same ``__grammar__``/``__binds__`` the in-memory synthesis carries — no
privileged formulation, no token-special export path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from lexic.compile import (
    compile_text,
    export_module,
    export_source,
    parse_module,
    verify_module,
)
from lexic.compile.notation.emit import emit_ir
from lexic.compile.notation.parse import load_ir

TOKEN_GRAMMAR = 'root ::= "a" <tok> b c\nb ::= !<[5-9]> .\nc ::= <[7]> | <[100-200]>\n'
"""Every token-terminal surface form in one grammar: a text token, negation,
any, a single id and an id range."""


@pytest.fixture(scope="module", name="compiled")
def _compiled():
    """The compiled full-surface token grammar."""
    return compile_text(TOKEN_GRAMMAR, cache_key="token-twin-module")


def test_notation_fixpoint_on_the_token_grammar(compiled):
    """load_ir(emit_ir(g)) == g for both the canonical and codegen IR —
    IrAlphabet / IrNot / IrChr round the notation exactly."""
    assert load_ir(emit_ir(compiled.grammar, 88)) == compiled.grammar
    assert load_ir(emit_ir(compiled.codegen_grammar, 88)) == compiled.codegen_grammar


@pytest.mark.parametrize("inline_tables", [False, True])
def test_token_export_parses_back_and_verifies(compiled, inline_tables):
    """A fresh token-grammar export parses back to a module model and passes
    the L2 binding cross-check, in both table modes."""
    source = export_source(compiled, inline_tables=inline_tables)
    module = parse_module(source)
    assert module.classes
    verify_module(compiled, source)


def test_export_module_reproduces_export_source_exactly(compiled, tmp_path: Path):
    """The written twin equals the in-memory export byte-for-byte."""
    out = tmp_path / "token_twin.py"
    export_module(compiled, out, stem=compiled.stem)
    assert out.read_text(encoding="utf-8") == export_source(compiled)


def test_written_twin_imports_with_identical_grammar_and_binds(
    compiled, tmp_path: Path
):
    """Importing the written twin yields classes whose __grammar__ and
    __binds__ equal the in-memory synthesis — the import seam carries the
    token nodes losslessly."""
    out = tmp_path / "token_twin_import.py"
    export_module(compiled, out)
    spec = importlib.util.spec_from_file_location("token_twin_import", out)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, cls in compiled.classes.items():
        twin = getattr(module, name)
        assert twin.__grammar__ == cls.__grammar__, name
        assert twin.__binds__ == cls.__binds__, name
