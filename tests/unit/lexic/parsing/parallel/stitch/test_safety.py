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
from lexic.parsing.parallel.discovery.scan import Overlap, mark_overlap
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.parallel.plan.envelope import admits
from lexic.parsing.parallel.stitch.safety import (
    Boundary,
    Refutation,
    _leads_once,
    owner_excludes,
    scan_agrees,
    terminates_once,
    unit_boundary,
)
from lexic.parsing.pda.core.charsets import CharSet
from tests.unit.lexic.parsing.parallel.envelope_fixtures import (
    CONTINUATION_SOURCE,
)


def _grammar(source: str):
    """Compile authored grammar text and expose its analysis view."""
    return compile_text(source).grammar


def _rules(source: str) -> dict:
    """Compile authored grammar text and expose its rules by name."""
    grammar = compile_text(source).grammar
    return {str(rule.name): rule for rule in grammar.rules}


def _leads_proof(literal: str) -> Refutation:
    """A minimal ``Refutation`` isolating ``_leads_once`` from the rest of
    the walk — head is ``[a-z]``, mark is ``"\\n"``, literal is the caller's."""
    found = Boundary(
        CharSet.from_chars(*"abcdefghijklmnopqrstuvwxyz"), CharSet.EMPTY, literal, 0
    )
    return Refutation(found, "\n", frozenset())


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
    delimiter, and the fence's internal newlines stay visible.

    ``plain`` admits a backtick in a character CLASS, which opens no region
    and so hides nothing; that denies both regions their sole-opening
    certificate, leaving unit anchoring as the only route — and two leading
    arms refuse it."""
    grammar = _grammar(
        "root ::= block+\n"
        "block ::= fence | codeword | title\n"
        'fence ::= "```" nl line* "```" nl\n'
        "line ::= [a-z]+ nl\n"
        'nl ::= "\\n"\n'
        'codeword ::= "`" [a-z]+ "`" nl\n'
        "title ::= plain nl\n"
        "plain ::= [a-z`]+\n"
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
    assert not scan_agrees(view, scanned, "fence", frozenset({"\n"}))


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
            Request(text, compiled.product),
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
            Request(text, compiled.product),
            2,
            analysis=compiled.grammar,
        )
        is None
    )
    assert compiled.parse(text, cores=2) == compiled.parse(text, cores=1)


# ── unit_boundary: certifying a cut that lands past the mark ────────────


def _admits_ignoring_the_mark(text: str, at: int, found: Boundary) -> bool:
    """A local twin of :func:`admits` without the ``!= mark`` exclusion.

    Proves the real function's mark exclusion is what stops the scan rather
    than an accident: run against a ``Boundary`` whose noise charset was NOT
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


def test_an_unskippable_string_literal_carrying_the_raw_mark_declines() -> None:
    """A raw newline can stand inside a string literal, which makes a false
    admission constructible past it — UNLESS the scan skips the literal whole.

    Here it cannot: ``name`` can spell a quote outside any region, so the quote
    is not a sole opener and the literal never certifies. The scan therefore
    reads into it, a newline there IS a candidate mark, and the proof must
    decline rather than certify a boundary a real document could break.
    """
    grammar = _grammar(
        "root ::= unit+\n"
        'unit ::= name ws ":" literal nl\n'
        'name ::= [a-z"]+\n'
        'ws ::= " "*\n'
        'literal ::= "\\"" lplain* "\\""\n'
        'lplain ::= [^"]\n'
        'nl ::= "\\n"\n'
    )

    assert unit_boundary(grammar, "unit", "\n") is None


def test_a_certified_string_literal_carrying_the_raw_mark_certifies() -> None:
    """The same shape, with the literal certifiable, DOES certify.

    Nothing else spells the quote, so the region is a sole opener and the scan
    skips it whole. A newline inside it is then never a CANDIDATE mark — no cut
    is proposed there — so it cannot begin a false match, and the boundary is
    exact. This is the pair to the decline above: what changes is not the
    literal's contents but whether the scan reads them.
    """
    grammar = _grammar(
        "root ::= unit+\n"
        'unit ::= name ws ":" literal nl\n'
        "name ::= [a-z]+\n"
        'ws ::= " "*\n'
        'literal ::= "\\"" lplain* "\\""\n'
        'lplain ::= [^"]\n'
        'nl ::= "\\n"\n'
    )

    found = unit_boundary(grammar, "unit", "\n")
    assert found is not None and found.literal == ":"


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


# ── _leads_once: the mirror clause for a LEADING mark ────────────────────


def test_leads_once_certifies_a_continuation_separator_via_unit_boundary() -> None:
    """``sep``'s mark is a LEADING edge, and what follows it (``"  | "``) is
    disjoint from the prefix head — the clause ``_leads_once`` exists for,
    proven through the public entry rather than the helper directly."""
    grammar = _grammar(CONTINUATION_SOURCE)

    found = unit_boundary(grammar, "defn", "\n")

    assert found is not None
    assert found.literal == " " and found.at == 1


def test_leads_once_declines_when_one_arm_s_first_overlaps_the_head() -> None:
    """The obligation is PER ARM: one arm's post-mark FIRST being disjoint
    from ``H`` does not excuse a second arm whose FIRST overlaps it."""
    rules = _rules(
        'root ::= target\ntarget ::= "\\n#" | "\\n" letter\nletter ::= [a-z]\n'
    )

    assert not _leads_once(rules["target"], _leads_proof("#"), rules, frozenset())


def test_leads_once_declines_on_an_undecidable_post_mark_cycle() -> None:
    """A left-recursive tail past the mark cannot be resolved to a FIRST set;
    the walk answers "reachable" rather than guessing and declines — even
    though the cycle's own literal (``#``) is disjoint from ``H``."""
    rules = _rules('root ::= target\ntarget ::= "\\n" cyc\ncyc ::= cyc "#"\n')

    assert not _leads_once(rules["target"], _leads_proof("#"), rules, frozenset())


def test_leads_once_declines_a_second_mark_inside_the_leading_literal() -> None:
    """The interior occurrence may hide in the LEADING literal's own tail:
    ``"\\nx\\n"`` leads with the mark, its follower ``x`` is disjoint from any
    head — and its second newline is still a real mid-construct candidate.
    The arm must get no clause, exactly as when the occurrence is a later
    item."""
    rules = _rules('root ::= target\ntarget ::= "\\n#x\\n#" tail\ntail ::= "z"\n')

    assert not _leads_once(rules["target"], _leads_proof("#"), rules, frozenset())


def test_leads_once_declines_when_the_mark_also_occurs_mid_arm() -> None:
    """A construct carrying the mark at its leading edge AND again later in
    the SAME arm gets no clause — the interior occurrence is a real cut
    candidate the ordinary reachability path must still refuse on its own."""
    rules = _rules(
        'root ::= target\ntarget ::= "\\n#" mid\nmid ::= "\\n" tail\ntail ::= "z"\n'
    )

    assert not _leads_once(rules["target"], _leads_proof("#"), rules, frozenset())


def test_leads_once_traverses_a_nullable_to_an_overlapping_follower() -> None:
    """FIRST is computed THROUGH a nullable item: an optional filler disjoint
    from ``H`` does not shield an overlapping follower standing behind it."""
    rules = _rules('root ::= target\ntarget ::= "\\n" "!"? letter\nletter ::= [a-z]\n')

    assert not _leads_once(rules["target"], _leads_proof("#"), rules, frozenset())


def test_leads_once_traverses_a_nullable_to_a_disjoint_follower() -> None:
    """The same nullable traversal, with a follower disjoint from ``H`` —
    certifies."""
    rules = _rules('root ::= target\ntarget ::= "\\n" "!"? tail\ntail ::= "#"\n')

    assert _leads_once(rules["target"], _leads_proof("#"), rules, frozenset())


# ── a spelling's own straddles ────────────────────────────────────────────

_ASSEMBLING_SOURCE = (
    'doc ::= para (bl para)*\nbl ::= "\\n\\n"\npara ::= line+\nline ::= [a-z]* "\\n"\n'
)
"""Lines may be EMPTY, so ``para`` assembles the separator across a join no
atom of it spells."""

_SAFE_SOURCE = _ASSEMBLING_SOURCE.replace("[a-z]*", "[a-z]+")
"""One character apart: every line opens with a letter, so the join cannot
assemble the separator and every occurrence of it is a real boundary."""


def test_owner_exclusion_refuses_an_assembled_separator():
    """The assembly obligation at the proof's own entry. Atom-wise emission
    would certify this owner; the pieces of a cut at the wrong occurrence both
    PARSE, so nothing downstream catches it and the proof must."""
    assert not owner_excludes(_grammar(_ASSEMBLING_SOURCE), "para", "\n\n")
    assert owner_excludes(_grammar(_SAFE_SOURCE), "para", "\n\n")


def test_assembling_and_safe_derive_the_same_plan_only_certification_differs():
    """The review's exact claim, as a direct assertion rather than a proto
    printout: one character (``[a-z]*`` vs ``[a-z]+``) changes nothing about
    what PLAN the scan derives — same mark, same owner — and everything
    about whether the assembly proof licenses it. If a future change made
    these two grammars derive DIFFERENT plans, this test would stop proving
    what it claims to, silently; asserting plan equality directly is what
    keeps it honest."""
    assembling_plan = split_plan(compile_text(_ASSEMBLING_SOURCE).codegen_grammar)
    safe_plan = split_plan(compile_text(_SAFE_SOURCE).codegen_grammar)
    assert assembling_plan is not None and safe_plan is not None
    assert assembling_plan.mark == safe_plan.mark == frozenset({"\n\n"})
    assert assembling_plan.owner == safe_plan.owner == "para"
    assert not owner_excludes(_grammar(_ASSEMBLING_SOURCE), "para", "\n\n")
    assert owner_excludes(_grammar(_SAFE_SOURCE), "para", "\n\n")


def test_an_owner_that_ends_with_the_border_puts_the_boundary_last():
    """``para`` ends with a newline and the separator is two, so every real
    boundary reads as a run of three and the left occurrence is false. The
    run's LAST occurrence is the separator."""
    assert mark_overlap(_grammar(_SAFE_SOURCE), "para", "\n\n") == Overlap(True, True)


def test_an_owner_that_straddles_both_ends_declines():
    """Text ending with the border pushes the run left, text beginning with it
    pushes the run right; an owner doing both leaves the boundary somewhere in
    the middle with nothing to say where."""
    source = 'doc ::= para (bl para)*\nbl ::= "\\n\\n"\npara ::= nl [a-z]+ nl\nnl ::= "\\n"\n'
    assert mark_overlap(_grammar(source), "para", "\n\n") == Overlap(False, False)


def test_a_mark_that_is_not_its_own_border_never_overlaps():
    """Two different characters cannot overlap, so there is no run to choose
    within and the question is answered before any walk runs."""
    assert mark_overlap(_grammar(_SAFE_SOURCE), "para", "ab") == Overlap(True, False)


def test_a_one_character_mark_is_decided_and_leading():
    """The strict-extension guarantee at this proof: one character has no
    border, so every grammar shipping today answers the same way."""
    assert mark_overlap(JSON_GRAMMAR, "member", ",") == Overlap(True, False)


def test_a_unit_that_can_begin_with_its_own_terminator_border_declines():
    """A unit proven to END with ``"\\n\\n"`` ends with a newline; if the next
    unit can BEGIN with one, adjacent units read a run of three and offer two
    boundaries where the grammar has one."""
    good = (
        "root ::= para+\npara ::= line+ blank\n"
        'line ::= [a-z0-9 ]+ nl\nblank ::= nl\nnl ::= "\\n"\n'
    )
    bad = good.replace("line ::= [a-z0-9 ]+ nl", "line ::= [a-z0-9 ]* nl")
    assert terminates_once(_grammar(good), "para", "\n\n")
    assert not terminates_once(_grammar(bad), "para", "\n\n")


def test_the_announcing_prefix_proof_declines_a_spelling_outright():
    """``unit_boundary`` states its obligations over a mark CHARACTER — a
    noise run with the mark subtracted, per-character alphabets. A spelling
    owes a second proof it does not make, and declines rather than borrow."""
    grammar = _grammar(CONTINUATION_SOURCE)
    assert unit_boundary(grammar, "defn", "\n") is not None
    assert unit_boundary(grammar, "defn", "\n\n") is None


# ── mark_overlap: the two rows the implementer's own pins do not reach ────


def test_an_owner_that_never_touches_the_border_is_the_only_occurrence():
    """Row (no, no): the owner can neither end with the border nor begin
    with it, so no run of the mark's characters ever forms around a real
    boundary — there IS only one occurrence, whatever ``trailing`` says."""
    source = 'doc ::= para (bl para)*\nbl ::= "\\n\\n"\npara ::= "x" [a-z]+ "y"\n'
    assert mark_overlap(_grammar(source), "para", "\n\n") == Overlap(True, False)


def test_an_owner_that_may_only_begin_with_the_border_puts_it_first():
    """Row (no, yes): the owner never ENDS with the border, only begins with
    it, so a run (when one forms) is pushed right and the FIRST occurrence
    is the true boundary. The verdict is the same ``Overlap(True, False)``
    as the "never touches" row above — both carry ``trailing=False`` because
    neither owner ever produces a genuine overlapping run for the flag to
    decide between; ``mark_overlap`` reads ``trailing = ends``, and ``ends``
    is ``False`` in both rows."""
    source = (
        'doc ::= para (bl para)*\nbl ::= "\\n\\n"\npara ::= nl [a-z]+\nnl ::= "\\n"\n'
    )
    assert mark_overlap(_grammar(source), "para", "\n\n") == Overlap(True, False)


def test_a_length_one_mark_never_reaches_the_border_walk():
    """The early return at ``len(mark) < 2``, isolated from the ``mark[0] !=
    mark[1]`` branch the "not its own border" pin above already exercises:
    a length-one mark cannot be its own border, and the decision table's
    walk over the owner's rules never runs at all."""
    assert mark_overlap(_grammar(_SAFE_SOURCE), "para", "\n") == Overlap(True, False)
