"""Grammar sources the specialisation tests share.

A helper, not a test: it defines inputs and asserts nothing, so the tests that
import it are free to be renamed without breaking each other at collection.
"""

from __future__ import annotations

ATTEMPT_GATED_VSTR = (
    "# @lexical unit\n"
    "root ::= n tail\n"
    "n ::= unit*\n"
    "unit ::= p | q\n"
    'p ::= "a"\n'
    'q ::= "b"\n'
    "tail ::= [a-c]\n"
)
"""``unit``'s FIRST (``a``/``b``) overlaps ``n``'s own stored continuation
(``tail``'s FIRST, unioned in from ``n``'s one call site), and no k-window
separates an unbounded run of ``unit`` from ``tail`` — so ``n``'s loop item is
genuinely ungatable and carries :data:`GATE_ATTEMPT`. ``# @lexical unit``
makes ``unit`` ref-free (the noise-alternation shape I12 fixed): a plain,
untabled ``value_str`` clone the buggy line would have inlined regardless of
the gate. Confirmed locally (not committed) that reverting I12's guard makes
every one of these inputs raise :class:`PdaFail` at position 0 — the runtime's
``gate_take`` sees the stored FIRST and follow overlap and bails immediately,
where the fixed build's ``attempt_iteration`` speculates and succeeds."""
