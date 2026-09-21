# PDA runtime program

Flat program records and opcodes, the lowering pass that builds them, the
`bake/` subpackage holding the two halves that compose a clone's build state —
the per-shape build tail and the product-side fill from its rule product — and
the specialization passes applied before the runtime consumes the result.
