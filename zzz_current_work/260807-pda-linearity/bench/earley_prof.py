"""Why is lexic-earley 63.8 us/char on arithmetic — 1.45x lark-earley's 43.9?

Target 1: the worst number lexic posts anywhere, and the one with a
same-algorithm peer beating it, so the gap is not intrinsic to Earley.

    PYTHONPATH=. uv run python .../bench/earley_prof.py
"""

import cProfile
import io
import pstats

from lexic.parsing import earley_model, lift_optional_nullables, normalize
from tools.benchmark.grammars import BENCHES

bench = next(b for b in BENCHES if b.name == "arithmetic")
text, cg = bench.corpus, bench.compiled
instance = normalize(lift_optional_nullables(cg.codegen_grammar))

earley_model(instance, text, cg.fold)  # warm
prof = cProfile.Profile()
prof.enable()
for _ in range(3):
    earley_model(instance, text, cg.fold)
prof.disable()
buf = io.StringIO()
pstats.Stats(prof, stream=buf).sort_stats("tottime").print_stats(12)
print(f"### lexic-earley, arithmetic, {len(text)} chars x 3")
for line in buf.getvalue().split("\n"):
    if "lexic" in line or "ncalls" in line or "function calls" in line:
        print(line[:128])
