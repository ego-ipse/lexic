"""Verdict — the analysis explainer: every decision point's classification.

Renders what :class:`~lexic.parsing.pda.analysis.analysis.GrammarAnalysis`
already computes for the compiled grammar: per rule, whether the PDA
runs it predictively, which gate family demoted its conflicts (k-window,
noise-skip, structured scan/probe), whether it attempts, islands, or
fail-islands — with the analysis' own notes verbatim. Nothing is
computed here; the analysis is the oracle and this is its transcript.

Import note: the analysis is not part of the parsing root's public
surface — this module carries opsis' recorded exemption (alongside the
future ``trace.py``) to reach one level into the engine, read-only.
"""

from __future__ import annotations

from html import escape
from typing import Any

from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis

_BADGES = (
    ("attempt", "ordered attempts decide"),
    ("island", "windowed Earley sub-parse"),
    ("gated", "demoted to a stored gate"),
    ("hard", "unresolved conflict"),
    ("predictive", "single-pass deterministic"),
)


def verdicts_html(cg: Any) -> str:
    """The per-rule verdict table for one compiled grammar."""
    analysis = GrammarAnalysis(lift_optional_nullables(cg.codegen_grammar))
    attempts = set(analysis.taxonomy.attempts)
    islands = set(analysis.islands) - attempts
    hard = {k: list(v) for k, v in analysis.taxonomy.conflicts.items() if v}
    soft = {k: list(v) for k, v in analysis.demoted.items() if v}
    rows = []
    for name in analysis.rules:
        cls, notes = _classify(name, attempts, islands, hard, soft)
        note_html = "".join(f"<div>{escape(n)}</div>" for n in notes)
        rows.append(
            f'<tr class="v-{cls}"><td><span class="badge">{cls}</span></td>'
            f'<td class="rule" data-goto="{escape(name)}">{escape(name)}</td>'
            f'<td class="notes">{note_html}</td></tr>'
        )
    legend = "".join(
        f'<span class="v-{cls}"><span class="badge">{cls}</span> {escape(txt)}</span>'
        for cls, txt in _BADGES
    )
    return (
        f'<div class="legend">{legend}</div>'
        f'<table class="verdicts">{"".join(rows)}</table>'
    )


def _classify(
    name: str,
    attempts: set[str],
    islands: set[str],
    hard: dict[str, list[str]],
    soft: dict[str, list[str]],
) -> tuple[str, list[str]]:
    """One rule's badge class and its analysis notes."""
    notes = hard.get(name, []) + soft.get(name, [])
    if name in attempts:
        return "attempt", notes
    if name in islands:
        return "island", notes
    if hard.get(name):
        return "hard", notes
    if soft.get(name):
        return "gated", notes
    return "predictive", notes
