"""Tests for the attempt-aware frame-less value-string loops."""

from __future__ import annotations

import pytest

from lexic.compile import Directives, compile_text
from lexic.parsing.pda.compiler.program.flatten import FlatArm
from lexic.parsing.pda.compiler.program.opcodes import OP_AVDISP, OP_AVSTR
from lexic.parsing.pda.core.errors import ProbeFork
from lexic.parsing.pda.runtime.admission import KernelCaches
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.kernel import attempt_inline as attempt_inline_module
from lexic.parsing.pda.runtime.kernel.attempt_inline import AttemptInlineMixin
from lexic.parsing.pda.runtime.kernel.decisions import Attempting
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.trace import watch
from tests.specialize_helpers import ATTEMPT_GATED_VSTR
from tests.unit.lexic.parsing.pda.compiler.test_clones import pda_from_text
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone
from tools.benchmark.cases.grammars import BENCHES


def test_an_attempt_aware_value_str_runs_its_fused_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The specialised item must not return to the per-iteration driver."""

    def unexpected(*_args: object) -> int:
        raise AssertionError("attempt-aware value_str used the generic loop")

    monkeypatch.setattr(Attempting, "attempt_iteration", unexpected)
    model = pda_model(pda_from_text(ATTEMPT_GATED_VSTR), "aaac")
    assert model.to_text() == "aaac"


def test_a_resumed_attempt_probe_keeps_its_completed_iteration() -> None:
    """A take-side probe must not demand its consumed iteration again at EOF."""
    bench = next(candidate for candidate in BENCHES if candidate.name == "gbnf-meta")
    compiled = compile_text(
        bench.source,
        cache_key="attempt-inline-resumed-count",
        flavour=bench.flavour,
        directives=Directives(lexical=frozenset({"comment-line"})),
    )
    chunk = bench.full[2542:5117]
    tables = compiled.pda_tables()

    run = watch(tables, chunk, compiled.executor, cap=10_000)

    assert run.derived
    assert pda_model(tables, chunk, compiled.executor).to_text() == chunk


# ── an undecidable iteration is the gated engine's, never a miss ────────────


class _UndecidableBelow(AttemptInlineMixin[str]):
    """Just enough kernel for one attempt-aware loop, whose every iteration
    meets a boundary the PDA cannot decide."""

    __slots__ = ("text", "pos", "_caches")

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self._caches = KernelCaches()

    def _sink_for(self, frame: Frame[str], arm: FlatArm, i: int) -> list[str]:
        return []

    def _attempt_choice(
        self, arm: FlatArm, i: int, pos: int, got: tuple[int, list[str]]
    ) -> bool:
        return True

    def _inline_once(self, arm: FlatArm, i: int, pos: int) -> tuple[int, list[str]]:
        raise ProbeFork("an undecidable boundary inside the iteration", pos)


def _one_loop_arm(kind: int) -> FlatArm:
    """An optional unbounded loop whose FIRST admits ``a`` and whose
    continuation does not: the forced branch of every attempt loop."""
    return flat_arm(
        1,
        kinds=(kind,),
        los=(0,),
        his=(-1,),
        gate_data=(((frozenset("a"), False), (frozenset(), False)),),
        payloads=(None,),
    )


def test_an_undecidable_iteration_is_not_read_as_a_miss() -> None:
    """Swallowed as a failed iteration, it closed the loop and committed a
    shorter reading the gated engine may build differently."""
    with pytest.raises(ProbeFork):
        _UndecidableBelow("a").attempt_inline(_one_loop_arm(OP_AVSTR), 0, 0)


def test_an_undecidable_dispatch_iteration_is_not_read_as_a_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dispatch loop's forced branch runs the matcher itself; an
    undecidable boundary there must leave the loop the same way."""

    def undecidable(*_args: object) -> int:
        raise ProbeFork("an undecidable boundary inside the dispatch", 0)

    monkeypatch.setattr(attempt_inline_module, "vdisp_once", undecidable)
    arm = _one_loop_arm(OP_AVDISP)
    frame: Frame[str] = Frame(arm, [], flat_clone(), 0)
    with pytest.raises(ProbeFork):
        _UndecidableBelow("a").attempt_inline_loop(frame, arm, 0, 0)
