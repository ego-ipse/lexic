"""Where does the COMMON path spend its time? — the optimization investigation.

Not the boundary-dense synthetic body this effort has been fixing (that is now
linear and cheap) but the workload `bench --only vyx` measures: a real 3.5 KB
vyx packet, the traffic an agent protocol actually parses, at 5.658 us/char
against antlr's 0.302 and parsimonious's 2.761.

Prior art, so it is not re-derived: micro-levers measured ~0% here before, and
a 30-50% win was judged to need a STRUCTURAL cut in how many models a parse
builds, not faster versions of the same work. This probe therefore reports two
things side by side — where the time is, and how many models are built per
character — so a candidate lever can be checked against both.

    uv run python .../probes/hotpath.py [profile|models|both]
"""

import cProfile
import io
import pstats
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import common  # noqa: F401  (path bootstrap)

from tools.benchmark.grammars import BENCHES


def corpus() -> tuple[str, object]:
    """The benchmark's own vyx input and compiled artefact — the real workload."""
    bench = next(b for b in BENCHES if b.name == "vyx")
    return bench.corpus, bench.compiled


def profile(text: str, compiled: object, rounds: int = 20) -> None:
    """Top of the parse by self time, over enough rounds to be stable."""
    compiled.parse(text)
    prof = cProfile.Profile()
    prof.enable()
    for _ in range(rounds):
        compiled.parse(text)
    prof.disable()
    buf = io.StringIO()
    pstats.Stats(prof, stream=buf).sort_stats("tottime").print_stats(14)
    print(f"### profile — {len(text)} chars x {rounds} rounds")
    for line in buf.getvalue().split("\n"):
        if "lexic" in line or "ncalls" in line or "function calls" in line:
            print(line[:132])


def models(text: str, compiled: object) -> None:
    """How many model objects one parse builds, and of what.

    The lever prior art points at: fewer models, not faster model-building.
    """
    from lexic.model import GrammarModel

    seen: Counter = Counter()
    total = 0
    stack = [compiled.parse(text)]
    while stack:
        node = stack.pop()
        if isinstance(node, GrammarModel):
            seen[type(node).__name__] += 1
            total += 1
            stack.extend(node)
        elif isinstance(node, tuple):
            stack.extend(node)
    print(f"\n### models — {total} for {len(text)} chars "
          f"({total / len(text):.3f} per char)")
    for name, count in seen.most_common(12):
        print(f"  {count:6}  {name}")


def main() -> None:
    """Run the requested half (default both)."""
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    text, compiled = corpus()
    if mode in ("profile", "both"):
        profile(text, compiled)
    if mode in ("models", "both"):
        models(text, compiled)


main()
