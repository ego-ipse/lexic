"""A committed chart is a rendered claim — it may not lie by geometry.

``tools.render_readme`` writes two SVGs under ``docs/assets/``. Three failures
are invisible in the source and silent in every viewer: an element drawn past
the declared viewBox is clipped away, a ``class`` no style rule defines is
painted in the default ink in both themes, and an element emitted once per row
that should have been emitted once per chart stacks on itself. All three have
shipped. ``chart_defects`` names them, ``checked`` refuses to hand the chart
on, and this gate holds the committed assets to it.
"""

import re
from pathlib import Path

import pytest

from tools.render_readme import (
    ELEMENT,
    STYLE,
    _box,
    _ce_slots,
    _palette_slots,
    chart_defects,
    checked,
    cross_engine_svg,
    mt_svg,
)

ROOT = Path(__file__).resolve().parents[4]
ASSETS = ROOT / "docs" / "assets"

SOUND = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50" '
    'width="100" height="50">'
    f"{STYLE}"
    '<circle cx="50.0" cy="25.0" r="5" class="c0"/>'
    '<text x="10.0" y="40.0" font-size="12" class="m">ok</text>'
    "</svg>"
)
"""A minimal chart holding every invariant — the synthetic cases perturb it."""


def _charts() -> list[Path]:
    """Every committed chart asset."""
    return sorted(ASSETS.glob("*.svg"))


@pytest.mark.parametrize("name", ["cross-engine.svg", "mt-speedup.svg"])
def test_committed_chart_holds_the_render_invariants(name: str) -> None:
    """The asset as checked in draws inside its viewBox, in defined classes, once."""
    assert chart_defects((ASSETS / name).read_text(encoding="utf-8")) == []


def test_every_committed_chart_is_checked() -> None:
    """No asset escapes the gate by being written under a name nobody names."""
    assert [path.name for path in _charts()] == ["cross-engine.svg", "mt-speedup.svg"]


def test_sound_synthetic_chart_reports_nothing() -> None:
    """The checker's baseline: the unperturbed synthetic case is clean."""
    assert chart_defects(SOUND) == []


def test_defect_element_outside_the_viewbox() -> None:
    """A drawn element past the declared extent is named, with its box."""
    broken = SOUND.replace('cx="50.0"', 'cx="140.0"')
    defects = chart_defects(broken)
    assert len(defects) == 1
    assert "outside viewBox 0 0 100 50" in defects[0]


def test_defect_text_running_past_the_right_edge() -> None:
    """Overflow is measured on the text's rendered width, not on its anchor."""
    broken = SOUND.replace(">ok<", ">a caption far too long for this box<")
    assert any("outside viewBox" in defect for defect in chart_defects(broken))


def test_defect_class_with_no_style_rule() -> None:
    """A class the chart's own style block never defines is named."""
    broken = SOUND.replace('class="c0"', 'class="c99"')
    assert chart_defects(broken) == ["class 'c99' used with no style rule"]


def test_undefined_class_is_judged_against_the_charts_own_style() -> None:
    """The chart travels alone, so the check reads the style it carries."""
    stripped = re.sub(r"<style>.*</style>", "", SOUND, flags=re.S)
    defects = chart_defects(stripped)
    assert "class 'c0' used with no style rule" in defects
    assert "class 'm' used with no style rule" in defects


def test_defect_element_emitted_twice() -> None:
    """The same element drawn twice — a per-row caption that is per-chart."""
    caption = '<text x="10.0" y="40.0" font-size="12" class="m">ok</text>'
    broken = SOUND.replace(caption, caption * 2)
    defects = chart_defects(broken)
    assert defects == [f"emitted 2 times: {caption}"]


def test_missing_viewbox_is_itself_a_defect() -> None:
    """A chart that declares no extent cannot be checked, and is not excused."""
    assert chart_defects("<svg></svg>") == [
        "no viewBox: the chart declares no extent to check against"
    ]


def test_checked_refuses_a_broken_chart() -> None:
    """A broken chart is refused rather than written, naming the asset."""
    broken = SOUND.replace('cx="50.0"', 'cx="140.0"')
    with pytest.raises(SystemExit, match="cross-engine.svg"):
        checked(broken, "cross-engine.svg")


def test_checked_passes_a_sound_chart_through() -> None:
    """The gate is transparent when the chart holds."""
    assert checked(SOUND, "synthetic.svg") == SOUND


def test_palette_exhaustion_raises_rather_than_wrapping() -> None:
    """A roster past the defined slots is refused, never folded onto slot zero."""
    roster = [f"g{k}" for k in range(len(_palette_slots()) + 1)]
    with pytest.raises(SystemExit, match="categorical slots"):
        _ce_slots(roster)


def test_palette_covers_the_current_roster_in_both_themes() -> None:
    """Every slot a chart can use is defined in the light and the dark block."""
    light, _, dark = STYLE.partition("prefers-color-scheme:dark")
    for slot in _palette_slots():
        assert f".{slot}{{" in light, slot
        assert f".{slot}{{" in dark, slot


def test_refusal_column_means_one_grammar() -> None:
    """Each × column carries a single categorical class across every row.

    The mark's x used to come from a per-row refusal counter, so one column
    held a different grammar in each row it appeared in — a reader who read
    the column as a category read it wrong.
    """
    svg = cross_engine_svg()
    marks = re.findall(r'<text x="([\d.]+)"[^>]*class="(c\d+) b">×</text>', svg)
    assert marks, "the artifact has refusals to draw"
    columns: dict[str, set[str]] = {}
    for x, cls in marks:
        columns.setdefault(x, set()).add(cls)
    assert all(len(seen) == 1 for seen in columns.values()), columns


def test_refuses_caption_is_emitted_once() -> None:
    """One chart, one legend for the × glyph."""
    assert cross_engine_svg().count(">refuses<") == 1


def test_every_dot_lands_inside_the_plot() -> None:
    """The log domain follows the data, so no value plots into the label gutter."""
    svg = cross_engine_svg()
    rows = [
        _box(elem)
        for elem in ELEMENT.findall(svg)
        if elem.startswith("<circle") and _box(elem)[1] > 60
    ]
    labels = [
        _box(elem)
        for elem in ELEMENT.findall(svg)
        if elem.startswith("<text") and 'font-size="13"' in elem and "×" not in elem
    ]
    assert min(box[0] for box in rows) > max(box[2] for box in labels)


def test_legend_names_every_grammar_that_is_plotted() -> None:
    """A wrapped legend still carries the whole roster, inside the viewBox."""
    svg = cross_engine_svg()
    legend = re.findall(r'<circle cx="[\d.]+" cy="(?:18|38|58)\.0"[^>]*/>', svg)
    dotted = {
        cls
        for elem in ELEMENT.findall(svg)
        for cls in re.findall(r'class="(c\d+)', elem)
    }
    assert len(legend) == len(dotted)


def test_both_charts_render_clean_from_the_artifact() -> None:
    """Rendering afresh from the committed baseline produces no defect."""
    assert chart_defects(cross_engine_svg()) == []
    assert chart_defects(mt_svg()) == []
