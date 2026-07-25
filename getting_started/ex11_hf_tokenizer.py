"""Read a ``tokenizer.json`` document into a live ``IrTokenizer``.

Three responsibilities, three homes — the reason this is three lines rather
than a format walker:

- **getting** the file is ``ext/API/hf.py``'s (the hub hosts documents in
  this format; fetching is not the format's business, and it ships outside
  the package);
- **reading** one is ``lexic.api.json_tokenizer``'s, used here;
- **the model** is ``lexic.ir``'s — ``IrTokenizer`` knows nothing about any
  file format.

Note what the reader is *given*: the json formulation, as a parameter. It has
no built-in idea of how json is spelled — pass a different grammar+reducer
pair (one compiled from a ground-truth ``.gbnf``, say) and the same code
reads the same document.

Everything about the tokenizer is **derived from the document's own
sections** — ``model.vocab``/``merges``/``byte_fallback``, ``added_tokens``,
``normalizer``, ``pre_tokenizer``. Nothing is hand-supplied, which is why the
integration suite reproduces both real SmolLM2 and gemma segmentation
reference-exactly (``tests/integration/test_real_tokenizer*.py``).

Run::

    uv run python -m getting_started.ex11_hf_tokenizer
"""

from __future__ import annotations

from lexic.api.json_tokenizer import read
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER

TOKENIZER_JSON = """\
{
  "version": "1.0",
  "added_tokens": [{"id": 7, "content": "<|end|>", "special": true}],
  "pre_tokenizer": {"type": "Digits", "individual_digits": true},
  "model": {
    "type": "BPE",
    "vocab": {"h": 0, "e": 1, "l": 2, "o": 3, "he": 4, "ll": 5, "hell": 6, "<|end|>": 7},
    "merges": ["h e", "l l", "he ll"]
  }
}
"""


def main() -> None:
    """Build the tokenizer the document describes, then use it."""
    tok = read(TOKENIZER_JSON, JSON_GRAMMAR, JSON_REDUCER, name="demo")

    print("pre-tokens read from the document →", tok.pipeline.pretokens)
    print("specials read from added_tokens   →", tok.pipeline.specials)

    ids = tok.tokenize("hello<|end|>")
    print("tokenize('hello<|end|>')          →", ids)
    spelled = "".join(str(tok.spell(i)) for i in ids)
    print("spelled back                      →", spelled)

    assert ids == [6, 3, 7]  # h+e, l+l, he+ll → hell; then o; then the special
    assert spelled == "hello<|end|>"


if __name__ == "__main__":
    main()
