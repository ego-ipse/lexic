"""Structural mirror for the reduce predictive runtime module.

:mod:`lexic.parsing.pda.reduce_runtime` homes ``_ReducePdaKernel`` (the b1
grammar-text twin) and ``parse_pda`` (the model-vs-reduce entry), split out of
``runtime`` for C0302 headroom. The reduce-path *parity* (byte-equal to
``parse_reduced``) is exercised in
:mod:`tests.unit.lexic.parsing.pda.test_runtime`; this pins the split — the
symbols live here, subclass the model kernel, and ``parse_pda`` dispatches on
``tables.reduce``.
"""

from __future__ import annotations

import pytest

from lexic.compile import parse_grammar, self_grammar_pda
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.grammars.abnf import ABNF_GRAMMAR
from lexic.grammars.gbnf import GBNF_GRAMMAR
from lexic.parsing.pda import reduce_runtime as rr
from lexic.parsing.pda.reduce_runtime import parse_pda
from lexic.parsing.pda.runtime import PdaFail, PdaKernel
from tests.integration.test_pda_parity import _ALL_STEMS
from tests.paths import GROUND_TRUTH


def test_reduce_kernel_lives_here_and_extends_the_model_kernel() -> None:
    """``_ReducePdaKernel`` is defined in reduce_runtime, subclassing PdaKernel."""
    kernel_cls = getattr(rr, "_ReducePdaKernel")
    assert issubclass(kernel_cls, PdaKernel)
    assert kernel_cls.__module__ == "lexic.parsing.pda.reduce_runtime"


def test_parse_pda_is_the_single_public_entry() -> None:
    """``parse_pda`` is exported here and is the only public name."""
    assert callable(rr.parse_pda)
    assert rr.__all__ == ["parse_pda"]


def test_reduce_kernel_overrides_only_the_completion_seams() -> None:
    """The reduce twin overrides the completion / island / delegate callbacks,
    inheriting the whole recognition machinery from the model kernel."""
    kernel_cls = getattr(rr, "_ReducePdaKernel")
    own = set(vars(kernel_cls))
    assert {"_complete", "_island", "_delegate_run"} <= own
    # recognition machinery is inherited, never re-defined on the twin
    assert own.isdisjoint({"_drive", "_enter", "_quant_step", "prefix_run", "run"})


# ── _reduce_span: YIELD-with-drop stitch (comment interiors) ──────────────
#
# ``parse_grammar`` is itself routed PDA-first (the Task-7 flip): it tries
# ``self_grammar_pda(flavour)`` before falling back to the Earley reducer.
# These pins therefore exercise the whole ``_ReduceRoute``/``parse_pda`` wiring
# end-to-end (no PdaFail, no silent divergence) rather than an independent
# Earley-only oracle — a mismatch here would mean the direct ``parse_pda``
# call and ``parse_grammar``'s own PDA route disagree or one PdaFails and the
# other doesn't.


def test_reduce_span_stitches_a_comment_with_an_embedded_tab() -> None:
    """An ABNF comment containing a TAB (``_reduce_span``'s YIELD-with-drop
    stitch — per-item ends + kept child strings) parses end-to-end and
    matches ``parse_grammar`` byte-for-byte; the comment interior is noise, so
    the TAB must not derail the fold."""
    text = "root = digit ; a\tb\r\ndigit = %x30-39\r\n"
    pda = self_grammar_pda(ABNF_FLAVOUR)
    assert pda is not None
    got = parse_pda(pda, text)
    assert got == parse_grammar(text, ABNF_FLAVOUR)


@pytest.mark.parametrize("stem", sorted(p.name for p in GROUND_TRUTH.glob("*.abnf")))
def test_reduce_pda_abnf_ground_truth_matches_parse_grammar(stem: str) -> None:
    """Every ``.abnf`` ground-truth file, parsed as grammar TEXT through the
    ABNF self-grammar reduce PDA, is byte-equal to ``parse_grammar`` — no
    ``PdaFail``."""
    pda = self_grammar_pda(ABNF_FLAVOUR)
    assert pda is not None
    text = (GROUND_TRUTH / stem).read_text(encoding="utf-8")
    assert parse_pda(pda, text) == parse_grammar(text, ABNF_FLAVOUR)


def test_reduce_pda_abnf_self_emit_matches_parse_grammar() -> None:
    """ABNF's own emitted self-grammar text round-trips through the reduce PDA
    byte-equal to ``parse_grammar`` — the self-hosting fixpoint, PDA-side."""
    pda = self_grammar_pda(ABNF_FLAVOUR)
    assert pda is not None
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert parse_pda(pda, text) == parse_grammar(text, ABNF_FLAVOUR)


_GBNF_GOOD_STEMS: tuple[str, ...] = tuple(
    stem
    for stem in _ALL_STEMS
    if stem.endswith(".gbnf") and stem not in {"json_arr.gbnf", "json_ws.gbnf"}
)
"""``test_pda_parity``'s full ground-truth stem list, narrowed to the six
GBNF files the self-grammar reduce PDA parses end-to-end (excluding the two
known ``PdaFail`` residues pinned below)."""


@pytest.mark.parametrize("stem", _GBNF_GOOD_STEMS)
def test_reduce_pda_gbnf_ground_truth_matches_parse_grammar(stem: str) -> None:
    """The seven known-good GBNF texts (six ground-truth files here, the
    self-emit below) parse end-to-end through the GBNF self-grammar reduce PDA
    byte-equal to ``parse_grammar``."""
    pda = self_grammar_pda(GBNF_FLAVOUR)
    assert pda is not None
    text = (GROUND_TRUTH / stem).read_text(encoding="utf-8")
    assert parse_pda(pda, text) == parse_grammar(text, GBNF_FLAVOUR)


def test_reduce_pda_gbnf_self_emit_matches_parse_grammar() -> None:
    """GBNF's own emitted self-grammar text — the seventh known-good text."""
    pda = self_grammar_pda(GBNF_FLAVOUR)
    assert pda is not None
    text = str(GBNF_FLAVOUR.apply(GBNF_GRAMMAR))
    assert parse_pda(pda, text) == parse_grammar(text, GBNF_FLAVOUR)


@pytest.mark.parametrize("stem", ["json_arr.gbnf", "json_ws.gbnf"])
def test_reduce_pda_gbnf_json_ws_variants_still_pdafail(stem: str) -> None:
    """``json_arr.gbnf``/``json_ws.gbnf`` still raise ``PdaFail`` on the direct
    reduce-PDA call — the recorded empty-first-arm residue. Removing this pin
    is EXPECTED (not a regression) once the struct arm gate lands."""
    pda = self_grammar_pda(GBNF_FLAVOUR)
    assert pda is not None
    text = (GROUND_TRUTH / stem).read_text(encoding="utf-8")
    with pytest.raises(PdaFail):
        parse_pda(pda, text)
