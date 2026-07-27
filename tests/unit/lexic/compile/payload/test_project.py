"""The projection: a parsed value onto three flat literals, and back.

Each test names the defect it stands over — every one of them was found by an
adversarial pass or by the review round, and each decoded to a plausible wrong
value rather than raising.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from lexic.compile import compile_from_path
from lexic.compile.payload import Payload, project, project_checked, reader
from lexic.exceptions import UnsupportedConstructError
from lexic.generate import generate
from lexic.ir import IR_DEFAULT, IrInt, IrLambda, IrMap, IrNone, IrStr, IrTuple
from tests.paths import GROUND_TRUTH

SPINE = {
    "IrStr": IrStr,
    "IrInt": IrInt,
    "IrTuple": IrTuple,
    "IrMap": IrMap,
    "IrNone": IrNone,
    "IR_DEFAULT": IR_DEFAULT,
}


def rt(value: object, symbols: dict | None = None) -> Any:
    """Project and read back, digest-checked."""
    payload = project(value)
    return reader.decode(
        payload.tables, symbols or {}, (payload.digest(), payload.shape())
    )


@pytest.mark.parametrize(
    "value",
    [
        (1, "a", [2], {"k": 3}),
        (True, False, None),
        (0.1, -0.0, float("inf")),
        (b"\x00\xff hi",),
        ({1, 2, 3}, frozenset({4})),
        (10**30, -(10**30)),
        {"a": [1.5, 2.5], "b": {"c": (1, 2)}},
        ((), [], {}, set(), frozenset()),
    ],
    ids=["mixed", "bools", "floats", "bytes", "sets", "bigints", "nested", "empties"],
)
def test_the_payload_vocabulary_round_trips(value: object) -> None:
    """The vocabulary is WIDE — JSON numbers are floats and C literals are floats."""
    assert rt(value) == value


def test_a_spine_value_round_trips() -> None:
    """The `ir` target: symbols name spine nodes."""
    value = IrTuple(IrStr("a"), IrMap(IrTuple(IrStr("k"), IrInt(1))))
    assert rt(value, SPINE) == value


def test_a_bare_name_singleton_is_interned_by_its_value() -> None:
    """``IrNone`` is what an importer imports; ``IrNoneType`` is not."""
    payload = project(IrTuple(IrStr("a"), IrNone))
    assert "IrNone" in payload.symbols
    assert "IrNoneType" not in payload.symbols
    assert rt(IrTuple(IrStr("a"), IrNone), SPINE) == IrTuple(IrStr("a"), IrNone)


def test_a_subclass_is_recorded_not_silently_downcast() -> None:
    """``class S(str)`` decoded to bare ``str`` with ``==`` AND ``repr`` passing."""

    class S(str):
        """A caller's own string type — the shape §4's outer ring is made of."""

    # The EXACT class, read off the value: `isinstance` passes for the bare
    # `str` this used to decode to, which is the defect, so it cannot be the
    # check.
    assert rt((S("hi"),), {"S": S})[0].__class__ is S


def test_a_missing_symbol_is_loud() -> None:
    """Recording the subclass turns a silent downcast into a refusal."""

    class S(str):
        """A caller's own string type, whose symbol the reader is not given."""

    with pytest.raises(KeyError):
        rt((S("hi"),))


def test_aliasing_survives_in_both_directions() -> None:
    """Sharing is keyed on IDENTITY: mutability answered both ways wrongly."""
    shared = [1, 2]
    aliased = rt((shared, shared))
    assert aliased[0] is aliased[1]
    distinct = rt(([1, 2], [1, 2]))
    assert distinct[0] is not distinct[1]
    distinct[0].append(9)
    assert distinct == ([1, 2, 9], [1, 2])


def test_synthesised_children_keep_their_values() -> None:
    """The memo holds a keepalive — an id means nothing once its object is gone.

    A container that builds its children on iteration frees them when its frame
    pops, and CPython hands the next one the same id: 3 998 of 4 000 elements
    were silently wrong without this.
    """

    class Fresh(tuple):
        """A container whose children do not exist until they are asked for."""

        def __iter__(self):
            return iter([(x,) for x in tuple.__iter__(self)])

    source = tuple(Fresh((i,)) for i in range(200))
    back = rt(source, {"Fresh": Fresh})
    # Read with `__getitem__`, not by iterating: `Fresh.__iter__` synthesises on
    # every pass, including this one, so iterating the decoded value wraps it
    # again and measures the fixture rather than the encoder.
    assert [x[0] for x in back] == [(i,) for i in range(200)]
    assert len({id(x) for x in back}) == 200, "the records collapsed onto one"


def test_a_cycle_refuses() -> None:
    """A value that contains itself has no finite encoding."""
    loop: list = [1]
    loop.append(loop)
    with pytest.raises(UnsupportedConstructError, match="cycle"):
        project(loop)


def test_a_callable_refuses() -> None:
    """Code is not data."""
    with pytest.raises(UnsupportedConstructError, match="code is not data"):
        project(IrLambda(lambda d, n, nc: n))


def test_the_sentinel_cannot_also_be_a_symbol() -> None:
    """A class actually called ``<plain>`` decoded to a plain ``str``, silently."""
    plain = type("<plain>", (str,), {})
    with pytest.raises(UnsupportedConstructError, match="sentinel"):
        project((plain("x"),))


def test_two_grammars_sharing_a_class_name_do_not_refuse() -> None:
    """The projection does not police a name — it records where each came from.

    One module exports one ``Root``, so a genuine clash is unrepresentable
    rather than undetected; the origin string makes it recoverable by
    inspection instead of invisible.
    """
    first = type("Root", (str,), {"__module__": "generated.a_1111"})
    second = type("Root", (str,), {"__module__": "generated.b_2222"})
    payload = project((first("x"), second("y")))
    assert payload.symbols == ("Root", "Root")
    assert payload.origins[1:] == ("generated.a_1111", "generated.b_2222")


def test_the_digest_refuses_an_altered_table() -> None:
    """Five of fifteen single-int corruptions had decoded to plausible values."""
    payload = project(({"a": 1}, [2, 3], "x"))
    nodes = list(payload.nodes)
    nodes[4] -= 1
    with pytest.raises(ValueError, match="digest mismatch"):
        reader.decode(
            (payload.types, payload.origins, payload.strs, tuple(nodes)),
            {},
            (payload.digest(), payload.shape()),
        )


def test_the_digest_is_injective_over_the_joined_text() -> None:
    """``('a','b')`` and ``('a\\x00b')`` are different tables."""
    one = reader.digest((("<plain>", "a", "b"), ("", "", ""), (), (0, 5, 0)))
    two = reader.digest((("<plain>", "a\x00b"), ("", ""), (), (0, 5, 0)))
    assert one != two


def test_the_digest_survives_a_big_integer() -> None:
    """``array('q')`` raised on any int >= 2**63 — an ordinary JSON literal."""
    assert project((10**30,)).digest()


def test_structural_checks_catch_a_forward_reference() -> None:
    """Free, and they catch what a partial write looks like."""
    with pytest.raises(ValueError, match="not an earlier record"):
        reader.decode((("<plain>",), ("",), (), (0, reader.K_SEQ, 1, 99)), {})


def test_an_unknown_kind_refuses() -> None:
    """The kind space is closed; an index past the table is the raising default."""
    with pytest.raises(ValueError, match="unknown record kind"):
        reader.decode((("<plain>",), ("",), (), (0, 99, 0)), {})


def test_the_export_gate_is_a_fixpoint_not_an_equality() -> None:
    """``==`` refuses ``nan``, which round-trips perfectly; the fixpoint does not."""
    assert project_checked((float("nan"),))


def test_the_export_gate_runs_where_repr_cannot() -> None:
    """``repr`` dies at 498 frames, on the very shape that exposed the gate's absence."""
    deep = IrTuple()
    for _ in range(600):
        deep = IrTuple(deep)
    assert project_checked(deep)


def test_a_payload_is_its_tables() -> None:
    """``Payload`` is a record of the four literals an artefact writes."""
    payload = project((1, 2))
    assert isinstance(payload, Payload)
    assert payload.types[0] == "<plain>"
    assert len(payload.types) == len(payload.origins)


# ── the corpus, verified by USE ───────────────────────────────────────────


@pytest.mark.parametrize("stem", ["json.gbnf", "arithmetic.gbnf", "list.gbnf"])
def test_a_parsed_document_survives_the_projection(stem: str) -> None:
    """The `classes` target, gated and digest-checked, verified by ``to_text()``.

    The one target that can be verified against its DOCUMENT rather than against
    the encoder — for `ir` and `plain` the fixpoint is all there is.
    """
    compiled = compile_from_path(GROUND_TRUTH / stem)
    rules = {str(rule.name): rule for rule in compiled.grammar.rules}
    start = str(compiled.grammar.rules[0].name)
    text = generate(start, rules, rng=random.Random(3))
    model = compiled.parse(text)
    payload = project_checked(model)
    back = reader.decode(
        payload.tables, dict(compiled.classes), (payload.digest(), payload.shape())
    )
    assert back.to_text() == text
