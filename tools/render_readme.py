"""Render README numbers and charts from committed benchmark artifacts.

The README never carries a hand-typed measurement. Every figure inside its
``<!-- lexic:begin NAME -->`` / ``<!-- lexic:end NAME -->`` markers, and every
SVG under ``docs/assets/``, is rendered by this tool from one committed
artifact — ``tools/benchmark/competitors_baseline.json``, the dated medians of
every seat, Lexic's own rows included, refreshed deliberately by rerunning the
full bench with ``--json``. The test count is what pytest collects,
parametrized cases included. Nothing here runs a benchmark.

Each chart is ONE theme-adaptive SVG: a ``<style>`` block carries the
light-mode palette and a ``prefers-color-scheme: dark`` override, so a plain
markdown image link renders correctly on both GitHub themes and in any
viewer that honors the media query.

    uv run python -m tools.render_readme            # rewrite README + assets
    uv run python -m tools.render_readme --check    # exit 1 if anything is stale

``tests/integration/lexic/invariants/test_readme_render.py`` runs the check as
a suite invariant, so a stale README fails CI instead of waiting to be noticed.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
ASSETS = ROOT / "docs" / "assets"
COMPETITORS = ROOT / "tools" / "benchmark" / "competitors_baseline.json"

Cell = float | str
"""One artifact value — a µs/char median, or the string ``"refuses"``."""

STYLE = """<style>
text{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;fill:#52514e}
.p{fill:#0b0b0b}.m{fill:#898781}.b{font-weight:600}
.gl{stroke:#e1e0d9}.ax{stroke:#c3c2b7}
circle{stroke:#fcfcfb;stroke-width:2}
.c0{fill:#2a78d6}.c1{fill:#eb6834}.c2{fill:#1baf7a}.c3{fill:#eda100}
.c4{fill:#e87ba4}.c5{fill:#008300}.c6{fill:#4a3aa7}.c7{fill:#e34948}
.c8{fill:#0f8f9e}.c9{fill:#8a5a2b}.c10{fill:#a03fa0}.c11{fill:#5a6675}
@media(prefers-color-scheme:dark){
text{fill:#c3c2b7}
.p{fill:#ffffff}
.gl{stroke:#2c2c2a}.ax{stroke:#383835}
circle{stroke:#1a1a19}
.c0{fill:#3987e5}.c1{fill:#d95926}.c2{fill:#199e70}.c3{fill:#c98500}
.c4{fill:#d55181}.c5{fill:#2e9e2e}.c6{fill:#9085e9}.c7{fill:#e66767}
.c8{fill:#21a7b8}.c9{fill:#b78655}.c10{fill:#c46fc4}.c11{fill:#96a3b3}
}
</style>"""
"""Both modes of the validated reference palette, swapped by media query.

Categorical slots ``c0``-``c7`` follow the palette's fixed CVD-safe order; ink
and chrome roles come from the same reference instance. ``c8``-``c11`` extend
that order for rosters past eight — colour alone stops separating that many
levels, so categorical identity also rides the legend and, for refusals, a
fixed per-grammar column. A roster longer than the defined slots is refused,
never wrapped back onto slot zero.
"""

GLYPH_ADVANCE = 0.6
"""Advance width per point of font size — the layout's one text metric.

Every width the charts reserve and every width the render check measures come
through :func:`_width`, so the guard cannot disagree with the layout it guards.
"""


def _width(text: str, size: float) -> float:
    """Approximate the rendered width of ``text`` set at ``size`` points."""
    return GLYPH_ADVANCE * size * len(text)


def _defined_classes(css: str) -> frozenset[str]:
    """Every class name a stylesheet defines a rule for."""
    return frozenset(re.findall(r"\.([A-Za-z][\w-]*)\s*\{", css))


def _style_classes() -> frozenset[str]:
    """Every class name the shared style block defines."""
    return _defined_classes(STYLE)


def _palette_slots() -> list[str]:
    """The categorical class names, in the palette's fixed order."""
    slots = [name for name in _style_classes() if re.fullmatch(r"c\d+", name)]
    return sorted(slots, key=lambda name: int(name[1:]))


def fmt(value: float) -> str:
    """Format a µs/char figure at a precision its magnitude supports."""
    if value >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def count_tests() -> int:
    """Count the tests pytest actually collects — parametrized cases included.

    A static ``def test_*`` census undercounts by a third here (parametrized
    families expand at collection), so the badge counts what the suite runs.
    Collection is skip-independent, so the number is stable across
    environments.
    """
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"(\d+) tests? collected", out.stdout)
    if match is None:
        raise SystemExit(
            f"test collection failed:\n{out.stdout[-2000:]}{out.stderr[-2000:]}"
        )
    return int(match.group(1))


def tests_badge() -> str:
    """The tests badge, rounded down to the nearest hundred so it churns rarely."""
    rounded = count_tests() // 100 * 100
    return (
        f"![Tests](https://img.shields.io/badge/tests-{rounded // 100 / 10:.1f}k%2B"
        "-brightgreen)"
    )


def mt_badge() -> str:
    """The parallel-parse badge — the ladder's top speedup, from the artifact."""
    top = max(speedup for _, speedup in mt_speedups())
    return (
        f"![Parallel parsing](https://img.shields.io/badge/"
        f"parallel_parse-up_to_{top:.1f}x_on_{mt_workers()}_threads-2a78d6)"
    )


def lexic_values() -> dict[str, dict[str, float]]:
    """The artifact's per-grammar medians — the Lexic seats read from the same run."""
    return json.loads(COMPETITORS.read_text(encoding="utf-8"))["values"]


def cell_records() -> dict[str, dict[str, dict[str, object]]]:
    """The artifact's per-cell provenance, by grammar and then seat."""
    return json.loads(COMPETITORS.read_text(encoding="utf-8"))["provenance"]


def _seat_cells(seat: str) -> list[dict[str, object]]:
    """Every recorded cell in one seat's column."""
    return [cells[seat] for cells in cell_records().values() if seat in cells]


def column_workers(seat: str) -> int | None:
    """The worker request every cell in one seat's column agrees on.

    A column header states ONE worker count, so it may only be printed when the
    cells behind it were all taken at that count. A partial refresh at a
    different count is refused here rather than relabelled: the artifact keeps
    both truths, and the README declines to average them into a false one.

    :param seat: The engine column to read.
    :returns: The agreed count, or ``None`` when the seat records none.
    :raises SystemExit: If the column's cells disagree.
    """
    counts = {record.get("cores") for record in _seat_cells(seat)}
    if len(counts) > 1:
        spread = sorted(str(count) for count in counts)
        raise SystemExit(
            f"{seat} was measured at {', '.join(spread)} workers across grammars; "
            f"one column header cannot state them. Re-measure the seat whole."
        )
    found = counts.pop() if counts else None
    return int(found) if isinstance(found, int) else None


def mt_workers() -> int:
    """The worker count the threaded row was measured at, from the artifact."""
    workers = column_workers("lexic-mt")
    if workers is None:
        raise SystemExit("the artifact records no worker count for lexic-mt")
    return workers


DISPLAY_SEATS = (
    "lexic-mt",
    "lexic-mt-lex-ns",
    "lexic-lex-ns",
    "lexic-pda",
    "lexic-earley",
    "lark-lalr",
    "lark-earley",
    "parsimonious",
    "pyparsing",
    "antlr-py",
    "antlr",
    "antlr-java",
)
"""The seats the README shows, of the artifact's full roster.

A deliberate, stated selection — the artifact keeps every measured seat
(directive-matched competitor variants, json specialists); the rendered
caption says how many were left in the file rather than dropping them
silently.

The two lexic threaded rows stand together, and so do the two directive-matched
ones, because a reader compares what is adjacent. Showing plain MT without
pruned MT put our slowest threaded row beside our fastest sequential one, so
`announced` and `mixedends` read as threads LOSING; like for like the pruned
threaded row leads the pruned sequential one on all twelve.
"""


def _measured_caption(dates: Iterable[str]) -> str:
    """What the artifact actually says about WHEN the shown cells were taken.

    Provenance is per cell, because a run may refresh one seat of one grammar
    and leave the rest of the file alone. One date is printed when they agree;
    a span when they do not, because a single date over cells taken weeks apart
    claims a run that never happened.

    :param dates: Every shown cell's recorded measurement date.
    :returns: The caption's date clause.
    """
    seen = sorted(set(dates))
    if not seen:
        return "undated"
    if len(seen) == 1:
        return f"measured {seen[0]}"
    return f"measured {seen[0]} to {seen[-1]}, per cell"


def _shown_dates(shown: list[str]) -> list[str]:
    """Every recorded date behind the cells the README displays."""
    return [
        str(record["measured"])
        for cells in cell_records().values()
        for seat, record in cells.items()
        if seat in shown
    ]


def competitor_data() -> tuple[
    str, dict[str, dict[str, str]], dict[str, dict[str, Cell]]
]:
    """The dated cross-engine artifact, narrowed to the display seats.

    Returns ``(caption, engines, values)`` — the caption carries the
    measurement dates the displayed CELLS record and, when the artifact holds
    more seats than the README shows, how many stayed in the file. The threaded
    columns' worker counts come from those same records.
    """
    data = json.loads(COMPETITORS.read_text(encoding="utf-8"))
    engines: dict[str, dict[str, str]] = data["engines"]
    shown = [name for name in DISPLAY_SEATS if name in engines]
    hidden = len(engines) - len(shown)
    picked = {}
    for name in shown:
        picked[name] = dict(engines[name])
        workers = column_workers(name)
        if workers is not None:
            picked[name]["label"] = f"{picked[name]['label']} ({workers} workers)"
    caption = _measured_caption(_shown_dates(shown))
    if hidden:
        caption += (
            f"; {hidden} further seats (directive-matched competitor variants,"
            " format specialists) stay in the artifact"
        )
    values = {
        grammar: {name: cells[name] for name in shown if name in cells}
        for grammar, cells in data["values"].items()
    }
    return caption, picked, values


def mt_speedups() -> list[tuple[str, float]]:
    """(grammar, wall-clock speedup) of the threaded row, fastest first."""
    rows = [
        (grammar, cells["lexic-pda"] / cells["lexic-mt"])
        for grammar, cells in sorted(lexic_values().items())
        if "lexic-mt" in cells
    ]
    return sorted(rows, key=lambda row: -row[1])


def lexic_table() -> str:
    """The Lexic ladder, straight from the artifact's Lexic seats."""
    head = (
        "| grammar | pda | `@lexical` | `@lexical` `@non-semantic` |"
        f" {mt_workers()}-worker | speedup | earley |\n|---|---|---|---|---|---|---|"
    )
    lines = [head]
    for grammar, cells in sorted(lexic_values().items()):
        speedup = cells["lexic-pda"] / cells["lexic-mt"]
        lines.append(
            f"| {grammar} | {fmt(cells['lexic-pda'])} | {fmt(cells['lexic-lex'])}"
            f" | {fmt(cells['lexic-lex-ns'])} | {fmt(cells['lexic-mt'])}"
            f" | **{speedup:.1f}×** | {fmt(cells['lexic-earley'])} |"
        )
    return "\n".join(lines)


def competitors_table() -> str:
    """The dated cross-engine table, from the competitors artifact."""
    caption, engines, values = competitor_data()
    names = list(engines)
    cols = " | ".join(
        f"**{engines[e]['label']}**"
        if e.startswith("lexic")
        else f"*{engines[e]['label']}*"
        if engines[e]["runtime"] == "java"
        else engines[e]["label"]
        for e in names
    )
    lines = [
        f"| grammar | {cols} |",
        "|---|" + "---|" * len(names),
    ]
    for grammar in values:
        cells = values[grammar]
        row = " | ".join(
            _styled(cells[e], e, engines[e]["runtime"]) if e in cells else "—"
            for e in names
        )
        lines.append(f"| {grammar} | {row} |")
    lines.append(f"\nµs/char, lower is faster; medians of isolated rounds; {caption}.")
    return "\n".join(lines)


def _styled(cell: Cell, engine: str, runtime: str) -> str:
    """One cross-engine table cell — lexic bold, Java italic, refusals plain."""
    if isinstance(cell, str):
        return cell
    if engine.startswith("lexic"):
        return f"**{fmt(cell)}**"
    return f"*{fmt(cell)}*" if runtime == "java" else fmt(cell)


def _median(cells: dict[str, Cell]) -> float:
    """Median of the numeric cells one engine posted."""
    ran = sorted(v for v in cells.values() if isinstance(v, float))
    mid = len(ran) // 2
    return ran[mid] if len(ran) % 2 else (ran[mid - 1] + ran[mid]) / 2


def _text(x: float, y: float, s: str, cls: str = "", size: int = 12) -> str:
    """One SVG text element; ``cls`` picks ink and weight from the style block."""
    attr = f' class="{cls}"' if cls else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}"{attr}>{s}</text>'


CE_W, CE_PAD, CE_ROW_H, CE_LEGEND_H = 880.0, 8.0, 32.0, 20.0
CE_MARK_PITCH, CE_MARK_GAP = 16.0, 16.0
"""Cross-engine chart geometry: width, padding, row pitch, refusal-column pitch.

Everything else — the label gutter, the legend height, the refusal band, the
log-x domain — is derived from the artifact, because the roster on both axes
comes from the artifact and changes when it is remeasured.
"""


class CeGeom(NamedTuple):
    """One cross-engine chart's resolved geometry, derived from its artifact."""

    left: float
    right: float
    top: float
    bottom: float
    lo: float
    hi: float


def _ce_x(geom: CeGeom, value: float) -> float:
    """A µs/char value's x position on the log axis.

    :param geom: the resolved chart geometry
    :param value: the µs/char figure to place
    :returns: the x coordinate, always inside the plot
    """
    span = (math.log10(value) - geom.lo) / (geom.hi - geom.lo)
    return geom.left + span * (geom.right - geom.left)


def _ce_domain(by_engine: dict[str, dict[str, Cell]]) -> tuple[float, float]:
    """The log-x domain containing every plotted value, with edge padding.

    :param by_engine: the plotted cells, per engine
    :returns: the ``(lo, hi)`` log10 bounds
    :raises SystemExit: if the artifact holds no numeric cell to plot
    """
    nums = [
        c
        for cells in by_engine.values()
        for c in cells.values()
        if isinstance(c, float)
    ]
    if not nums:
        raise SystemExit("cross-engine chart: the artifact holds no numeric cell")
    lo, hi = math.log10(min(nums)), math.log10(max(nums))
    pad = max((hi - lo) * 0.06, 0.15)
    return lo - pad, hi + pad


def _wrap(text: str, width: float, size: float) -> list[str]:
    """Break ``text`` on spaces into lines no wider than ``width`` at ``size``."""
    lines: list[str] = []
    for word in text.split(" "):
        if lines and _width(f"{lines[-1]} {word}", size) <= width:
            lines[-1] = f"{lines[-1]} {word}"
            continue
        lines.append(word)
    return lines


def _legend_rows(grammars: list[str], width: float) -> list[list[str]]:
    """Grammar chips packed into rows no wider than ``width``."""
    rows: list[list[str]] = [[]]
    used = 0.0
    for grammar in grammars:
        step = 18.0 + _width(grammar, 12) + 14.0
        if rows[-1] and used + step > width:
            rows.append([])
            used = 0.0
        rows[-1].append(grammar)
        used += step
    return rows


def _ce_legend(rows: list[list[str]], slot: dict[str, str]) -> list[str]:
    """The wrapped grammar legend across the chart top."""
    parts: list[str] = []
    for line, names in enumerate(rows):
        x = CE_PAD
        y = CE_PAD + 14.0 + line * CE_LEGEND_H
        for grammar in names:
            chip = f'<circle cx="{x + 5:.1f}" cy="{y - 4:.1f}" r="5"'
            parts.append(f'{chip} class="{slot[grammar]}"/>')
            parts.append(_text(x + 14, y, grammar))
            x += 18.0 + _width(grammar, 12) + 14.0
    return parts


def _ce_grid(geom: CeGeom) -> list[str]:
    """Hairline gridlines at the decade ticks inside the domain, with labels."""
    parts: list[str] = []
    for power in range(math.ceil(geom.lo), math.floor(geom.hi) + 1):
        x = _ce_x(geom, 10.0**power)
        parts.append(
            f'<line x1="{x:.1f}" y1="{geom.top - 8:.1f}" x2="{x:.1f}"'
            f' y2="{geom.bottom + 4:.1f}" class="gl" stroke-width="1"/>'
        )
        label = f"{10.0**power:g}"
        parts.append(_text(x - _width(label, 12) / 2, geom.bottom + 22, label, "m"))
    note = "µs/char — log scale, lower is faster"
    parts.append(_text(geom.right - _width(note, 12), geom.bottom + 40, note, "m"))
    return parts


def _ce_row(
    geom: CeGeom,
    y: float,
    cells: dict[str, Cell],
    slot: dict[str, str],
    column: dict[str, int],
) -> list[str]:
    """One engine's dots — and × marks in each refused grammar's own column.

    The × column is keyed by grammar, not by how many refusals the row has
    already emitted, so a column means one grammar in every row it appears in.
    """
    parts: list[str] = []
    for grammar, cell in cells.items():
        if isinstance(cell, str):
            x = geom.right + CE_MARK_GAP + column[grammar] * CE_MARK_PITCH
            parts.append(_text(x, y + 4.5, "×", f"{slot[grammar]} b", 13))
            continue
        dot = f'<circle cx="{_ce_x(geom, cell):.1f}" cy="{y:.1f}" r="5"'
        parts.append(f'{dot} class="{slot[grammar]}"/>')
    return parts


def _ce_slots(grammars: list[str]) -> dict[str, str]:
    """Each grammar's categorical class, refusing a roster the palette cannot hold."""
    slots = _palette_slots()
    if len(grammars) > len(slots):
        raise SystemExit(
            f"cross-engine chart: {len(grammars)} grammars but only {len(slots)}"
            " categorical slots — extend the palette in STYLE"
        )
    return dict(zip(grammars, slots))


def _ce_geometry(
    engines: dict[str, dict[str, str]],
    by_engine: dict[str, dict[str, Cell]],
    grammars: list[str],
    legend_lines: int,
) -> tuple[CeGeom, list[str]]:
    """Resolve the plot box and the refusal band from the artifact's own shape."""
    gutter = max(_width(e["label"], 13) for e in engines.values())
    refusing = [
        g
        for g in grammars
        if any(isinstance(c.get(g), str) for c in by_engine.values())
    ]
    band = CE_PAD
    if refusing:
        marks = CE_MARK_GAP + CE_MARK_PITCH * len(refusing) + CE_PAD
        band = max(marks, CE_MARK_GAP + _width("refuses", 11) + CE_PAD)
    top = CE_PAD + 14.0 + legend_lines * CE_LEGEND_H + 14.0
    lo, hi = _ce_domain(by_engine)
    bottom = top + CE_ROW_H * len(engines)
    return CeGeom(CE_PAD + gutter + 12.0, CE_W - band, top, bottom, lo, hi), refusing


def _ce_rows(
    geom: CeGeom,
    engines: dict[str, dict[str, str]],
    by_engine: dict[str, dict[str, Cell]],
    slot: dict[str, str],
    column: dict[str, int],
) -> list[str]:
    """Every engine row, fastest median first, label then dots then × marks."""
    parts: list[str] = []
    for i, engine in enumerate(sorted(engines, key=lambda e: _median(by_engine[e]))):
        y = geom.top + CE_ROW_H * i + CE_ROW_H / 2
        cls = "b" if engine.startswith("lexic") else ""
        parts.append(_text(CE_PAD, y + 4, engines[engine]["label"], cls, 13))
        parts += _ce_row(geom, y, by_engine[engine], slot, column)
    return parts


def _ce_caption(bottom: float, lines: list[str]) -> list[str]:
    """The wrapped provenance caption under the axis."""
    return [
        _text(CE_PAD, bottom + 60.0 + 14.0 * line, body, "m", 11)
        for line, body in enumerate(lines)
    ]


def cross_engine_svg() -> str:
    """The cross-engine dot plot: engines as labeled rows, grammars as dots.

    Engine identity rides the row label (never colour alone); the grammars take
    categorical slots in artifact order with a wrapped legend; the x axis is log
    µs/char over the domain the data occupies, and a refusal renders as an ×
    glyph in that grammar's own right-margin column instead of a dot. One
    adaptive SVG serves both GitHub themes.
    """
    caption, engines, values = competitor_data()
    grammars = list(values)
    by_engine = {
        e: {g: values[g][e] for g in grammars if e in values[g]} for e in engines
    }
    legend = _legend_rows(grammars, CE_W - 2 * CE_PAD)
    geom, refusing = _ce_geometry(engines, by_engine, grammars, len(legend))
    lines = _wrap(caption, CE_W - 2 * CE_PAD, 11)
    height = geom.bottom + 60.0 + 14.0 * len(lines)
    slot = _ce_slots(grammars)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CE_W:.0f} {height:.0f}"'
        f' width="{CE_W:.0f}" height="{height:.0f}" role="img"'
        f' aria-label="Parse speed per engine and grammar, log µs/char">',
        STYLE,
    ]
    parts += _ce_legend(legend, slot)
    parts += _ce_grid(geom)
    if refusing:
        parts.append(_text(geom.right + CE_MARK_GAP, geom.top - 10, "refuses", "m", 11))
    parts += _ce_rows(geom, engines, by_engine, slot, dict(_columns(refusing)))
    parts += _ce_caption(geom.bottom, lines)
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _columns(refusing: list[str]) -> list[tuple[str, int]]:
    """Each refusing grammar paired with the right-margin column it owns."""
    return [(grammar, k) for k, grammar in enumerate(refusing)]


MT_TOP, MT_BAR, MT_GAP, MT_W, MT_RIGHT = 30.0, 16.0, 10.0, 720.0, 70.0
"""Speedup-ladder geometry: top margin, bar pitch, width, value-label margin.

The left gutter is derived from the artifact's own grammar names, the same way
the cross-engine chart derives its engine-label gutter.
"""


def mt_caption() -> str:
    """What the ladder's bars are ratios of, at the recorded worker count."""
    return (
        f"one document, {mt_workers()} workers vs the same engine sequential — "
        "from the committed ratchet baseline"
    )


def _mt_x(left: float, value: float, ceiling: float) -> float:
    """A speedup value's x position on the linear axis scaled to ``ceiling``."""
    return left + value / ceiling * (MT_W - left - MT_RIGHT)


def _mt_grid(left: float, bottom: float, ceiling: float) -> list[str]:
    """Tick gridlines with the 1× baseline emphasized as the axis."""
    parts: list[str] = []
    for tick in range(1, int(ceiling) + 1):
        x = _mt_x(left, float(tick), ceiling)
        cls = "ax" if tick == 1 else "gl"
        parts.append(
            f'<line x1="{x:.1f}" y1="{MT_TOP - 6:.1f}" x2="{x:.1f}"'
            f' y2="{bottom + 4:.1f}" class="{cls}" stroke-width="1"/>'
        )
        label = f"{tick}×"
        parts.append(_text(x - _width(label, 12) / 2, bottom + 20, label, "m"))
    note = "sequential"
    x = _mt_x(left, 1.0, ceiling) - _width(note, 11) / 2
    parts.append(_text(x, MT_TOP - 12, note, "m", 11))
    return parts


def _mt_bar(left: float, y: float, row: tuple[str, float], ceiling: float) -> list[str]:
    """One grammar's bar — rounded data-end, direct value label."""
    grammar, speedup = row
    end = _mt_x(left, speedup, ceiling)
    return [
        _text(CE_PAD, y + MT_BAR - 3, grammar, "", 13),
        f'<path d="M {left:.1f} {y:.1f} H {end - 4:.1f} Q {end:.1f} {y:.1f}'
        f" {end:.1f} {y + 4:.1f} V {y + MT_BAR - 4:.1f} Q {end:.1f} {y + MT_BAR:.1f}"
        f' {end - 4:.1f} {y + MT_BAR:.1f} H {left:.1f} Z" class="c0"/>',
        _text(end + 7, y + MT_BAR - 3, f"{speedup:.1f}×", "p b"),
    ]


def mt_svg() -> str:
    """The multithreading ladder: one bar per grammar, threaded-row speedup."""
    rows = mt_speedups()
    workers = mt_workers()
    left = CE_PAD + max(_width(grammar, 13) for grammar, _ in rows) + 12.0
    bottom = MT_TOP + len(rows) * (MT_BAR + MT_GAP)
    lines = _wrap(mt_caption(), MT_W - 2 * CE_PAD, 11)
    height = bottom + 44.0 + 14.0 * len(lines)
    ceiling = math.ceil(max(speedup for _, speedup in rows)) + 0.5
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {MT_W:.0f} {height:.0f}"'
        f' width="{MT_W:.0f}" height="{height:.0f}" role="img"'
        f' aria-label="Wall-clock speedup at {workers} workers, per grammar">',
        STYLE,
    ]
    parts += _mt_grid(left, bottom, ceiling)
    for i, row in enumerate(rows):
        parts += _mt_bar(left, MT_TOP + i * (MT_BAR + MT_GAP), row, ceiling)
    for line, body in enumerate(lines):
        parts.append(_text(CE_PAD, bottom + 44.0 + 14.0 * line, body, "m", 11))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


ELEMENT = re.compile(r"<(?:circle|line|path)\b[^>]*/>|<text\b[^>]*>.*?</text>")
"""Every drawn element of a rendered chart, as this module emits them."""


def _attr(elem: str, name: str) -> float:
    """One numeric attribute of an emitted element, zero when it carries none."""
    found = re.search(rf'\b{name}="(-?[\d.]+)"', elem)
    return float(found.group(1)) if found else 0.0


def _path_step(
    cmd: str, nums: list[float], x: float, y: float
) -> list[tuple[float, float]]:
    """The absolute points one path command reaches from the current point."""
    if cmd == "H":
        return [(n, y) for n in nums]
    if cmd == "V":
        return [(x, n) for n in nums]
    return list(zip(nums[0::2], nums[1::2]))


def _path_box(elem: str) -> tuple[float, float, float, float]:
    """A path's bounding box, tracking the H/V commands that carry one ordinate."""
    found = re.search(r'\bd="([^"]*)"', elem)
    points = [(0.0, 0.0)]
    for cmd, args in re.findall(
        r"([MHVQZ])([-\d.\s]*)", found.group(1) if found else ""
    ):
        nums = [float(n) for n in args.split()]
        points += _path_step(cmd, nums, *points[-1])
    xs = [x for x, _ in points[1:]]
    ys = [y for _, y in points[1:]]
    return min(xs), min(ys), max(xs), max(ys)


def _box(elem: str) -> tuple[float, float, float, float]:
    """The drawn bounding box of one emitted element, as ``(x0, y0, x1, y1)``."""
    if elem.startswith("<circle"):
        reach = _attr(elem, "r") + 1.0
        cx, cy = _attr(elem, "cx"), _attr(elem, "cy")
        return cx - reach, cy - reach, cx + reach, cy + reach
    if elem.startswith("<line"):
        xs = (_attr(elem, "x1"), _attr(elem, "x2"))
        ys = (_attr(elem, "y1"), _attr(elem, "y2"))
        return min(xs), min(ys), max(xs), max(ys)
    if elem.startswith("<path"):
        return _path_box(elem)
    size, x, y = _attr(elem, "font-size"), _attr(elem, "x"), _attr(elem, "y")
    body = elem.partition(">")[2].rpartition("</text>")[0]
    return x, y - size * 0.8, x + _width(body, size), y + size * 0.25


def chart_defects(svg: str) -> list[str]:
    """Every render-level violation in one chart, as sentences.

    Three classes, each of which has shipped in a committed asset: an element
    drawn outside the declared viewBox (silently clipped by every renderer), a
    ``class`` no ``<style>`` rule defines (silently drawn in the default ink,
    in both themes), and the same element emitted twice (a per-row caption that
    should have been a per-chart one).

    :param svg: the rendered chart text
    :returns: one sentence per violation, empty when the chart is sound
    """
    view = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if view is None:
        return ["no viewBox: the chart declares no extent to check against"]
    width, height = float(view.group(1)), float(view.group(2))
    elements = ELEMENT.findall(svg)
    css = svg.partition("<style>")[2].partition("</style>")[0]
    out = _overflows(elements, width, height) + _undefined_classes(elements, css)
    twice = [elem for elem, n in Counter(elements).items() if n > 1]
    out += [f"emitted {Counter(elements)[elem]} times: {elem}" for elem in twice]
    return out


def _overflows(elements: list[str], width: float, height: float) -> list[str]:
    """Elements whose drawn box leaves the declared viewBox."""
    out: list[str] = []
    for elem in elements:
        x0, y0, x1, y1 = _box(elem)
        if x0 >= -0.5 and y0 >= -0.5 and x1 <= width + 0.5 and y1 <= height + 0.5:
            continue
        box = f"({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f})"
        out.append(f"outside viewBox 0 0 {width:.0f} {height:.0f} at {box}: {elem}")
    return out


def _undefined_classes(elements: list[str], css: str) -> list[str]:
    """Classes an element names that the chart's own style block never defines.

    Read from the chart rather than from :data:`STYLE`, because the SVG travels
    alone: an undefined class is drawn in the default ink in every theme.
    """
    defined = _defined_classes(css)
    used = {
        name
        for elem in elements
        for group in re.findall(r'class="([^"]+)"', elem)
        for name in group.split()
    }
    return [
        f"class {name!r} used with no style rule" for name in sorted(used - defined)
    ]


def checked(svg: str, name: str) -> str:
    """Return ``svg`` unchanged, or refuse to hand a broken chart on.

    :param svg: the rendered chart text
    :param name: the asset name, for the refusal message
    :returns: ``svg``
    :raises SystemExit: if the chart violates a render invariant
    """
    defects = chart_defects(svg)
    if defects:
        joined = "\n  ".join(defects)
        raise SystemExit(f"{name}: refusing to write a broken chart:\n  {joined}")
    return svg


def rendered_blocks() -> dict[str, str]:
    """Every marker-block body this tool owns, by marker name."""
    return {
        "tests-badge": tests_badge(),
        "mt-badge": mt_badge(),
        "lexic-bench": lexic_table(),
        "cross-bench": competitors_table(),
    }


def rendered_assets() -> dict[Path, str]:
    """Every generated asset, by path — each held to the render invariants first."""
    return {
        ASSETS / "cross-engine.svg": checked(cross_engine_svg(), "cross-engine.svg"),
        ASSETS / "mt-speedup.svg": checked(mt_svg(), "mt-speedup.svg"),
    }


def splice(text: str, name: str, body: str) -> str:
    """Replace one marker block's body inside the README text."""
    begin, end = f"<!-- lexic:begin {name} -->", f"<!-- lexic:end {name} -->"
    head, found, rest = text.partition(begin)
    _, sep, tail = rest.partition(end)
    if not sep or not found:
        raise SystemExit(f"README marker missing or unterminated: {name}")
    return f"{head}{begin}\n{body}\n{end}{tail}"


def stale() -> list[str]:
    """Names of README blocks and asset files that differ from a fresh render."""
    text = README.read_text(encoding="utf-8")
    out = [
        name
        for name, body in rendered_blocks().items()
        if splice(text, name, body) != text
    ]
    out += [
        str(path.relative_to(ROOT))
        for path, body in rendered_assets().items()
        if not path.is_file() or path.read_text(encoding="utf-8") != body
    ]
    out += [
        str(path.relative_to(ROOT))
        for path in sorted(ASSETS.glob("*.svg"))
        if path not in rendered_assets()
    ]
    return out


def write() -> None:
    """Rewrite the README blocks and regenerate the chart assets."""
    text = README.read_text(encoding="utf-8")
    for name, body in rendered_blocks().items():
        text = splice(text, name, body)
    README.write_text(text, encoding="utf-8")
    ASSETS.mkdir(parents=True, exist_ok=True)
    fresh = rendered_assets()
    for path, body in fresh.items():
        path.write_text(body, encoding="utf-8")
    for path in sorted(ASSETS.glob("*.svg")):
        if path not in fresh:
            path.unlink()


def main() -> None:
    """Render, or verify freshness with ``--check``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report stale blocks/assets and exit nonzero",
    )
    if parser.parse_args().check:
        out = stale()
        if out:
            raise SystemExit(
                f"stale (run `uv run python -m tools.render_readme`): {out}"
            )
        print("README render is current")
        return
    write()
    print("README and docs/assets rendered")


if __name__ == "__main__":
    main()
