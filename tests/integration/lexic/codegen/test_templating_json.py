"""Templating v2 integration pins — real file, cross-flavour, equivalence.

The unit suite drives :func:`~lexic.compile.templating.template` over a toy
``compile_text`` grammar; these pins close Task 11's remaining gates on real
formulations: the SAME shape + spec extract through ``json.gbnf`` AND
``json.abnf`` (no privileged formulation — the kept spans agree), a kept
model is literally a sub-model of the full parse (extraction ≡ parse), and
the real SmolLM2 ``tokenizer.json`` yields ``model.type == "BPE"`` through
the compiled ``json.gbnf`` (skip-if-absent, like every real-fixture lane).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from lexic.compile import compile_from_path
from lexic.compile.templating import KEEP, MapShape, template
from lexic.model import GrammarModel
from tests.paths import GROUND_TRUTH

_FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "resources"
    / "tokenizers"
    / "smollm2.tokenizer.json"
)

_SHAPE = MapShape("object", "member", "string", "value")
"""The json map declaration — identical for both flavours (same rule names)."""

_DOC = '{"a": 1, "model": {"type": "BPE", "n": 2}}'
_SPEC = {'"model"': {'"type"': KEEP}}


def _kept_type(ext: str, text: str) -> GrammarModel:
    """Extract ``model.type`` from ``text`` via the compiled json ``ext`` grammar."""
    compiled = compile_from_path(GROUND_TRUTH / f"json.{ext}")
    out = template(compiled, _SHAPE, _SPEC).run(text)
    return out['"model"', '"type"']


def _submodels(model: GrammarModel) -> Iterator[GrammarModel]:
    """Every GrammarModel in ``model``'s tree, including itself."""
    stack: list[GrammarModel] = [model]
    while stack:
        node = stack.pop()
        yield node
        for value in node:
            if isinstance(value, GrammarModel):
                stack.append(value)
            elif isinstance(value, tuple):
                stack.extend(v for v in value if isinstance(v, GrammarModel))


def test_same_shape_and_spec_extract_through_both_flavours():
    """json.gbnf and json.abnf agree on the kept span — flavour independence."""
    gbnf, abnf = _kept_type("gbnf", _DOC), _kept_type("abnf", _DOC)
    assert gbnf.to_text() == abnf.to_text() == '"BPE"'


def test_kept_model_is_a_sub_model_of_the_full_parse():
    """Extraction ≡ parse: the kept model occurs verbatim in the full model."""
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    kept = _kept_type("gbnf", _DOC)
    full = compiled.parse(_DOC)
    assert any(sub == kept for sub in _submodels(full))


@pytest.mark.skipif(
    not _FIXTURE.is_file(),
    reason="real tokenizer fixture absent — run 'uv run python -m ext.API.hf'",
)
def test_real_tokenizer_json_model_type_extracts_via_json_gbnf():
    """The 2 MB real file: templating keeps exactly ``model.type`` — the
    machinery scales to the real document through the standard pipeline."""
    kept = _kept_type("gbnf", _FIXTURE.read_text(encoding="utf-8"))
    assert kept.to_text() == '"BPE"'
