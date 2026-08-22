"""Direct proofs for separator ownership safety.

These tests exercise the conservative proof independently of orchestration:
an unsafe owner must decline, while punctuation behind a nested delimiter is
owned by that nested region and remains eligible.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.grammars.json import JSON_GRAMMAR
from lexic.parsing import parse_model
from lexic.parsing.parallel import split_model, split_plan
from lexic.parsing.parallel.discovery.interiors import interior_rules
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.parallel.plan.envelope import admits
from lexic.parsing.parallel.stitch.safety import (
    Boundary,
    owner_excludes,
    scan_agrees,
    terminates_once,
    unit_boundary,
)
from lexic.parsing.pda.core.charsets import CharSet


def _grammar(source: str):
    """Compile authored grammar text and expose its analysis view."""
    return compile_text(source).grammar


def test_flat_owner_that_emits_the_separator_is_rejected() -> None:
    """A flat item comma is a competing owner, so splitting is unsafe."""
    grammar = _grammar(
        'root ::= item more*\nmore ::= "," item\nitem ::= [a-z]+ "," [a-z]+\n'
    )

    assert not owner_excludes(grammar, "item", ",")


def test_nested_delimited_commas_are_not_pooled_into_the_owner() -> None:
    """Commas behind braces belong to the nested delimiter, not its owner."""
    grammar = _grammar(
        "root ::= item more*\n"
        'more ::= "," item\n'
        "item ::= pair\n"
        'pair ::= "{" inner "}"\n'
        'inner ::= [a-z]+ "," [a-z]+\n'
    )

    assert owner_excludes(grammar, "item", ",")
    assert owner_excludes(JSON_GRAMMAR, "member", ",", region_scan=True)


@pytest.mark.parametrize("body", ("[a-z,]", "[^a]"))
def test_charclass_and_cofinite_owner_emissions_are_rejected(body: str) -> None:
    """A class that can emit the separator cannot earn an exclusion proof."""
    grammar = _grammar(f'root ::= item more*\nmore ::= "," item\nitem ::= {body}\n')

    assert not owner_excludes(grammar, "item", ",")


def test_unknown_or_missing_owner_declines_conservatively() -> None:
    """Unknown references and owner names fail closed instead of guessing."""
    grammar = _grammar('root ::= item more*\nmore ::= "," item\nitem ::= unknown\n')

    assert not owner_excludes(grammar, "item", ",")
    assert not owner_excludes(grammar, "missing", ",")


def test_recursive_owner_graph_terminates_and_rejects_possible_separator() -> None:
    """A recursive path is finite to inspect and rejects its comma arm."""
    grammar = _grammar(
        "root ::= item more*\n"
        'more ::= "," item\n'
        "item ::= recurse\n"
        'recurse ::= item | ","\n'
    )

    assert not owner_excludes(grammar, "item", ",")


def test_common_terminator_through_newline_refs_is_safe_for_each_stmt_arm() -> None:
    """Both block and bind arms end once through the shared ``nl`` rule."""
    grammar = _grammar(
        "root ::= stmt+\n"
        "stmt ::= block | bind\n"
        'block ::= "block" nl\n'
        'bind ::= "bind" nl\n'
        'nl ::= "\\n"\n'
    )

    assert terminates_once(grammar, "stmt", "\n")


def test_a_fenced_unit_hides_its_internal_newlines_from_the_scan() -> None:
    """A fence's inner lines sit between delimiters nothing inside can spell,
    so the scan never reads their newlines and the unit ends once — visibly."""
    grammar = _grammar(
        "root ::= fence+\n"
        'fence ::= "```" nl line* "```" nl\n'
        "line ::= [a-z]+ nl\n"
        'nl ::= "\\n"\n'
    )

    assert terminates_once(grammar, "fence", "\n")


def test_terminates_once_passes_through_a_merged_tail_literal() -> None:
    """A unit whose final item is a merged literal like ``"}\\n"`` still
    proves its terminator once — the literal's LAST character, occurring
    nowhere else in it."""
    grammar = _grammar('root ::= unit+\nunit ::= [a-z]+ "}\\n"\n')
    assert terminates_once(grammar, "unit", "\n")


def test_terminates_once_declines_when_the_terminator_sits_mid_literal() -> None:
    """A literal carrying the terminator character MORE than once must not
    be read as ending exactly once — which occurrence is the true edge is
    unprovable, so the unit fails to certify."""
    grammar = _grammar('root ::= unit+\nunit ::= [a-z]+ "a\\nb\\n"\n')
    assert not terminates_once(grammar, "unit", "\n")


def test_a_reachable_delimiter_speller_fails_sole_spelling_and_declines() -> None:
    """A backtick spelled by a sibling rule, reachable without entering the
    fence, breaks sole spelling. The wrapping arm's leading whitespace also
    keeps unit anchoring from rescuing it (the arm is no longer a plain
    reference to the fence rule), so neither certificate holds and the
    fence's internal newlines stay visible."""
    grammar = _grammar(
        "root ::= block+ other\n"
        'block ::= " "* fence\n'
        'fence ::= "```" nl line* "```" nl\n'
        "line ::= [a-z]+ nl\n"
        'nl ::= "\\n"\n'
        'other ::= "`" "x"\n'
    )

    assert "fence" not in interior_rules(grammar)
    assert not terminates_once(grammar, "block", "\n")


def test_a_second_leading_arm_fails_unit_anchoring_and_declines() -> None:
    """Two ``block`` arms can each open with a backtick — the fence directly,
    and a sibling ``codeword`` that spells it too — so no single arm owns the
    delimiter (and the sibling's own literal breaks sole spelling as well),
    and the fence's internal newlines stay visible."""
    grammar = _grammar(
        "root ::= block+\n"
        "block ::= fence | codeword\n"
        'fence ::= "```" nl line* "```" nl\n'
        "line ::= [a-z]+ nl\n"
        'nl ::= "\\n"\n'
        'codeword ::= "`" [a-z]+ "`" nl\n'
    )

    assert "fence" not in interior_rules(grammar)
    assert not terminates_once(grammar, "block", "\n")


def test_scan_agrees_declines_when_the_view_derives_a_different_delimiter() -> None:
    """A structural view whose fence spells a different delimiter than the
    grammar actually being scanned must never let either side's regions be
    trusted — the pairing they each derive is not the same pairing."""
    scanned = _grammar(
        "root ::= fence+\n"
        'fence ::= "```" nl line* "```" nl\n'
        "line ::= [a-z]+ nl\n"
        'nl ::= "\\n"\n'
    )
    view = _grammar(
        "root ::= fence+\n"
        'fence ::= "~~~" nl line* "~~~" nl\n'
        "line ::= [a-z]+ nl\n"
        'nl ::= "\\n"\n'
    )

    assert terminates_once(view, "fence", "\n")
    assert not scan_agrees(view, scanned, "fence", "\n")


def test_start_plan_guard_is_non_vacuous_for_a_flat_comma_owner() -> None:
    """A valid start plan is declined when its item owns the comma."""
    compiled = compile_text(
        'root ::= item more*\nmore ::= "," item\nitem ::= [a-z]+ "," [a-z]+\n'
    )
    text = "aa,bb,cc,dd"

    assert split_plan(compiled.codegen_grammar) is not None
    assert (
        split_model(
            parse_model,
            compiled.codegen_grammar,
            Request(text, compiled.fold),
            2,
        )
        is None
    )
    assert compiled.parse(text, cores=1).to_text() == text


def test_nested_region_exact_adversarial_declines_without_becoming_vacuous() -> None:
    """The nested triple-comma adversary declines while sequential parsing works."""
    compiled = compile_text(
        "root ::= pre group post\n"
        'pre ::= "x"\n'
        'group ::= "{" items "}"\n'
        "items ::= word more*\n"
        'more ::= "," word\n'
        "word ::= triple | simple\n"
        'triple ::= simple "," simple "," simple\n'
        "simple ::= [a-z]+\n"
        'post ::= "y"\n'
    )
    text = "x{" + "a" * 1700 + "," + "b" * 1700 + "," + "c" * 1700 + "}y"

    assert (
        split_model(
            parse_model,
            compiled.codegen_grammar,
            Request(text, compiled.fold),
            2,
            analysis=compiled.grammar,
        )
        is None
    )
    assert compiled.parse(text, cores=2) == compiled.parse(text, cores=1)


# ── unit_boundary: certifying a cut that lands past the mark ────────────


def _admits_ignoring_the_mark(text: str, at: int, found: Boundary) -> bool:
    """A local twin of :func:`admits` without the ``!= mark`` exclusion.

    Proves the real function's mark exclusion is load-bearing rather than
    incidental: run against a ``Boundary`` whose noise charset was NOT
    stripped of the mark, this version keeps scanning across it.
    """
    size = len(text)
    start = at
    while at < size and found.head.has(text[at]):
        at += 1
    if at == start:
        return False
    while at < size and found.noise.has(text[at]):
        at += 1
    return text.startswith(found.literal, at)


def test_a_line_split_between_head_and_literal_is_refused_though_the_grammar_allows_it() -> (
    None
):
    """The admission test is strictly stronger than the grammar it certifies:
    a unit whose head and defining literal are split across a physical line
    (legal here — ``cwsp`` reaches across a newline via ``crlfwsp``) is
    refused rather than admitted, because the noise charset excludes the mark
    by construction. A version of the match that skips that exclusion would
    wrongly admit the very same text, at exactly this offset."""
    grammar = _grammar(
        "root ::= unit+\n"
        'unit ::= name cwsp* "=" cwsp* value crlf\n'
        'cwsp ::= " " | crlfwsp\n'
        'crlfwsp ::= crlf " "\n'
        'crlf ::= "\\n"\n'
        "name ::= [a-z]+\n"
        "value ::= [a-z]+\n"
    )
    found = unit_boundary(grammar, "unit", "\n")
    assert found is not None
    text = "abc\n   = two\n"

    assert not admits(text, 0, found, "\n")

    broken = found._replace(noise=found.noise.union(CharSet.from_chars("\n")))
    assert _admits_ignoring_the_mark(text, 0, broken)


def test_a_gbnf_string_literal_that_may_carry_the_raw_mark_declines() -> None:
    """A raw newline can stand inside a GBNF-shaped string literal (``lplain``
    excludes only the closing quote), which makes a false admission
    constructible past that literal. The proof must decline rather than
    certify a boundary a real document could break."""
    grammar = _grammar(
        "root ::= unit+\n"
        'unit ::= name ws ":" literal nl\n'
        "name ::= [a-z]+\n"
        'ws ::= " "*\n'
        'literal ::= "\\"" lplain* "\\""\n'
        'lplain ::= [^"]\n'
        'nl ::= "\\n"\n'
    )

    assert unit_boundary(grammar, "unit", "\n") is None


def test_a_json_shaped_member_certifies_on_the_same_walk_as_an_abnf_rule() -> None:
    """``member ::= string colon value`` announces itself exactly as an
    ABNF-shaped ``rule`` does (``rulename c-wsp* defined …``) — the same walk,
    nothing abnf-specific in the mechanism."""
    grammar = _grammar(
        'root ::= member ("," member)*\n'
        'member ::= string ":" value\n'
        'string ::= "\\"" [a-z]* "\\""\n'
        "value ::= [a-z]+\n"
    )

    found = unit_boundary(grammar, "member", ",")

    assert found is not None
    assert found.literal == ":"
    assert found.at == 1
