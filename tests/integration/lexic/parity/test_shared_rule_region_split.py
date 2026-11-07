"""A bracket arm that shares its rule with other arms divides like a hoisted one.

``val ::= "[" val ("," val)* "]" | num`` and ``val ::= arr | num`` with
``arr ::= "[" val ("," val)* "]"`` derive the same strings, so they must split
alike. Regions are found over the authored grammar, where the bracket belongs
to ``val``; the codegen grammar holds that arm in a single-arm rule of its own,
and the region's own opening character names which — a rule may bracket two
ways (``"[" … "]" | "{" … "}"``). The hoisted forms are the controls.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from tests.split_helpers import assert_parallel_matches_sequential, engages

_CORES = (2, 3, 8)

_ARRAY_ARM = '"[" val ("," val)* "]"'
_OBJECT_ARM = '"{" pair ("," pair)* "}"'
_TAIL = 'pair ::= key ":" val\nkey ::= [a-z]+\nnum ::= [0-9]+\n'


def _array(n: int) -> str:
    """An array of numbers and small nested arrays."""
    return (
        "[" + ",".join(f"[{i},{i}]" if i % 4 == 0 else str(i) for i in range(n)) + "]"
    )


def _object(n: int) -> str:
    """An object whose values are numbers and small nested arrays."""
    keys = ("k" + "abcdefg"[: i % 7 + 1] for i in range(n))
    return (
        "{"
        + ",".join(
            f"{key}:[{i},{i}]" if i % 4 == 0 else f"{key}:{i}"
            for i, key in enumerate(keys)
        )
        + "}"
    )


def _mixed(n: int) -> str:
    """An array holding two large objects among numbers: both bracket kinds."""
    return "[" + ",".join(["1", _object(n), "2", _object(n), "3"]) + "]"


CASES = {
    "one-arm-shared-at-root": (
        f"root ::= {_ARRAY_ARM.replace('val', 'root')} | num\nnum ::= [0-9]+\n",
        _array(5000),
    ),
    "one-arm-shared-below-root": (
        f"root ::= val\nval ::= {_ARRAY_ARM} | num\nnum ::= [0-9]+\n",
        _array(5000),
    ),
    "one-arm-hoisted": (
        f"root ::= val\nval ::= arr | num\narr ::= {_ARRAY_ARM}\nnum ::= [0-9]+\n",
        _array(5000),
    ),
    "two-arms-shared-array-document": (
        f"root ::= val\nval ::= {_ARRAY_ARM} | {_OBJECT_ARM} | num\n" + _TAIL,
        _array(5000),
    ),
    "two-arms-shared-object-document": (
        f"root ::= val\nval ::= {_ARRAY_ARM} | {_OBJECT_ARM} | num\n" + _TAIL,
        _object(3000),
    ),
    "two-arms-shared-both-kinds": (
        f"root ::= val\nval ::= {_ARRAY_ARM} | {_OBJECT_ARM} | num\n" + _TAIL,
        _mixed(2000),
    ),
    "two-arms-hoisted-both-kinds": (
        f"root ::= val\nval ::= arr | obj | num\narr ::= {_ARRAY_ARM}\n"
        f"obj ::= {_OBJECT_ARM}\n" + _TAIL,
        _mixed(2000),
    ),
}


@pytest.mark.parametrize("cores", _CORES)
@pytest.mark.parametrize("case", sorted(CASES))
def test_a_shared_rule_bracket_divides_and_keeps_the_sequential_model(
    case: str, cores: int
) -> None:
    """Engaged, and the class, model and bytes of the sequential parse."""
    source, text = CASES[case]
    compiled = compile_text(source, cache_key=f"shared-region-{case}")
    assert engages(compiled, text, cores), case
    assert_parallel_matches_sequential(compiled, text, cores)
