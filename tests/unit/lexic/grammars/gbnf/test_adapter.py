"""Unit tests for GbnfAdapter and the GBNF escape codec it declares."""

from __future__ import annotations

import pytest

from lexic.grammars.gbnf.adapter import (
    GBNF_ESCAPES,
    GbnfAdapter,
    decode_gbnf_escapes,
    encode_gbnf_escapes,
)
from lexic.grammars.gbnf.ast import Rule
from lexic.grammars.gbnf.emitter import GbnfEmitter
from lexic.grammars.gbnf.parser import GbnfParser

_ADAPTER = GbnfAdapter()


# ── adapter wiring ───────────────────────────────────────────────────


def test_adapter_name():
    """The adapter advertises itself as the 'gbnf' flavour."""
    assert _ADAPTER.name == "gbnf"


def test_adapter_extensions():
    """The adapter claims the .gbnf file extension."""
    assert _ADAPTER.extensions == (".gbnf",)


def test_adapter_parser_is_gbnf_parser():
    """The adapter exposes a GbnfParser instance for parsing input."""
    assert isinstance(_ADAPTER.parser, GbnfParser)


def test_adapter_emitter_is_gbnf_emitter():
    """The adapter exposes a GbnfEmitter instance for emission."""
    assert isinstance(_ADAPTER.emitter, GbnfEmitter)


def test_adapter_emitter_supports_known_features():
    """The exposed emitter advertises the canonical GBNF feature set."""
    assert "literal" in _ADAPTER.emitter.supports
    assert "alternation" in _ADAPTER.emitter.supports
    assert "char_class" in _ADAPTER.emitter.supports


def test_adapter_parser_parse_returns_rules():
    """The adapter's parser produces Rule objects from valid GBNF text."""
    result = _ADAPTER.parser.parse('root ::= "hello"')
    assert len(result) == 1
    assert isinstance(result[0], Rule)
    assert result[0].name == "root"


def test_adapter_emitter_emit_empty_specs_returns_newline():
    """Emitting an empty rule list yields a bare newline."""
    assert _ADAPTER.emitter.emit([]) == "\n"


# ── GBNF escape codec (declared on this module) ──────────────────────


def test_module_aliases_are_bound_to_canonical_instance():
    """The free-function aliases delegate to GBNF_ESCAPES, not a separate impl."""
    assert decode_gbnf_escapes == GBNF_ESCAPES.decode
    assert encode_gbnf_escapes == GBNF_ESCAPES.encode


@pytest.mark.parametrize(
    "src,expected",
    [
        (r"\n", "\n"),
        (r"\t", "\t"),
        (r"\r", "\r"),
        (r"\\", "\\"),
        (r"\"", '"'),
        (r"\x41", "A"),
        ("A", "A"),
        (r"hello\nworld", "hello\nworld"),
    ],
)
def test_decode_gbnf_escapes(src, expected):
    """decode_gbnf_escapes correctly decodes GBNF escape sequences."""
    assert decode_gbnf_escapes(src) == expected


@pytest.mark.parametrize(
    "canonical,expected",
    [
        ("\n", r"\n"),
        ("\t", r"\t"),
        ("\r", r"\r"),
        ("\\", r"\\"),
        ('"', r"\""),
        ("hello\nworld", r"hello\nworld"),
        ("plain", "plain"),
    ],
)
def test_encode_gbnf_escapes(canonical, expected):
    """encode_gbnf_escapes correctly encodes special characters."""
    assert encode_gbnf_escapes(canonical) == expected


def test_decode_then_encode_roundtrip_on_pure_ascii():
    """decode_gbnf_escapes and encode_gbnf_escapes round-trip on pure ASCII."""
    s = "abc-def_123"
    assert encode_gbnf_escapes(decode_gbnf_escapes(s)) == s


def test_encode_then_decode_roundtrip_on_canonical_python():
    """Round-trip on canonical Python strings with control characters."""
    s = "tab\there\nnewline"
    assert decode_gbnf_escapes(encode_gbnf_escapes(s)) == s
