# `lexic.ir.spine` — The spine — what every IR node is made of.

`spine` holds the abstract tiers (`IrSelf`, `IrNode`, `IrLeaf`), absence
(`IrNone`) and the one callable-carrying node (`IrLambda`). `scalars` and
`records` are the two concrete shapes a node takes: a value leaf IS its payload,
a record IS its field tuple. `meta` is the metaclass that derives `_bound` and
injects `__slots__`; `bind` is the marker a generated model's field carries.
`identity` reads the tiers back: the census of a value's graph — unique nodes,
share counts, the refusal boundary — under the field-tuple child definition
this folder defines.

Everything else in `lexic.ir` is downstream of this folder. Nothing here imports
anything above it.

## Modules

- `bind.py`
- `identity.py`
- `meta.py`
- `records.py`
- `scalars.py`
- `spine.py`

Import from `lexic.ir`, not from these paths: the package façade is the
public surface, and it is lazy, so naming a symbol there costs only the
module that defines it.
