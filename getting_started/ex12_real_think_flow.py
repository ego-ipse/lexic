"""The ``<think>`` flow end to end, against a REAL model vocabulary.

ex06 shows token grammars against a hand-built toy vocab. This is the same
machinery against Qwen3's actual ``tokenizer.json`` — 151k tokens, fetched
from the hub — with ``resources/ground_truth/think.gbnf``::

    root     ::= <think> thinking </think> .*
    thinking ::= !</think>*

Three homes, visible in the imports: ``ext.API.hf`` GETS the document,
``lexic.api.json_tokenizer`` READS it, ``lexic`` compiles and parses. The
grammar names an encoding (``tokens``); ``registry=`` binds that NAME to a
vocabulary, which is why a tokenizer called ``qwen3`` can serve a grammar
that says ``tokens``.

Skips cleanly when the fixture is absent — nothing is committed, since hub
files are third-party. To run it::

    uv run python -m ext.API.hf              # fetch (once)
    uv run python -m getting_started.ex12_real_think_flow

Note: reading an 11 MB ``tokenizer.json`` takes ~30 s — lexic parses it with
its own json grammar, so the cost is the document size, not the vocabulary.
"""

from __future__ import annotations

from pathlib import Path

from ext.API import cache
from lexic.api.json_tokenizer import read_from_path
from lexic.compile import Vocabulary, compile_from_path
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrMap, IrStr, IrTuple

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAMMAR_PATH = REPO_ROOT / "resources" / "ground_truth" / "think.gbnf"

TEXT = "<think>The user asked 2+2. It is 4.</think>The answer is 4."


def main() -> None:
    """Read a real vocabulary, then parse and constrain a thinking block."""
    cached = cache.cached("qwen3")
    if cached is None:
        print("qwen3 tokenizer not cached — skipping.")
        print("  fetch it with:  uv run python -m ext.API.hf")
        return

    print("reading tokenizer.json (~30s — lexic parses it with its json grammar)…")
    tok = read_from_path(cached, JSON_GRAMMAR, JSON_REDUCER)
    print(f"  vocabulary      → {len(tok.encode)} tokens, {len(tok.ranks)} merges")
    print(f"  pipeline read   → {tok.pipeline.pretokens}, {tok.pipeline.normalize}")

    # The grammar says `tokens`; this vocabulary is called `qwen3`. The
    # registry binds the GRAMMAR's name, so the two stay decoupled.
    registry = IrMap(IrTuple(IrStr("tokens"), tok))
    compiled = compile_from_path(GRAMMAR_PATH, vocabulary=Vocabulary(registry=registry))

    # Capability B — parse. Every terminal matches id-granular against the
    # tokenizer's own segmentation, and the model round-trips char-exact.
    model = compiled.parse(TEXT)
    ids = tok.tokenize(TEXT)
    print(f"\nparsed {len(ids)} tokens; round-trip exact: {model.to_text() == TEXT}")
    print("  first four      →", [str(tok.spell(i)) for i in ids[:4]])

    # Capability C — constrain. At the empty prefix the grammar admits
    # exactly one token, because `root` must open with <think>.
    mask = compiled.constrain().mask()
    print(f"\nadmissible first tokens: {len(mask)}")
    for tid in sorted(mask):
        print(f"  {tid} → {str(tok.spell(tid))!r}")

    assert model.to_text() == TEXT
    assert len(mask) == 1 and str(tok.spell(sorted(mask)[0])) == "<think>"


if __name__ == "__main__":
    main()
