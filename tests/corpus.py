"""Generated documents over the ground-truth corpus — one recipe, two suites.

Both the addressed-emission gates and the watched-run gates need the same
thing: real documents for every shipped grammar, produced through the standard
pipeline rather than hand-written to suit the mechanism under test. Deriving
them twice is how the two suites would drift apart about what "the corpus"
means.
"""

from __future__ import annotations

import random

from lexic.compile import canonical_grammar
from lexic.generate import generate
from lexic.grammars.gbnf import GBNF_FLAVOUR
from tests.paths import GROUND_TRUTH

SEEDS: tuple[int, ...] = (0, 1, 2, 3, 4)
"""The seeds both suites generate at — fixed, so a failure is replayable."""


def documents(name: str, seeds: tuple[int, ...] = SEEDS) -> list[str]:
    """Generated documents for one ground-truth grammar, deterministic per seed.

    :param name: The grammar's file name (e.g. ``"json.gbnf"``).
    :param seeds: The RNG seeds to generate at.
    :returns: The non-empty documents, in seed order.
    """
    ast = canonical_grammar((GROUND_TRUTH / name).read_text(), GBNF_FLAVOUR)
    rules = {rule.name: rule for rule in ast.rules}
    texts = [generate(ast.start, rules, rng=random.Random(seed)) for seed in seeds]
    return [text for text in texts if text]
