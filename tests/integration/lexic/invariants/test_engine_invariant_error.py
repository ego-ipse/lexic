"""`EngineInvariantError` escapes the two catches a fallback is built on.

The class exists for one property: a breach of an engine invariant must not be
answered with a correct-looking parse. Both fallback seams catch a family —
`LexicError` on the way to a sequential parse, `PdaFail` on the way to the
gated engine — and either would turn "the engine built a wrong model" into
"this chunk did not parse, try the other route".

So the property is asserted directly rather than inferred from the base class,
because the base class is the thing a future edit would change.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from lexic.exceptions import EngineInvariantError, LexicError
from lexic.parsing.parallel import pool
from lexic.parsing.pda.core.errors import PdaFail


def test_it_is_not_a_member_of_either_caught_family() -> None:
    """Neither family, and a `RuntimeError` — stated as three facts."""
    error = EngineInvariantError("the engine broke")

    assert not isinstance(error, LexicError)
    assert not isinstance(error, PdaFail)
    assert isinstance(error, RuntimeError)


def test_an_except_lexicerror_lets_it_through() -> None:
    """The seam that falls back to a sequential parse does not see it."""
    with pytest.raises(EngineInvariantError):
        try:
            raise EngineInvariantError("the engine broke")
        except LexicError:  # pragma: no cover - the point is that it misses
            pytest.fail("a fallback seam swallowed an engine invariant breach")


def test_an_except_pdafail_lets_it_through() -> None:
    """The seam that falls back to the gated engine does not see it either."""
    with pytest.raises(EngineInvariantError):
        try:
            raise EngineInvariantError("the engine broke")
        except PdaFail:  # pragma: no cover - the point is that it misses
            pytest.fail("the engine seam swallowed an engine invariant breach")


def test_a_top_level_except_exception_does_see_it() -> None:
    """It is an error, not control flow — so it reaches a bug report.

    The precedent that suggests `BaseException` is `_Return`, which is control
    flow and must escape everything. This must escape the two fallback catches
    and nothing more; a breach that a top-level handler could not log would
    kill the process with no account of itself.
    """
    with pytest.raises(Exception) as caught:  # the breadth IS the assertion
        raise EngineInvariantError("the engine broke")

    assert isinstance(caught.value, EngineInvariantError)


def test_the_one_broad_catch_in_src_re_raises_it() -> None:
    """`pool.py`'s `BaseException` handler is cleanup, not a catch.

    It is the only broad handler in `src/`, so it is the only place that could
    swallow this by accident. Pinned by AST rather than by searching the source
    text: `"raise" in source` is satisfied by a COMMENT containing the word, so
    a string pin passes precisely when someone documents the edit that breaks
    it — and delimiting the handler by blank lines makes it fail on formatting.
    """
    tree = ast.parse(inspect.getsource(pool))
    broad = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
        and isinstance(node.type, ast.Name)
        and node.type.id == "BaseException"
    ]

    assert broad, "pool.py's broad handler is gone — re-point this pin"
    for handler in broad:
        raises = [one for one in ast.walk(handler) if isinstance(one, ast.Raise)]
        assert raises, f"the handler at line {handler.lineno} swallows"
