"""Load an HF-style ``tokenizer.json`` with lexic's own machinery.

The format lives entirely in the caller: lexic ships json (grammar + reducer)
and ``IrTokenizer`` — "HF tokenizer.json" is just an application. The document
reduces to typed IR values (``parse_reduced`` + the json kit), the vocab and
merges read straight off the ``IrMap``, and ``IrTokenizer.from_merges`` builds
the exact ranked-merge BPE. No stdlib ``json``, no format module in src.

The inline document below is a miniature of the real schema; the integration
suite runs the identical flow against the real SmolLM2 and gemma files
(``tools/fetch_tokenizers.py``, ``tests/integration/test_real_tokenizer*.py``)
where ``tokenize()`` is pinned reference-exact against the ``tokenizers``
library.

Run::

    uv run python getting_started/ex11_hf_tokenizer.py
"""

from __future__ import annotations

from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir.base import IrTuple
from lexic.ir.encoding import IrTokenizer, IrTokenPipeline
from lexic.ir.mapping import IrMap
from lexic.parsing import parse_reduced

TOKENIZER_JSON = """\
{
  "version": "1.0",
  "added_tokens": [{"id": 6, "content": "<|end|>", "special": true}],
  "model": {
    "type": "BPE",
    "vocab": {"h": 0, "e": 1, "l": 2, "o": 3, "he": 4, "ll": 5, "hell": 6, "<|end|>": 7},
    "merges": ["h e", "l l", "he ll"]
  }
}
"""


def main() -> None:
    """Reduce the document, lift vocab + merges, build and use the tokenizer."""
    doc = parse_reduced(JSON_GRAMMAR, TOKENIZER_JSON, JSON_REDUCER)
    assert isinstance(doc, IrMap)
    assert doc.at("model", "type") == "BPE", "only BPE models here"

    # The caller owns the format: vocab is already a map, merges normalise
    # from HF's "left right" strings to (left, right) dyads — five lines.
    # ``at(..., into=T)`` walks the nested values with typed, path-carrying
    # reads; the pipeline lifts a plain specials list itself.
    vocab = {
        str(k): int(v) for k, v in doc.at("model", "vocab", into=IrMap).items()
    }
    merges = [
        tuple(str(m).split(" ", 1)) for m in doc.at("model", "merges", into=IrTuple)
    ]
    specials = [
        str(entry.at("content"))
        for entry in doc.at("added_tokens", into=IrTuple)
        if isinstance(entry, IrMap)
    ]

    tok = IrTokenizer.from_merges("hf", vocab, merges, IrTokenPipeline(specials))
    ids = tok.tokenize("hello<|end|>")
    print("tokenize('hello<|end|>') →", ids)
    print("spelled back           →", "".join(str(tok.spell(i)) for i in ids))
    assert ids == [6, 3, 7]  # h+e, l+l, he+ll → hell; then o; then the special
    assert "".join(str(tok.spell(i)) for i in ids) == "hello<|end|>"


if __name__ == "__main__":
    main()
