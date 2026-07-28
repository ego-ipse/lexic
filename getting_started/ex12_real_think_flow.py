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

    uv run python -m ext.API.hf                              # fetch (once)
    uv run python -m getting_started.ex12_real_think_flow
    uv run python -m getting_started.ex12_real_think_flow --reset   # rebuild it

**The vocabulary is compiled once and imported thereafter.** Reading an 11 MB
``tokenizer.json`` takes ~30 s — lexic parses it with its own json grammar, so
the cost is the document size, not the vocabulary. A tokenizer is an IR value
like any other, so the second run pays an ``import`` instead: ``export_value``
projects it to three flat tables under a digest and byte-compiles the result,
and importing that rebuilds the same ``IrTokenizer``. ``--reset`` deletes the
compiled form so the next run reads the json again.

That is the payload projection (ex13) on a workload where it earns its keep.
"""

from __future__ import annotations

import importlib
import shutil
import sys
import time
from pathlib import Path

from ext.API import cache
from lexic.api.json_tokenizer import read_from_path
from lexic.compile import Vocabulary, compile_from_path
from lexic.compile.payload import export_value
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrMap, IrStr, IrTokenizer, IrTuple

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAMMAR_PATH = REPO_ROOT / "resources" / "ground_truth" / "think.gbnf"

COMPILED_DIR = REPO_ROOT / "generated" / "ex12_tokenizer"
COMPILED_MODULE = "qwen3_vocab"
"""Where the compiled vocabulary lands. Real files, kept — open
`qwen3_vocab.py` and the 151k-token vocabulary is three flat literals."""

TEXT = "<think>The user asked 2+2. It is 4.</think>The answer is 4."


def _load_compiled() -> IrTokenizer | None:
    """The vocabulary from its compiled form, or ``None`` if not built yet.

    :returns: The rebuilt tokenizer, or ``None`` when there is nothing to load.
    """
    if not (COMPILED_DIR / f"{COMPILED_MODULE}.py").exists():
        return None
    sys.path.insert(0, str(COMPILED_DIR))
    try:
        module = importlib.import_module(COMPILED_MODULE)
    finally:
        sys.path.remove(str(COMPILED_DIR))
    value = module.VALUE
    return value if isinstance(value, IrTokenizer) else None


def _read_and_compile(source: Path) -> IrTokenizer:
    """Read the hub's json, then write the vocabulary as an importable module.

    :param source: The fetched ``tokenizer.json``.
    :returns: The tokenizer, freshly read.
    """
    print("reading tokenizer.json (~30s — lexic parses it with its json grammar)…")
    started = time.perf_counter()
    tok = read_from_path(source, JSON_GRAMMAR, JSON_REDUCER)
    print(f"  read            → {time.perf_counter() - started:.1f}s")

    COMPILED_DIR.mkdir(parents=True, exist_ok=True)
    written = export_value(tok, COMPILED_DIR / f"{COMPILED_MODULE}.py")
    print(
        f"  compiled to     → {written.relative_to(REPO_ROOT)} "
        f"({written.stat().st_size // 1024:,} KiB)"
    )
    return tok


def main(argv: list[str] | None = None) -> None:
    """Read a real vocabulary, then parse and constrain a thinking block."""
    if "--reset" in (argv if argv is not None else sys.argv[1:]):
        shutil.rmtree(COMPILED_DIR, ignore_errors=True)
        print(f"reset: removed {COMPILED_DIR.relative_to(REPO_ROOT)}")

    cached = cache.cached("qwen3")
    if cached is None:
        print("qwen3 tokenizer not cached — skipping.")
        print("  fetch it with:  uv run python -m ext.API.hf")
        return

    started = time.perf_counter()
    tok = _load_compiled()
    if tok is None:
        tok = _read_and_compile(cached)
    else:
        print(
            f"loaded the compiled vocabulary in "
            f"{time.perf_counter() - started:.2f}s — no json parsed"
        )
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
