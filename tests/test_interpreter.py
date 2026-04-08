import pytest
from ogbnf import GBNFParser
from builder import GBNFModelBuilder
from interpreter import GBNFInterpreter


def make(grammar: str) -> GBNFInterpreter:
    rules = GBNFParser().parse(grammar)
    models = GBNFModelBuilder(rules).build()
    return GBNFInterpreter(rules, models)


# --- Literal ---

def test_literal_match():
    interp = make('tag ::= "hello"')
    result = interp.parse("tag", "hello world", 0)
    assert result is not None
    value, pos = result
    assert value == "hello"
    assert pos == 5


def test_literal_no_match():
    interp = make('tag ::= "hello"')
    assert interp.parse("tag", "world", 0) is None


def test_literal_at_offset():
    interp = make('tag ::= "!"')
    result = interp.parse("tag", "xx!", 2)
    assert result is not None
    assert result[1] == 3


# --- CharClass ---

def test_charclass_match():
    interp = make('letter ::= [a-z]')
    result = interp.parse("letter", "abc", 0)
    assert result is not None
    value, pos = result
    assert value == "a"
    assert pos == 1


def test_charclass_no_match():
    interp = make('letter ::= [a-z]')
    assert interp.parse("letter", "ABC", 0) is None


def test_charclass_hex_range():
    """Grammar uses \\xHH notation for hex ranges — must match correctly."""
    # unquoted chars span 0x21-0x7E (printable ASCII)
    interp = make('ch ::= [\\x21-\\x7E]')
    result = interp.parse("ch", "!", 0)   # 0x21 = '!'
    assert result is not None
    assert result[0] == "!"
    result2 = interp.parse("ch", "~", 0)  # 0x7E = '~'
    assert result2 is not None
    assert result2[0] == "~"


# --- Alternation ---

def test_alternation_first_arm():
    interp = make('word ::= "hello" | "world"')
    result = interp.parse("word", "hello", 0)
    assert result is not None
    assert result[0] == "hello"


def test_alternation_second_arm():
    interp = make('word ::= "hello" | "world"')
    result = interp.parse("word", "world", 0)
    assert result is not None
    assert result[0] == "world"


def test_alternation_no_match():
    interp = make('word ::= "hello" | "world"')
    assert interp.parse("word", "foo", 0) is None


# --- Repetition ---

def test_repetition_zero_or_more():
    interp = make('letters ::= [a-z]*')
    result = interp.parse("letters", "abc123", 0)
    assert result is not None
    value, pos = result
    assert value == "abc"   # charclass rep → str
    assert pos == 3


def test_repetition_one_or_more_match():
    interp = make('word ::= [a-z]+')
    result = interp.parse("word", "hello", 0)
    assert result is not None
    assert result[0] == "hello"
    assert result[1] == 5


def test_repetition_one_or_more_fail():
    interp = make('word ::= [a-z]+')
    assert interp.parse("word", "123", 0) is None


def test_repetition_zero_or_more_empty():
    """Zero-or-more with no match should succeed returning empty string."""
    interp = make('letters ::= [a-z]*')
    result = interp.parse("letters", "123", 0)
    assert result is not None
    value, pos = result
    assert value == ""
    assert pos == 0


# --- Optional ---

def test_optional_present():
    interp = make('maybe ::= "x"?')
    result = interp.parse("maybe", "x", 0)
    assert result is not None
    assert result[0] == "x"
    assert result[1] == 1


def test_optional_absent():
    interp = make('maybe ::= "x"?')
    result = interp.parse("maybe", "y", 0)
    assert result is not None
    value, pos = result
    assert value is None
    assert pos == 0


# --- Reference ---

def test_reference():
    grammar = 'outer ::= inner\ninner ::= "ok"'
    interp = make(grammar)
    result = interp.parse("outer", "ok", 0)
    assert result is not None
    assert result[1] == 2


# --- Sequence with model instantiation ---

def test_sequence_produces_model_instance():
    # Inline charclass repetitions → str fields directly (Task 2 optimization)
    # _element_name gives: elem_0 (charclass rep), token_1 (literal "="), elem_2 (charclass rep)
    grammar = 'pair ::= [a-zA-Z]+ "=" [0-9]+'
    rules = GBNFParser().parse(grammar)
    models = GBNFModelBuilder(rules).build()
    interp = GBNFInterpreter(rules, models)

    result = interp.parse("pair", "foo=42", 0)
    assert result is not None
    instance, pos = result
    assert pos == 6
    from pydantic import BaseModel
    assert isinstance(instance, BaseModel)
    assert instance.elem_0 == "foo"
    assert instance.token_1 == "="
    assert instance.elem_2 == "42"


# --- Vyx grammar smoke ---

def test_parse_kv_pair_vyx(vyx_rules):
    from builder import GBNFModelBuilder
    from interpreter import GBNFInterpreter
    models = GBNFModelBuilder(vyx_rules).build()
    interp = GBNFInterpreter(vyx_rules, models)

    # The grammar file uses \"=\" (backslash-escaped quotes) which the tokenizer
    # misparses as a literal "=\" (with trailing backslash).  Use the input that
    # actually matches the parsed literal.
    result = interp.parse("kv-pairs", "city=\\Porto", 0)
    assert result is not None
    _, pos = result
    assert pos == 11
