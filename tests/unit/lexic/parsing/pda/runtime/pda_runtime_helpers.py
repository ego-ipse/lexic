"""Shared helpers for the ``lexic.parsing.pda.runtime`` unit tests.

``reduce_pda`` is duplicated verbatim (pre-relocation) across
``test_runtime.py`` and ``test_reduce_runtime.py``.
"""

from __future__ import annotations

from pathlib import Path

from lexic.compile import CompiledGrammar, canonical_grammar, compile_from_path
from lexic.compile.pipeline.passes import build_codegen_grammar
from lexic.grammars import flavour_for_extension
from lexic.model import GrammarModel
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.compiler.clones import compile_pda
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.products import _model_product, _reduce_product, earley_reduce


def reduce_pda(flavour):
    """The flavour's self-grammar reduce PDA (built + memoised in the engine)."""
    return _reduce_product(flavour.grammar, flavour.reducer).pda


def compiled_and_pda(path: Path) -> tuple[CompiledGrammar, PdaTables]:
    """Compile a ground-truth grammar both ways: the engine artifact + its PdaTables.

    Mirrors ``test_clones.py``'s ``_pda_for`` — the same inputs
    ``compile.py``'s (not-yet-landed) Task-6 wiring will use, built entirely
    through public seams: ``lifted`` from ``canonical_grammar`` +
    ``build_codegen_grammar`` + ``lift_optional_nullables``,
    ``instance_grammar``/``fold.config`` read off the already-compiled
    :class:`CompiledGrammar`.
    """
    flavour = flavour_for_extension(path)
    canonical = canonical_grammar(path.read_text(encoding="utf-8"), flavour)
    lifted = lift_optional_nullables(build_codegen_grammar(canonical))
    compiled = compile_from_path(path)
    instance = _model_product(compiled.codegen_grammar, compiled.fold).instance_grammar
    pda = compile_pda(lifted, instance, compiled.fold.config)
    return compiled, pda


def path_specs(path: Path) -> dict:
    """The rule-name → IrRule view :func:`~lexic.generate.generate` walks."""
    flavour = flavour_for_extension(path)
    canonical = canonical_grammar(path.read_text(encoding="utf-8"), flavour)
    return {r.name: r for r in canonical.rules}


def assert_parity(
    engine_model: GrammarModel, pda_model: GrammarModel, text: str
) -> None:
    """Assert semantic parity + round-trip (the raw-equality invariant is owned
    by the integration raw-parity test)."""
    assert pda_model.semantic_dump() == engine_model.semantic_dump()
    assert pda_model.to_text() == text


def ref_reduce(flavour, text: str):
    """The Earley reducer's own reduction of ``text`` — the parity oracle."""
    return earley_reduce(normalize(flavour.grammar), text, flavour.reducer)
