"""The windows that show what a PARSE is.

Every one of these is about a parse rather than about a grammar: the
floor and its measured claims, the forest, the chart, what the
predictive runtime actually ran, and where a text was cut into tokens.
They live together because they all ask the same question first — which
grammar read this reading — and that is the only thing they share.
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrDoc, IrTokenizer
from opsis.opsis.draw.canvas import el
from opsis.opsis.floor.analysis import analysis_view
from opsis.opsis.floor.chart import chart_view, segmentation_view
from opsis.opsis.floor.engine import (
    derivation_view,
    execution_view,
    floor_view,
    forest_view,
    tables_view,
)
from opsis.opsis.pane import RESUMES, Pane, artefact, grammar_of, read_by
from opsis.opsis.read.parts import chip
from opsis.opsis.read.views import resume_view
from opsis.praxis.reading import Reading
from opsis.praxis.session import Session

__all__ = [
    "analysis_pane",
    "chart_pane",
    "derivations_pane",
    "execution_pane",
    "floor_pane",
    "forest_pane",
    "resolver",
    "resume_pane",
    "segmentation_pane",
    "segments",
    "tables_pane",
]


def analysis_pane(_session: Session, reading: Reading) -> Pane:
    """Every decision the predictive analysis settled, in its own words."""
    compiled = grammar_of(reading)
    return Pane(
        f"{reading.title} — its verdicts", (660, 420), lambda: [analysis_view(compiled)]
    )


def resume_pane(_session: Session, reading: Reading) -> Pane:
    """The growing chart, its marks, and what it accepts so far."""
    held = RESUMES.of(reading)
    return Pane(
        f"{reading.title} — resume",
        (600, 380),
        lambda: [resume_view(reading.ident, held)],
    )


def tables_pane(_session: Session, reading: Reading) -> Pane:
    """The predictive artefact this grammar compiled to."""
    compiled = grammar_of(reading)
    return Pane(
        f"{reading.title} — its tables", (640, 380), lambda: [tables_view(compiled)]
    )


def segments(session: Session, reading: Reading) -> IrTokenizer | None:
    """The vocabulary this text is cut by, when it is read as tokens."""
    above = session.readings.get(reading.reader)
    under = artefact(above) if above is not None and reading.text else None
    if under is None or not under.tokens.segmented:
        return None
    return under.tokens.tokenizer


def execution_pane(session: Session, reading: Reading) -> Pane:
    """What the predictive runtime did to this text, decision by decision."""
    under = read_by(session, reading)
    text = reading.text
    return Pane(
        f"{reading.title} — what ran", (700, 460), lambda: [execution_view(under, text)]
    )


def chart_pane(session: Session, reading: Reading) -> Pane:
    """The Earley chart this text fills, column by column."""
    under = read_by(session, reading)
    text = reading.text
    return Pane(
        f"{reading.title} — its chart", (700, 460), lambda: [chart_view(under, text)]
    )


def segmentation_pane(session: Session, reading: Reading) -> Pane:
    """Where this text was cut into tokens, and into which ids."""
    vocab = segments(session, reading)
    if vocab is None:
        raise UnsupportedConstructError(f"{reading.title} is not read as tokens")
    text = reading.text
    return Pane(
        f"{reading.title} — its tokens ▲",
        (640, 420),
        lambda: [segmentation_view(vocab, text)],
    )


def floor_pane(session: Session, reading: Reading) -> Pane:
    """Both engines on this text, and whether they agree."""
    under = read_by(session, reading)
    text = reading.text
    return Pane(
        f"{reading.title} — floor",
        (640, 380),
        lambda: [floor_view(under, text), resolver(reading)],
    )


def forest_pane(session: Session, reading: Reading) -> Pane:
    """The forest this text derives."""
    under = read_by(session, reading)
    text = reading.text
    return Pane(
        f"{reading.title} — forest", (700, 460), lambda: [forest_view(under, text)]
    )


def derivations_pane(session: Session, reading: Reading) -> Pane:
    """Every way this text derives."""
    under = read_by(session, reading)
    text = reading.text
    return Pane(
        f"{reading.title} — derivations",
        (640, 380),
        lambda: [derivation_view(under, text), resolver(reading)],
    )


def resolver(reading: Reading) -> IrDoc:
    """The resolver plug — the caller's answer to an ambiguity.

    Not a flag: an ambiguity is refused unless somebody says which
    derivation they meant, and this is where they say it. Empty means
    refuse, which is the default and the honest one.
    """
    return el(
        "div",
        {"class": "controls"},
        chip(
            "resolver",
            f"c-res-{reading.ident}",
            reading.params.resolver,
            "empty refuses",
            False,
        ),
        el(
            "span",
            {"class": "note"},
            "'first' takes the first derivation; empty refuses an ambiguous "
            "span rather than choosing for you",
        ),
    )
