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

from lexic.parsing.pda import reduce_runtime as rr
from lexic.parsing.pda.runtime import PdaKernel


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
