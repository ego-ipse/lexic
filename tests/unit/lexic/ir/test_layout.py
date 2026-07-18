"""Tests for ir/layout.py — the Wadler-style layout algebra + render().

IrText/IrLine/IrCat/IrNest/IrGroup are the doc combinators; render() solves
line breaks against a target width deterministically via Sheet's explicit
stack. Layout is text-agnostic — these tests exercise the doc shapes
directly, not any particular emitter's constructor-call syntax.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.layout import IrCat, IrGroup, IrLine, IrNest, IrText, Sheet, render

# ── render() determinism ────────────────────────────────────────────────


def test_render_is_deterministic_across_repeated_calls():
    """The same doc renders to the same string every time — no hidden state."""
    doc = IrGroup(IrCat(IrText("a"), IrLine(" ", ""), IrText("b")))
    first = render(doc, 80)
    second = render(doc, 80)
    assert first == second == "a b"


def test_render_does_not_mutate_the_doc_between_calls():
    """Rendering the same doc at two different widths gives independent results."""
    doc = IrGroup(IrCat(IrText("aaaaaaaaaa"), IrLine(" ", ","), IrText("bbbbbbbbbb")))
    wide = render(doc, 80)
    narrow = render(doc, 5)
    assert wide == "aaaaaaaaaa bbbbbbbbbb"
    assert narrow == "aaaaaaaaaa,\nbbbbbbbbbb"
    # re-rendering at the original width still gives the original result
    assert render(doc, 80) == wide


# ── flat vs broken groups ───────────────────────────────────────────────


def test_group_that_fits_renders_flat():
    """A group whose flattened text fits the width stays on one line."""
    doc = IrGroup(IrCat(IrText("a"), IrLine(" ", ""), IrText("b")))
    assert render(doc, 10) == "a b"


def test_group_that_overflows_breaks_every_direct_line():
    """A group too wide for the line breaks at every direct IrLine."""
    doc = IrGroup(IrCat(IrText("aaaaaaaaaa"), IrLine(" ", ","), IrText("bbbbbbbbbb")))
    assert render(doc, 5) == "aaaaaaaaaa,\nbbbbbbbbbb"


def test_nest_applies_indent_to_breaks_inside_it():
    """IrNest's indent applies to breaks inside it, not to breaks outside it."""
    call = IrCat(
        IrText("f("),
        IrNest(2, IrCat(IrLine("", ""), IrText("arg"))),
        IrLine("", ","),
        IrText(")"),
    )
    doc = IrGroup(call)
    assert render(doc, 80) == "f(arg)"
    assert render(doc, 5) == "f(\n  arg,\n)"


def test_inner_groups_redecide_independently_of_the_outer_break():
    """When the outer group breaks, each inner group still fits-checks itself
    at its own column — one may stay flat while a sibling breaks."""
    short_group = IrGroup(IrCat(IrText("a"), IrLine(" ", ""), IrText("b")))
    long_group = IrGroup(IrCat(IrText("ccccccccccccccc"), IrLine(" ", ""), IrText("d")))
    doc = IrGroup(
        IrCat(
            IrText("outer("),
            short_group,
            IrText(", "),
            long_group,
            IrText(")"),
        )
    )
    # Wide enough that everything fits flat.
    assert render(doc, 80) == "outer(a b, ccccccccccccccc d)"
    # Narrow enough that the whole thing can't fit flat, but short_group alone
    # (at column 6, plus its continuation) still clears the width while
    # long_group does not — each group decides for itself.
    assert render(doc, 26) == "outer(a b, ccccccccccccccc\nd)"
    # Narrower still: both groups break.
    assert render(doc, 10) == "outer(a\nb, ccccccccccccccc\nd)"


# ── IrLine flat/pre semantics ───────────────────────────────────────────


def test_irline_flat_renders_its_flat_text():
    """A flat IrLine emits its ``flat`` text, nothing else."""
    sheet = Sheet(80)
    IrLine("x", "y").layout(sheet, indent=0, flat=True)
    assert "".join(sheet.parts) == "x"
    assert sheet.col == 1


def test_irline_broken_renders_pre_then_newline_then_indent():
    """A broken IrLine emits ``pre``, a newline, then indent spaces."""
    sheet = Sheet(80)
    IrLine("x", "y").layout(sheet, indent=3, flat=False)
    assert "".join(sheet.parts) == "y\n   "
    assert sheet.col == 3


def test_irline_trailing_comma_pattern():
    """``IrLine("", ",")`` — the trailing-comma pattern: nothing when flat,
    a comma before the break when broken."""
    flat_sheet = Sheet(80)
    IrLine("", ",").layout(flat_sheet, indent=0, flat=True)
    assert "".join(flat_sheet.parts) == ""

    broken_sheet = Sheet(80)
    IrLine("", ",").layout(broken_sheet, indent=0, flat=False)
    assert "".join(broken_sheet.parts) == ",\n"


def test_irline_defaults_are_both_empty():
    """IrLine() with no args carries empty flat and pre text."""
    line = IrLine()
    assert line.flat == ""
    assert line.pre == ""


# ── continuation-aware fits ──────────────────────────────────────────────


def test_continuation_forces_a_break_even_though_the_group_alone_fits():
    """A group whose own flattened text fits the width must still break if
    the sheet's pending continuation (e.g. a trailing comma after the group,
    the black-call shape) would overflow the line."""
    call = IrCat(
        IrText("f("),
        IrNest(2, IrCat(IrLine("", ""), IrText("arg"))),
        IrLine("", ","),
        IrText(")"),
    )
    group = IrGroup(call)
    doc = IrCat(group, IrText(","))

    # "f(arg)" is 6 chars — fits alone at width 6, but "f(arg)," is 7 chars,
    # which overflows: the continuation comma forces the group to break.
    assert render(doc, 6) == "f(\n  arg,\n),"
    # At width 7 the whole "f(arg)," (7 chars) fits exactly at the boundary.
    assert render(doc, 7) == "f(arg),"
    # Comfortably wide: stays flat.
    assert render(doc, 20) == "f(arg),"


def test_sheet_fits_reports_the_boundary_inclusively():
    """Sheet.fits is a ``<=`` boundary check against the target width."""
    sheet = Sheet(10)
    assert sheet.fits(IrText("1234567890")) is True  # exactly 10 chars
    assert sheet.fits(IrText("12345678901")) is False  # 11 chars


# ── IrText: no embedded newlines ────────────────────────────────────────


def test_irtext_refuses_an_embedded_newline():
    """IrText is a leaf without its own line device — embedded newlines are
    a construction error; use IrLine to introduce a break."""
    with pytest.raises(UnsupportedConstructError):
        IrText("a\nb")


def test_irtext_default_is_empty_string():
    """IrText() with no argument is the empty-text leaf."""
    assert str(IrText()) == ""


def test_irtext_layout_writes_its_text_regardless_of_flat():
    """IrText.layout ignores the flat flag — it always writes its own text."""
    sheet = Sheet(80)
    IrText("hi").layout(sheet, indent=0, flat=False)
    assert "".join(sheet.parts) == "hi"


# ── scan() — the flat-width lookahead over nested docs ──────────────────


def test_scan_of_a_flat_group_sums_nested_text_widths():
    """Rendering a nested IrCat/IrNest/IrGroup doc at a generous width sums
    every leaf's text — the flat-width lookahead composes through nesting."""
    doc = IrCat(
        IrText("a"),
        IrNest(4, IrCat(IrText("b"), IrGroup(IrText("c")))),
        IrText("d"),
    )
    assert render(doc, 1000) == "abcd"


def test_irtext_scan_returns_its_length():
    """IrText.scan reports its own character width, flat or not."""
    assert IrText("abc").scan(True, []) == 3
    assert IrText("").scan(False, []) == 0


def test_irline_scan_returns_flat_length_when_flat_and_none_when_broken():
    """A broken IrLine's scan is None — a break that ends the lookahead."""
    line = IrLine("xy", "z")
    assert line.scan(True, []) == 2
    assert line.scan(False, []) is None


def test_ircat_irnest_irgroup_scan_push_children_and_return_zero():
    """The container docs contribute zero width themselves — their scan
    step pushes children onto the work list for the caller to continue."""
    work: list = []
    assert IrCat(IrText("x")).scan(True, work) == 0
    assert work

    work2: list = []
    assert IrNest(2, IrText("x")).scan(True, work2) == 0
    assert work2 == [(True, IrText("x"))]

    work3: list = []
    assert IrGroup(IrText("x")).scan(True, work3) == 0
    assert work3 == [(True, IrText("x"))]


# ── Sheet.write / Sheet.newline ──────────────────────────────────────────


def test_sheet_write_appends_text_and_advances_column():
    """Sheet.write appends verbatim text and moves the column forward."""
    sheet = Sheet(80)
    sheet.write("abc")
    assert "".join(sheet.parts) == "abc"
    assert sheet.col == 3
    sheet.write("de")
    assert "".join(sheet.parts) == "abcde"
    assert sheet.col == 5


def test_sheet_newline_emits_pre_then_breaks_and_lands_at_indent():
    """Sheet.newline writes pre, breaks, and resets the column to indent."""
    sheet = Sheet(80)
    sheet.write("abc")
    sheet.newline(2, pre="!")
    assert "".join(sheet.parts) == "abc!\n  "
    assert sheet.col == 2


def test_sheet_newline_default_pre_is_empty():
    """Sheet.newline's pre parameter defaults to no broken-only text."""
    sheet = Sheet(80)
    sheet.newline(0)
    assert "".join(sheet.parts) == "\n"
    assert sheet.col == 0
