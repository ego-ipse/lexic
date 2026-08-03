"""Theme contract — the register renders as non-empty, complete CSS."""

from __future__ import annotations

from opsis.opsis.draw.theme import PALETTE, RULES, css


def test_css_is_non_empty() -> None:
    """The rendered stylesheet is never blank."""
    assert css()


def test_css_contains_every_rule_selector() -> None:
    """Every selector named in RULES appears somewhere in the output."""
    rendered = css()
    missing = [selector for selector, _ in RULES if selector not in rendered]
    assert missing == []


def test_css_contains_the_palette_variables() -> None:
    """Every named hue is bound as a CSS custom property."""
    rendered = css()
    assert all(f"--{name}:" in rendered for name in PALETTE)
