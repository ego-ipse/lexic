"""Token additivity — a char grammar is unaffected by token machinery.

The invariant: **char grammars are byte-identical under every token change.**
Binding a tokenizer, or binding a different one, must not move a grammar that
has no token terminals — not its codegen grammar, not its fold, not its
classes, and not what it parses.

This holds structurally (``concretize`` rewrites only ``IrAlphabet`` atoms, so
it is a no-op on a char grammar), which is exactly why it is worth pinning:
the property is invisible until something breaks it, and the whole-suite green
is only indirect evidence — a regression would surface somewhere unrelated,
if at all.

The two tokenizers below deliberately differ in BOTH vocabulary and ids, so a
leak through either channel fails the comparison.
"""

from __future__ import annotations

import random

import pytest

from lexic.compile import CompiledGrammar, Vocabulary, canonical_grammar, compile_text
from lexic.generate import generate
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir import IrChr, IrMap, IrStr, IrTokenizer, IrTuple
from tests.paths import ABNF_GRAMMARS, GBNF_GRAMMARS, GROUND_TRUTH

_TOKEN_GRAMMARS: frozenset[str] = frozenset({"think.gbnf"})
"""The ground-truth grammars that DO carry token terminals."""

CHAR_GRAMMARS: tuple[str, ...] = tuple(
    stem for stem in GBNF_GRAMMARS + ABNF_GRAMMARS if stem not in _TOKEN_GRAMMARS
)
"""Every ground-truth grammar with no token terminals — derived from the
corpus rather than re-listed, so a grammar added to the corpus is covered
here automatically instead of silently escaping the invariant."""


def _tokenizer(name: str, words: tuple[str, ...]) -> IrTokenizer:
    """A longest-match tokenizer over ``words`` (position is the id)."""
    encode = IrMap(*(IrTuple(IrStr(w), IrChr(i)) for i, w in enumerate(words)))
    return IrTokenizer.from_vocab(name, encode)


_TOK_A = _tokenizer("tokens", ("<think>", "</think>", "a", "b"))
_TOK_B = _tokenizer("tokens", ("x", "y", "z", "<think>", "</think>"))
"""Two tokenizers differing in BOTH vocabulary and ids — a leak through either
channel breaks the comparison."""


def _flavour(stem: str):
    """The flavour a ground-truth stem is written in."""
    return GBNF_FLAVOUR if stem.endswith(".gbnf") else ABNF_FLAVOUR


def _three_ways(stem: str) -> tuple[CompiledGrammar, ...]:
    """The same grammar compiled bare, with tokenizer A, and with tokenizer B."""
    text = (GROUND_TRUTH / stem).read_text(encoding="utf-8")
    flavour = _flavour(stem).name
    return (
        compile_text(text, flavour=flavour, cache_key=f"add-bare-{stem}"),
        compile_text(
            text,
            flavour=flavour,
            vocabulary=Vocabulary(_TOK_A),
            cache_key=f"add-a-{stem}",
        ),
        compile_text(
            text,
            flavour=flavour,
            vocabulary=Vocabulary(_TOK_B),
            cache_key=f"add-b-{stem}",
        ),
    )


def _sample(stem: str, seed: int) -> str:
    """A generated instance of ``stem``'s language (empty ones are skipped)."""
    ast = canonical_grammar(
        (GROUND_TRUTH / stem).read_text(encoding="utf-8"), _flavour(stem)
    )
    rules = {rule.name: rule for rule in ast.rules}
    return generate(ast.start, rules, rng=random.Random(seed))


@pytest.mark.parametrize("stem", CHAR_GRAMMARS)
def test_codegen_grammar_is_unmoved_by_a_bound_tokenizer(stem: str) -> None:
    """The compiled grammar is identical bare, with A, and with B."""
    bare, with_a, with_b = _three_ways(stem)
    assert bare.codegen_grammar == with_a.codegen_grammar
    assert bare.codegen_grammar == with_b.codegen_grammar


@pytest.mark.parametrize("stem", CHAR_GRAMMARS)
def test_classes_and_fold_are_unmoved_by_a_bound_tokenizer(stem: str) -> None:
    """The synthesized classes and the fold table are identical across all three."""
    bare, with_a, with_b = _three_ways(stem)
    assert sorted(bare.classes) == sorted(with_a.classes) == sorted(with_b.classes)
    assert sorted(bare.product.routines) == sorted(with_a.product.routines)
    assert sorted(bare.product.routines) == sorted(with_b.product.routines)
    for name, cls in bare.classes.items():
        assert cls.__binds__ == with_a.classes[name].__binds__
        assert cls.__binds__ == with_b.classes[name].__binds__


@pytest.mark.parametrize("stem", CHAR_GRAMMARS)
def test_parse_is_unmoved_by_a_bound_tokenizer(stem: str) -> None:
    """A generated instance parses to the same model whichever tokenizer is bound.

    The end-to-end half: structural equality above could hold while the parse
    ROUTE differed (a token grammar islands the PDA), so this pins the product.
    """
    bare, with_a, with_b = _three_ways(stem)
    for seed in range(4):
        text = _sample(stem, seed)
        if not text:
            continue  # a nullable start rule generated the empty string
        first = bare.parse(text)
        assert first.dump() == with_a.parse(text).dump(), (stem, seed, text)
        assert first.dump() == with_b.parse(text).dump(), (stem, seed, text)
        assert first.to_text() == text


def test_a_char_grammar_binds_no_segmentation_tokenizer() -> None:
    """Binding a tokenizer to a char grammar leaves it a CHAR parse.

    The tokenizer is bound in the registry (its name is resolvable) but nothing
    segments, because no rule references it — which is what makes additivity
    structural rather than accidental.
    """
    _, with_a, _ = _three_ways("arithmetic.gbnf")
    assert with_a.tokens.tokenizer is not None  # bound ...
    assert not with_a.tokens.segmented  # ... but nothing references it
    text = _sample("arithmetic.gbnf", 1)
    assert with_a.parse(text).to_text() == text  # ... but the parse is char-wise
