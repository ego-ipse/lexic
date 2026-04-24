"""Unit tests for GbnfAdapter."""

from __future__ import annotations

from lexic.grammars.gbnf.adapter import GbnfAdapter
from lexic.grammars.gbnf.ast import Rule
from lexic.grammars.gbnf.emitter import GbnfEmitter
from lexic.grammars.gbnf.parser import GbnfParser

_ADAPTER = GbnfAdapter()


def test_adapter_name():
    assert _ADAPTER.name == "gbnf"


def test_adapter_extensions():
    assert _ADAPTER.extensions == (".gbnf",)


def test_adapter_parser_is_gbnf_parser():
    assert isinstance(_ADAPTER.parser, GbnfParser)


def test_adapter_emitter_is_gbnf_emitter():
    assert isinstance(_ADAPTER.emitter, GbnfEmitter)


def test_adapter_emitter_supports_known_features():
    assert "literal" in _ADAPTER.emitter.supports
    assert "alternation" in _ADAPTER.emitter.supports
    assert "char_class" in _ADAPTER.emitter.supports


def test_adapter_parser_parse_returns_rules():
    result = _ADAPTER.parser.parse('root ::= "hello"')
    assert len(result) == 1
    assert isinstance(result[0], Rule)
    assert result[0].name == "root"


def test_adapter_emitter_emit_empty_specs_returns_newline():
    assert _ADAPTER.emitter.emit([]) == "\n"
