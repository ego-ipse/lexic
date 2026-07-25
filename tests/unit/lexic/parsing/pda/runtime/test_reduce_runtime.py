"""Structural mirror for the reduce predictive runtime module.

:mod:`lexic.parsing.pda.runtime.reduce_runtime` homes ``_ReducePdaKernel`` (the b1
grammar-text twin) and the two runtime entries ``pda_reduce`` / ``pda_model``,
split out of ``runtime`` for C0302 headroom. The reduce-path *parity*
(byte-equal to ``parse_reduced``) is exercised in
:mod:`tests.unit.lexic.parsing.pda.test_runtime`; this pins the split — the
symbols live here and subclass the model kernel.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text, parse_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.grammars.abnf import ABNF_GRAMMAR
from lexic.grammars.gbnf import GBNF_GRAMMAR
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.compiler.clones import compile_pda
from lexic.parsing.pda.runtime import reduce_runtime as rr
from lexic.parsing.pda.runtime.reduce_runtime import pda_reduce
from lexic.parsing.pda.runtime.runtime import PdaKernel
from tests.integration.test_pda_parity import ALL_STEMS
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.runtime.pda_runtime_helpers import reduce_pda


def test_reduce_kernel_lives_here_and_extends_the_model_kernel() -> None:
    """``_ReducePdaKernel`` is defined in reduce_runtime, subclassing PdaKernel."""
    kernel_cls = getattr(rr, "_ReducePdaKernel")
    assert issubclass(kernel_cls, PdaKernel)
    assert kernel_cls.__module__ == "lexic.parsing.pda.runtime.reduce_runtime"


def test_the_two_runtime_entries_are_the_only_public_names() -> None:
    """``pda_reduce`` / ``pda_model`` are the module's whole public surface.

    One entry per product, so neither carries a parameter the other ignores
    (``fold`` was dead on the reduce branch) and neither returns a union the
    caller has to cast back.
    """
    assert callable(rr.pda_reduce) and callable(rr.pda_model)
    assert rr.__all__ == ["pda_model", "pda_reduce"]


def test_pda_reduce_refuses_a_model_pda() -> None:
    """The reduce entry rejects tables with no reducer instead of mis-parsing."""
    compiled = compile_text('root ::= "a"\n')
    lifted = lift_optional_nullables(compiled.codegen_grammar)
    model_tables = compile_pda(lifted, normalize(lifted), compiled.fold.config)
    with pytest.raises(UnsupportedConstructError, match="needs a reduce PDA"):
        rr.pda_reduce(model_tables, "a")


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
# ``reduce_pda(flavour)`` before falling back to the Earley reducer.
# These pins therefore exercise the whole ``_ReduceRoute``/``pda_reduce`` wiring
# end-to-end (no PdaFail, no silent divergence) rather than an independent
# Earley-only oracle — a mismatch here would mean the direct ``pda_reduce``
# call and ``parse_grammar``'s own PDA route disagree or one PdaFails and the
# other doesn't.


def test_reduce_span_stitches_a_comment_with_an_embedded_tab() -> None:
    """An ABNF comment containing a TAB (``_reduce_span``'s YIELD-with-drop
    stitch — per-item ends + kept child strings) parses end-to-end and
    matches ``parse_grammar`` byte-for-byte; the comment interior is noise, so
    the TAB must not derail the fold."""
    text = "root = digit ; a\tb\r\ndigit = %x30-39\r\n"
    pda = reduce_pda(ABNF_FLAVOUR)
    assert pda is not None
    got = pda_reduce(pda, text)
    assert got == parse_grammar(text, ABNF_FLAVOUR)


@pytest.mark.parametrize("stem", sorted(p.name for p in GROUND_TRUTH.glob("*.abnf")))
def test_reduce_pda_abnf_ground_truth_matches_parse_grammar(stem: str) -> None:
    """Every ``.abnf`` ground-truth file, parsed as grammar TEXT through the
    ABNF self-grammar reduce PDA, is byte-equal to ``parse_grammar`` — no
    ``PdaFail``."""
    pda = reduce_pda(ABNF_FLAVOUR)
    assert pda is not None
    text = (GROUND_TRUTH / stem).read_text(encoding="utf-8")
    assert pda_reduce(pda, text) == parse_grammar(text, ABNF_FLAVOUR)


def test_reduce_pda_abnf_self_emit_matches_parse_grammar() -> None:
    """ABNF's own emitted self-grammar text round-trips through the reduce PDA
    byte-equal to ``parse_grammar`` — the self-hosting fixpoint, PDA-side."""
    pda = reduce_pda(ABNF_FLAVOUR)
    assert pda is not None
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert pda_reduce(pda, text) == parse_grammar(text, ABNF_FLAVOUR)


GBNF_GOOD_STEMS: tuple[str, ...] = tuple(
    stem
    for stem in ALL_STEMS
    if stem.endswith(".gbnf") and stem not in {"json_arr.gbnf", "json_ws.gbnf"}
)
"""``test_pda_parity``'s full ground-truth stem list, narrowed to the six GBNF
files without an empty-first-arm rule; ``json_arr``/``json_ws`` (whose ``ws``
rule leads with an empty arm) are pinned separately below — they too parse
pure-PDA once the empty-arm structured gate demotes the self-grammar's ``arm``
decision."""


@pytest.mark.parametrize("stem", GBNF_GOOD_STEMS)
def test_reduce_pda_gbnf_ground_truth_matches_parse_grammar(stem: str) -> None:
    """The seven known-good GBNF texts (six ground-truth files here, the
    self-emit below) parse end-to-end through the GBNF self-grammar reduce PDA
    byte-equal to ``parse_grammar``."""
    pda = reduce_pda(GBNF_FLAVOUR)
    assert pda is not None
    text = (GROUND_TRUTH / stem).read_text(encoding="utf-8")
    assert pda_reduce(pda, text) == parse_grammar(text, GBNF_FLAVOUR)


def test_reduce_pda_gbnf_self_emit_matches_parse_grammar() -> None:
    """GBNF's own emitted self-grammar text — the seventh known-good text."""
    pda = reduce_pda(GBNF_FLAVOUR)
    assert pda is not None
    text = str(GBNF_FLAVOUR.apply(GBNF_GRAMMAR))
    assert pda_reduce(pda, text) == parse_grammar(text, GBNF_FLAVOUR)


@pytest.mark.parametrize("stem", ["json_arr.gbnf", "json_ws.gbnf"])
def test_reduce_pda_gbnf_empty_first_arm_variants_pure_pda(stem: str) -> None:
    """``json_arr.gbnf``/``json_ws.gbnf`` — whose ``ws`` rule has an empty first
    arm — parse pure-PDA (no ``PdaFail``) byte-equal to ``parse_grammar``: the
    empty-arm structured gate demotes the self-grammar's ``arm`` decision."""
    pda = reduce_pda(GBNF_FLAVOUR)
    assert pda is not None
    text = (GROUND_TRUTH / stem).read_text(encoding="utf-8")
    assert pda_reduce(pda, text) == parse_grammar(text, GBNF_FLAVOUR)
