"""The compile half of the product ABI — where authored declarations are bound.

`parsing/product/` owns what a program IS, how one is lowered, and what runs
it; this package owns what BINDS one to a source artefact and keeps it alive.
The split follows the layering the whole repo rests on: the engine is a leaf
that reads compiled data, and everything that knows about grammars, reducers,
signatures and targets sits on this side of the seam.

Lowering itself sits on the engine side, because it reads and writes only the
ABI records and knows nothing of grammars or reducers — and because binding is
where an authored product becomes executable, which would otherwise put a
compile import inside the engine.

Today this package owns bound-product lifetime and the generated-model
binding. Signature verification, lower × upper state composition, demand
propagation and the morphism surfaces join it as their phases land; each
arrives as its own module rather than by growing this one.
"""

from __future__ import annotations

from lexic.compile.product.registry import (
    ProductRegistry,
    ProgramProduct,
    RegisteredProduct,
    register_model,
    rules_by_name,
)

__all__ = [
    "ProductRegistry",
    "RegisteredProduct",
    "ProgramProduct",
    "register_model",
    "rules_by_name",
]
