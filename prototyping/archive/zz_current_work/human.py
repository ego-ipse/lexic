import lexic.parsing_2.chart as chart
import lexic.parsing_2.ops as ops
from lexic.grammars import ABNF_FLAVOUR
from lexic.grammars.abnf_2 import ABNF_GRAMMAR
from lexic.parsing_2 import recognize
from lexic.parsing_2.normalize import normalize

stats = {"iadd": 0, "dup": 0, "predict": 0}
# count Column.__iadd__ total vs duplicates
orig_iadd = chart.Column.__iadd__


def counting_iadd(self, item):
    stats["iadd"] += 1
    if item in self._seen:
        stats["dup"] += 1
    return orig_iadd(self, item)


chart.Column.__iadd__ = counting_iadd

# count Predict.eval calls and redundant (ref already predicted in this column)
predicted = {}  # id(column) -> set of refs
orig_predict = ops.Predict.eval


def counting_predict(self, _d, n, nc, /):
    stats["predict"] += 1
    ctx = nc[0]
    key = id(ctx.column)
    seen = predicted.setdefault(key, set())
    if n in seen:
        stats.setdefault("redundant_predict", 0)
        stats["redundant_predict"] += 1
    seen.add(n)
    return orig_predict(self, _d, n, nc)


ops.Predict.eval = counting_predict

g = normalize(ABNF_GRAMMAR)
t = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR)) * 4  # x4
recognize(g, t)
print("Column.__iadd__ total:", stats["iadd"])
print(
    "  of which duplicates:",
    stats["dup"],
    f"({100 * stats['dup'] / stats['iadd']:.0f}%)",
)
print("Predict.eval calls:", stats["predict"])
print(
    "  redundant (ref already predicted in col):",
    stats.get("redundant_predict", 0),
    f"({100 * stats.get('redundant_predict', 0) / stats['predict']:.0f}%)",
)
