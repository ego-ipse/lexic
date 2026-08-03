"""Tests for opsis.opsis._theme — the register as data."""

from __future__ import annotations

from opsis.opsis._theme import PALETTE, RULES, css


def test_css_root_block_has_every_palette_name():
    """css() opens a :root block carrying every PALETTE name as a --var."""
    out = css()
    assert ":root" in out
    for name in PALETTE:
        assert f"--{name}:" in out


def test_css_covers_every_rule_selector_and_hue_tints():
    """css() renders every RULES selector plus the derived hue tints."""
    out = css()
    for selector, _props in RULES:
        assert selector in out
    for hue in ("cyan", "green", "amber", "magenta"):
        assert f".ring.{hue} .rdot" in out
