"""Token grammars — constrain output to tokenizer tokens, not characters.

Build a tokenizer, compile a GBNF grammar whose terminals are *tokens*
(``<think>`` / ``</think>`` / ``.``), then exercise the three token
capabilities on the real engine:

- **A — read / emit**: the grammar round-trips through ``to_grammar()``.
- **B — parse**: ``parse(text)`` segments the text with the tokenizer and
  matches each terminal id-granular; the model round-trips char-exact.
- **C — constrain**: ``constrain()`` yields the admissible *next-token* mask at
  every prefix — the generation-time viability oracle.

The tokenizer is built from a plain vocab Mapping; how that Mapping was produced
(an HF ``tokenizer.json`` parsed via a grammar, a merges file, …) is the caller's
concern — see ``tests/integration/test_hf_tokenizer.py``.

Run::

    uv run python -m getting_started.ex06_token_grammar
"""

from __future__ import annotations

from lexic import compile_text, parse_grammar
from lexic.compile import Vocabulary
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrChr, IrMap, IrStr, IrTokenizer, IrTuple

# A tiny vocab: two special tokens plus a few word/punctuation tokens. The
# encoding name ("tokens") is the one GBNF's token terminals reference.
# (A longest-match tokenizer matches ``<think>`` whole naturally; a BPE tokenizer
# with atomic special tokens — HF's added_tokens — does too. See
# IrTokenizer.from_merges(..., IrTokenPipeline(specials)) — see ex11.)
VOCAB = {"<think>": 0, "</think>": 1, "hi": 2, " ": 3, "there": 4, "!": 5}

# root: a <think>…</think> block, then any trailing tokens (``.*``).
# thinking: any run of tokens that are not the closing </think> (``!</think>*``).
GRAMMAR = "root ::= <think> thinking </think> .*\nthinking ::= !</think>*"


def _tokenizer() -> IrTokenizer:
    """A longest-match tokenizer over :data:`VOCAB` (named ``tokens``)."""
    encode = IrMap(*(IrTuple(IrStr(t), IrChr(i)) for t, i in VOCAB.items()))
    return IrTokenizer.from_vocab("tokens", encode)


def main() -> None:
    """Compile a token grammar and run all three token capabilities."""
    tokenizer = _tokenizer()
    compiled = compile_text(GRAMMAR, vocabulary=Vocabulary(tokenizer), cache_key="ex06")

    # Capability A — read / emit, no tokenizer: the token terminals round-trip.
    print("Grammar (re-emitted):")
    print(GBNF_FLAVOUR.apply(parse_grammar(GRAMMAR, GBNF_FLAVOUR)))
    print()

    # Capability B — parse an instance token-granular, round-trip char-exact.
    text = "<think>hi there</think>!"
    model = compiled.parse(text)
    print("Segmented ids:", tokenizer.tokenize(text))
    print("Parsed model: ", model)
    print("Fields:       ", model.dump())
    print("Round-trip:   ", repr(model.to_text()))
    assert model.to_text() == text, "round-trip must be lossless"
    print()

    # Capability C — the admissible next-token mask at each prefix.
    cursor = compiled.constrain()
    print("Admissible first tokens:", _spell(tokenizer, cursor.mask()))
    # Only <think> can open the block — the mask enforces it.
    assert cursor.mask() == {VOCAB["<think>"]}, "only <think> may start the block"
    cursor.push(VOCAB["<think>"])
    # Inside `thinking` (!</think>*) any token is admissible, including </think>
    # (which would close the block immediately).
    print("After <think>:          ", _spell(tokenizer, cursor.mask()))

    # The cursor keeps ONE live chart across the generation: each push extends
    # it in place (the prefix is never reparsed), each mask explores candidate
    # continuations on top and rolls them back.
    for token in ("hi", " ", "there", "</think>"):
        cursor.push(VOCAB[token])
    assert cursor.accepts(), "a closed block is a complete parse (trailing .*)"
    print("Sequence accepted:      ", cursor.ids)


def _spell(tokenizer: IrTokenizer, ids: set[int]) -> list[str]:
    """The token texts for a mask of ids, sorted for a stable printout."""
    return sorted(str(tokenizer.spell(i)) for i in ids)


if __name__ == "__main__":
    main()
