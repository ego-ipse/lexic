"""The Vyx escape reproducer has one model, and its shape stays on the PDA path.

Vyx's own ``nl-escape`` run can hold the ``" "`` of the closing ``" >"``, and
only the third character tells its exit from its take, one more than a
stop-set's proof reads. So the rule islands there, and the public parse answers
it. The escape's shape, ``"#"+`` before a class that holds ``#``, stays on the
native path wherever the run cannot hold its closer.
"""

from __future__ import annotations

from lexic.compile import compile_from_path, compile_text
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.products import earley_model
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.parsing_helpers import prod

VYX_ESCAPE = "!H \\#\\n\\# >"

ESCAPE_SHAPE = 'doc ::= "!H " esc " >"\nesc ::= "\\\\" "#"+ [\\x21-\\x7E]*\n'
"""Vyx's escape with a tail class that cannot hold the closer's space."""


def test_vyx_nested_escape_has_one_model_in_both_engines() -> None:
    """Repeat loopback does not turn ``\\#\\n\\#`` into an arm choice: the
    public parse is Earley's one model."""
    compiled = compile_from_path(GROUND_TRUTH / "vyx.gbnf")
    product = prod(compiled)
    via_earley = earley_model(
        product.instance_grammar,
        VYX_ESCAPE,
        compiled.product,
        product.tables,
    )
    parsed = compiled.parse(VYX_ESCAPE)
    assert parsed == via_earley
    assert "NlEscape('\\\\#\\\\n\\\\#')" in repr(parsed)
    assert parsed.to_text() == VYX_ESCAPE


def test_the_escape_shape_stays_on_the_native_pda_path() -> None:
    """The same escape where its run cannot hold the closer: the PDA answers
    directly, with Earley's model."""
    compiled = compile_text(ESCAPE_SHAPE, cache_key="adversarial-escape-shape")
    product = prod(compiled)
    via_pda = pda_model(product.pda, VYX_ESCAPE, compiled.executor)
    via_earley = earley_model(
        product.instance_grammar,
        VYX_ESCAPE,
        compiled.product,
        product.tables,
    )
    assert via_pda == via_earley
    assert "Esc('\\\\#\\\\n\\\\#')" in repr(via_pda)
    assert via_pda.to_text() == VYX_ESCAPE
