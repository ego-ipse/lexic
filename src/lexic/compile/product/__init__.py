"""The compile half of the product ABI — where authored declarations become
an executable program.

`parsing/product/` owns what a program IS and what runs it; this package owns
how one is BUILT. The split follows the layering the whole repo rests on: the
engine is a leaf that reads compiled data, and everything that knows about
grammars, reducers, signatures and targets sits on this side of the seam.

Today this package owns product-operation lowering and bound-product
lifetime. Signature verification, lower × upper state composition, demand
propagation and the morphism surfaces join it as their phases land; each
arrives as its own module rather than by growing this one.
"""

from __future__ import annotations

from lexic.compile.product.binding import (
    BindingRegistry,
    BoundProduct,
    ProgramProduct,
    bind_model,
    rules_by_name,
)
from lexic.compile.product.lower import LoweringOwned, lower_product, lower_routes

__all__ = [
    "BindingRegistry",
    "BoundProduct",
    "LoweringOwned",
    "ProgramProduct",
    "bind_model",
    "rules_by_name",
    "lower_product",
    "lower_routes",
]
