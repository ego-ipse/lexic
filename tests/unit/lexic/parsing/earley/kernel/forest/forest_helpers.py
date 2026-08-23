"""Shared kernel/handle construction for the forest unit tests."""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.earley.kernel.forest.support.readout import accept_item
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.products import _model_product


def kernel_and_handle(text: str, grammar: str, cache_key: str) -> tuple[Kernel, int]:
    """Compile ``grammar``, run a finished kernel over ``text``, and pack the
    accepting handle."""
    compiled = compile_text(grammar, cache_key=cache_key)
    product = _model_product(compiled.codegen_grammar, compiled.fold)
    kernel = Kernel(product.tables, text, True).run()
    acc = accept_item(kernel)
    return kernel, (acc << kernel.tables.packing.bits) | len(text)
