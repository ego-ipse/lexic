"""new_gbnf — IrItem-shape mirror of grammars/gbnf/.

Exists during the parallel-track IR cutover. Renamed to grammars/gbnf/
at cutover (Slice 4). Internal imports reference lexic.grammars.new_gbnf.X
so the slice can land green without touching legacy gbnf/.
"""

from lexic.grammars.new_gbnf.escapes import GbnfEscapes
from lexic.grammars.new_gbnf.flavour import GbnfFlavour
from lexic.grammars.new_gbnf.meta_grammar import META_GRAMMAR

__all__ = ["GbnfEscapes", "GbnfFlavour", "META_GRAMMAR"]
