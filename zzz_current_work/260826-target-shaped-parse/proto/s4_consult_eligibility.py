"""How many value-string clones does the consult actually reach, per grammar?

The census measured eligibility against the WIDEST possible continuation,
which is the generous reading and an upper bound. The consult that ships must
be proved against each clone's OWN hard continuation, because a recognizer
allowed to run past its terminator answers a different question than the
per-character program it replaces.

This reports the real number: per grammar, how many contextual clones are
match-only, how many of those carry a proof against their own tail, and which
rules they are. It is the population every gate row below is measured over,
and it is deliberately reported BEFORE any timing, so a row can never be
argued into existence by the number it produces.

Run: `uv run python zzz_current_work/260826-target-shaped-parse/proto/s4_consult_eligibility.py`
"""

from __future__ import annotations

from pathlib import Path

from lexic.compile import compile_from_path
from lexic.exceptions import LexicError
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.clones import PdaCompiler

GROUND_TRUTH = Path(__file__).resolve().parents[3] / "resources" / "ground_truth"
"""The corpus every number below is measured over."""


class Defect(AssertionError):
    """A claim this witness makes that the corpus does not support."""


def _grammars() -> list[Path]:
    """Every ground-truth fixture, in a stable order."""
    found = sorted(
        path
        for suffix in ("*.gbnf", "*.abnf", "*.ebnf")
        for path in GROUND_TRUTH.glob(suffix)
    )
    if len(found) < 8:
        raise Defect(f"s4 consult: only {len(found)} fixtures — not the corpus")
    return found


def _specs(path: Path) -> tuple[int, int, list[str]] | None:
    """One grammar's ``(match_only, with a consult, their rule names)``."""
    compiled = compile_from_path(path)
    binding = compiled.product
    lifted = lift_optional_nullables(compiled.codegen_grammar)
    try:
        compiler = PdaCompiler(GrammarAnalysis(lifted), binding.routines)
        compiler.compile_start()
    except LexicError:
        return None  # a token-terminal grammar compiles no predictive program
    match_only = [spec for spec in compiler.clones.values() if spec.match_only]
    with_consult = [spec for spec in match_only if spec.consult is not None]
    return (
        len(match_only),
        len(with_consult),
        sorted({spec.name for spec in with_consult}),
    )


def main() -> None:
    """Report the consult's real population, per grammar and in total."""
    print(f"{'grammar':<22}{'match_only':>12}{'consult':>9}  rules")
    total_match = total_consult = 0
    skipped: list[str] = []
    for path in _grammars():
        found = _specs(path)
        if found is None:
            skipped.append(path.name)
            continue
        match_only, consult, names = found
        total_match += match_only
        total_consult += consult
        shown = ", ".join(names) if names else "—"
        print(f"{path.name:<22}{match_only:>12}{consult:>9}  {shown}")
    print(f"\n{'TOTAL':<22}{total_match:>12}{total_consult:>9}")
    print(
        f"\npopulation\t{total_consult} of {total_match} match-only clones carry a "
        "proof against their OWN continuation"
    )
    if skipped:
        print(f"skipped\t\t{len(skipped)} grammar(s) compile no PDA: {skipped}")
    print("\ns4 consult eligibility: OK")


if __name__ == "__main__":
    main()
