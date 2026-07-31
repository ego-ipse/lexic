"""Tests for lexic.parsing.pda.core.errors — PdaFail.

Homed in its own leaf module so :mod:`~lexic.parsing.pda.runtime.kernel.kernel` and
:mod:`~lexic.parsing.pda.runtime.islands` can both raise it without an import cycle;
``runtime`` re-exports it, so callers importing either path get the identical
class.
"""

from __future__ import annotations

import pytest

from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.kernel.kernel import PdaFail as RuntimePdaFail


def test_pda_fail_is_an_exception_subclass():
    """PdaFail is a plain Exception subclass — no special construction."""
    assert issubclass(PdaFail, Exception)


def test_pda_fail_carries_its_message():
    """str() on a raised instance recovers the original message, unchanged."""
    assert str(PdaFail("island 'x': no match at 3")) == "island 'x': no match at 3"


def test_pda_fail_is_raisable_and_catchable():
    """A raised PdaFail is catchable via pytest.raises like any Exception."""
    with pytest.raises(PdaFail, match="boom"):
        raise PdaFail("boom")


def test_runtime_reexports_the_identical_class():
    """kernel.py's re-export is the SAME object, not a duplicate definition."""
    assert RuntimePdaFail is PdaFail
