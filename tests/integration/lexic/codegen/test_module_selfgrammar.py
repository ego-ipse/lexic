"""L3: the whole-file self-grammar fixpoint over a corpus subset.

``lexic`` parses its own exported twin modules (the L1/L2 gates pinned in
``tests/unit/lexic/compile/test_selfgrammar.py``); this closes the loop at
file granularity — ``parse_module(export_source(compiled))`` succeeds,
``verify_module`` cross-checks it against the binding view, and writing +
re-reading via ``export_module`` reproduces the SAME text byte-for-byte
(the exporter is a fixpoint, not just a parseable one).

Kept to a small corpus subset (list/json/arithmetic.abnf) — the full
22-export sweep already runs in ``tools/check_generated.py``; a whole-file
parse is real cost (vyx alone is ~635ms), so this integration test stays
sane rather than re-running the full corpus.
"""

from __future__ import annotations

import pytest

from lexic.compile import (
    compile_from_path,
    export_module,
    export_source,
    parse_module,
    verify_module,
)
from tests.paths import GROUND_TRUTH

CORPUS = (
    ("list", "gbnf"),
    ("json", "gbnf"),
    ("arithmetic", "abnf"),
)


@pytest.mark.parametrize("inline_tables", [False, True])
@pytest.mark.parametrize("stem,ext", CORPUS)
def test_parse_module_succeeds_on_the_export(stem: str, ext: str, inline_tables: bool):
    """A fresh export of every corpus grammar parses back to a module model,
    in both table modes."""
    compiled = compile_from_path(GROUND_TRUTH / f"{stem}.{ext}")
    source = export_source(compiled, inline_tables=inline_tables)
    module = parse_module(source)
    assert module.classes


@pytest.mark.parametrize("inline_tables", [False, True])
@pytest.mark.parametrize("stem,ext", CORPUS)
def test_verify_module_passes_on_the_export(stem: str, ext: str, inline_tables: bool):
    """verify_module's L2 binding cross-check passes for every corpus
    grammar's export, in both table modes."""
    compiled = compile_from_path(GROUND_TRUTH / f"{stem}.{ext}")
    source = export_source(compiled, inline_tables=inline_tables)
    verify_module(compiled, source)


@pytest.mark.parametrize("inline_tables", [False, True])
@pytest.mark.parametrize("stem,ext", CORPUS)
def test_export_module_reproduces_export_source_exactly(
    stem: str, ext: str, inline_tables: bool, tmp_path
):
    """export_module's written file is byte-identical to export_source's
    return value — the exporter is a fixpoint, not merely reparseable."""
    compiled = compile_from_path(GROUND_TRUTH / f"{stem}.{ext}")
    expected = export_source(compiled, inline_tables=inline_tables)
    written = export_module(
        compiled,
        tmp_path / f"{stem}_{ext}.py",
        stem=compiled.stem,
        inline_tables=inline_tables,
    )
    assert written.read_text(encoding="utf-8") == expected


def test_parsed_back_module_grammar_equals_the_compiled_canonical_ast():
    """The GRAMMAR expression parsed back out of the file equals the AST
    the exporter rendered it FROM — the round-trip closes at file
    granularity, not just at the notation-expression granularity."""
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    module = parse_module(export_source(compiled))
    assert module.grammar == compiled.grammar
