"""Drive a generation loop with the next-token mask.

The generation-time pattern behind constrained decoding: at every step ask the
cursor for the admissible next-token ids, let "the model" pick one (here: a
seeded random choice — in production, the LLM's logits masked to the set),
``push`` it, and stop when the grammar accepts. The cursor keeps one live
chart for the whole generation — each push extends it in place, each mask
explores candidate spellings on top and rolls them back, so the per-step cost
does not grow with the generated prefix.

This grammar has NO token terminals, so the cursor runs the char-granular
path: a token is admissible iff its spelling keeps the text a viable prefix —
any tokenizer vocab can drive any char grammar.

Run::

    uv run python getting_started/ex07_constrained_generation.py
"""

from __future__ import annotations

import random

from lexic import compile_text
from lexic.ir.base import IrStr, IrTuple
from lexic.ir.encoding import IrTokenizer
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import IrChr

# A tiny arithmetic sum: 1-3 digit numbers joined by "+", closed by "=".
GRAMMAR = """\
sum    ::= number ("+" number)* "="
number ::= [0-9] [0-9]? [0-9]?
"""

# A BPE-ish vocab: single chars plus a few multi-char tokens ("12", "+3").
VOCAB = {str(d): d for d in range(10)} | {"+": 10, "=": 11, "12": 12, "+3": 13}


def main() -> None:
    """Generate a random valid sum, one masked token at a time."""
    encode = IrMap(*(IrTuple(IrStr(t), IrChr(i)) for t, i in VOCAB.items()))
    tokenizer = IrTokenizer.from_vocab("tokens", encode)
    cursor = compile_text(GRAMMAR, cache_key="ex07").constrain(tokenizer)
    # The tokenizer already inverts id → spelling; no side table needed.
    spell = tokenizer.spell

    rng = random.Random(7)
    steps: list[str] = []
    while not (cursor.accepts() and rng.random() < 0.5):
        admissible = cursor.mask()
        if not admissible:  # only end-of-input remains
            break
        choice = rng.choice(sorted(admissible))
        cursor.push(choice)
        steps.append(str(spell(choice)))
        print(
            f"step {len(steps):>2}: picked {str(spell(choice))!r:5} "
            f"from {sorted(str(spell(i)) for i in admissible)}"
        )

    generated = "".join(steps)
    print("\nGenerated:", generated)
    assert cursor.accepts(), "the loop only stops on a complete parse"
    # The generated text really is in the grammar's language.
    compiled = compile_text(GRAMMAR, cache_key="ex07")
    assert compiled.parse(generated).to_text() == generated


if __name__ == "__main__":
    main()
