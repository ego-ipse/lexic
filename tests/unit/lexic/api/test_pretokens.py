"""``lexic.api.pretokens`` — the ``tokenizer.json`` split specs.

These families are one format's vocabulary, which is why they live outside
``lexic.ir`` (the spine keeps only ``IrPretoken``, the concept). Their
patterns are hand-implemented — ``\\p{L}`` / ``\\p{N}`` have no stdlib ``re``
spelling — so the matching logic needs direct tests rather than only
end-to-end ones: the real-file suites prove *exactness* but run in the slow
lane and cannot say WHICH alternative fired.

The invariant every spec must hold: **splitting preserves the input**. The
pieces concatenate back exactly, or offsets stop being derivable and token
spans silently drift.
"""

from __future__ import annotations

import pytest

from lexic.api.pretokens import (
    BYTE_LEVEL_REMAP,
    IrByteLevel,
    IrCl100k,
    IrDigits,
    IrSplitMerged,
)

_SPECS = (
    IrCl100k(),
    IrByteLevel(),
    IrDigits(True),
    IrDigits(False),
    IrSplitMerged(" "),
)

_TEXTS = (
    "",
    " ",
    "\n",
    "Hello world",
    "  leading and  double",
    "I'll don't he's",
    "abc123def",
    "3.14 * r**2",
    "a\n\nb\r\nc",
    "x😀y",
    "世界 hello",
    "trailing   ",
    "\t\ttabs",
    "MiXeD_CaSe-99",
)


@pytest.mark.parametrize("spec", _SPECS, ids=lambda s: type(s).__name__)
@pytest.mark.parametrize("text", _TEXTS, ids=repr)
def test_splitting_preserves_the_input(spec, text: str) -> None:
    """Pieces concatenate back to the input — every spec, every text.

    This is the contract ``IrPretoken`` states, and the one that keeps token
    spans mappable to char offsets. A spec that drops or duplicates a char
    corrupts offsets rather than failing loudly.
    """
    assert "".join(spec.split(text)) == text


# ── the cl100k pattern, alternative by alternative ───────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello world", ["Hello", " world"]),  # letters, then prefix+letters
        ("I'll", ["I", "'ll"]),  # contraction is its own piece
        ("IT'S", ["IT", "'S"]),  # ... case-insensitively
        ("abc123", ["abc", "1", "2", "3"]),  # digits are SINGLE, never runs
        ("a1b", ["a", "1", "b"]),
        ("3.14", ["3", ".", "1", "4"]),  # symbol run between digits
        ("a  b", ["a", " ", " b"]),  # \\s+(?!\\S) leaves one space to prefix
        ("a\n\nb", ["a", "\n\n", "b"]),  # \\s*[\\r\\n]+ takes the newline run
        ("hi!!", ["hi", "!!"]),  # symbol run
        ("", []),
    ],
)
def test_cl100k_alternatives(text: str, expected: list[str]) -> None:
    """Each pattern alternative fires where the spec says it should.

    The distinguishing feature against the GPT-2 pattern is ``\\p{N}``: this
    one emits ONE digit per piece where GPT-2 takes a run, so ``abc123``
    splits four ways rather than two.
    """
    assert IrCl100k().split(text) == expected


def test_cl100k_differs_from_the_gpt2_pattern() -> None:
    """The two fixed patterns are genuinely different specs, not aliases."""
    assert IrCl100k().split("abc123") != IrByteLevel().split("abc123")
    assert IrByteLevel().split("abc123") == ["abc", "123"]  # runs


# ── the other families ───────────────────────────────────────────────────


def test_digits_individual_versus_runs() -> None:
    """``IrDigits`` splits number chars singly or as runs, per its flag."""
    assert IrDigits(True).split("a12b") == ["a", "1", "2", "b"]
    assert IrDigits(False).split("a12b") == ["a", "12", "b"]


def test_split_merged_sticks_the_separator_backward() -> None:
    """``IrSplitMerged`` ends each piece AT its separator (inclusive)."""
    assert IrSplitMerged(" ").split("a b c") == ["a ", "b ", "c"]
    assert IrSplitMerged("-").split("x-y-") == ["x-", "y-"]


def test_an_empty_separator_never_splits() -> None:
    """A degenerate separator yields the text whole, not an infinite loop."""
    assert IrSplitMerged("").split("abc") == ["abc"]


def test_byte_level_remap_covers_every_byte_bijectively() -> None:
    """The remap is a 256-entry bijection — it must invert to decode."""
    assert len(BYTE_LEVEL_REMAP) == 256
    assert len({str(v) for v in BYTE_LEVEL_REMAP.values()}) == 256
