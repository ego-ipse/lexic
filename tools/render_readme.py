"""Render README numbers and charts from committed benchmark artifacts.

The README never carries a hand-typed measurement. Every figure inside its
``<!-- lexic:begin NAME -->`` / ``<!-- lexic:end NAME -->`` markers, and every
SVG under ``docs/assets/``, is rendered by this tool from two committed
artifacts — ``tools/benchmark/lexic_baseline.json`` (the pre-commit ratchet's
fresh-process Lexic rows, updated whenever a performance change is accepted)
and ``tools/benchmark/competitors_baseline.json`` (the dated cross-engine
medians, refreshed deliberately by rerunning the full bench). The test count
is what pytest collects, parametrized cases included. Nothing here runs a
benchmark.

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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
ASSETS = ROOT / "docs" / "assets"
LEXIC_BASELINE = ROOT / "tools" / "benchmark" / "lexic_baseline.json"
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
@media(prefers-color-scheme:dark){
text{fill:#c3c2b7}
.p{fill:#ffffff}
.gl{stroke:#2c2c2a}.ax{stroke:#383835}
circle{stroke:#1a1a19}
.c0{fill:#3987e5}.c1{fill:#d95926}.c2{fill:#199e70}.c3{fill:#c98500}
.c4{fill:#d55181}.c6{fill:#9085e9}.c7{fill:#e66767}
}
</style>"""
"""Both modes of the validated reference palette, swapped by media query.

Categorical slots ``c0``-``c7`` follow the palette's fixed CVD-safe order;
ink and chrome roles come from the same reference instance.
"""


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
    """The parallel-parse badge — the ladder's top speedup, from the ratchet."""
    top = max(speedup for _, speedup in mt_speedups())
    return (
        f"![Parallel parsing](https://img.shields.io/badge/"
        f"parallel_parse-up_to_{top:.1f}x_on_16_threads-2a78d6)"
    )


def lexic_values() -> dict[str, dict[str, float]]:
    """The ratchet's per-grammar row medians."""
    return json.loads(LEXIC_BASELINE.read_text(encoding="utf-8"))["values"]


DISPLAY_SEATS = (
    "lexic-mt",
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
"""


def competitor_data() -> tuple[
    str, dict[str, dict[str, str]], dict[str, dict[str, Cell]]
]:
    """The dated cross-engine artifact, narrowed to the display seats.

    Returns ``(caption, engines, values)`` — the caption carries the
    measurement date and, when the artifact holds more seats than the README
    shows, how many stayed in the file.
    """
    data = json.loads(COMPETITORS.read_text(encoding="utf-8"))
    engines: dict[str, dict[str, str]] = data["engines"]
    shown = [name for name in DISPLAY_SEATS if name in engines]
    hidden = len(engines) - len(shown)
    cores = data.get("cores")
    picked = {}
    for name in shown:
        picked[name] = dict(engines[name])
        if name.startswith("lexic-mt") and cores:
            picked[name]["label"] = f"{picked[name]['label']} ({cores} workers)"
    caption = f"measured {data['measured']}"
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
    """(grammar, wall-clock speedup) of the 16-worker row, fastest first."""
    rows = [
        (grammar, cells["lexic-pda"] / cells["lexic-mt"])
        for grammar, cells in sorted(lexic_values().items())
        if "lexic-mt" in cells
    ]
    return sorted(rows, key=lambda row: -row[1])


def lexic_table() -> str:
    """The always-current Lexic table, straight from the ratchet baseline."""
    head = (
        "| grammar | pda | `@lexical` | `@lexical` `@non-semantic` |"
        " 16-worker | speedup | earley |\n|---|---|---|---|---|---|---|"
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


CE_LEFT, CE_RIGHT, CE_TOP, CE_ROW_H, CE_W = 150.0, 96.0, 56.0, 32.0, 880.0
CE_PLOT = CE_W - CE_LEFT - CE_RIGHT
CE_LO, CE_HI = math.log10(0.05), math.log10(250.0)
"""Cross-engine chart geometry: margins, row pitch, and the log-x domain."""


def _ce_x(value: float) -> float:
    """A µs/char value's x position on the log axis."""
    return CE_LEFT + (math.log10(value) - CE_LO) / (CE_HI - CE_LO) * CE_PLOT


def _ce_legend(grammars: list[str]) -> list[str]:
    """The grammar legend row across the chart top."""
    parts: list[str] = []
    x = CE_LEFT
    for k, grammar in enumerate(grammars):
        parts.append(f'<circle cx="{x + 5:.1f}" cy="22" r="5" class="c{k}"/>')
        parts.append(_text(x + 14, 26, grammar))
        x += 18 + 7.2 * len(grammar) + 14
    return parts


def _ce_grid(height: float) -> list[str]:
    """Hairline gridlines at the decade ticks, with labels and the axis note."""
    parts: list[str] = []
    for tick in (0.1, 1.0, 10.0, 100.0):
        x = _ce_x(tick)
        parts.append(
            f'<line x1="{x:.1f}" y1="{CE_TOP - 8:.1f}" x2="{x:.1f}"'
            f' y2="{height - 54:.1f}" class="gl" stroke-width="1"/>'
        )
        label = f"{tick:g}"
        parts.append(_text(x - 3.5 * len(label), height - 38, label, "m"))
    parts.append(
        _text(
            CE_LEFT + CE_PLOT - 178,
            height - 22,
            "µs/char — log scale, lower is faster",
            "m",
        )
    )
    return parts


def _ce_row(y: float, cells: dict[str, Cell], grammars: list[str]) -> list[str]:
    """One engine's dots — and × marks in the right margin where it refuses."""
    parts: list[str] = []
    refusals = 0
    for k, grammar in enumerate(grammars):
        cell = cells.get(grammar)
        if cell is None:
            continue
        if isinstance(cell, str):
            x = CE_LEFT + CE_PLOT + 16 + refusals * 16
            refusals += 1
            parts.append(_text(x, y + 4.5, "×", f"c{k} b", 13))
            continue
        parts.append(
            f'<circle cx="{_ce_x(cell):.1f}" cy="{y:.1f}" r="5" class="c{k}"/>'
        )
    if refusals:
        parts.append(_text(CE_LEFT + CE_PLOT + 16, CE_TOP - 14, "refuses", "m", 11))
    return parts


def cross_engine_svg() -> str:
    """The cross-engine dot plot: engines as labeled rows, grammars as dots.

    Engine identity rides the row label (never color alone); the grammars take
    categorical slots in artifact order with a legend; the x axis is log
    µs/char and a refusal renders as an × glyph in the right margin instead of
    a dot. One adaptive SVG serves both GitHub themes.
    """
    caption, engines, values = competitor_data()
    grammars = list(values)
    by_engine = {
        e: {g: values[g][e] for g in grammars if e in values[g]} for e in engines
    }
    order = sorted(engines, key=lambda e: _median(by_engine[e]))
    height = CE_TOP + CE_ROW_H * len(order) + 58.0
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CE_W:.0f} {height:.0f}"'
        f' width="{CE_W:.0f}" height="{height:.0f}" role="img"'
        f' aria-label="Parse speed per engine and grammar, log µs/char">',
        STYLE,
    ]
    parts += _ce_legend(grammars)
    parts += _ce_grid(height)
    for i, engine in enumerate(order):
        y = CE_TOP + CE_ROW_H * i + CE_ROW_H / 2
        label = engines[engine]["label"]
        cls = "b" if engine.startswith("lexic") else ""
        parts.append(_text(8, y + 4, label, cls, 13))
        parts += _ce_row(y, by_engine[engine], grammars)
    parts.append(_text(8, height - 8, caption, "m", 11))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


MT_LEFT, MT_TOP, MT_BAR, MT_GAP, MT_W = 120.0, 30.0, 16.0, 10.0, 720.0
MT_PLOT = MT_W - MT_LEFT - 70.0
"""Speedup-ladder geometry: margins, bar pitch, plot width."""


def _mt_x(value: float, ceiling: float) -> float:
    """A speedup value's x position on the linear axis scaled to ``ceiling``."""
    return MT_LEFT + value / ceiling * MT_PLOT


def _mt_grid(height: float, ceiling: float) -> list[str]:
    """Tick gridlines with the 1× baseline emphasized as the axis."""
    parts: list[str] = []
    for tick in range(1, int(ceiling) + 1):
        x = _mt_x(float(tick), ceiling)
        cls = "ax" if tick == 1 else "gl"
        parts.append(
            f'<line x1="{x:.1f}" y1="{MT_TOP - 6:.1f}" x2="{x:.1f}"'
            f' y2="{height - 34:.1f}" class="{cls}" stroke-width="1"/>'
        )
        parts.append(_text(x - 8, height - 18, f"{tick}×", "m"))
    parts.append(_text(_mt_x(1.0, ceiling) - 8, MT_TOP - 12, "sequential", "m", 11))
    return parts


def _mt_bar(y: float, grammar: str, speedup: float, ceiling: float) -> list[str]:
    """One grammar's bar — rounded data-end, direct value label."""
    end = _mt_x(speedup, ceiling)
    return [
        _text(8, y + MT_BAR - 3, grammar, "", 13),
        f'<path d="M {MT_LEFT:.1f} {y:.1f} H {end - 4:.1f} Q {end:.1f} {y:.1f}'
        f" {end:.1f} {y + 4:.1f} V {y + MT_BAR - 4:.1f} Q {end:.1f} {y + MT_BAR:.1f}"
        f' {end - 4:.1f} {y + MT_BAR:.1f} H {MT_LEFT:.1f} Z" class="c0"/>',
        _text(end + 7, y + MT_BAR - 3, f"{speedup:.1f}×", "p b"),
    ]


def mt_svg() -> str:
    """The multithreading ladder: one bar per grammar, 16-worker speedup."""
    rows = mt_speedups()
    height = MT_TOP + len(rows) * (MT_BAR + MT_GAP) + 40.0
    ceiling = math.ceil(max(s for _, s in rows)) + 0.5
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {MT_W:.0f} {height:.0f}"'
        f' width="{MT_W:.0f}" height="{height:.0f}" role="img"'
        f' aria-label="Wall-clock speedup at 16 workers, per grammar">',
        STYLE,
    ]
    parts += _mt_grid(height, ceiling)
    for i, (grammar, speedup) in enumerate(rows):
        parts += _mt_bar(MT_TOP + i * (MT_BAR + MT_GAP), grammar, speedup, ceiling)
    parts.append(
        _text(
            MT_LEFT,
            height - 4,
            "one document, 16 workers vs the same engine sequential — "
            "from the committed ratchet baseline",
            "m",
            11,
        )
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def rendered_blocks() -> dict[str, str]:
    """Every marker-block body this tool owns, by marker name."""
    return {
        "tests-badge": tests_badge(),
        "mt-badge": mt_badge(),
        "lexic-bench": lexic_table(),
        "cross-bench": competitors_table(),
    }


def rendered_assets() -> dict[Path, str]:
    """Every generated asset, by path."""
    return {
        ASSETS / "cross-engine.svg": cross_engine_svg(),
        ASSETS / "mt-speedup.svg": mt_svg(),
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
