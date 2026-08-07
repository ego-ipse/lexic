"""What the analysis decided, in its own words.

Before the predictive runtime can run, every decision point in a
grammar has to be settled: which arm a lookahead picks, whether a loop
can be entered, where nothing can be decided and Earley has to take
over. That analysis writes notes as it goes, and this is the window
that shows them.

The notes are shown verbatim. A paraphrase would be opsis deciding what
the analysis meant, and the whole value of a note is that the thing
which made the decision wrote it.
"""

from __future__ import annotations

from opsis.opsis.draw.canvas import el
from opsis.opsis.draw.canvas import text as _text
from opsis.opsis.floor.engine import walked
from opsis.opsis.read.views import facts, panel, refusal
from opsis.praxis.reading import FOREIGN

from lexic.compile import CompiledGrammar
from lexic.ir import IrDoc
from lexic.parsing import GrammarAnalysis

__all__ = ["analysis_view", "verdict_of"]


def verdict_of(analysis: GrammarAnalysis, rule: str) -> str:
    """What the analysis concluded about one rule.

    The four outcomes a rule can have, in the order that matters: an
    island means the predictive half gave up there, a conflict means it
    could not decide, a demotion means it decided by a weaker gate, and
    silence means it went through cleanly.
    """
    if rule in analysis.fail_islands:
        return "island · Earley takes this span"
    if rule in analysis.islands:
        return "island"
    if rule in analysis.conflicts:
        return "conflict"
    if rule in analysis.demoted:
        return "demoted"
    return "decided"


def analysis_view(compiled: CompiledGrammar) -> IrDoc:
    """Every decision the analysis settled, and the ones it could not.

    A grammar with no notes is not an empty window: it is a grammar the
    predictive half decided cleanly all the way down, which is the most
    useful thing that window could say.
    """
    try:
        analysis = GrammarAnalysis(walked(compiled))
    except FOREIGN as exc:
        return refusal(f"{type(exc).__name__}: {exc}")
    counts = [
        ("islands", f"{len(analysis.islands):,}", "handed to Earley"),
        ("failing islands", f"{len(analysis.fail_islands):,}", "gave up predicting"),
        ("conflicts", f"{len(analysis.conflicts):,}", "could not be decided"),
        ("demoted", f"{len(analysis.demoted):,}", "decided by a weaker gate"),
    ]
    notes = _notes(analysis)
    if not notes:
        return facts(
            counts,
            el(
                "div",
                {"class": "claim ok"},
                _text(
                    "no notes: every decision point in this grammar was settled "
                    "cleanly, so the predictive runtime never falls back"
                ),
            ),
        )
    return facts(counts, panel(f"{len(notes)} notes, verbatim", *notes))


def _notes(analysis: GrammarAnalysis) -> list[IrDoc]:
    """Every note the analysis wrote, against the rule it wrote it about."""
    out: list[IrDoc] = []
    for rule, said in sorted(analysis.demoted.items()):
        for one in said:
            out.append(_note(str(rule), str(one), "demoted"))
    for rule, said in sorted(analysis.conflicts.items()):
        for one in said:
            out.append(_note(str(rule), str(one), "conflict"))
    return out


def _note(rule: str, said: str, kind: str) -> IrDoc:
    """One note, wired to the rule it is about."""
    return el(
        "div",
        {"class": "cell", "data-rule": rule},
        el("code", None, _text(f"{rule} · {kind}")),
        el("span", None, _text(said)),
    )
