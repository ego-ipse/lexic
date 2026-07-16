"""Adversarial: a deep GRAMMAR structure must not overflow compile-time walks.

A 300-rule unit-ref chain (``r0 ::= "[" r1 "]"`` ... ``r300 ::= "0"``) used to
overflow the Python stack inside pydantic's ``model_rebuild`` — the naive
rebuild order built the whole model chain in one recursive descent. codegen
now rebuilds leaf-first (referenced classes before their referrers), so each
schema build sees its dependencies already complete and stays shallow. The
parse side keeps its own stack safety in the PDA clone compiler, so the deep
chain compiles, parses, and round-trips cleanly.

Note: the nested-inline-groups shape (``r ::= (((..."a"...)))``) overflows a
different recursive IR walk in ``ir/canonical.py`` and is deferred — not
exercised here (see FINDINGS.md L7).
"""

from __future__ import annotations

from lexic.compile import compile_text

_DEPTH = 300


def _ref_chain(depth: int) -> str:
    """A ``depth``+1 rule unit-ref chain bottoming out at the leaf ``0``."""
    lines = [f'r{i} ::= "[" r{i + 1} "]"' for i in range(depth)]
    lines.append(f'r{depth} ::= "0"')
    return "\n".join(lines) + "\n"


def test_deep_ref_chain_round_trips_without_overflow() -> None:
    """A 300-rule ref chain compiles, parses, and round-trips — no RecursionError."""
    compiled = compile_text(_ref_chain(_DEPTH), cache_key="adversarial-deepg-chain")
    assert len(compiled.classes) == _DEPTH + 1
    text = "[" * _DEPTH + "0" + "]" * _DEPTH
    assert compiled.parse(text).to_text() == text
