"""The Earley chart, and the segmentation a token parse runs on.

Two windows onto what a parse is made of. The chart is columns of
items: one column per input position, each holding the partial
derivations still alive there. The segmentation is the other half of a
token parse — where one text was cut, and into which ids.

Both are bounded and say what they left out. A chart over a long input
has more items than a screen has room for, and pretending otherwise
would be worse than saying so.
"""

from __future__ import annotations

from opsis.opsis.draw.canvas import el
from opsis.opsis.draw.canvas import text as _text
from opsis.opsis.floor.engine import walked
from opsis.opsis.read.views import facts, grid, panel, refusal, titled
from opsis.praxis.reading import FOREIGN

from lexic.compile import CompiledGrammar
from lexic.ir import IrDoc, IrTokenizer
from lexic.parsing import ParserTables, compile_tables
from lexic.parsing.earley.kernel.forest.readout import decode_item
from lexic.parsing.earley.kernel.loop.kernel import Kernel

__all__ = ["chart_view", "segmentation_view"]

COLUMNS = 24
"""How many columns one chart draws before it states the rest."""

ITEMS = 12
"""How many items one column shows before it states the rest."""


def chart_view(compiled: CompiledGrammar, text: str) -> IrDoc:
    """The chart this text fills: one column per position, items within.

    An Earley column at position ``i`` holds every partial derivation
    still alive after reading ``i`` characters. Reading the columns left
    to right IS the parse — nothing else happened.
    """
    try:
        tables = compile_tables(walked(compiled))
        kernel = Kernel(tables, text).run()
    except FOREIGN as exc:
        return refusal(f"{type(exc).__name__}: {exc}")
    columns = list(kernel.cols)
    total = sum(len(col) for col in columns)
    rows = [
        _column(tables, index, list(col), text)
        for index, col in enumerate(columns[:COLUMNS])
    ]
    left = len(columns) - len(rows)
    return panel(
        f"{len(columns)} columns · {total:,} items in all"
        + (f" · {left} columns not drawn" if left > 0 else ""),
        *rows,
    )


def _column(tables: ParserTables, index: int, items: list[int], text: str) -> IrDoc:
    """One column: where it sits in the text, and what is alive there."""
    shown = items[:ITEMS]
    rest = len(items) - len(shown)
    where = f"after {text[:index][-24:]!r}" if index else "before anything"
    return titled(
        f"@{index}",
        f"{len(items)} items",
        where,
        grid([(_item(tables, one), "") for one in shown]),
        *(
            [el("div", {"class": "note"}, _text(f"{rest} more items here"))]
            if rest > 0
            else []
        ),
    )


def _item(tables: ParserTables, packed: int) -> str:
    """One Earley item, decoded into the rule and position it stands for."""
    try:
        return str(decode_item(tables, packed))[:120]
    except FOREIGN:
        return f"item {packed}"


def segmentation_view(vocabulary: IrTokenizer, text: str) -> IrDoc:
    """Where this text was cut, and into which ids.

    A token parse does not read characters — it reads ids, and which
    ids a text becomes is the vocabulary's answer, not the grammar's.
    So the cut is shown before anything downstream of it is believed.
    """
    try:
        cuts = list(vocabulary.boundaries(text))
    except FOREIGN as exc:
        return refusal(f"{type(exc).__name__}: {exc}")
    if not cuts:
        return panel(f"{vocabulary.name} cut this text into nothing")
    rows = [
        (f"@{start} · {ident}", repr(text[start:end]))
        for start, end, ident in cuts[:200]
    ]
    left = len(cuts) - len(rows)
    return facts(
        [
            ("tokens", f"{len(cuts):,}", f"from {len(text):,} characters"),
            ("vocabulary", str(vocabulary.name), f"{len(vocabulary.encode):,} entries"),
            ("ratio", f"{len(text) / max(len(cuts), 1):.1f}", "characters per token"),
        ],
        grid(rows),
        *(
            [el("div", {"class": "note"}, _text(f"{left:,} tokens not drawn"))]
            if left > 0
            else []
        ),
    )
