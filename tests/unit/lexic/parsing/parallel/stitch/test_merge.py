"""Focused shell and boundary reconstruction tests."""

from __future__ import annotations

import pytest

import lexic.parsing.parallel.stitch.merge as merge_module
from lexic.compile import compile_text
from lexic.exceptions import LexicError
from lexic.parsing.parallel.policy import MIN_CHUNK
from tests.unit.lexic.parsing.parallel.stitch.support import (
    assert_exact_split,
    assert_outer_split,
    recorded_split,
    split_case,
)

OUTER = (
    "root ::= outer\n"
    "outer ::= lead group trail\n"
    'lead ::= "[" ws\n'
    "group ::= open items close\n"
    'open ::= "{" ws\n'
    'close ::= ws "}"\n'
    "items ::= item more*\n"
    "more ::= comma item\n"
    'comma ::= "," ws\n'
    "item ::= [a-z]+\n"
    'trail ::= ws "]"\n'
    'ws ::= " "*\n'
)

INLINE_BOUNDARIES = (
    "root ::= array\n"
    'array ::= "[" ws items "]" ws\n'
    "items ::= value more*\n"
    "more ::= comma value\n"
    'comma ::= "," ws\n'
    "value ::= object\n"
    'object ::= "{" word "}" ws\n'
    "word ::= [a-z]+\n"
    'ws ::= " "*\n'
)

TRAILING_ONLY = (
    "root ::= array\n"
    'array ::= "[" items close\n'
    "items ::= word more*\n"
    'more ::= "," word\n'
    'close ::= ws "]"\n'
    "word ::= [a-z]+\n"
    'ws ::= " "*\n'
)


def test_configured_outer_arm_preserves_closing_boundary_spaces() -> None:
    """An indirect group keeps whitespace owned by its closing arm."""
    text = "[ { " + ", ".join("a" * 20 for _ in range(900))
    text += "   } ]"
    assert_outer_split(split_case(OUTER, text, "group", 4), text)


def test_mixed_separator_whitespace_survives_shallow_joint_reconstruction() -> None:
    """Boundary tails retain varying separator whitespace during a shallow join."""
    separators = [", ", ",    ", ",   ", ",  "]
    items = ["a" * 20]
    for index in range(899):
        items.append(separators[index % len(separators)] + "a" * 20)
    text = "[ { " + "".join(items) + " } ]"
    assert_exact_split(split_case(OUTER, text, "group", 8), text)


def test_inline_closer_preserves_opening_whitespace_slot() -> None:
    """Opening whitespace survives despite an inline closing bracket."""
    text = "[   " + ", ".join("{" + "a" * 20 + "}" for _ in range(900)) + "]"
    assert_exact_split(split_case(INLINE_BOUNDARIES, text, "array", 8), text)


def test_trailing_only_close_preserves_closing_boundary_spaces() -> None:
    """A trailing close arm retains its final whitespace during stitching."""
    words = ",".join("a" * 20 for _ in range(900))
    text = "[" + words + "   ]"
    plan, sequential, parallel = split_case(TRAILING_ONLY, text, "array", 8)

    assert plan is not None
    assert plan.outer_begin is None
    assert plan.outer_end is not None
    assert parallel is not None
    assert parallel == sequential
    assert parallel.to_text() == text


def test_missing_shallow_witness_declines_without_reparsing_delegated_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed shell witness does not fall back to a large head parse."""
    grammar_source = (
        "root ::= doc\n"
        "doc ::= group\n"
        'group ::= "{" items "}"\n'
        "items ::= item more*\n"
        'more ::= "," item\n'
        "item ::= [0-9]+\n"
    )
    compiled = compile_text(grammar_source)
    text = "{" + ",".join(str(index) for index in range(2600)) + "}"

    def fail_generate(*_args, **_kwargs):
        raise LexicError("forced shallow witness failure")

    monkeypatch.setattr(merge_module, "_template_tail", lambda *_args: None)
    monkeypatch.setattr(merge_module, "generate", fail_generate)
    recording_parse, parallel = recorded_split(compiled, text, 4)

    assert parallel is None
    assert recording_parse.calls
    short_calls = [
        (start, length) for start, length in recording_parse.calls if length < MIN_CHUNK
    ]
    assert short_calls == []
    assert not any(start == "item" for start, _length in recording_parse.calls)


def test_multiple_regions_use_unique_generated_standins_not_source_heads() -> None:
    """Shared head rules never make shell routing reparse a delegated item."""
    grammar_source = (
        "root ::= group group\n"
        'group ::= "{" items "}"\n'
        "items ::= item more*\n"
        'more ::= "," item\n'
        "item ::= [a-z]+\n"
    )
    compiled = compile_text(grammar_source)
    item = "a" * 3000
    group = "{" + ",".join([item] * 8) + "}"
    text = group + group
    recording_parse, parallel = recorded_split(compiled, text, 8)

    assert parallel is not None
    assert parallel.to_text() == text
    group_calls = [
        length for start, length in recording_parse.calls if start == "group"
    ]
    assert len([length for length in group_calls if length >= MIN_CHUNK]) == 16
    assert all(length >= MIN_CHUNK or length <= 256 + 2 for length in group_calls)
