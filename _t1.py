import cProfile
import io
import pstats

from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.abnf_2 import ABNF_GRAMMAR, ABNF_REDUCER
from lexic.parsing_2.engine import parse
from lexic.parsing_2.normalize import (
    desugar_quantifiers,
    flatten_groups,
    split_literals,
)


def _normalize(g):
    return split_literals(desugar_quantifiers(flatten_groups(g)))


g = _normalize(ABNF_GRAMMAR)
text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))

pr = cProfile.Profile()
pr.enable()
tree = parse(g, text)
ABNF_REDUCER.apply(tree)
pr.disable()
s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
ps.print_stats(25)
print(s.getvalue())
