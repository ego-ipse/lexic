"""Tests for lexic.parsing.pda.core.errors — PdaFail.

Homed in its own leaf module so :mod:`~lexic.parsing.pda.runtime.kernel.kernel` and
:mod:`~lexic.parsing.pda.runtime.islands` can both raise it without an import cycle;
``runtime`` re-exports it, so callers importing either path get the identical
class.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing import PdaKernel
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
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


def test_pda_fail_carries_a_structured_position():
    """The position is an attribute, not something to regex out of the message."""
    fail = PdaFail("no arm at 7", 7)
    assert fail.pos == 7
    assert str(fail) == "no arm at 7"


def test_pda_fail_without_a_position_reports_minus_one():
    """A failure that is not about a position says so, rather than inventing one."""
    assert PdaFail("start rule produced no model").pos == -1


def test_probe_fork_inherits_the_position():
    """ProbeFork is a PdaFail and carries its boundary the same way."""
    fork = ProbeFork("attempt loop at 4: taking and stopping are both viable", 4)
    assert isinstance(fork, PdaFail)
    assert fork.pos == 4


def test_a_real_refusal_reports_the_position_it_stopped_at():
    """The kernel's own failure names its position as an int, not as prose."""
    compiled = compile_text('root ::= "abc" digit\ndigit ::= [0-9]\n')
    with pytest.raises(PdaFail) as caught:
        PdaKernel(compiled.pda_tables(), "abcX", compiled.fold).run()
    assert caught.value.pos == 3


def test_the_position_is_where_the_failing_construct_began():
    """Not the deepest matched character — the offset the attempt started from.

    A mismatch inside a literal reports the literal's own start, and the
    optimizer merges adjacent exactly-once literals into one run, so
    ``"abc" "def"`` against ``abcXef`` reports 0 rather than 3. Pinned because
    a caller drawing a caret needs to know which of the two it is getting.
    """
    compiled = compile_text('root ::= "abc" "def"\n')
    with pytest.raises(PdaFail) as caught:
        PdaKernel(compiled.pda_tables(), "abcXef", compiled.fold).run()
    assert caught.value.pos == 0
