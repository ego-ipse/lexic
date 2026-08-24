"""Tests for the attempt-aware frame-less value-string loops."""

from __future__ import annotations

import pytest

from lexic.parsing.pda.runtime.kernel.decisions import Attempting
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from tests.unit.lexic.parsing.pda.compiler.program.test_specialize import (
    ATTEMPT_GATED_VSTR,
)
from tests.unit.lexic.parsing.pda.compiler.test_clones import pda_from_text


def test_an_attempt_aware_value_str_runs_its_fused_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The specialised item must not return to the per-iteration driver."""

    def unexpected(*_args: object) -> int:
        raise AssertionError("attempt-aware value_str used the generic loop")

    monkeypatch.setattr(Attempting, "attempt_iteration", unexpected)
    model = pda_model(pda_from_text(ATTEMPT_GATED_VSTR), "aaac")
    assert model.to_text() == "aaac"
