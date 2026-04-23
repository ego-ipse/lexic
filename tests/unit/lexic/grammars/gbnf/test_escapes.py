"""Unit tests for src/lexic/utils/escapes.py"""

from lexic.grammars.gbnf.escapes import decode_gbnf_escapes


def test_newline():
    assert decode_gbnf_escapes("\\n") == "\n"


def test_tab():
    assert decode_gbnf_escapes("\\t") == "\t"


def test_carriage_return():
    assert decode_gbnf_escapes("\\r") == "\r"


def test_double_quote():
    assert decode_gbnf_escapes('\\"') == '"'


def test_backslash():
    assert decode_gbnf_escapes("\\\\") == "\\"


def test_mixed():
    assert decode_gbnf_escapes("a\\nb") == "a\nb"


def test_no_escapes():
    assert decode_gbnf_escapes("hello") == "hello"


def test_backslash_then_n():
    # \\n (4 chars: backslash backslash n) should decode to \n (2 chars: backslash n), not newline
    assert decode_gbnf_escapes("\\\\n") == "\\n"
