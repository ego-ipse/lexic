"""Is ``_STOP_FORCED`` reachable? — PLAN item 1's second question.

It occurs ZERO times in 3,829 suite verdicts, and its only known subject
(gbnf-meta's terminator theft) stopped forking when `relax_non_semantic` was
narrowed. If it is genuinely unreachable the stop-probe goes and the lockstep
work halves. "Never observed in one suite" is not "cannot happen" — but ONE
counterexample settles it the cheap way, so this hunts for one before anyone
argues.

The shape being hunted: a loop that CAN take another iteration, where taking
kills the rest of the parse and stopping completes — the loop stealing a
character a later mandatory item needs.

    uv run python .../probes/stopforced.py
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import common  # noqa: F401  (path bootstrap)
import lexic.parsing.pda.runtime.kernel.decisions as decisions
from lexic.compile import compile_text
from lexic.parsing import PdaKernel

VERDICT = {
    decisions._TAKE: "TAKE",
    decisions._STOP_FORCED: "STOP_FORCED",
    decisions._FORKED: "FORKED",
}
SEEN: Counter = Counter()
_ORIGINAL = decisions.Attempting._fork_verdict


def _recording(self, arm, i, pos, taken):  # noqa: ANN001, ANN201
    """``_fork_verdict``, tallying its verdict."""
    got = _ORIGINAL(self, arm, i, pos, taken)
    SEEN[VERDICT.get(got, got)] += 1
    return got


decisions.Attempting._fork_verdict = _recording

# Each case: a loop whose greedy take would eat what a later mandatory item
# needs. If the stop side completes where the take side dies, the verdict is
# STOP_FORCED — that is the shape the stop-probe exists for.
CASES = (
    ('root ::= a+ tail\na ::= "x"\ntail ::= "xy"\n', "xxxy"),
    ('root ::= a+ "xy"\na ::= "x"\n', "xxxy"),
    ('root ::= item+ end\nitem ::= [a-z]\nend ::= "zz"\n', "abczz"),
    ('root ::= w+ tail\nw ::= [ab]\ntail ::= "ab" "c"\n', "ababc"),
    ('root ::= d+ tail\nd ::= [0-9]\ntail ::= "12" "x"\n', "34512x"),
    ('root ::= p+ q\np ::= "ab"\nq ::= "abab"\n', "ababab"),
)


def main() -> None:
    """Run every candidate; report the verdicts each produced."""
    print("── hunting a STOP_FORCED counterexample ──")
    for grammar, text in CASES:
        SEEN.clear()
        head = grammar.split("\n")[0]
        try:
            compiled = compile_text(grammar)
            PdaKernel(compiled.pda_tables(), text, compiled.fold).run()
            outcome = "parsed"
        except Exception as refusal:
            outcome = type(refusal).__name__
        verdicts = dict(SEEN) or "no fork verdict reached"
        print(f"  {head:34} {text!r:10} {outcome:14} {verdicts}")


main()
