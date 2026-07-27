"""The reader is lexic-free — by its SOURCE, and by a fresh interpreter.

Stated precisely, because the obvious phrasing is false: the module as it sits in
the tree is *not* lexic-free to import. It lives under ``lexic.compile``, so
importing it by path runs the package root and then ``lexic.compile.__init__``,
which is the seam onto the engine. What is lexic-free is the reader's SOURCE, and
that is the form an artefact carries — the sidecar emitted beside it, which is
what lets an artefact be read with no lexic installed.
"""

from __future__ import annotations

import ast as pyast
import subprocess
import sys

import pytest

from lexic.compile import compile_text
from lexic.compile.payload import project, reader
from tests.paths import PROJECT_ROOT

SOURCE = PROJECT_ROOT / "src" / "lexic" / "compile" / "payload" / "reader.py"


def test_the_reader_source_imports_no_lexic() -> None:
    """Read from its AST: not one import names the package it lives in."""
    tree = pyast.parse(SOURCE.read_text(encoding="utf-8"))
    modules = {
        alias.name
        for node in pyast.walk(tree)
        if isinstance(node, pyast.Import)
        for alias in node.names
    } | {
        node.module
        for node in pyast.walk(tree)
        if isinstance(node, pyast.ImportFrom) and node.module
    }
    assert not [m for m in modules if m.split(".")[0] == "lexic"], sorted(modules)


def test_an_inlined_reader_decodes_a_payload_with_zero_lexic_modules() -> None:
    """The cycle the property defends: inline the source, decode, in a child.

    In this process every lexic module is resident, so the question cannot be
    asked here at all — and importing the reader by path would answer it wrongly,
    because that runs the compile seam.
    """
    payload = project(({"a": [1, 2]}, "x", 3.5, None))
    script = (
        SOURCE.read_text(encoding="utf-8") + "\nimport sys\n"
        f"VALUE = decode({payload.tables!r}, {{}},"
        f" ({payload.digest()!r}, {payload.shape()!r}))\n"
        "assert VALUE == ({'a': [1, 2]}, 'x', 3.5, None), VALUE\n"
        "print(len([m for m in sys.modules if m.startswith('lexic')]))\n"
    )
    got = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src")},
    )
    assert got.stdout.strip() == "0"


def test_child_slots_covers_every_kind() -> None:
    """The arity table and the decoder table are the same length, or a kind lies."""
    assert len(reader.CHILD_SLOTS) == len(reader.DECODE)


def test_an_empty_table_refuses_rather_than_indexing_off_the_end() -> None:
    """``built[-1]`` on nothing is an IndexError; the refusal says what happened."""
    with pytest.raises(ValueError, match="empty"):
        reader.decode((("<plain>",), ("",), (), ()), {})


def test_decode_refuses_a_symbol_that_came_from_another_module() -> None:
    """The name still resolves — to a class the payload was never built from.

    ``shape_of`` reads 0 for a class carrying no rule, so this is the ONLY
    provenance such a symbol has, and without it the value is rebuilt out of the
    wrong class in silence.
    """
    payload = project((type("Thing", (str,), {"__module__": "vocab_one"})("x"),))
    other = type("Thing", (str,), {"__module__": "vocab_two"})
    with pytest.raises(ValueError, match="another module"):
        reader.decode(
            payload.tables, {"Thing": other}, (payload.digest(), payload.shape())
        )


def test_decode_allows_a_generated_class_to_have_moved_module() -> None:
    """A generated class's module MOVES, legitimately, and its grammar does not.

    A value parsed with runtime classes is read back against the twin, which
    reports its own file — so the origin check must not apply where the rules
    already answer the question.
    """
    shape = 0x5EED
    payload = project(
        (type("Node", (str,), {"__module__": "generated.x1", "__shape__": shape})("v"),)
    )
    twin = type("Node", (str,), {"__module__": "twin_pkg.node", "__shape__": shape})
    got = reader.decode(
        payload.tables, {"Node": twin}, (payload.digest(), payload.shape())
    )
    assert got[0].__class__ is twin  # the exact class, not a subclass


NARROW_V1 = "root ::= item\nitem ::= num | word\nnum ::= [0-9]+\nword ::= [a-z]+\n"
NARROW_V2 = "root ::= item\nitem ::= word | punct\nnum ::= [0-9]+\nword ::= [a-z]+\npunct ::= [.]\n"


def test_a_narrowed_alternation_is_caught_though_no_named_rule_moved() -> None:
    """The hole a per-rule digest cannot see.

    An alternation is a pass-through — the fold hands its matched arm's model
    straight up — so it never materialises in a value and is never a named
    symbol. Narrow one and every rule the payload NAMES is byte-identical,
    while the document the decoded value re-emits no longer parses. The
    closure moves where the bare rule does not.
    """
    v1, v2 = compile_text(NARROW_V1), compile_text(NARROW_V2)
    payload = project(v1.parse("42"))
    named = list(payload.types[1:])
    assert all(
        repr(v1.classes[n].__grammar__) == repr(v2.classes[n].__grammar__)
        for n in named
    ), "the premise: no NAMED rule moved"
    supplied = {n: v2.classes[n] for n in named}
    with pytest.raises(ValueError, match="shape mismatch"):
        reader.decode(payload.tables, supplied, (payload.digest(), payload.shape()))


def test_a_sub_model_legal_under_both_grammars_still_reads() -> None:
    """The false positive the closure exists to avoid.

    A lone ``Num`` is a legal ``Num`` under both grammars and re-emits the same
    text, so refusing it would be wrong — which is what a whole-grammar digest
    would do, since the grammar around it did change.
    """
    v1, v2 = compile_text(NARROW_V1), compile_text(NARROW_V2)
    payload = project(v1.classes["Num"]("42"))
    supplied = {n: v2.classes[n] for n in payload.types[1:]}
    got = reader.decode(payload.tables, supplied, (payload.digest(), payload.shape()))
    assert got.to_text() == "42"


def test_a_subclass_does_not_borrow_its_parents_provenance() -> None:
    """Own attribute, not inherited.

    Every generated class declares its own ``__shape__``; a caller's subclass of
    one inherits it through ``hasattr`` and would otherwise pass the shape check
    on rules that are not its own AND skip the origin check that covers a class
    carrying no grammar of its own.
    """
    num = compile_text(NARROW_V1).classes["Num"]
    mine = type("Mine", (num,), {"__module__": "my_vocab"})
    assert hasattr(mine, "__shape__")  # inherited — which is why hasattr is wrong
    payload = project((mine("42"),))
    moved = type("Mine", (num,), {"__module__": "somewhere_else"})
    with pytest.raises(ValueError, match="another module"):
        reader.decode(
            payload.tables, {"Mine": moved}, (payload.digest(), payload.shape())
        )


@pytest.mark.parametrize("bad", [-1, 1 << 64, "not an int", True])
def test_a_declared_shape_that_is_not_a_digest_is_refused_by_name(bad: object) -> None:
    """A clear refusal, not an ``OverflowError`` from inside the digest.

    ``int(shape).to_bytes(8, ...)`` raises on a negative, an over-wide or a
    non-numeric value — three different exceptions, none naming the class or
    saying what is wrong with it.
    """
    cls = type("Thing", (str,), {"__shape__": bad})
    with pytest.raises(ValueError, match="not a 64-bit digest"):
        reader.shape_of(("<plain>", "Thing"), {"Thing": cls})


def _artefact_tables():
    """A real compiled document, its tables and its symbols."""
    compiled = compile_text(NARROW_V1)
    payload = project(compiled.parse("42"))
    return payload, {n: compiled.classes[n] for n in payload.symbols}


def test_navigating_to_the_root_is_the_whole_document() -> None:
    """``at`` is not a different reader — the root IS the document."""
    payload, symbols = _artefact_tables()
    root = len(reader.offsets(payload.tables[3])) - 1
    assert repr(reader.subtree(payload.tables, symbols, root)) == repr(
        reader.decode(payload.tables, symbols)
    )


def test_navigating_to_a_child_agrees_with_the_full_decode() -> None:
    """A subtree materialised alone is the same value it is inside the whole."""
    payload, symbols = _artefact_tables()
    whole = reader.decode(payload.tables, symbols)
    root = len(reader.offsets(payload.tables[3])) - 1
    kids = reader.children(payload.tables, root)
    assert kids
    assert repr(reader.subtree(payload.tables, symbols, kids[0])) == repr(whole[0])


def test_a_subtree_builds_only_what_it_reaches() -> None:
    """The claim is proportionality, so what it reaches is the measurable part.

    Every child index points at an EARLIER record, which is what makes a
    subtree a closed set — and what makes the cost of one its own rather than
    the document's.
    """
    payload, _ = _artefact_tables()
    starts = reader.offsets(payload.tables[3])
    assert len(reader.reaches(payload.tables, starts, 0)) == 1  # a leaf
    assert len(reader.reaches(payload.tables, starts, len(starts) - 1)) == len(starts)


def test_navigating_past_the_table_refuses() -> None:
    """An index that names no record is said plainly, not indexed into."""
    payload, symbols = _artefact_tables()
    with pytest.raises(ValueError, match="is not in a table of"):
        reader.subtree(payload.tables, symbols, 10_000)
