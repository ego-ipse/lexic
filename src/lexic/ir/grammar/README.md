# `lexic.ir.grammar` — The grammar AST, and the passes over it.

`nodes` is the AST a grammar parses to (`IrAst`, `IrRule`, `IrItem`,
`IrCharClass`, `IrAlphabet`) and `operators` the family between the spine and
it. The other three are language-preserving transforms: `canonical` normalises,
`order` sorts rules start-first, and `concretize` resolves an alphabet's
spelling to an id once a vocabulary is bound.

## Modules

- `canonical.py`
- `concretize.py`
- `nodes.py`
- `operators.py`
- `order.py`

Import from `lexic.ir`, not from these paths: the package façade is the
public surface, and it is lazy, so naming a symbol there costs only the
module that defines it.
