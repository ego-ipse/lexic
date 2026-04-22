from lexic.utils.charclass import parse_charclass_chars, parse_escape


def test_parse_escape_basic():
    assert parse_escape("\\n", 0) == ("\n", 2)
    assert parse_escape("\\t", 0) == ("\t", 2)
    assert parse_escape('\\"', 0) == ('"', 2)
    assert parse_escape("\\\\", 0) == ("\\", 2)


def test_parse_escape_hex():
    assert parse_escape("\\x41", 0) == ("A", 4)
    assert parse_escape("\\u00e9", 0) == ("é", 6)


def test_parse_charclass_simple_range():
    assert parse_charclass_chars("a-c") == ["a", "b", "c"]
    assert parse_charclass_chars("0-3") == ["0", "1", "2", "3"]


def test_parse_charclass_escape_range():
    result = parse_charclass_chars("\\x00-\\x03")
    assert result == [chr(c) for c in range(0, 4)]


def test_parse_charclass_direct_chars():
    assert parse_charclass_chars("abc") == ["a", "b", "c"]


def test_parse_charclass_mixed():
    assert parse_charclass_chars("a-c_") == ["a", "b", "c", "_"]
