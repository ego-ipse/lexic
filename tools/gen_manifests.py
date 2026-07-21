"""Generate the flavour manifests (`grammars/*.flavour.ir`).

A manifest is one IR-constructor-notation expression — an ``IrMap`` of the seven
sections :func:`lexic.compile.notation.loader.load_flavour` consumes. This dev-time tool
repr-generates them (the demo_05 licence): the ``grammar``/``reductions``/
``actions`` sections come straight off the authored singletons via :func:`repr`
(a superset of the notation), and the ``escapes`` section is spelled as the five
IR dyad tables (ruling D1). It NEVER reprs a ``Reducer`` or a noise map —
``IrLambda.__repr__`` can raise, and a manifest carries no noise section (the
loader derives noise from the self-grammar's ``semantic=False`` flags).

All three manifests are generated from their shipped singletons
(:mod:`lexic.grammars.gbnf` / :mod:`abnf` / :mod:`ebnf`).

Run: ``uv run python tools/gen_manifests.py`` (writes into ``src/lexic/grammars/``
and the EBNF ground-truth corpus ``arithmetic.ebnf`` / ``json.ebnf``).
"""

from __future__ import annotations

from pathlib import Path

from lexic.grammars.abnf import (
    ABNF_ACTIONS,
    ABNF_ESCAPES,
    ABNF_GRAMMAR,
    ABNF_REDUCTIONS,
)
from lexic.grammars.ebnf import (
    EBNF_ACTIONS,
    EBNF_ESCAPES,
    EBNF_FLAVOUR,
    EBNF_GRAMMAR,
    EBNF_REDUCTIONS,
)
from lexic.grammars.gbnf import (
    GBNF_ACTIONS,
    GBNF_ESCAPES,
    GBNF_FLAVOUR,
    GBNF_GRAMMAR,
    GBNF_REDUCTIONS,
)
from lexic.ir.base import IrInt, IrStr, IrTuple
from lexic.ir.escapes import EscapeCodec
from lexic.ir.mapping import IrMap, IrTypeMap
from lexic.ir.nodes import (
    IrAst,
)

# ── section spelling ──────────────────────────────────────────────────────


def escapes_as_ir(codec: EscapeCodec) -> IrMap:
    """The five codec tables spelled as IR dyads (ruling D1).

    :param codec: The escape codec to serialize.
    :returns: The ``escapes`` section ``IrMap`` of the five named tables.
    """
    return IrMap(
        IrTuple(
            IrStr("short"),
            IrMap(
                *(IrTuple(IrStr(k), IrStr(v)) for k, v in codec.SHORT_ESCAPES.items())
            ),
        ),
        IrTuple(
            IrStr("hex"),
            IrTuple(*(IrTuple(IrStr(t), IrInt(n)) for t, n in codec.HEX_ESCAPES)),
        ),
        IrTuple(
            IrStr("class-short"),
            IrMap(*(IrTuple(IrInt(k), IrStr(v)) for k, v in codec.CLASS_SHORT.items())),
        ),
        IrTuple(
            IrStr("class-meta"),
            IrTuple(*(IrStr(c) for c in sorted(codec.CLASS_META))),
        ),
        IrTuple(
            IrStr("quote-safe"),
            IrTuple(*(IrTuple(IrInt(a), IrInt(b)) for a, b in codec.QUOTE_SAFE)),
        ),
    )


def format_manifest(
    name: str,
    extensions: tuple[str, ...],
    line_comment: str,
    codec: EscapeCodec,
    grammar: IrAst,
    reductions: IrMap,
    actions: IrTypeMap,
) -> str:
    """One manifest as readable notation text — each section on its own line.

    Section values are ``repr``'d (a superset of the notation); the surrounding
    ``IrMap(...)`` is laid out by hand so the file is greppable and hand-editable.
    """
    sections = [
        ("name", repr(IrStr(name))),
        ("extensions", repr(IrTuple(*(IrStr(e) for e in extensions)))),
        ("line-comment", repr(IrStr(line_comment))),
        ("escapes", repr(escapes_as_ir(codec))),
        ("grammar", repr(grammar)),
        ("reductions", repr(reductions)),
        ("actions", repr(actions)),
    ]
    lines = [f"    IrTuple(IrStr({key!r}), {value})" for key, value in sections]
    return "IrMap(\n" + ",\n".join(lines) + "\n)\n"


ARITHMETIC_EBNF = """\
(* arithmetic — an EBNF-subset demo flavour; parses to the same canonical IR
   as arithmetic.gbnf *)
root  = ( expr, "=", ws, term, "\\n" )+ ;
expr  = term, { ("-" | "+" | "*" | "/"), term } ;
term  = ident | num | ( "(", ws, expr, ")", ws ) ;
ident = "a".."z", { "a".."z" | "0".."9" | "_" }, ws ;
num   = "0".."9"+, ws ;
ws    = { " " | "\\t" | "\\n" } ;
"""


# ── entry ──────────────────────────────────────────────────────────────────

_GRAMMARS = Path("src/lexic/grammars")
_GROUND_TRUTH = Path("resources/ground_truth")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path} ({len(text)} bytes)")


def main() -> None:
    """Generate the three manifests + the demo EBNF corpus grammar."""
    _write(
        _GRAMMARS / "gbnf.flavour.ir",
        format_manifest(
            "gbnf",
            (".gbnf",),
            "#",
            GBNF_ESCAPES,
            GBNF_GRAMMAR,
            GBNF_REDUCTIONS,
            GBNF_ACTIONS,
        ),
    )
    _write(
        _GRAMMARS / "abnf.flavour.ir",
        format_manifest(
            "abnf",
            (".abnf",),
            ";",
            ABNF_ESCAPES,
            ABNF_GRAMMAR,
            ABNF_REDUCTIONS,
            ABNF_ACTIONS,
        ),
    )
    _write(
        _GRAMMARS / "ebnf.flavour.ir",
        format_manifest(
            "ebnf",
            (".ebnf",),
            "",
            EBNF_ESCAPES,
            EBNF_GRAMMAR,
            EBNF_REDUCTIONS,
            EBNF_ACTIONS,
        ),
    )
    _write(_GROUND_TRUTH / "arithmetic.ebnf", ARITHMETIC_EBNF)
    _write(_GROUND_TRUTH / "json.ebnf", _json_ebnf())


def _json_ebnf() -> str:
    """The json GT in EBNF — the canonical json.gbnf emitted at width 88."""
    from lexic.compile import parse_grammar
    from lexic.ir.canonical import canonicalize

    text = (_GROUND_TRUTH / "json.gbnf").read_text(encoding="utf-8")
    canonical = canonicalize(parse_grammar(text, GBNF_FLAVOUR))
    return str(EBNF_FLAVOUR.apply(canonical)) + "\n"


if __name__ == "__main__":
    main()
