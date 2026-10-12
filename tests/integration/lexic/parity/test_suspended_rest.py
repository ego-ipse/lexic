"""What may follow a boundary is read from the item each enclosing frame is
suspended in.

An exactly-once reference (``OP_REF1``) advances its frame past itself before
it descends, so ``frame.i`` already names the NEXT item while the child runs.
Reading the rest from ``frame.i`` skipped the item right after the reference,
so a stop side that continues into it read as dead, and the take was forced.
Both witnesses gave a public answer the gated engine does not give.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lexic.compile import compile_text
from lexic.parsing.pda.compiler.program.opcodes import OP_CC, OP_LIT1, OP_REF, OP_REF1
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.kernel.verdicts import Verdicts
from lexic.parsing.pda.runtime.matchers import REST_ADMITS, REST_ADMITS_HARD, REST_DEAD
from tests.parity_helpers import DECLINED, REFUSED, answers
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone

X_TAIL_END = (
    'doc ::= x end\nx ::= part+ tail?\npart ::= "aa"\ntail ::= [a;]+\nend ::= "a"?\n'
)
"""``x`` is an exactly-once reference in ``doc``'s arm, so while ``x`` runs
``doc`` already stands at ``end``. Whether ``tail?`` may stop at the last
``a`` is whether ``end`` can take it, which the old reading never asked."""

W1 = (
    "root ::= item+\nitem ::= p | q\n"
    'p ::= "p" x " c"\nx ::= w (" " w)*\nw ::= [a-z]+\n'
    'q ::= "p" [a-z ]+\n'
)
"""Inside ``p``, ``x``'s group loop meets a space; whether ``x`` may stop
there is whether ``p``'s `` c`` follows, the item right after ``x``'s
reference."""


@pytest.mark.parametrize("text", ["aaa", "aaaaa"])
def test_a_stop_side_continuing_after_a_reference_is_seen(text: str) -> None:
    """``tail`` takes the last ``a`` and ``end`` is empty, as the gated
    engine has it; the predictive route no longer forces ``tail?`` to stop."""
    predictive, gated = answers(X_TAIL_END, "suspended-x-tail-end", text)
    compiled = compile_text(X_TAIL_END, cache_key="suspended-x-tail-end")
    assert "Tail('a')" in gated
    assert repr(compiled.parse(text, cores=1)) == gated
    assert predictive in (gated, DECLINED)


@pytest.mark.parametrize("text", ["pa c", "pab c", "pa b c"])
def test_an_arm_choice_hidden_behind_a_reference_is_refused(text: str) -> None:
    """``p`` and ``q`` both derive the text: the gated engine refuses it, and
    so does the public parse now, instead of committing ``q``."""
    predictive, gated = answers(W1, "suspended-w1", text)
    assert gated == REFUSED
    assert predictive in (DECLINED, REFUSED)
    compiled = compile_text(W1, cache_key="suspended-w1")
    with pytest.raises(Exception, match="ambiguous"):
        compiled.parse(text, cores=1)


# ── each enclosing frame is read from the item it is suspended in ──────────


def _boundary_class(parent: Frame, text: str, pos: int) -> int:
    """``_beyond_class`` at a loop that ends its own arm, under ``parent``,
    so the walk's answer is the parent's."""
    top_arm = flat_arm(1, kinds=(OP_REF,), los=(0,))
    top = Frame(top_arm, [], flat_clone(), 0)
    kern = SimpleNamespace(text=text, stack=[parent, top])
    return vars(Verdicts)["_beyond_class"](kern, top_arm, 0, pos)


def test_a_frame_suspended_by_an_exactly_once_reference_reads_after_it() -> None:
    """``x " " ">"``: ``OP_REF1`` advanced the parent to the closer's space
    before ``x`` descended, so the child runs for ``x`` and the stop side
    continues into `` >``. Read from ``frame.i`` the walk started at ``>``
    and called the stop side dead."""
    arm = flat_arm(
        3,
        kinds=(OP_REF1, OP_LIT1, OP_LIT1),
        payloads=(None, " ", ">"),
        los=(1, 1, 1),
    )
    parent = Frame(arm, [], flat_clone(), 0)
    parent.i, parent.count = 1, 0
    assert _boundary_class(parent, "ab >", 2) == REST_ADMITS_HARD


def test_a_frame_suspended_in_a_quantified_descent_reads_after_its_own_item() -> None:
    """A quantified descent counts itself and stands AT its item, so its rest
    starts after it: the optional class at item 1 is not in it, and the
    mandatory ``q`` refusing ``z`` leaves the stop side dead. Read as an
    ``OP_REF1`` suspension, item 1 would admit ``z`` and make it viable."""
    arm = flat_arm(
        3,
        kinds=(OP_REF1, OP_CC, OP_LIT1),
        payloads=(None, (frozenset("z"), False), "q"),
        los=(1, 0, 1),
    )
    parent = Frame(arm, [], flat_clone(), 0)
    parent.i, parent.count = 1, 1
    assert _boundary_class(parent, "az", 1) == REST_DEAD
    parent.count = 0
    assert _boundary_class(parent, "az", 1) == REST_ADMITS
