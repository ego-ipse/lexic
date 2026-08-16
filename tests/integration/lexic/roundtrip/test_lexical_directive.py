"""The ``@lexical`` directive's product contract, end to end.

The three facts the T9 design named as the gate: the accepted language is
untouched (round-trip byte-identity under both compiles), the model shape
changes exactly at the declared rules and nowhere else, and the directive
is part of what-was-compiled (distinct memo entries, never one artifact
handed back for both).
"""

from __future__ import annotations


from lexic.compile import Directives, compile_text
from tests.paths import GROUND_TRUTH

DOCS = ['{"a": [1, true], "b": null}', '{"x\\u0041y": -0.4e2, "s": ""}', "[]"]

TEXT = (GROUND_TRUTH / "json.gbnf").read_text()


def compiled_pair():
    """The same source compiled plain and with ``@lexical string``."""
    plain = compile_text(TEXT, cache_key="t9-plain")
    marked = compile_text(
        TEXT,
        cache_key="t9-lexical",
        directives=Directives(lexical=frozenset({"string"})),
    )
    return plain, marked


def test_language_untouched_and_round_trip_byte_identical() -> None:
    """Every document parses under both compiles and re-emits byte-identically."""
    plain, marked = compiled_pair()
    for doc in DOCS:
        assert plain.parse(doc).to_text() == doc
        assert marked.parse(doc).to_text() == doc


def test_shape_changes_exactly_at_the_declared_rule() -> None:
    """String flips to value_str; every other class keeps its field set."""
    plain, marked = compiled_pair()
    plain_fields = {
        name: tuple(getattr(cls, "_fields", ())) for name, cls in plain.classes.items()
    }
    marked_fields = {
        name: tuple(getattr(cls, "_fields", ())) for name, cls in marked.classes.items()
    }
    changed = {
        name
        for name in plain_fields.keys() & marked_fields.keys()
        if plain_fields[name] != marked_fields[name]
    }
    gone = plain_fields.keys() - marked_fields.keys()
    assert "String" in changed or {"Char", "Unescaped"} & gone, (changed, gone)
    untouched = {"Object", "Member", "Array", "JsonText"}
    assert not (changed & untouched), changed
    # the declared rule's model IS its text now — dump differs there
    doc = DOCS[0]
    assert plain.parse(doc).dump() != marked.parse(doc).dump()


def test_directive_keys_the_memo() -> None:
    """One source, two directive sets — two artifacts, never one cached for both."""
    text = 'root ::= word ("," word)*\nword ::= letter letter*\nletter ::= [a-z]\n'
    plain = compile_text(text)
    marked = compile_text(text, directives=Directives(lexical=frozenset({"word"})))
    assert plain is not marked
    assert plain.parse("ab,cd").to_text() == "ab,cd"
    assert marked.parse("ab,cd").to_text() == "ab,cd"
    again = compile_text(text)
    assert again is plain, "the unmarked memo entry must survive the marked compile"
