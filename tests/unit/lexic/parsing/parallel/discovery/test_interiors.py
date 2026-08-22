"""Tests for ``lexic.parsing.parallel.discovery.interiors`` — the opaque regions.

A comma inside a string is TEXT, not a separator. The delimited region that
makes it so is DERIVED from the grammar's own shape — a rule whose one arm
opens and closes with the same literal spelling around a span nothing inside
can spell that literal's lead character — so every json formulation yields the
same answer without any of them being named.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path, parse_grammar
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.grammars.json import JSON_GRAMMAR
from lexic.parsing.parallel.discovery.interiors import (
    Interior,
    interior_rules,
    interior_shapes,
    interiors,
    skip_leads,
    skip_table,
)
from lexic.parsing.pda.core.charsets import CharSet
from tests.paths import GROUND_TRUTH

JSON_FORMULATIONS = ("json.gbnf", "json.abnf", "json.ebnf")


def _interiors(source: str) -> tuple[Interior, ...]:
    return interiors(parse_grammar(source, GBNF_FLAVOUR))


def test_the_native_json_grammar_derives_the_quoted_string():
    """``string ::= quote char* quote`` with a backslash-led escape arm."""
    assert interiors(JSON_GRAMMAR) == (Interior("string", '"', '"', "\\", 0, 2),)


@pytest.mark.parametrize("name", JSON_FORMULATIONS)
def test_every_json_formulation_derives_the_same_interior(name: str):
    """No privileged formulation: the shape is what is read, not the file."""
    path = GROUND_TRUTH / name
    if not path.exists():
        pytest.skip(f"fixture absent: {name}")
    assert interiors(compile_from_path(path).grammar) == (
        Interior("string", '"', '"', "\\", 0, 2),
    )


def test_a_body_with_no_escape_arm_derives_an_empty_escape():
    """The escape is a fact about the body, not an assumption about quoting."""
    source = 'root ::= str\nstr ::= "\'" body* "\'"\nbody ::= [^\']'
    assert _interiors(source) == (Interior("str", "'", "'", "", 0, 2),)


def test_the_escape_is_the_char_a_two_item_body_arm_leads_with():
    """``char ::= unescaped | "\\\\" escape`` — the second arm's lead."""
    source = (
        'root ::= str\nstr ::= "\'" char* "\'"\n'
        "char ::= unescaped | \"~\" escape\nunescaped ::= [^'~]\nescape ::= ['~]"
    )
    assert _interiors(source) == (Interior("str", "'", "'", "~", 0, 2),)


def test_distinct_delimiters_close_a_region_the_body_cannot_spell():
    """A region need not close with the character that opened it — a comment
    runs to a newline. What makes the span opaque is that nothing inside can
    spell the CLOSER, which holds here and licenses skipping it.

    Whether a scan should skip one is that scan's question: the region sweep
    drops any region whose opening carries a bracket or separator role, so a
    divisible bracketed run still reaches the region splitter intact."""
    assert _interiors('root ::= "(" body* ")"\nbody ::= [^()]') == (
        Interior("root", "(", ")", "", 0, 2),
    )


def test_a_bounded_body_is_an_interior_when_it_cannot_spell_the_delimiter():
    """Repetition is not what makes a span opaque; being unable to close it
    is. A body that spells no delimiter ends exactly at the next one."""
    assert _interiors('root ::= "\'" body "\'"\nbody ::= [^\']') == (
        Interior("root", "'", "'", "", 0, 2),
    )


def test_an_inline_body_is_an_interior_when_it_cannot_spell_the_delimiter():
    """A body needs a name only when the escape must be read from its arms;
    one that spells no delimiter needs no escape at all."""
    assert _interiors('root ::= "\'" [^\']* "\'"') == (
        Interior("root", "'", "'", "", 0, 2),
    )


def test_a_multi_arm_rule_is_not_an_interior():
    """A choice has no single delimited shape to read."""
    source = 'root ::= str\nstr ::= "\'" body* "\'" | "x"\nbody ::= [^\']'
    assert _interiors(source) == ()


def test_a_grammar_with_no_delimited_region_derives_none():
    """Empty is the honest answer, and the scan's cue to watch nothing."""
    assert _interiors('root ::= item+\nitem ::= [a-z]+ "\\n"') == ()


def test_the_analysis_is_memoised_per_grammar_identity():
    """The same object answers from the memo; an equal one recomputes — the
    strong reference in the memo is what stops a recycled id aliasing."""
    grammar = parse_grammar(
        'root ::= str\nstr ::= "\'" b* "\'"\nb ::= [^\']', GBNF_FLAVOUR
    )
    assert interiors(grammar) is interiors(grammar)


# ── the tightened self-grammars ─────────────────────────────────────────


def test_gbnf_abnf_and_vyx_quote_rules_are_shapes_but_never_certified():
    """A ``"`` inside a GBNF character class, an ABNF comment, or a vyx
    comment can desync a left-to-right pairing scan, so these real
    self-grammars' quote-like rules are DERIVED shapes but never certified —
    the sole-spelling tightening applies beyond constructed examples."""
    gbnf = GBNF_FLAVOUR.grammar
    abnf = ABNF_FLAVOUR.grammar
    vyx = compile_from_path(GROUND_TRUTH / "vyx.gbnf").grammar

    assert any(shape.rule == "literal" for shape in interior_shapes(gbnf))
    assert "literal" not in interior_rules(gbnf)

    assert any(shape.rule == "char-val" for shape in interior_shapes(abnf))
    assert "char-val" not in interior_rules(abnf)

    assert any(shape.rule == "quoted" for shape in interior_shapes(vyx))
    assert "quoted" not in interior_rules(vyx)


def test_a_quote_inside_a_gbnf_character_class_round_trips_exactly():
    """A stray ``"`` inside ``[a-z"]`` is ordinary class content; nothing the
    tightened certificate feeds may read it as a delimiter half."""
    rules = "".join(f'rule{i} ::= "text{i}"\n' for i in range(400))
    source = rules + 'weird ::= [a-z"]\n'
    assert len(source) >= 8 * 1024  # clears the split floor with headroom

    ast = parse_grammar(source, GBNF_FLAVOUR)
    weird = next(rule for rule in ast.rules if str(rule.name) == "weird")
    charclass = tuple(tuple(weird.body)[0])[0].atom
    charset = CharSet.from_charclass(charclass)

    assert charset.has('"')
    assert charset.has("m")
    assert not charset.has("!")


def test_a_quote_inside_an_abnf_comment_round_trips_exactly():
    """A stray ``"`` inside an ABNF comment is ordinary comment text; the
    tightened ``char-val`` certificate must not let a region scan treat the
    comment's quote as a delimiter half."""
    rules = "".join(f'rule{i} = "text{i}"\r\n' for i in range(400))
    source = rules + '; a comment with a " quote inside\r\nlast = "z"\r\n'
    assert len(source) >= 8 * 1024

    ast = parse_grammar(source, ABNF_FLAVOUR)
    names = {str(rule.name) for rule in ast.rules}
    # Every numbered rule AND the trailing rule survive: the comment's quote
    # neither swallowed "last" nor spliced it into an earlier rule's body.
    assert {f"rule{i}" for i in range(400)} <= names
    assert "last" in names


# ── multi-delimiter composition ─────────────────────────────────────────


def test_skip_leads_drops_a_lead_two_spellings_share():
    """``code`` and ``fence`` both open with a backtick — a scan reaching
    that lead cannot tell which one it is, so the composed table refuses it
    even though each spelling is individually a valid delimiter."""
    fence = Interior("fence", "```", "```", "", 0, 2)
    code = Interior("code", "`", "`", "", 0, 1)

    table = skip_table((fence, code))
    assert table["`"] == (fence, code)  # longest delimiter first

    assert "`" not in skip_leads((fence, code))


def test_skip_leads_keeps_an_unshared_lead():
    """A lead only one region opens stays an unambiguous lookup."""
    fence = Interior("fence", "```", "```", "", 0, 2)
    quote = Interior("string", '"', '"', "\\", 0, 2)

    leads = skip_leads((fence, quote))

    assert leads["`"] == ("```", "", 3, "```", 3)
    assert leads['"'] == ('"', "\\", 1, "", 1)


# ── asymmetric regions and compositional certification ──────────────────


def test_a_semicolon_to_crlf_comment_derives_an_asymmetric_interior_with_a_visible_closer():
    """``";" cchar* crlf`` opens and closes with different spellings; the
    closer stays scan-visible (``resumes == closes``, not ``closes + 1``) —
    it may itself be the mark a split cuts on, as a comment's newline is."""
    shapes = _interiors(
        'root ::= comment\ncomment ::= ";" cchar* crlf\ncchar ::= [^\\n]\ncrlf ::= "\\n"'
    )

    assert shapes == (Interior("comment", ";", "\n", "", 0, 2),)
    region = shapes[0]
    assert not region.consumes_closer
    assert region.resumes == region.closes


def test_mutually_shadowing_comment_and_string_regions_certify_together():
    """abnf's own shape: a comment body may spell a quote and a string body
    may spell a semicolon, so neither region is sole ALONE — but each is sole
    once the OTHER is already hidden. The greatest fixpoint starts with both
    skipped and finds this stable, certifying both together."""
    source = (
        "root ::= (comment | string)*\n"
        'comment ::= ";" cchar* crlf\n'
        "cchar ::= [^\\n]\n"
        'string ::= "\\"" schar* "\\""\n'
        'schar ::= [^"]\n'
        'crlf ::= "\\n"\n'
    )

    assert _interiors(source) == (
        Interior("comment", ";", "\n", "", 0, 2),
        Interior("string", '"', '"', "", 0, 2),
    )


def test_a_third_rule_spelling_a_delimiter_outside_both_regions_refuses_both():
    """A rule reachable without entering either region that spells one
    region's delimiter breaks that region's sole spelling; once it drops out
    of the hidden set, its own (now-visible) body breaks the OTHER region's
    sole spelling too — the fixpoint drops both, not just the one directly
    hit."""
    source = (
        "root ::= (comment | string | stray)*\n"
        'comment ::= ";" cchar* crlf\n'
        "cchar ::= [^\\n]\n"
        'string ::= "\\"" schar* "\\""\n'
        'schar ::= [^"]\n'
        'stray ::= ";"\n'
        'crlf ::= "\\n"\n'
    )

    assert _interiors(source) == ()


def test_a_shared_opening_character_refuses_both_regions_through_the_visible_opener():
    """Certification treats the OPENING delimiter as visible — it is where a
    scan decides which region opens — so a sibling opening with the SAME
    character still refuses, even though it is that sibling's own delimiter
    rather than something inside its body. Two regions sharing a lead
    character (``;``) each see the other's visible opener and both decline."""
    source = (
        "root ::= (comment | special)*\n"
        'comment ::= ";" cchar* crlf\n'
        "cchar ::= [^\\n]\n"
        'special ::= ";" thing ";"\n'
        "thing ::= [^;]*\n"
        'crlf ::= "\\n"\n'
    )

    assert _interiors(source) == ()
