"""Reduce a document straight to typed IR values — no model classes at all.

A ``Reducer`` is something ANY grammar can carry, not just the flavours'
self-grammars: ``grammars/json.py`` ships the RFC 8259 grammar authored
directly as IR plus its reduction kit, and ``parse_reduced`` folds a document
to typed IR values in one engine pass — objects become ``IrMap``, arrays
``IrTuple``, strings decoded ``IrStr`` (escapes and surrogate pairs decode
through the ``IrUtf`` encoding), integers ``IrInt``, ``null`` → ``IrNone``.

Compare ex03, which parses the same language into MODEL classes that
round-trip char-exact: reduce when you want the VALUES, parse when you want
the DOCUMENT.

Run::

    uv run python getting_started/ex09_json_reducer.py
"""

from __future__ import annotations

from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir.base import IrInt, IrNone, IrTuple
from lexic.ir.mapping import IrMap
from lexic.parsing import parse_reduced

DOC = '{"name": "lexic", "stars": 3, "tags": ["grammar", "\\u00e9lan"], "wip": null}'


def main() -> None:
    """Reduce a JSON document to IR values and read them off natively."""
    value = parse_reduced(JSON_GRAMMAR, DOC, JSON_REDUCER)
    assert isinstance(value, IrMap)
    print("Reduced:", value)

    # IR values ARE their payloads: IrStr is a str, IrInt an int, IrMap a
    # mapping — read them with plain Python (plain-str keys hash-match IrStr).
    assert value.get("name") == "lexic"
    assert value.get("stars") == 3
    tags = value.get("tags")
    assert isinstance(tags, IrTuple)  # .get returns IrSelf | None — narrow it
    print("Tags:   ", [str(t) for t in tags])
    assert [str(t) for t in tags] == ["grammar", "élan"]  # \\u00e9 decoded
    assert value.get("wip") is IrNone
    assert isinstance(value.get("stars"), IrInt)


if __name__ == "__main__":
    main()
