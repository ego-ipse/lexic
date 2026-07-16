"""Adversarial: a deep GRAMMAR structure must not overflow compile-time walks.

A 300-rule unit-ref chain (``r0 ::= "[" r1 "]"`` ... ``r300 ::= "0"``) used to
overflow the Python stack inside pydantic's ``model_rebuild`` — the naive
rebuild order built the whole model chain in one recursive descent. codegen
now rebuilds leaf-first (referenced classes before their referrers), so each
schema build sees its dependencies already complete and stays shallow. The
parse side keeps its own stack safety in the PDA clone compiler, so the deep
chain compiles, parses, and round-trips cleanly.

The nested-inline-groups shape (``r ::= (((..."a"...)))``) used to overflow
the recursive canonicalizer walk instead; ``canonicalize`` now runs on the
iterative :class:`~lexic.ir.walk.IrBottomUp` driver, which also collapses the
single-arm nesting to a flat rule, so everything downstream sees a shallow
tree.
"""

from __future__ import annotations

from lexic.compile import compile_text

_DEPTH = 300


def test_deep_nested_groups_round_trip_without_overflow() -> None:
    """300 nested inline groups canonicalize, compile, and round-trip."""
    grammar = "r ::= " + "(" * _DEPTH + '"a"' + ")" * _DEPTH + "\n"
    compiled = compile_text(grammar, cache_key="adversarial-deepg-groups")
    assert compiled.parse("a").to_text() == "a"


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


def test_800_rule_chain_round_trips_and_dumps() -> None:
    """An 800-rule chain — past pydantic's schema-inlining cliff (~450).

    Schema expansion joints (every ``binding._SCHEMA_JOINT_STRIDE``-th class
    along an acyclic ref chain presents a shallow validate-through-the-class
    schema) bound the inlined schema depth, so compile, parse, round-trip,
    dump, and dict-input validation all hold at depths pydantic alone cannot
    build.
    """
    depth = 800
    compiled = compile_text(_ref_chain(depth), cache_key="adversarial-deepg-800")
    text = "[" * depth + "0" + "]" * depth
    model = compiled.parse(text)
    assert model.to_text() == text
    dumped = model.model_dump()
    steps = 0
    cursor: object = dumped
    while isinstance(cursor, dict) and len(cursor) == 1:
        cursor = next(iter(cursor.values()))
        steps += 1
    assert steps == depth + 1  # every chain level serialized to a plain dict
    assert model.semantic_dump()  # the method still works across joints
