"""``CompiledGrammar.reduce`` against the fused ``parse_reduced`` oracle.

The artefact's reduce product runs a reducer-derived ``@lexical`` variant
parse plus a thin fold; the fused product runs the reducer inside the
engine's completions. Same reducer, same text, same value — pinned over the
whole ground-truth corpus (every flavour self-grammar reducing real grammar
text) and over json documents chosen to cross every derivation tier:
escapes, ``\\uXXXX`` units, surrogate pairs, empty strings, ε whitespace,
refusing bodies, and the KEEP_RAW literal channel.
"""

from __future__ import annotations

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
    IrTuple,
)
from lexic.parsing import Reducer
from lexic.parsing.earley.reduce.policy import KEEP_RAW, YIELD
from tests.reduce_oracle import reduce_one as parse_reduced
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
def test_json_reduce_matches_fused(name):
    """Every tier-crossing json document reduces to the fused oracle's value."""
    doc = _JSON_DOCS[name]
    got = _json_artifact().reduce(doc, JSON_REDUCER, cores=1)
    assert got == parse_reduced(JSON_GRAMMAR, doc, JSON_REDUCER)


@pytest.mark.parametrize("formulation", _JSON_FORMULATIONS)
def test_every_json_formulation_reduces_through_the_artifact_seam(formulation):
    """Native, GBNF, ABNF and EBNF spellings all meet the fused oracle."""
    artifact = _json_artifact(formulation)
    doc = _JSON_DOCS["escapes"]
    got = artifact.reduce(doc, JSON_REDUCER, cores=1)
    assert got == parse_reduced(artifact.grammar, doc, JSON_REDUCER)


def test_named_island_escape_path_matches_fused():
    """A poisoned char run takes the group-named sub-grammar escape hatch."""
    artifact = _json_artifact()
    run = derive_reduction(artifact.grammar, JSON_REDUCER).runs["char-run"]
    doc = '"line\\nlatin \\u00e9 emoji \\ud83d\\ude00"'
    assert run.poison == frozenset({"\\"})
    assert any(char in doc for char in run.poison), "the island case is vacuous"
    got = artifact.reduce(doc, JSON_REDUCER, cores=1)
    assert got == parse_reduced(artifact.grammar, doc, JSON_REDUCER)


def test_json_reduce_matches_fused_with_default_cores():
    """The default cores route (split allowed) agrees with the oracle too."""
    doc = '{"vocab": {' + ",".join(f'"tok{i}": {i}' for i in range(500)) + "}}"
    got = _json_artifact().reduce(doc, JSON_REDUCER)
    assert got == parse_reduced(JSON_GRAMMAR, doc, JSON_REDUCER)


def test_refusing_body_refuses_with_the_fused_words():
    """An IrRaise body refuses at fold time with the fused exception verbatim."""
    doc = '{"x": 1.5}'
    with pytest.raises(UnsupportedConstructError) as fused:
        parse_reduced(JSON_GRAMMAR, doc, JSON_REDUCER)
    with pytest.raises(UnsupportedConstructError) as folded:
        _json_artifact().reduce(doc, JSON_REDUCER, cores=1)
    assert str(folded.value) == str(fused.value)


@pytest.mark.parametrize("path", _CORPUS, ids=lambda p: p.name)
def test_self_grammar_reduce_matches_fused(path):
    """Every ground-truth grammar reduces equal through its flavour's artefact."""
    flavour = get_flavour(path.suffix.lstrip("."))
    reducer = flavour.reducer
    assert isinstance(reducer, Reducer)  # the flavour ClassVar's boundary
    artifact = compile_ast(flavour.grammar, cache_key=f"parity-reduce-{path.suffix}")
    text = path.read_text(encoding="utf-8")
    got = artifact.reduce(text, reducer, cores=1)
    assert got == parse_reduced(flavour.grammar, text, reducer)


def test_keep_raw_literal_channel_matches_fused():
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
    assert got == parse_reduced(grammar, text, reducer)
