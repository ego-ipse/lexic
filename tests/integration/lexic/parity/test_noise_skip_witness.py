"""The P3 noise-skip arm selection, exercised by a document.

``NoiseSkipSelect`` is the predictive machine's answer to arms that share a
leading run of non-semantic noise: it skips the maximal run WITHOUT consuming,
picks the arm admitting the first character past it, and lets the winner
re-parse the noise itself. Until ``commands.gbnf`` joined the corpus no shipped
grammar reached it — every benchmark row carried ``None`` in that slot — so the
whole path could have broken without a test noticing.

What makes ``commands.gbnf`` reach it, where a merely whitespace-tolerant
grammar does not, is that the run is UNBOUNDED. The demotion cascade tries the
bounded k-window first (``demote.py``), and a fixed ``k`` separates two arms
whose indentation can be any length only by luck; the peek is what is left.
A grammar with `ws ::= " "?` would be served by the window and prove nothing.

Every test here asserts the path was actually taken rather than inferring it
from the shape, because "this grammar surely routes to P3" is exactly the
assumption that left every benchmark grammar carrying ``None`` there.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.compiler.program.gating import NoiseSkipSelect
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.products import _model_product, earley_model, pda_model
from lexic.parsing.trace import GATE, watch
from tests.integration.lexic.invariants.test_clone_population import referenced
from tests.paths import GROUND_TRUTH

INDENTED = "  set alpha = 12\n\tget beta\n"
"""Two entries, each behind a non-empty and differently spelled noise run."""

FLUSH = "set alpha = 12\nget beta\n"
"""The same two entries with EMPTY runs — the peek's zero-length case."""

MIXED = "set a = 1\n   \tget bb\nset ccc = 900\n"
"""Empty and non-empty runs in one document, and a tab inside a run."""


def built():
    """The witness grammar's compile, and the model product beside it."""
    compiled = compile_from_path(GROUND_TRUTH / "commands.gbnf")
    return compiled, _model_product(compiled.codegen_grammar, compiled.product)


def test_the_witness_grammar_compiles_to_a_noise_skip_selection() -> None:
    """The premise, asserted — not inferred from the grammar's shape.

    If the analysis ever routes `entry` to a k-window or back to a hard
    overlap, every other test in this file silently stops testing the peek.
    This is the one that says so.
    """
    _compiled, product = built()

    wide = {
        clone.name: clone.wide_selectors
        for clone in referenced(product.pda).values()
        if clone.wide_selectors is not None
    }

    assert "entry" in wide, f"no wide selection on `entry`; got {sorted(wide)}"
    assert isinstance(wide["entry"], NoiseSkipSelect), (
        f"`entry` is selected by {type(wide['entry']).__name__}, not the peek"
    )
    assert len(wide["entry"].arms) == 2, "both arms hang off the selection"


@pytest.mark.parametrize(
    ("label", "document"),
    [
        ("non-empty runs", INDENTED),
        ("empty runs", FLUSH),
        ("both, and a tab", MIXED),
    ],
)
def test_the_two_engines_build_the_same_model(label: str, document: str) -> None:
    """PDA and Earley agree on the value, and the value spells the input.

    The peek is recognition-only: it chooses an arm and consumes nothing, and
    the winner re-parses the noise it peeked past. A peek that consumed would
    still parse — it would just lose the run from the model — so the
    round-trip is the assertion that catches it, not the parse.
    """
    compiled, product = built()

    predictive = pda_model(product.pda, document, compiled.product.executor)
    gated = earley_model(
        product.instance_grammar, document, compiled.product, product.tables
    )

    assert predictive.dump() == gated.dump(), label
    assert predictive.to_text() == document, label


def test_the_peek_gate_is_what_the_run_consults() -> None:
    """The path is TAKEN, not merely compiled.

    Read off the watched run rather than a counter, so it is the engine's own
    account: entering `entry` records the gate it consults, and the label is
    the selection's own (:attr:`NoiseSkipSelect.label`).
    """
    compiled, product = built()

    run = watch(product.pda, MIXED, compiled.product.executor)

    gates = [event for event in run.events if event.kind == GATE]
    peeks = [one for one in gates if "prefix negation" in str(one.verdict)]
    assert run.derived, "the predictive machine handled this document"
    assert peeks, (
        f"no peek gate consulted; gates seen: {[str(g.verdict) for g in gates]}"
    )


def test_a_document_no_arm_admits_is_refused_by_both() -> None:
    """A miss past the noise run is an ordinary refusal, on either engine.

    `put` is neither `set` nor `get`, so the character after the run admits no
    arm. The peek has no default to fall to, which is the `PdaFail` branch
    `select_gated` raises — and the gated engine must refuse the same document,
    or the peek is rejecting something the grammar accepts.

    The refusing RULE is asserted, not just that something raised: a document
    this malformed would also be refused by a dozen other paths, and only
    `entry` is the clone carrying the peek.
    """
    compiled, product = built()
    document = "   put alpha = 1\n"

    with pytest.raises(PdaFail) as refusal:
        pda_model(product.pda, document, compiled.product.executor)
    assert refusal.value.rule == "entry", "refused by the clone holding the peek"

    with pytest.raises(UnsupportedConstructError):
        earley_model(
            product.instance_grammar, document, compiled.product, product.tables
        )
