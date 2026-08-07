"""PROTOTYPE: index-with-bounds instead of one-char slicing, on the hot gates.

`text[pos:pos+1]` allocates a string per lookahead and then tests `== ""` for
EOF. `pos < len(text) and text[pos]` does the same work with no allocation.
Patches the two sites that are cheapest to reach from outside — `gate_take`'s
stop/attempt branches — and measures in situ rather than trusting the
microbenchmark, which over-predicted twice this mission.
"""
import time

import lexic.parsing.pda.compiler.flatten as F
from lexic.parsing import PdaKernel
from tools.benchmark.grammars import BENCHES

_orig = F.gate_take
GATE_STOP, GATE_ATTEMPT = F.GATE_STOP, F.GATE_ATTEMPT
ProbeFork = F.ProbeFork


def gate_take(text, pos, gk, gate):
    """`gate_take` with the two hottest branches free of the slice."""
    if gk == GATE_STOP:
        chars, negated = gate
        if pos >= len(text):
            return False
        ch = text[pos]
        return (ch not in chars) if negated else (ch in chars)
    if gk == GATE_ATTEMPT:
        if pos >= len(text):
            return False
        ch = text[pos]
        chars, negated = gate[0]
        take = (ch not in chars) if negated else (ch in chars)
        if take:
            fchars, fnegated = gate[1]
            if (ch not in fchars) if fnegated else (ch in fchars):
                raise ProbeFork(
                    f"attempt loop at {pos}: taking and stopping are both viable", pos
                )
        return take
    return _orig(text, pos, gk, gate)


def bench(label):
    for name in ("csv", "arithmetic", "json", "vyx"):
        b = next(x for x in BENCHES if x.name == name)
        cg = b.compiled
        cg.pda_tables()
        run = lambda: PdaKernel(cg.pda_tables(), b.corpus, cg.fold).run()
        run()
        t = min(
            (lambda t0: (run(), time.perf_counter() - t0)[1])(time.perf_counter())
            for _ in range(11)
        )
        ok = cg.parse(b.corpus).to_text() == b.corpus
        print(f"  {label:9} {name:11} {t * 1e6 / len(b.corpus):6.3f} µs/char  rt={ok}")


bench("baseline")
F.gate_take = gate_take
import lexic.parsing.pda.runtime.matchers as M
import lexic.parsing.pda.runtime.kernel.kernel as KM
M.gate_take = gate_take
KM.gate_take = gate_take
bench("no-slice")
