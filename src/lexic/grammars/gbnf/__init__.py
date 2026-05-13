"""gbnf — IrItem-shape mirror of grammars/gbnf/.

Exists during the parallel-track IR cutover. Renamed to grammars/gbnf/
at cutover (Slice 4). Internal imports reference lexic.grammars.gbnf.X
so the slice can land green without touching legacy gbnf/.
"""

from lexic.grammars.gbnf.escapes import GbnfEscapes
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.grammars.gbnf.meta_grammar import META_GRAMMAR

__all__ = ["GbnfEscapes", "GbnfFlavour", "META_GRAMMAR"]
