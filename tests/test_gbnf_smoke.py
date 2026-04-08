from ogbnf import GBNFParser, GBNFAlternation, GBNFRepetition, _unescape


def test_unescape_backslash():
    assert _unescape('"\\"') == "\\"


def test_unescape_newline():
    assert _unescape('"\\n"') == "\n"


def test_unescape_nl_force():
    assert _unescape('"# "') == "# "


def test_parse_body_line_is_alternation(vyx_rules):
    assert isinstance(vyx_rules["body-line"], GBNFAlternation)


def test_unquoted_is_repetition_min1(vyx_rules):
    # unquoted ::= [\\x21-...\\x7E]+  — a charclass with +
    body = vyx_rules["unquoted"]
    assert isinstance(body, GBNFRepetition)
    assert body.min == 1
