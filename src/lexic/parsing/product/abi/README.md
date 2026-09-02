# `parsing.product.abi`

The product ABI records: `records.py` (the authored operations and the flat
int-coded tables they lower to), `expressions.py` (the reducer's own algebra
in authored form, its own lowering table), and `construction.py` (the
construction records both name — what a completion builds its value with).
Reached only through `lexic.parsing.product`'s façade; nothing outside the
package imports a module here directly.
