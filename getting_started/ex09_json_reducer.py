"""Reduce a document straight to typed IR values — no model classes at all.

A ``Reducer`` is something ANY grammar can carry, not just the flavours'
self-grammars: ``grammars/json.py`` ships the RFC 8259 grammar authored
directly as IR plus its reduction kit, and ``CompiledGrammar.reduce`` folds a
document to typed IR values — objects become ``IrMap``, arrays
``IrTuple``, strings decoded ``IrStr`` (escapes and surrogate pairs decode
through the ``IrUtf`` encoding), integers ``IrInt``, ``null`` → ``IrNone``.

Compare ex03, which parses the same language into MODEL classes that
round-trip char-exact: reduce when you want the VALUES, parse when you want
the DOCUMENT.

Run::

    uv run python -m getting_started.ex09_json_reducer
"""

from __future__ import annotations

from lexic.compile import compile_ast
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrInt, IrMap, IrNone

DOC = '{"name": "lexic", "stars": 3, "tags": ["grammar", "\\u00e9lan"], "wip": null}'


def main() -> None:
    """Reduce a JSON document to IR values and read them off natively."""
    # A reducer folds to whatever its bodies produce, so reduce returns
    # IrSelf — and a JSON document really can be any JSON value. "This one is
    # an object" is a fact about DOC, not about the API, so the caller states
    # it: ``ensure`` is the spine's boundary narrow (the class-level sibling
    # of ``bind``), and unlike an assert it is a real check that raises.
    value = IrMap.ensure(
        compile_ast(JSON_GRAMMAR).reduce(DOC, JSON_REDUCER), "document"
    )
    print("Reduced:", value)

    # IR values ARE their payloads: IrStr is a str, IrInt an int, IrMap a
    # mapping — read them with plain Python (plain-str keys hash-match IrStr).
    assert value["name"] == "lexic"
    assert value["stars"] == 3
    assert IrInt.ensure(value["stars"]) == 3  # a JSON number IS an IrInt
    tags = value["tags"]
    print("Tags:   ", [str(t) for t in tags])
    assert [str(t) for t in tags] == ["grammar", "élan"]  # \\u00e9 decoded
    # Absence is the IrNone sentinel, never Python None.
    assert value["wip"] is IrNone


if __name__ == "__main__":
    main()
