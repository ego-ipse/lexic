"""PROTOTYPE: FIRST_k admission at the attempt seam. Out-of-tree, no src edits.

Attaches a FIRST_k window set to each flat attempt entry (computed at compile
time from the IrAst, mapped by attempt order — verified 1:1) and filters
candidates before any speculative sub-run.
"""
import time
from collections import Counter

import lexic.parsing.pda.runtime.kernel.kernel as KM
from lexic.parsing import PdaKernel
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.gates.kwindow import KWindowFirst
from lexic.parsing.pda.compiler.flatten import _window_admits
from lexic.parsing.pda.runtime.admission import admits, prefix_admits
from tools.benchmark.grammars import BENCHES

K = 4
WIN: dict[int, tuple] = {}          # id(sub clone) -> window tuple
STAT = Counter()
_orig_sole = KM.sole_admitted


def to_windows(prefs):
    """A prefix set as the `(chars, negated)`-tuple windows _window_admits wants."""
    out = []
    for pref in prefs:
        win = pref[0] if isinstance(pref, tuple) and len(pref) == 2 else pref
        try:
            out.append(tuple((frozenset(cs.chars), cs.negated) for cs in win))
        except (AttributeError, TypeError):
            return ()                      # UNK / unrecognised shape — no filter
    return tuple(w for w in out if w)


def build(cg):
    """Attach windows to every attempt entry of the compiled grammar."""
    tables = cg.pda_tables()
    inst = tables.instance_grammar
    rules = {str(r.name): r for r in inst.rules}
    an = GrammarAnalysis(inst)
    solver = KWindowFirst(rules, K)
    seen, work = set(), [tables.program.start]
    while work:
        c = work.pop()
        if not hasattr(c, "attempt") or id(c) in seen:
            continue
        seen.add(id(c))
        for _x, _y, a in c.selectors:
            if hasattr(a, "kinds"):
                work += [p for k, p in zip(a.kinds, a.payloads) if hasattr(p, "attempt")]
            elif hasattr(a, "attempt"):
                work.append(a)
        if c.attempt is None:
            continue
        spec = an.taxonomy.attempts.get(c.name)
        rule = rules.get(c.name)
        if spec is None or rule is None or len(spec.order) != len(c.attempt[1]):
            STAT["clone skipped (shape mismatch)"] += 1
            continue
        for entry, idx in zip(c.attempt[1], spec.order):
            arm = rule.body[idx]
            items = list(arm) if hasattr(arm, "__iter__") else [arm]
            try:
                w = to_windows(solver.arm_prefixes(items, K))
            except Exception:
                w = ()
            if w:
                WIN[id(entry[-1])] = w
                STAT["entries windowed"] += 1
            else:
                STAT["entries with no usable window"] += 1
            work.append(entry[-1])


def filtered_sole(entries, text, pos):
    """`sole_admitted` plus the FIRST_k exclusion."""
    sole, n = None, 0
    for chars, negated, prefix, sub in entries:
        char = text[pos : pos + 1]
        if not admits(char, chars, negated):
            continue
        if prefix is not None and not prefix_admits(text, pos, prefix):
            continue
        win = WIN.get(id(sub))
        if win is not None and not _window_admits(text, pos, win):
            STAT["EXCLUDED by window"] += 1
            continue
        n += 1
        if n > 1:
            return None
        sole = sub
    return sole


def measure(label, cg, corpus):
    runs = Counter()
    import lexic.parsing.pda.runtime.kernel.decisions as D
    orig = D.Attempting._attempt_run
    def counting(self, sub, p):
        runs["n"] += 1
        return orig(self, sub, p)
    D.Attempting._attempt_run = counting
    try:
        PdaKernel(cg.pda_tables(), corpus, cg.fold).run()
    finally:
        D.Attempting._attempt_run = orig
    run = lambda: PdaKernel(cg.pda_tables(), corpus, cg.fold).run()
    run()
    t = min((lambda t0: (run(), time.perf_counter() - t0)[1])(time.perf_counter())
            for _ in range(9))
    print(f"  {label:16} {t*1e6/len(corpus):6.3f} µs/char   sub-runs {runs['n']}")
    return t


b = next(x for x in BENCHES if x.name == "vyx")
cg = b.compiled
cg.pda_tables()
base = measure("baseline", cg, b.corpus)
build(cg)
KM.sole_admitted = filtered_sole
opt = measure(f"FIRST_{K} filter", cg, b.corpus)
KM.sole_admitted = _orig_sole
model = cg.parse(b.corpus)
print(f"  {dict(STAT)}")
print(f"  => {(1-opt/base)*100:+.1f}%   round-trip {model.to_text() == b.corpus}")
