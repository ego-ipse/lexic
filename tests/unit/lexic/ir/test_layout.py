"""Tests for ir/layout.py — the Wadler-style layout algebra + render().

IrText/IrLine/IrCat/IrNest/IrGroup are the doc combinators; render() solves
line breaks against a target width deterministically via Sheet's explicit
stack. Layout is text-agnostic — these tests exercise the doc shapes
directly, not any particular emitter's constructor-call syntax.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.access import IrField
from lexic.ir.layout import (
    IrCat,
    IrDocConcat,
    IrDocJoin,
    IrGroup,
    IrLine,
    IrNest,
    IrText,
    Sheet,
    as_doc,
    render,
)
from lexic.ir.nodes import IrAlternation, IrLiteral, IrRule, IrSequence
from lexic.ir.records import IrTuple
from lexic.ir.spine import IrNone

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
    """IrText.scan reports (own width, line continues), flat or not."""
    assert IrText("abc").scan(True, []) == (3, False)
    assert IrText("").scan(False, []) == (0, False)


def test_irline_scan_counts_pre_and_ends_the_line_when_broken():
    """A broken IrLine contributes its broken-only ``pre`` width to the
    CURRENT line and then ends the lookahead — so trailing commas count."""
    line = IrLine("xy", "z")
    assert line.scan(True, []) == (2, False)
    assert line.scan(False, []) == (1, True)


def test_ircat_irnest_irgroup_scan_push_children_and_return_zero():
    """The container docs contribute zero width themselves — their scan
    step pushes children onto the work list for the caller to continue."""
    work: list = []
    assert IrCat(IrText("x")).scan(True, work) == (0, False)
    assert work

    work2: list = []
    assert IrNest(2, IrText("x")).scan(True, work2) == (0, False)
    assert work2 == [(True, IrText("x"))]

    work3: list = []
    assert IrGroup(IrText("x")).scan(True, work3) == (0, False)
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


# ── as_doc: str→IrText lift, doc pass-through ─────────────────────────────


def test_as_doc_lifts_a_plain_string_to_irtext():
    """as_doc wraps a bare str-tier value as an IrText leaf."""
    result = as_doc("hi")
    assert isinstance(result, IrText)
    assert result == IrText("hi")


def test_as_doc_stringifies_a_non_doc_non_str_value():
    """as_doc str()s anything that isn't already a doc (e.g. an IrLiteral)."""
    result = as_doc(IrLiteral("x"))
    assert result == IrText("x")


def test_as_doc_passes_an_existing_doc_through_unchanged():
    """A value that already is an IrDoc is returned as-is, not re-wrapped."""
    doc = IrGroup(IrText("x"))
    assert as_doc(doc) is doc


# ── IrLine.eval — identity (line is action-body DATA, not a rebuild) ─────


def test_irline_eval_is_identity():
    """IrLine.eval returns the same instance — its str fields can't rebuild
    through the evaluating record-tier default."""
    line = IrLine("x", "y")
    assert line.eval(IrNone, IrNone, ()) is line


# ── IrGroup / IrNest — doc nodes as action-body TEMPLATES ────────────────


def test_irgroup_eval_rebuilds_around_the_evaluated_interior():
    """IrGroup.eval evaluates its interior action node against the
    dispatcher/node/nc, then rebuilds the group around the result."""
    node = IrRule("foo", IrAlternation(IrSequence()))
    template = IrGroup(IrDocConcat(parts=IrTuple(IrField("name"))))
    result = template.eval(IrNone, node, ())
    assert isinstance(result, IrGroup)
    assert result.doc == IrCat(IrText("foo"))


def test_irnest_eval_rebuilds_around_the_evaluated_interior():
    """IrNest.eval preserves its indent and evaluates its interior doc."""
    node = IrRule("bar", IrAlternation(IrSequence()))
    template = IrNest(4, IrDocConcat(parts=IrTuple(IrField("name"))))
    result = template.eval(IrNone, node, ())
    assert isinstance(result, IrNest)
    assert result.indent == 4
    assert result.doc == IrCat(IrText("bar"))


def test_irgroup_eval_lifts_a_str_tier_interior_result():
    """A str-tier action result (e.g. IrField's IrStr) lifts to IrText so the
    rebuilt group still satisfies the IrDoc.doc slot."""
    node = IrRule("baz", IrAlternation(IrSequence()))
    template = IrGroup(IrDocConcat(parts=IrTuple(IrField("name"))))
    result = template.eval(IrNone, node, ())
    assert isinstance(result, IrGroup)
    assert isinstance(result.doc, IrCat)


# ── IrDocConcat — the doc-tier sum of IrConcat ────────────────────────────


def test_irdocconcat_default_parts_is_empty_tuple():
    """IrDocConcat() with no args carries an empty parts tuple."""
    assert IrDocConcat().parts == IrTuple()


def test_irdocconcat_eval_concatenates_evaluated_parts_into_an_ircat():
    """IrDocConcat.eval evaluates each part and returns their IrCat."""
    node = IrRule("x", IrAlternation(IrSequence()))
    concat = IrDocConcat(parts=IrTuple(IrField("name"), IrText("!")))
    result = concat.eval(IrNone, node, ())
    assert isinstance(result, IrCat)
    assert render(result, None) == "x!"


def test_irdocconcat_lifts_str_tier_parts_to_irtext():
    """A part whose eval returns a plain str-tier leaf lifts via as_doc."""
    concat = IrDocConcat(parts=IrTuple(IrLiteral("a"), IrLiteral("b")))
    result = concat.eval(IrNone, IrNone, ())
    assert render(result, None) == "ab"


# ── IrDocJoin — the doc-tier sum of IrJoin ────────────────────────────────


def test_irdocjoin_defaults_are_empty_parts_and_empty_text():
    """IrDocJoin() with no args: empty parts, empty separator, empty fallback."""
    join = IrDocJoin()
    assert join.parts == IrTuple()
    assert join.separator == IrText()
    assert join.empty == IrText()


def test_irdocjoin_eval_interleaves_parts_with_the_separator():
    """IrDocJoin.eval places the separator doc between consecutive parts."""
    parts = IrTuple(IrText("a"), IrText("b"), IrText("c"))
    join = IrDocJoin(parts=parts, separator=IrText(", "))
    result = join.eval(IrNone, IrNone, ())
    assert render(result, None) == "a, b, c"


def test_irdocjoin_falsy_separator_is_skipped():
    """An empty-text separator contributes nothing between parts (the
    str-join neutral)."""
    parts = IrTuple(IrText("a"), IrText("b"))
    join = IrDocJoin(parts=parts, separator=IrText(""))
    result = join.eval(IrNone, IrNone, ())
    assert render(result, None) == "ab"


def test_irdocjoin_empty_parts_falls_back_to_empty_doc():
    """When parts evaluates empty, IrDocJoin.eval returns the empty fallback."""
    join = IrDocJoin(parts=IrTuple(), empty=IrText("<empty>"))
    result = join.eval(IrNone, IrNone, ())
    assert render(result, None) == "<empty>"


def test_irdocjoin_lifts_str_tier_parts_to_irtext():
    """Parts that evaluate to plain str-tier leaves lift to IrText."""
    join = IrDocJoin(
        parts=IrTuple(IrLiteral("a"), IrLiteral("b")), separator=IrText("-")
    )
    result = join.eval(IrNone, IrNone, ())
    assert render(result, None) == "a-b"


# ── render(doc, None) — the flat (unbounded) rendering ────────────────────


def test_render_at_width_none_never_breaks_a_group():
    """width=None: every group fits, so a normally-overflowing group stays flat."""
    doc = IrGroup(IrCat(IrText("aaaaaaaaaa"), IrLine(" ", ","), IrText("bbbbbbbbbb")))
    assert render(doc, None) == "aaaaaaaaaa bbbbbbbbbb"


def test_render_at_width_none_still_breaks_a_top_level_line():
    """A bare (ungrouped) IrLine at the top level renders in the root's
    flat=False frame regardless of width — width=None does not flatten it."""
    doc = IrCat(IrText("a"), IrLine("", ""), IrText("b"))
    assert render(doc, None) == "a\nb"


def test_render_default_width_is_88():
    """render()'s width parameter defaults to 88."""
    doc = IrText("x" * 10)
    assert render(doc) == "x" * 10


# ── Sheet(None) — the always-fits cursor ──────────────────────────────────


def test_sheet_with_none_width_always_fits():
    """A Sheet with width=None reports every candidate as fitting, however wide."""
    sheet = Sheet(None)
    assert sheet.fits(IrText("x" * 1000)) is True


def test_sheet_with_none_width_fits_even_after_prior_writes():
    """The always-fits shortcut does not consult the pending stack at all."""
    sheet = Sheet(None)
    sheet.write("already on the line " * 20)
    assert sheet.fits(IrText("more text")) is True
