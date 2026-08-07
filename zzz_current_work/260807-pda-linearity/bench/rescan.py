"""PROTOTYPE: C-level char-class scanning in place of the per-character loop.

Replaces `match_cc`'s Python `while` with a per-CharSet precompiled `re`,
built once and memoised on the (chars, negated) pair. Keeps the loop for the
length-1 case the kill-test showed regex loses.
"""
import re
import time

import lexic.parsing.pda.runtime.matchers as M
from lexic.parsing import PdaKernel
from tools.benchmark.grammars import BENCHES

_PAT: dict[tuple, object] = {}


def pattern(chars, negated):
    """A compiled `re` for one membership set, built once per set."""
    key = (chars, negated)
    got = _PAT.get(key)
    if got is None:
        body = "".join(re.escape(c) for c in sorted(chars))
        got = re.compile(f"[{'^' if negated else ''}{body}]*")
        _PAT[key] = got
    return got


_orig = M.match_cc


def match_cc(text, arm, i, pos):
    """`match_cc` with the run consumed by a C-level scan."""
    chars, negated = arm.payloads[i]
    lo, hi = arm.los[i], arm.his[i]
    end = pattern(chars, negated).match(text, pos).end()
    if hi >= 0:
        end = min(end, pos + hi)
    if end - pos < lo:
        return _orig(text, arm, i, pos)      # let the original raise its PdaFail
    return end


def bench(label):
    for name in ("csv", "arithmetic", "json", "vyx"):
        b = next(x for x in BENCHES if x.name == name)
        cg = b.compiled
        cg.pda_tables()
        run = lambda: PdaKernel(cg.pda_tables(), b.corpus, cg.fold).run()
        run()
        t = min(
            (lambda t0: (run(), time.perf_counter() - t0)[1])(time.perf_counter())
            for _ in range(9)
        )
        ok = cg.parse(b.corpus).to_text() == b.corpus
        print(f"  {label:9} {name:11} {t * 1e6 / len(b.corpus):6.3f} µs/char  rt={ok}")


bench("baseline")
M.match_cc = match_cc
import lexic.parsing.pda.runtime.kernel.kernel as KM
KM.match_cc = match_cc
bench("re-scan")
