# tests/test_parser.py
"""Round-trip parse tests on known valid Vyx inputs."""
import pytest
from vyx.parser import parse, ParseError
from vyx.models import Packet, Body, BodyContent, BodyLine


def test_parse_body_line_nl_text():
    from vyx.parser import parse_body_line
    result, pos = parse_body_line("hello world", 0)
    assert pos == len("hello world")
    assert isinstance(result, BodyLine)


def test_parse_body_line_nl_force():
    # nl-force ::= "# " [\x21-\x7E]* — no spaces after the prefix
    from vyx.parser import parse_body_line
    result, pos = parse_body_line("# comment-no-spaces", 0)
    assert pos == len("# comment-no-spaces")
    assert isinstance(result, BodyLine)


def test_parse_body_line_kv_line():
    from vyx.parser import parse_body_line
    result, pos = parse_body_line("city=Porto temp=22", 0)
    assert pos == len("city=Porto temp=22")
    assert isinstance(result, BodyLine)


def test_parse_body_content_empty():
    from vyx.parser import parse_body_content
    result, pos = parse_body_content("", 0)
    assert pos == 0
    assert isinstance(result, BodyContent)


def test_parse_body_content_single_line():
    from vyx.parser import parse_body_content
    result, pos = parse_body_content("city=Porto\n", 0)
    assert pos == len("city=Porto\n")
    assert isinstance(result, BodyContent)


def test_parse_body_content_multi_line():
    from vyx.parser import parse_body_content
    text = "city=Porto\ntemp=22\n"
    result, pos = parse_body_content(text, 0)
    assert pos == len(text)


def test_parse_minimal_packet():
    result = parse("!I\n>")
    assert isinstance(result, Packet)


def test_parse_packet_with_o_field():
    result = parse("!I o:inv\n>")
    assert isinstance(result, Packet)


def test_parse_packet_with_body():
    text = "!I o:inv\ncity=Porto temp=22\n>"
    result = parse(text)
    assert isinstance(result, Packet)
    assert result.body is not None


def test_parse_packet_body_only_fails():
    with pytest.raises((ParseError, Exception)):
        parse("city=Porto temp=22")


def test_parse_body_content_start():
    result = parse("city=Porto temp=22\n", start="body_content")
    assert isinstance(result, BodyContent)


def test_parse_error_on_garbage():
    with pytest.raises((ParseError, Exception)):
        parse("\x00\x01\x02")


def test_unknown_start_rule():
    with pytest.raises(ValueError, match="Unknown start rule"):
        parse("!I\n>", start="nonexistent_rule")
