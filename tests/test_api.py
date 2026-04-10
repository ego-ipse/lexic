# tests/test_api.py
"""Public API integration tests."""
import pytest
from vyx import parse, ParseError, Packet, BodyContent, SeqItem, BodyLine


def test_public_parse_packet():
    result = parse("!I o:inv\ncity=Porto temp=22\n>")
    assert isinstance(result, Packet)


def test_public_parse_body_content():
    result = parse("city=Porto temp=22\n", start="body_content")
    assert isinstance(result, BodyContent)


def test_public_parse_error():
    with pytest.raises(ParseError):
        parse("not_a_valid_packet!!!")


def test_public_parse_seq_item():
    result = parse("- city=Porto\n", start="seq_item")
    assert isinstance(result, SeqItem)


def test_public_parse_roundtrip_kv_body():
    text = "!I o:inv\ncity=Porto\ntemp=22\n>"
    result = parse(text)
    assert isinstance(result, Packet)
    assert result.body is not None


def test_unknown_start_rule():
    with pytest.raises(ValueError, match="Unknown start rule"):
        parse("!I\n>", start="nonexistent_rule")


def test_public_parse_body_line():
    result = parse("city=Porto temp=22", start="body_line")
    assert isinstance(result, BodyLine)
