"""Shared helpers for the ``lexic.parsing.pda.runtime`` unit tests."""

from __future__ import annotations

from pathlib import Path

from lexic.compile import CompiledGrammar, canonical_grammar, compile_from_path
from lexic.compile.pipeline.moments import build_codegen_grammar
from lexic.grammars import flavour_for_extension
from lexic.model import GrammarModel
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.compiler.clones import compile_pda
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.products import _model_product


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
    instance = _model_product(
        compiled.codegen_grammar, compiled.product
    ).instance_grammar
    pda = compile_pda(lifted, instance, compiled.product)
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
