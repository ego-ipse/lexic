"""A bracketed region that IS the start rule divides like one a reference down.

``root ::= "[" value ("," value)* "]"`` and ``root ::= arr`` over the same
bracket derive the same strings, so they must split alike: no formulation is
privileged. A region whose rule is the start rule has no owner to splice its
merged node into — the node is the whole result — and is laid over the shell's
own model; a recursive start rule's nested regions are not, and stay spliced
into their owners. The wrapped forms are the controls the root forms must match.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import LexicError
from tests.split_helpers import assert_parallel_matches_sequential, engages

_CORES = (2, 3, 8)


def _numbers(entries: int) -> str:
    return "[" + ",".join(str(n) for n in range(entries)) + "]"


def _entries(entries: int, opener: str, closer: str) -> str:
    """``key:n`` entries with letter-only keys of varying width."""
    keys = ("k" + "abcdefg"[: n % 7 + 1] for n in range(entries))
    return opener + ",".join(f"{key}:{n}" for n, key in enumerate(keys)) + closer


_ENTRY_RULES = 'entry ::= key ":" value\nkey ::= [a-z]+\nvalue ::= [0-9]+\n'

CASES = {
    "array-at-root": (
        'root ::= "[" value ("," value)* "]"\nvalue ::= [0-9]+\n',
        _numbers(4000),
    ),
    "array-wrapped": (
        'root ::= arr\narr ::= "[" value ("," value)* "]"\nvalue ::= [0-9]+\n',
        _numbers(4000),
    ),
    "hoisted-list-at-root": (
        'root ::= "<" list ">"\nlist ::= entry ("," entry)*\n' + _ENTRY_RULES,
        _entries(3000, "<", ">"),
    ),
    "hoisted-list-wrapped": (
        'root ::= env\nenv ::= "<" list ">"\nlist ::= entry ("," entry)*\n'
        + _ENTRY_RULES,
        _entries(3000, "<", ">"),
    ),
    "object-at-root": (
        'root ::= "{" entry ("," entry)* "}"\n' + _ENTRY_RULES,
        _entries(3000, "{", "}"),
    ),
    "recursive-start": (
        'root ::= "[" item ("," item)* "]"\nitem ::= root | num\nnum ::= [0-9]+\n',
        "["
        + ",".join(f"[{n},[{n},{n}],{n}]" if n % 3 else str(n) for n in range(2500))
        + "]",
    ),
    "nested-divides-inside-root": (
        'root ::= "[" item ("," item)* "]"\nitem ::= root | num\nnum ::= [0-9]+\n',
        "["
        + ",".join(str(n) for n in range(200))
        + ",["
        + ",".join(str(n) for n in range(6000))
        + "],"
        + ",".join(str(n) for n in range(200))
        + ",["
        + ",".join(str(n) for n in range(6000))
        + "]]",
    ),
    "trailing-noise-at-root": (
        'root ::= "[" value ("," value)* "]" ws\nvalue ::= [0-9]+\nws ::= [ \\n]*\n',
        _numbers(4000) + " \n  \n",
    ),
}


@pytest.mark.parametrize("cores", _CORES)
@pytest.mark.parametrize("case", sorted(CASES))
def test_a_bracket_at_the_root_divides_and_keeps_the_sequential_model(
    case: str, cores: int
) -> None:
    """Engaged, and the class, model and bytes of the sequential parse."""
    source, text = CASES[case]
    compiled = compile_text(source, cache_key=f"root-region-{case}")
    assert engages(compiled, text, cores), case
    assert_parallel_matches_sequential(compiled, text, cores)


def test_a_root_region_refuses_malformed_text_as_sequential_does() -> None:
    """A piece that fails declines the split; the sequential parse refuses."""
    source, text = CASES["array-at-root"]
    compiled = compile_text(source, cache_key="root-region-malformed")
    broken = text[: len(text) // 2] + ",," + text[len(text) // 2 :]
    with pytest.raises(LexicError) as sequential:
        compiled.parse(broken, cores=1)
    with pytest.raises(type(sequential.value)) as split:
        compiled.parse(broken, cores=8)
    assert str(split.value) == str(sequential.value)
