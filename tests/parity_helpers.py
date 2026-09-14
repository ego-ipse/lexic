"""Ask both engines the same question — the shared parity-test vocabulary.

Every gate and licence test asks the same thing: does the predictive path give
the answer the gated engine gives, on a document chosen to sit on the boundary
the mechanism reads? That question has one correct shape, and it is fiddly in a
way worth writing once:

- a `PdaFail` is a **decline**, not an answer. The composed entry falls through
  to the gated engine, so a decline beside a gated refusal is *both refusing* —
  reading it as a divergence manufactures one per boundary document.
- a refusal must be told apart from a model, so both are rendered to strings and
  the caller compares those.

One copy, because two drift: a change to how an engine is entered should break
one place rather than leave a stale second answer behind.
"""

from __future__ import annotations

from lexic.compile import CompiledGrammar, compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.products import (
    _ModelProduct,
    _model_product,
    earley_model,
    pda_model,
)

DECLINED = "declined"
"""What the predictive path said when it refused to answer at all."""

REFUSED = "refused"
"""What an engine said when the document is not in the language."""


def built(source: str, key: str) -> tuple[CompiledGrammar, _ModelProduct]:
    """Compile ``source`` and pair it with the model product to parse with."""
    compiled = compile_text(source, cache_key=key)
    return compiled, _model_product(compiled.codegen_grammar, compiled.product)


def answers(source: str, key: str, text: str) -> tuple[str, str]:
    """``(predictive, gated)`` for one document, each rendered as a string.

    :param source: The grammar text.
    :param key: The compile cache key.
    :param text: The document both engines are asked about.
    :returns: The predictive answer — a model's ``repr``, :data:`DECLINED` or
        :data:`REFUSED` — beside the gated engine's.
    """
    compiled, product = built(source, key)
    try:
        predictive = repr(pda_model(product.pda, text, compiled.product.executor))
    except PdaFail:
        predictive = DECLINED
    except UnsupportedConstructError:
        predictive = REFUSED
    try:
        gated = repr(
            earley_model(
                product.instance_grammar, text, compiled.product, product.tables
            )
        )
    except UnsupportedConstructError:
        gated = REFUSED
    return predictive, gated
