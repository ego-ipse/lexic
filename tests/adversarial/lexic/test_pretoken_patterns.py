"""Adversarial: the hand-written pre-token patterns vs the engine that defines them.

``tests/unit/lexic/api/test_pretokens.py`` pins each alternative with
written-out expectations, which can only ever be as correct as the author's
reading of the pattern. These are DIFFERENTIAL instead: every case runs
through ``tokenizers``' own regex engine over the very pattern string the
module stores, so a misreading surfaces as a mismatch rather than as a
matching pair of mistakes.

Two hazards live in hand-implementing a regex with no engine, and both have
produced wrong ids on a real vocabulary: a character class spelled with the
nearest Python predicate rather than the Unicode property the pattern means,
and case-insensitivity spelled as ``lower()`` rather than as folding. The
sweeps here are exhaustive over the codepoint space precisely because
sampling cannot say a class is *exactly* right.

Fixture-free — the patterns are fixed strings, so no vocabulary is involved.
"""

from __future__ import annotations

import itertools
import random

import pytest

from lexic.api.pretokens import (
    _CONTRACTIONS,
    QWEN_PATTERN,
    IrByteLevel,
    IrQwenSplit,
    _gpt2_piece,
    _is_letter,
    _is_number,
    _is_space,
    _qwen_piece,
)
from lexic.ir import MAX_CODEPOINT

tokenizers = pytest.importorskip("tokenizers")

GPT2_PATTERN = (
    "'s|'t|'re|'ve|'m|'ll|'d| ?\\p{L}+| ?\\p{N}+| ?[^\\s\\p{L}\\p{N}]+|\\s+(?!\\S)|\\s+"
)
"""The ByteLevel pre-token pattern.

Held here rather than in ``src`` because nothing in the library needs the
string — ``_gpt2_piece`` *is* the pattern. A constant an oracle is built from
is only as good as its provenance, so
:func:`test_the_gpt2_pattern_is_the_one_bytelevel_ships` checks it against the
shipped ``ByteLevel`` rather than against the author's memory.
"""

_SURROGATES = range(0xD800, 0xE000)
"""Not encodable as utf-8, so the engine cannot be asked about them."""

_CLASSES = (
    ("\\s", _is_space),
    ("\\p{L}", _is_letter),
    ("\\p{N}", _is_number),
)

_PATTERNS = (
    pytest.param(QWEN_PATTERN, IrQwenSplit(), id="qwen"),
    pytest.param(GPT2_PATTERN, IrByteLevel(), id="gpt2"),
)

_BOUNDARY = (
    "\x1c",
    "\x1d",
    "\x1f",  # str.isspace(), but not White_Space
    " ",
    "\t",
    "\n",
    "\r",
    "\x0b",
    "\x0c",
    "\x85",
    "\xa0",
    " ",
    "　",  # the exotic White_Space members
    "'",
    "’",  # the literal apostrophe and its lookalike
    "s",
    "S",
    "ſ",
    "t",
    "r",
    "e",
    "l",
    "d",  # contraction letters + long s
    "ẞ",
    "İ",  # folds that change length
    "a",
    "1",
    "١",
    "!",
    "-",
    "中",
    "́",
)
"""One character from every class boundary the patterns can discriminate on."""


def _splitter(pattern: str):
    """The engine's own splitter over ``pattern``."""
    return tokenizers.pre_tokenizers.Split(
        tokenizers.Regex(pattern), behavior="isolated"
    )


def _pieces(splitter, text: str) -> list[str]:
    """``text`` as the engine splits it."""
    return [piece for piece, _span in splitter.pre_tokenize_str(text)]


def _members(pattern: str):
    """A splitter that REMOVES ``pattern``, so an empty result means membership."""
    return tokenizers.pre_tokenizers.Split(
        tokenizers.Regex(pattern), behavior="removed"
    )


def _codepoints() -> list[int]:
    """Every codepoint the engine can be asked about."""
    return [cp for cp in range(MAX_CODEPOINT + 1) if cp not in _SURROGATES]


@pytest.mark.parametrize(("pattern", "predicate"), _CLASSES)
def test_a_class_predicate_matches_the_engine_over_every_codepoint(
    pattern: str, predicate
) -> None:
    """The three character classes agree with the engine's, codepoint by codepoint.

    Exhaustive rather than sampled because the claim being made is that a
    predicate is EXACTLY a Unicode property. ``str.isspace()`` is true for
    four separators that ``White_Space`` excludes, and sampling found that
    only once an input happened to contain one.
    """
    engine = _members(pattern)
    wrong = [
        cp
        for cp in _codepoints()
        if predicate(chr(cp)) != (engine.pre_tokenize_str(chr(cp)) == [])
    ]
    assert wrong == []


def test_the_gpt2_pattern_is_the_one_bytelevel_ships() -> None:
    """:data:`GPT2_PATTERN` is the shipped pattern, not a plausible retelling.

    ByteLevel remaps bytes to working characters, so the pieces are not
    comparable — the CUTS are, and they are what a pattern determines.

    The long digit and letter runs are load-bearing: a quantifier retold as
    ``{1,3}`` (the way a neighbouring family spells the same alternative) is
    indistinguishable from ``+`` on any run short enough to fit it.
    """
    engine = _splitter(GPT2_PATTERN)
    shipped = tokenizers.pre_tokenizers.ByteLevel(
        add_prefix_space=False, use_regex=True
    )
    for text in (
        "Hello world",
        "  \n\n x",
        "don't DON'T",
        " 123 456",
        "a\tb",
        "\r\n\r\n",
        "'s'S",
        "x  y",
        "\x1c!",
        "a\x1d\x1d!",
        "  ---  ",
        "1234567890",
        " 98765 4321",
        "abcdefghij",
        "١٢٣٤٥",
    ):
        spans = [span for _piece, span in engine.pre_tokenize_str(text)]
        assert spans == [span for _piece, span in shipped.pre_tokenize_str(text)], repr(
            text
        )


def test_nothing_case_folds_to_an_apostrophe() -> None:
    """The contraction scan starts only at ``'``; that gate needs this to hold.

    Every contraction alternative begins with a literal apostrophe, so
    skipping every other position is sound exactly while no other codepoint
    can fold into one.
    """
    folds_to_apostrophe = [
        cp for cp in _codepoints() if cp != 0x27 and chr(cp).casefold() == "'"
    ]
    assert folds_to_apostrophe == []


def test_case_folding_never_yields_the_empty_string() -> None:
    """Why a candidate slice is never longer than the contraction it folds to.

    Folding maps each character to at least one, so a slice folding to a word
    of length *n* is itself at most *n* characters — which is what bounds the
    candidate lengths the scan has to try.
    """
    vanishing = [cp for cp in _codepoints() if not chr(cp).casefold()]
    assert vanishing == []


def test_every_codepoint_folding_into_a_contraction_splits_like_the_engine() -> None:
    """The characters that make case folding observable, in contraction position.

    Python folds fully and the engine folds simply, so the two could disagree
    on which characters reach a contraction at all. These are every codepoint
    that can, found by sweep rather than by guessing.
    """
    tails = {word[1:] for word in _CONTRACTIONS}
    folding = [cp for cp in _codepoints() if chr(cp).casefold() in tails]
    assert 0x017F in folding  # long s — the case a lower()-based scan misses
    engine = _splitter(QWEN_PATTERN)
    spec = IrQwenSplit()
    for cp in folding:
        for template in ("'%s", "'%se", "a'%s", "'%s "):
            text = template % chr(cp)
            assert spec.split(text) == _pieces(engine, text), repr(text)


@pytest.mark.parametrize(("pattern", "spec"), _PATTERNS)
def test_a_pattern_matches_the_engine_over_every_boundary_triple(
    pattern: str, spec
) -> None:
    """Exhaustive three-character strings over one character per class boundary.

    Single-codepoint sweeps cannot reach the alternatives that only differ
    when classes ABUT — a separator between two symbols, whitespace before a
    newline run, an apostrophe after a letter.
    """
    engine = _splitter(pattern)
    for combo in itertools.product(_BOUNDARY, repeat=3):
        text = "".join(combo)
        assert spec.split(text) == _pieces(engine, text), repr(text)


@pytest.mark.parametrize(("pattern", "spec"), _PATTERNS)
def test_a_pattern_matches_the_engine_over_deeper_boundary_strings(
    pattern: str, spec
) -> None:
    """Longer boundary strings, where backtracking alternatives can interact."""
    engine = _splitter(pattern)
    rnd = random.Random(20260725)
    for _ in range(20000):
        text = "".join(rnd.choice(_BOUNDARY) for _ in range(rnd.randint(4, 9)))
        assert spec.split(text) == _pieces(engine, text), repr(text)


@pytest.mark.parametrize("piece_at", (_qwen_piece, _gpt2_piece))
def test_a_piece_is_never_empty(piece_at) -> None:
    """An empty piece would hang the split loop, which advances by piece length.

    Every alternative that can be reached consumes at least one character; if
    a class edit ever breaks that, the suite must fail rather than stop
    responding.
    """
    for combo in itertools.product(_BOUNDARY, repeat=2):
        text = "".join(combo)
        for index in range(len(text)):
            assert piece_at(text, index) != "", (repr(text), index)
