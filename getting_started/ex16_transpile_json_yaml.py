"""Transpile a DOCUMENT between formats — json to yaml, on the model plane.

ex04 transpiles a GRAMMAR between notations. This transpiles what a grammar
READ: a json document becomes a yaml document, and the whole mechanism is

    text_A ──A.parse──► A-models ──T──► B-models ──.to_text()──► text_B

Only ``T`` is authored — and T is DATA, whole: a table of per-rule bodies in
the grammars' own vocabulary, with not one function or class of this file's
own in it. Rows are keyed by json's RULE NAMES; ``Make`` builds yaml's
models by name; ``Spelled`` carries a scalar's exact source spelling (floats
need no float type; ``true`` and ``1`` are different rules; duplicate keys
survive in order); ``Flat``/``Split`` read and grow the hoisted lists; the
stated domain refuses through ``IrRaise`` with lexic's own exception.
:func:`lexic.compile.transpile` bakes the table against the two compiled
grammars and gates every run — completeness, membership, fidelity.

Run::

    uv run python -m getting_started.ex16_transpile_json_yaml
"""

from __future__ import annotations

from pathlib import Path

from lexic import compile_from_path, compile_text
from lexic.compile import Flat, Is, Make, Spelled, Split, transpile
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrArg,
    IrChild,
    IrCond,
    IrEach,
    IrField,
    IrLiteral,
    IrMap,
    IrPipe,
    IrRaise,
    IrRuleRef,
    IrThis,
    IrTuple,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_GRAMMAR = REPO_ROOT / "resources" / "ground_truth" / "json.gbnf"

# The TARGET language, written before the transform: a yaml subset — a
# block map of scalars, flow sequences and flow maps.
YAML_GRAMMAR = r"""doc ::= entry*
entry ::= fent "\n"
key ::= "\"" (("\\" ("u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] | ["\\/bfnrt])) | [^"\\\n])* "\""
value ::= string | number | boolean | nullv | flowseq | flowmap
string ::= "\"" (("\\" ("u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] | ["\\/bfnrt])) | [^"\\\n])* "\""
number ::= "-"? [0-9]+ ("." [0-9]+)? (("e" | "E") ("+" | "-")? [0-9]+)?
boolean ::= "true" | "false"
nullv ::= "null"
flowseq ::= "[" avals? "]"
avals ::= value (", " value)*
flowmap ::= "{" fents? "}"
fents ::= fent (", " fent)*
fent ::= key ": " value
"""

DOC = (
    '{"name": "lexic", "version": 1.5, "features": ["typed", "lossless"], '
    '"meta": {"wip": null, "fast": true}, "my key": "a: b"}'
)

# ── T, whole — pure data, in the two grammars' own vocabulary ───────────

_ENTRIES = IrPipe(
    IrChild("fents"), IrPipe(Split(), IrEach(Make("entry", IrTuple(IrThis()))))
)
"""A flow map's entries, re-spelled as the block map's lines."""

RULES = IrMap(
    IrTuple(IrRuleRef("string"), Make("string", IrTuple(Spelled()))),
    IrTuple(IrRuleRef("number"), Make("number", IrTuple(Spelled()))),
    IrTuple(IrRuleRef("true"), Make("boolean", IrTuple(IrLiteral("true")))),
    IrTuple(IrRuleRef("false"), Make("boolean", IrTuple(IrLiteral("false")))),
    IrTuple(IrRuleRef("null"), Make("nullv", IrTuple(IrLiteral("null")))),
    IrTuple(
        IrRuleRef("member"),
        Make(
            "fent",
            IrTuple(Make("key", IrTuple(IrPipe(IrArg(0), IrField("value")))), IrArg(2)),
        ),
    ),
    IrTuple(IrRuleRef("object-item"), IrArg(1)),
    IrTuple(IrRuleRef("object-item2"), Make("fents", Flat())),
    IrTuple(IrRuleRef("object"), Make("flowmap", IrTuple(IrArg(1)))),
    IrTuple(IrRuleRef("array-item"), IrArg(1)),
    IrTuple(IrRuleRef("array-item2"), Make("avals", Flat())),
    IrTuple(IrRuleRef("array"), Make("flowseq", IrTuple(IrArg(1)))),
    IrTuple(
        IrRuleRef("json-text"),
        IrPipe(
            IrArg(1),
            IrCond(
                test=Is("flowmap"),
                then_op=Make("doc", IrTuple(_ENTRIES)),
                else_op=IrRaise(
                    message="transpile: a top-level {node_type} has no "
                    "spelling here — this yaml subset's documents are maps"
                ),
            ),
        ),
    ),
)
"""The whole transform. No class objects, no functions — it would travel
through the IR notation like a grammar or a reducer does."""


def main() -> None:
    """Compile both grammars, bake the table, run it — lexic gates the rest."""
    to_yaml = transpile(
        compile_from_path(JSON_GRAMMAR),
        compile_text(YAML_GRAMMAR, cache_key="ex16-yaml"),
        RULES,
    )

    yaml_text = to_yaml.run(DOC)
    print("=== json in ===")
    print(DOC)
    print("=== yaml out ===")
    print(yaml_text)
    print("witness: run() gated completeness · membership · fidelity")

    # The stated domain refuses with words — lexic's own exception, the
    # refusing value's own name in them.
    try:
        to_yaml.run("[1, 2, 3]")
        raise AssertionError("expected a refusal")
    except UnsupportedConstructError as refusal:
        print(f"refused, with words: {refusal}")


if __name__ == "__main__":
    main()
