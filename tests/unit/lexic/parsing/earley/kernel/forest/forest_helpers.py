"""Shared kernel/handle construction and fast-build stand-ins for the forest
unit tests."""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.ir import IrAlternation, IrAst, IrLiteral, IrNone, IrRule, IrRuleRef, IrSelf
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.support.readout import accept_item
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.products import model_product
from tests.unit.lexic.parsing.ir_fixtures import norm


def kernel_and_handle(text: str, grammar: str, cache_key: str) -> tuple[Kernel, int]:
    """Compile ``grammar``, run a finished kernel over ``text``, and pack the
    accepting handle."""
    compiled = compile_text(grammar, cache_key=cache_key)
    product = model_product(compiled.codegen_grammar, compiled.product)
    kernel = Kernel(product.tables, text, True).run()
    acc = accept_item(kernel)
    return kernel, (acc << kernel.tables.packing.bits) | len(text)


def decline_fast_builds(patch: pytest.MonkeyPatch, declined: int) -> None:
    """Make every fast build miss on the first ``declined`` handles asked of
    any :class:`FastTree`, and build normally after.

    Patched on the class, so every module's binding of it sees the misses —
    the first-derivation reader's, and the meaning comparison's too.
    """
    real = FastTree.build
    tried: list[int] = []

    def build(self: FastTree, handle: int) -> IrSelf:
        """Decline while fewer than ``declined`` handles have been asked."""
        tried.append(handle)
        return IrNone if len(tried) <= declined else real(self, handle)

    patch.setattr(FastTree, "build", build)


def twin_arm_grammar() -> IrAst:
    """v ::= a | b, a/b both "x" — the start completes the whole input two ways."""
    return norm(
        IrRule("v", IrAlternation(IrRuleRef("a"), IrRuleRef("b"))),
        IrRule("a", IrLiteral("x")),
        IrRule("b", IrLiteral("x")),
        start="v",
    )
