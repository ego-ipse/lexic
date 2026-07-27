"""Generate the flavour manifests (`grammars/*.flavour.ir`).

A manifest is one IR-constructor-notation expression — an ``IrMap`` of the seven
sections :func:`lexic.compile.notation.loader.load_flavour` consumes. This dev-time tool
repr-generates them (the demo_05 licence): the ``grammar``/``reduction``/
``actions`` sections come straight off the authored singletons via :func:`repr`
(a superset of the notation), and the ``escapes`` section is spelled as the five
IR dyad tables (ruling D1). The ``reduction`` section is the flavour's whole
``Reducer`` — actions, default, noise and literal — which reprs because the
policy sentinels are real nodes rather than ``IrLambda`` closures whose repr is
lambda source.

All three manifests are generated from their shipped singletons
(:mod:`lexic.grammars.gbnf` / :mod:`abnf` / :mod:`ebnf`).

Run: ``uv run python tools/gen_manifests.py`` (writes into ``src/lexic/grammars/``
and the EBNF ground-truth corpus ``arithmetic.ebnf`` / ``json.ebnf``).
"""

from __future__ import annotations

from pathlib import Path

from lexic.compile import parse_grammar
from lexic.grammars.abnf import (
    ABNF_ACTIONS,
    ABNF_FLAVOUR,
)
from lexic.grammars.ebnf import (
    EBNF_ACTIONS,
    EBNF_FLAVOUR,
)
from lexic.grammars.gbnf import (
    GBNF_ACTIONS,
    GBNF_FLAVOUR,
)
from lexic.ir import (
    EscapeCodec,
    IrFlavour,
    IrMap,
    IrStr,
    IrTuple,
    IrTypeMap,
    canonicalize,
)

# ── section spelling ──────────────────────────────────────────────────────


def escapes_as_ir(codec: EscapeCodec) -> IrMap:
    """The five codec tables spelled as IR dyads (ruling D1).

    The codec's ``short``/``hex``/``class_short``/``quote_safe`` fields are
    already the IR-native tables, passed through verbatim; ``class-meta`` is
    re-sorted by code point for a deterministic manifest.

    :param codec: The escape codec to serialize.
    :returns: The ``escapes`` section ``IrMap`` of the five named tables.
    """
    return IrMap(
        IrTuple(IrStr("short"), codec.short),
        IrTuple(IrStr("hex"), codec.hexes),
        IrTuple(IrStr("class-short"), codec.class_short),
        IrTuple(
            IrStr("class-meta"),
            IrTuple(*(IrStr(c) for c in sorted(str(m) for m in codec.class_meta))),
        ),
        IrTuple(IrStr("quote-safe"), codec.quote_safe),
    )


def format_manifest(flavour: IrFlavour, actions: IrTypeMap) -> str:
    """One manifest as readable notation text — each section on its own line.

    Six of the seven sections are the flavour's own ClassVars, so it is
    passed whole rather than unpacked at every call site (a flavour is data).

    :param flavour: The flavour whose metadata, escapes, grammar and reduction
        to emit.
    :param actions: Its emit actions.
    :returns: The manifest as notation text.
    """
    sections = [
        ("name", repr(IrStr(flavour.name))),
        ("extensions", repr(IrTuple(*(IrStr(e) for e in flavour.extensions)))),
        ("line-comment", repr(IrStr(flavour.line_comment))),
        ("escapes", repr(escapes_as_ir(flavour.escapes))),
        ("grammar", repr(flavour.grammar)),
        ("reduction", repr(flavour.reducer)),
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
        format_manifest(GBNF_FLAVOUR, GBNF_ACTIONS),
    )
    _write(
        _GRAMMARS / "abnf.flavour.ir",
        format_manifest(ABNF_FLAVOUR, ABNF_ACTIONS),
    )
    _write(
        _GRAMMARS / "ebnf.flavour.ir",
        format_manifest(EBNF_FLAVOUR, EBNF_ACTIONS),
    )
    _write(_GROUND_TRUTH / "arithmetic.ebnf", ARITHMETIC_EBNF)
    _write(_GROUND_TRUTH / "json.ebnf", _json_ebnf())


def _json_ebnf() -> str:
    """The json GT in EBNF — the canonical json.gbnf emitted at width 88."""
    text = (_GROUND_TRUTH / "json.gbnf").read_text(encoding="utf-8")
    canonical = canonicalize(parse_grammar(text, GBNF_FLAVOUR))
    return str(EBNF_FLAVOUR.apply(canonical)) + "\n"


if __name__ == "__main__":
    main()
