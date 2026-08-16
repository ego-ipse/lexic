"""Tests for compile/presentation.py — the ceiling mechanism itself."""

from __future__ import annotations

import pytest

from lexic.compile import (
    Draw,
    Presentation,
    Row,
    Rows,
    compile_text,
    present,
    reset_cache_for_tests,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAddress,
    IrCond,
    IrLen,
    IrMap,
    IrSpan,
    IrStr,
    IrTuple,
    IrTypeMap,
)

GRAMMAR = 'pair ::= key "=" value\nkey ::= [a-z]+\nvalue ::= [0-9]+\n'


def rows_for(**roles: str) -> IrMap:
    """A table as data — rule name to role."""
    return IrMap(*(IrTuple(IrStr(rule), Draw(role)) for rule, role in roles.items()))


@pytest.fixture(name="pairs")
def pairs_fixture():
    """The small grammar, compiled under its own cache key."""
    reset_cache_for_tests()
    return compile_text(GRAMMAR, cache_key="presentation-unit")


def ceiling(pairs, **roles: str) -> Presentation:
    """A ceiling over the small grammar."""
    return present(pairs, rows_for(**roles))


# ── the records ───────────────────────────────────────────────────────


def test_a_row_is_its_field_tuple() -> None:
    """A spine record — read by name or by index, no accessors."""
    row = Row("heading", IrAddress(), IrSpan(0, 3), Rows())
    assert tuple(row) == ("heading", IrAddress(), IrSpan(0, 3), Rows())
    assert row.span.of("abc") == "abc"


def test_a_row_carries_no_geometry() -> None:
    """The B3 line, pinned: nothing here knows about a screen."""
    assert set(Row._fields) == {"role", "address", "span", "parts"}


def test_draw_lifts_a_plain_role_to_a_leaf() -> None:
    """One field, two ways to spell it — and one of them is a convenience."""
    assert Draw("heading") == Draw(IrStr("heading"))
    assert isinstance(Draw("heading").role, IrStr)


def test_draw_outside_a_ceiling_refuses_with_words() -> None:
    """A body needs the walk's own cursor; anything else is a misuse."""
    with pytest.raises(UnsupportedConstructError, match="ceiling's own cursor"):
        Draw("x").eval(IrStr("not a cursor"), IrStr("focus"), ())


# ── drawing ───────────────────────────────────────────────────────────


def test_a_ceiling_draws_every_occurrence_once(pairs) -> None:
    """One row per occurrence, nested where the occurrence nests."""
    ceil = ceiling(pairs, pair="entry", key="name", value="number")
    rows = ceil.apply(pairs.parse("ab=12"))
    assert len(rows) == 1
    assert rows[0].role == "entry"
    assert [(part.role, tuple(part.span)) for part in rows[0].parts] == [
        ("name", (0, 2)),
        ("number", (3, 5)),
    ]


def test_the_spans_are_the_documents_own(pairs) -> None:
    """A row slices back to exactly the text its occurrence spelled."""
    text = "ab=12"
    ceil = ceiling(pairs, pair="entry", key="name", value="number")
    rows = ceil.apply(pairs.parse(text))
    assert rows[0].span.of(text) == text
    assert [part.span.of(text) for part in rows[0].parts] == ["ab", "12"]


def test_the_address_is_the_emissions_own(pairs) -> None:
    """Shared leaves: the row's address resolves against the same model."""
    model = pairs.parse("ab=12")
    ceil = ceiling(pairs, pair="entry", key="name", value="number")
    for row in ceil.apply(model)[0].parts:
        assert model.occurrence(row.address) is not None


def test_a_role_can_be_computed_by_algebra(pairs) -> None:
    """A body is ordinary IR algebra — one rule, two roles.

    ``IrCond`` over the focus's own length draws a short key differently from
    a long one, which is the whole reason a row is a BODY and not a string.
    """
    rows = IrMap(
        IrTuple(IrStr("pair"), Draw("entry")),
        IrTuple(
            IrStr("key"),
            Draw(IrCond(IrLen(), IrStr("name"), IrStr("empty"))),
        ),
        IrTuple(IrStr("value"), Draw("number")),
    )
    ceil = present(pairs, rows)
    assert ceil.apply(pairs.parse("ab=12"))[0].parts[0].role == "name"


def test_a_body_that_builds_no_row_refuses(pairs) -> None:
    """The product must land in row space — the completeness idea, per body."""
    rows = IrMap(
        IrTuple(IrStr("pair"), Draw("entry")),
        IrTuple(IrStr("key"), IrStr("not a row")),
        IrTuple(IrStr("value"), Draw("number")),
    )
    with pytest.raises(UnsupportedConstructError, match="must be rows"):
        present(pairs, rows).apply(pairs.parse("ab=12"))


# ── the gates and the bake ────────────────────────────────────────────


def test_membership_refuses_a_row_naming_no_rule(pairs) -> None:
    """A ceiling cannot claim a rule the grammar never had."""
    with pytest.raises(UnsupportedConstructError, match="name no drawable rule"):
        ceiling(pairs, pair="entry", key="name", value="number", nope="x")


def test_completeness_refuses_a_hole(pairs) -> None:
    """A partial ceiling is a refused offer, and the hole is named."""
    with pytest.raises(UnsupportedConstructError, match="hole") as caught:
        ceiling(pairs, pair="entry", key="name")
    assert "value" in str(caught.value)


def test_the_bake_keeps_the_authored_table(pairs) -> None:
    """What travels is what was authored, not the baked class map."""
    table = rows_for(pair="entry", key="name", value="number")
    ceil = present(pairs, table)
    assert ceil.rows == table
    assert isinstance(ceil.bodies, IrTypeMap)


def test_the_baked_table_is_keyed_by_class(pairs) -> None:
    """Baked means resolved: a row's key is a synthesized class, not a name."""
    ceil = ceiling(pairs, pair="entry", key="name", value="number")
    assert all(isinstance(key, type) for key in ceil.bodies.keys())
    assert set(ceil.bodies.keys()) <= set(pairs.classes.values())
