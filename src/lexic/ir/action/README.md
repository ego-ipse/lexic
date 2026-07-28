# `lexic.ir.action` — The action algebra — bodies that run over the spine.

Four groups by what a node is FOR: `access` reaches into a node, `compute`
turns values into values, `control` decides what runs and in what order, and
`build` produces a node. `walk` is the dispatcher they run under and `mapping`
is the table family it dispatches on — they live here because they are the
machinery, not a separate subject.

The groups are almost independent: the only cross-reference in the code is
`IrReturn` needing `IrThis`, and they sit together in `control`.

## Modules

- `access.py`
- `build.py`
- `compute.py`
- `control.py`
- `mapping.py`
- `walk.py`

Import from `lexic.ir`, not from these paths: the package façade is the
public surface, and it is lazy, so naming a symbol there costs only the
module that defines it.
