"""The Vyx escape reproducer stays on the native PDA path."""

from __future__ import annotations

from lexic.compile import compile_from_path
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.products import earley_model
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.parsing_helpers import prod

VYX_ESCAPE = "!H \\#\\n\\# >"


def test_vyx_nested_escape_has_one_model_in_both_engines() -> None:
    """Repeat loopback does not turn ``\\#\\n\\#`` into an arm choice."""
    compiled = compile_from_path(GROUND_TRUTH / "vyx.gbnf")
    product = prod(compiled)
    via_pda = pda_model(product.pda, VYX_ESCAPE, compiled.fold)
    via_earley = earley_model(
        product.instance_grammar,
        VYX_ESCAPE,
        compiled.fold,
        product.tables,
    )
    assert via_pda == via_earley
    assert "NlEscape('\\\\#\\\\n\\\\#')" in repr(via_pda)
    assert via_pda.to_text() == VYX_ESCAPE
