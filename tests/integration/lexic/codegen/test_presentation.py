"""Presentation ceilings on three languages — markdown, JSON, an ABNF one.

What this defends is that the MECHANISM is formulation-generic while a TABLE is
not. Three authored ceilings, three unrelated languages, one code path: nothing
here special-cases a grammar, and none of the three is privileged — the JSON
ceiling is written the same way the markdown one is, through the standard
pipeline, against a grammar the repo already shipped.

The tables are data, not fixtures with logic: each is a rule name to a role,
and what is asserted is the STRUCTURE the ceiling draws — the roles in document
order, the nesting, and the spans, which slice back out of the document.
"""

from __future__ import annotations

import pytest

from lexic.compile import (
    CompiledGrammar,
    Draw,
    Presentation,
    Row,
    Rows,
    compile_from_path,
    compile_text,
    load_ir,
    present,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrMap, IrStr, IrTuple, align_names
from tests.paths import GROUND_TRUTH


def table(roles: dict[str, str]) -> IrMap:
    """A ceiling as data — one rule name to one role."""
    return IrMap(*(IrTuple(IrStr(rule), Draw(role)) for rule, role in roles.items()))


MARKDOWN = table(
    {
        "document": "page",
        "heading": "heading",
        "bullet": "item",
        "paragraph": "paragraph",
        "blank": "gap",
        "level": "depth",
        "line": "text",
        "plain": "words",
        "opener": "words",
        "code": "code",
        "emphasis": "emphasis",
    }
)

JSON = table(
    {
        "json-text": "document",
        "object": "map",
        "array": "list",
        "member": "entry",
        "string": "text",
        "number": "number",
        "true": "constant",
        "false": "constant",
        "null": "constant",
        "begin-object": "open",
        "end-object": "close",
        "begin-array": "open",
        "end-array": "close",
        "name-separator": "punctuation",
        "value-separator": "punctuation",
        "quotation-mark": "punctuation",
        "decimal-point": "punctuation",
        "escape": "punctuation",
        "minus": "sign",
        "plus": "sign",
        "e": "exponent",
        "exp": "exponent",
        "frac": "fraction",
        "zero": "digit",
        "digit": "digit",
        "digit1-9": "digit",
        "hexdig": "digit",
        "unescaped": "glyph",
    }
)

ARITHMETIC = table(
    {
        "root": "formula",
        "expr": "expression",
        "term": "term",
        "op": "operator",
        "num": "number",
        "digit": "digit",
    }
)

# The same arithmetic, every rule renamed and the flavour changed with it —
# a pure rename, which is no real difference (T4c's ruling).
RENAMED_ARITHMETIC = """# @non-semantic space
calc    ::= sum
sum     ::= factor (sign factor)*
factor  ::= digits
sign    ::= "+" | "-" | "*" | "/"
digits  ::= numeral+
numeral ::= [0-9]
space   ::= " " | "\\t"
"""


def drawn(rows: Rows, depth: int = 0) -> list[tuple[int, str, int, int]]:
    """The whole drawing flattened — depth, role, and span, in document order."""
    out: list[tuple[int, str, int, int]] = []
    for row in rows:
        out.append((depth, row.role, row.span.start, row.span.end))
        out.extend(drawn(row.parts, depth + 1))
    return out


def ceiling(name: str, rows: IrMap) -> tuple[CompiledGrammar, Presentation]:
    """One ground-truth grammar and a ceiling baked against it."""
    compiled = compile_from_path(GROUND_TRUTH / name)
    return compiled, present(compiled, rows)


# ── the three demonstrations ──────────────────────────────────────────


def test_a_markdown_ceiling_draws_a_document() -> None:
    """The language whose whole point is how it draws."""
    compiled, ceil = ceiling("markdown.gbnf", MARKDOWN)
    text = "# Title\nsome *bold* text\n- one\n"
    rows = ceil.apply(compiled.parse(text))
    assert drawn(rows)[:6] == [
        (0, "page", 0, 31),
        (1, "heading", 0, 8),
        (2, "depth", 0, 1),
        (2, "text", 2, 7),
        (3, "words", 2, 7),
        (1, "paragraph", 8, 25),
    ]
    assert [row.span.of(text) for row in rows[0].parts] == [
        "# Title\n",
        "some *bold* text\n",
        "- one\n",
    ]


def test_a_markdown_ceiling_reaches_the_inline_styles() -> None:
    """Emphasis and code draw as their own roles, nested where they stand."""
    compiled, ceil = ceiling("markdown.gbnf", MARKDOWN)
    text = "a *b* and `c` here\n"
    roles = [entry[1] for entry in drawn(ceil.apply(compiled.parse(text)))]
    assert "emphasis" in roles
    assert "code" in roles


def test_a_json_ceiling_draws_a_document() -> None:
    """A different language, the same mechanism, no special case anywhere."""
    compiled, ceil = ceiling("json.gbnf", JSON)
    text = '{"a": 1}'
    flat = drawn(ceil.apply(compiled.parse(text)))
    assert flat[0] == (0, "document", 0, len(text))
    assert ("map", 0, len(text)) in [(role, a, b) for _, role, a, b in flat]
    assert "entry" in [role for _, role, _a, _b in flat]


def test_an_abnf_ceiling_draws_a_document() -> None:
    """The third ruled language, authored in ABNF rather than GBNF."""
    compiled, ceil = ceiling("arithmetic.abnf", ARITHMETIC)
    rows = ceil.apply(compiled.parse("12+3"))
    assert drawn(rows)[:4] == [
        (0, "formula", 0, 4),
        (1, "expression", 0, 4),
        (2, "term", 0, 2),
        (3, "number", 0, 2),
    ]


@pytest.mark.parametrize(
    ("name", "rows", "text"),
    (
        ("markdown.gbnf", MARKDOWN, "# T\nbody\n- x\n"),
        ("json.gbnf", JSON, '{"k": [1, true]}'),
        ("arithmetic.abnf", ARITHMETIC, "1+2*3"),
    ),
)
def test_every_span_slices_back_to_the_document(
    name: str, rows: IrMap, text: str
) -> None:
    """The spans are the document's own — a row points at real text."""
    compiled, ceil = ceiling(name, rows)
    for _depth, _role, start, end in drawn(ceil.apply(compiled.parse(text))):
        assert 0 <= start <= end <= len(text)
    assert ceil.apply(compiled.parse(text))[0].span.of(text) == text


@pytest.mark.parametrize(
    ("name", "rows", "text"),
    (
        ("markdown.gbnf", MARKDOWN, "# T\nbody\n"),
        ("json.gbnf", JSON, '{"k": 1}'),
        ("arithmetic.abnf", ARITHMETIC, "1+2"),
    ),
)
def test_a_row_is_nested_inside_the_row_that_contains_it(
    name: str, rows: IrMap, text: str
) -> None:
    """The drawing is a tree, and the tree agrees with the spans."""
    compiled, ceil = ceiling(name, rows)

    def check(row: Row) -> None:
        for part in row.parts:
            assert row.span.start <= part.span.start <= part.span.end <= row.span.end
            check(part)

    for row in ceil.apply(compiled.parse(text)):
        check(row)


# ── the gates ─────────────────────────────────────────────────────────


def test_a_row_naming_no_rule_refuses_with_words() -> None:
    """Membership: a ceiling cannot claim a rule the grammar never had."""
    compiled = compile_from_path(GROUND_TRUTH / "arithmetic.abnf")
    stray = IrMap(
        *(IrTuple(key, body) for key, body in ARITHMETIC.items()),
        IrTuple(IrStr("paragraph"), Draw("prose")),
    )
    with pytest.raises(UnsupportedConstructError, match="name no drawable rule"):
        present(compiled, stray)


def test_a_table_with_a_hole_refuses_with_the_rules_named() -> None:
    """Completeness: a partial ceiling is a refused offer, not a partial draw."""
    compiled = compile_from_path(GROUND_TRUTH / "arithmetic.abnf")
    holey = table({"root": "formula", "expr": "expression", "term": "term"})
    with pytest.raises(UnsupportedConstructError, match=r"3 hole\(s\)"):
        present(compiled, holey)


def test_the_hole_refusal_names_what_is_missing() -> None:
    """The words are actionable — which rules, not how many."""
    compiled = compile_from_path(GROUND_TRUTH / "arithmetic.abnf")
    with pytest.raises(UnsupportedConstructError) as caught:
        present(compiled, table({"root": "formula"}))
    for name in ("expr", "term", "op", "num", "digit"):
        assert name in str(caught.value)


def test_a_noise_rule_needs_no_row() -> None:
    """Structural noise draws nothing, so a ceiling is not asked about it."""
    compiled, _ = ceiling("arithmetic.abnf", ARITHMETIC)
    assert "wsp" not in {str(key) for key in ARITHMETIC.keys()}
    assert "wsp" in {str(rule.name) for rule in compiled.grammar.rules}


def test_a_helper_rule_needs_no_row_and_still_draws() -> None:
    """Binding-derived routing: declare one name, derive the rest.

    ``expr-item`` is minted by the pipeline's own hoist pass and is not a name
    anyone authored against — so it carries no row, and its occurrences draw
    under the canonical rule it was hoisted out of.
    """
    compiled, ceil = ceiling("arithmetic.abnf", ARITHMETIC)
    codegen = {str(rule.name) for rule in compiled.codegen_grammar.rules}
    canonical = {str(rule.name) for rule in compiled.grammar.rules}
    assert codegen - canonical, "the fixture no longer mints a helper rule"
    roles = [entry[1] for entry in drawn(ceil.apply(compiled.parse("1+2+3")))]
    assert roles.count("expression") > 1, "the helper's occurrences did not draw"


# ── travel: notation, and across a renaming ───────────────────────────


@pytest.mark.parametrize("rows", (MARKDOWN, JSON, ARITHMETIC))
def test_an_authored_table_travels_as_notation(rows: IrMap) -> None:
    """A ceiling is data: repr is codegen, and it loads back equal."""
    assert load_ir(repr(rows), symbols={"Draw": Draw}) == rows


def test_a_ceiling_transports_across_a_pure_renaming() -> None:
    """The alignment witness carries the table; the drawing is identical.

    The renamed twin is a different FLAVOUR as well as different names — which
    makes the point sharper: what transports is the structure, and the witness
    is what says the two structures are one.
    """
    source = compile_from_path(GROUND_TRUTH / "arithmetic.abnf")
    twin = compile_text(RENAMED_ARITHMETIC, cache_key="presentation-twin")
    alignment = align_names(source.grammar, twin.grammar)
    assert len(alignment.renamings) == 1
    moved = alignment.renamings[0].rekeyed(ARITHMETIC)
    assert {str(key) for key in moved.keys()} == {
        "calc",
        "sum",
        "factor",
        "sign",
        "digits",
        "numeral",
    }
    here = present(source, ARITHMETIC).apply(source.parse("12+3*4"))
    there = present(twin, moved).apply(twin.parse("12+3*4"))
    assert drawn(here) == drawn(there)


def test_a_table_does_not_transport_to_a_different_factoring() -> None:
    """Formulation-bound, honestly: a real difference refuses, in words."""
    json_grammar = compile_from_path(GROUND_TRUTH / "json.gbnf")
    other = compile_from_path(GROUND_TRUTH / "json_arr.gbnf")
    assert not align_names(json_grammar.grammar, other.grammar).renamings
    with pytest.raises(UnsupportedConstructError):
        present(other, JSON)


def test_the_baked_ceiling_keeps_the_table_it_was_authored_as() -> None:
    """What travels is the authored table, not the baked class map."""
    compiled, ceil = ceiling("arithmetic.abnf", ARITHMETIC)
    assert ceil.rows == ARITHMETIC
    assert ceil.grammar is compiled


def test_a_ceiling_carries_no_geometry() -> None:
    """The B3 line: a row says WHERE in the document, never where on a screen."""
    fields = set(Row._fields)
    assert fields == {"role", "address", "span", "parts"}
    assert not fields & {"x", "y", "width", "height", "column", "pixels"}


def test_the_row_address_is_the_emissions_own() -> None:
    """Shared leaves: a row and an extent name one occurrence with one record."""
    compiled, ceil = ceiling("arithmetic.abnf", ARITHMETIC)
    model = compiled.parse("1+2")
    addresses = {tuple(extent.address) for extent in model.emit_addressed().extents}
    for depth_row in ceil.apply(model):
        assert tuple(depth_row.address) in addresses
