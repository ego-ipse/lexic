"""Semantic gates for the sole ``CompiledGrammar.reduce`` route.

The artefact runs a reducer-derived ``@lexical`` variant parse plus a thin
fold. Its value is pinned independently over the whole ground-truth corpus
and over JSON documents chosen to cross every derivation tier:
escapes, ``\\uXXXX`` units, surrogate pairs, empty strings, ε whitespace,
refusing bodies, and the KEEP_RAW literal channel.
"""

from __future__ import annotations

import json

import pytest

from lexic.compile import compile_ast, compile_from_path
from lexic.compile.reduction import derive_reduction
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import get_flavour
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import (
    IrAlternation,
    IrArgs,
    IrAst,
    IrBuild,
    IrCharClass,
    IrChr,
    IrItem,
    IrInt,
    IrJoin,
    IrLiteral,
    IrMap,
    IrNone,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
    IrStr,
    IrTuple,
    KEEP_RAW,
    Reducer,
    YIELD,
)
from tests.paths import GROUND_TRUTH

_CORPUS = sorted(
    path for ext in ("*.gbnf", "*.abnf", "*.ebnf") for path in GROUND_TRUTH.glob(ext)
)

_JSON_DOCS = {
    "structural": '{"a": [1, 2, 3], "b": {"c": "xy", "d": 45}, "e": "tail"}',
    "escapes": '{"a": "x\\n\\"y\\\\z", "u": "\\u00e9 \\ud83d\\ude00", "m": "a\\u0041b"}',
    "numbers": '{"a": -12, "b": 0, "c": [1, 23, 456], "d": -0}',
    "keywords": '[true, false, null, "s", {"k": "v"}, 7, "", {}]',
    "whitespace": '  { "a"  :  [ 1 ,  2 ] , "b" : "c d"  }  ',
}

_JSON_FORMULATIONS = ("native", "json.gbnf", "json.abnf", "json.ebnf")
"""The four shipped spellings of JSON used by the split differential too."""

_JSON_ARTIFACTS = {}


def _json_value(value):
    """The stdlib JSON value represented on lexic's IR spine."""
    if value is None:
        return IrNone
    if isinstance(value, bool):
        return IrInt(value)
    if isinstance(value, int):
        return IrInt(value)
    if isinstance(value, str):
        return IrStr(value)
    if isinstance(value, list):
        return IrTuple(*(_json_value(item) for item in value))
    if isinstance(value, dict):
        return IrMap(
            *(IrTuple(IrStr(key), _json_value(item)) for key, item in value.items())
        )
    raise AssertionError(type(value).__name__)


def _json_artifact(name="native"):
    """One JSON formulation's artefact, compiled once for this module."""
    if name not in _JSON_ARTIFACTS:
        if name == "native":
            artifact = compile_ast(JSON_GRAMMAR, cache_key="parity-reduce-json")
        else:
            artifact = compile_from_path(GROUND_TRUTH / name)
        _JSON_ARTIFACTS[name] = artifact
    return _JSON_ARTIFACTS[name]


@pytest.mark.parametrize("name", sorted(_JSON_DOCS))
def test_json_reduce_matches_the_json_value(name):
    """Every tier-crossing document reduces to its independent JSON value."""
    doc = _JSON_DOCS[name]
    got = _json_artifact().reduce(doc, JSON_REDUCER, cores=1)
    assert got == _json_value(json.loads(doc))


@pytest.mark.parametrize("formulation", _JSON_FORMULATIONS)
def test_every_json_formulation_reduces_through_the_artifact_seam(formulation):
    """Native, GBNF, ABNF and EBNF spellings produce the same JSON value."""
    artifact = _json_artifact(formulation)
    doc = _JSON_DOCS["escapes"]
    got = artifact.reduce(doc, JSON_REDUCER, cores=1)
    assert got == _json_value(json.loads(doc))


def test_named_island_escape_path_decodes_exactly():
    """A poisoned char run takes the group-named sub-grammar escape hatch."""
    artifact = _json_artifact()
    run = derive_reduction(artifact.grammar, JSON_REDUCER).runs["char-run"]
    doc = '"line\\nlatin \\u00e9 emoji \\ud83d\\ude00"'
    assert run.poison == frozenset({"\\"})
    assert any(char in doc for char in run.poison), "the island case is vacuous"
    got = artifact.reduce(doc, JSON_REDUCER, cores=1)
    assert got == IrStr("line\nlatin é emoji 😀")


def test_json_reduce_with_default_cores_matches_the_json_value():
    """The default worker policy preserves the exact JSON value."""
    doc = '{"vocab": {' + ",".join(f'"tok{i}": {i}' for i in range(500)) + "}}"
    got = _json_artifact().reduce(doc, JSON_REDUCER)
    assert got == _json_value(json.loads(doc))


def test_refusing_body_refuses_with_the_declared_words():
    """An ``IrRaise`` body refuses at fold time with its declared message."""
    doc = '{"x": 1.5}'
    with pytest.raises(UnsupportedConstructError) as folded:
        _json_artifact().reduce(doc, JSON_REDUCER, cores=1)
    assert str(folded.value) == (
        "json: fractional numbers have no IR value (no float leaf)"
    )


@pytest.mark.parametrize("path", _CORPUS, ids=lambda p: p.name)
def test_self_grammar_reduce_is_deterministic(path):
    """Every ground-truth grammar reduces to the same raw AST on repeat."""
    flavour = get_flavour(path.suffix.lstrip("."))
    reducer = flavour.reducer
    assert isinstance(reducer, Reducer)  # the flavour ClassVar's boundary
    artifact = compile_ast(flavour.grammar, cache_key=f"parity-reduce-{path.suffix}")
    text = path.read_text(encoding="utf-8")
    got = artifact.reduce(text, reducer, cores=1)
    assert artifact.reduce(text, reducer, cores=1) == got


def test_keep_raw_literal_channel_rebuilds_each_character():
    """literal=KEEP_RAW rebuilds the per-character IrLiteral channel exactly."""
    # literal=KEEP_RAW feeds one IrLiteral per consumed character; the fold
    # must rebuild that channel for an unmarked span-collapsed rule.
    grammar = IrAst(
        IrSeq(
            IrRule(
                "pair",
                IrAlternation(
                    IrSequence(
                        IrItem(IrRuleRef("word")),
                        IrItem(IrLiteral(":")),
                        IrItem(IrRuleRef("word")),
                    )
                ),
            ),
            IrRule(
                "word",
                IrAlternation(
                    IrSequence(
                        IrItem(
                            IrCharClass(IrRange(IrChr(97), IrChr(122))),
                            IrQuantifier(1, IrNone),
                        )
                    )
                ),
            ),
        ),
        "pair",
    )
    reducer = Reducer(
        actions=IrMap(
            IrTuple(IrRuleRef("pair"), IrBuild(IrTuple)),
            IrTuple(IrRuleRef("word"), IrJoin(IrArgs())),
        ),
        default=YIELD,
        literal=KEEP_RAW,
    )
    artifact = compile_ast(grammar, cache_key="parity-reduce-keepraw")
    text = "abc:de"
    got = artifact.reduce(text, reducer, cores=1)
    assert got == IrTuple(IrStr("abc"), IrLiteral(":"), IrStr("de"))
