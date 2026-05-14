# tests/unit/lexic/ir/test_directives.py
"""parse_directives — extracts IR-level directives from source comments."""

from __future__ import annotations

from lexic.ir.directives import Directives, parse_directives


def test_empty_text_returns_empty_directives():
    """An empty grammar source has no directives."""
    d = parse_directives("", line_comment="#")
    assert d == Directives()


def test_no_directives_in_grammar_returns_empty():
    """A grammar with comments but no directives has empty directives."""
    text = "root ::= expr\nexpr ::= [0-9]+"
    assert parse_directives(text, line_comment="#") == Directives()


def test_non_semantic_single_arg():
    """A single @non-semantic directive extracts one rule name."""
    text = "# @non-semantic ws\nroot ::= ws value"
    d = parse_directives(text, line_comment="#")
    assert d.non_semantic == frozenset({"ws"})


def test_non_semantic_multiple_args():
    """Multiple @non-semantic arguments are all collected."""
    text = "# @non-semantic ws comment_block\nroot ::= ws value"
    d = parse_directives(text, line_comment="#")
    assert d.non_semantic == frozenset({"ws", "comment_block"})


def test_directive_must_have_at_marker():
    """Comments without @<name> are not directives."""
    text = "# this is just a comment\nroot ::= x"
    assert parse_directives(text, line_comment="#") == Directives()


def test_directive_respects_line_comment_marker():
    """ABNF uses ; — # is just data inside an ABNF source."""
    text = "; @non-semantic WSP\nroot = WSP value"
    d = parse_directives(text, line_comment=";")
    assert d.non_semantic == frozenset({"WSP"})


def test_unknown_directive_is_ignored():
    """Unknown directives are silently ignored."""
    text = "# @future-thing foo\n# @non-semantic ws"
    d = parse_directives(text, line_comment="#")
    assert d.non_semantic == frozenset({"ws"})


def test_directive_can_have_leading_whitespace_before_marker():
    """`  # @non-semantic ws` is the same as `# @non-semantic ws`."""
    text = "  # @non-semantic ws\nroot ::= ws value"
    d = parse_directives(text, line_comment="#")
    assert d.non_semantic == frozenset({"ws"})


def test_empty_line_comment_disables_directive_parsing():
    """A flavour with no comment marker (line_comment='') has no directive channel."""
    text = "# @non-semantic ws\nroot ::= ws value"
    assert parse_directives(text, line_comment="") == Directives()


def test_directives_dataclass_has_default_empty_frozenset():
    """Directives() defaults to an empty frozenset."""
    d = Directives()
    assert d.non_semantic == frozenset()


def test_start_directive_sets_start_rule():
    """@start overrides the default start rule."""
    text = "# @start expr\nroot ::= ws expr\nexpr ::= [0-9]+\n"
    assert parse_directives(text, line_comment="#").start == "expr"


def test_no_start_directive_leaves_start_none():
    """No @start directive means start is None."""
    assert parse_directives("root ::= [a-z]+\n", line_comment="#").start is None


def test_start_directive_respects_line_comment_marker():
    """@start respects the line_comment marker."""
    assert parse_directives("; @start root\n", line_comment=";").start == "root"


def test_start_and_non_semantic_coexist():
    """Multiple directives can appear in the same source."""
    text = "# @start root\n# @non-semantic ws\nroot ::= ws value\n"
    d = parse_directives(text, line_comment="#")
    assert d.start == "root"
    assert d.non_semantic == frozenset({"ws"})


def test_start_directive_last_wins():
    """Multiple @start directives: last value wins."""
    text = "# @start a\n# @start b\n"
    assert parse_directives(text, line_comment="#").start == "b"
