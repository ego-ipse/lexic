"""Adversarial: the split is FAITHFUL on inputs aimed at each proof's edge.

One invariant governs every case: for any grammar and any document, the split
path must be indistinguishable from the sequential parse — same model, same
bytes back, and the same refusal (type AND message) where sequential refuses.
Engaging or declining is the mechanism's own business; being WRONG never is.

Each case below aims at one specific assumption: escape runs straddling a cut
candidate, empty-instance delimiters colliding with their own family, a
trailing-literal closer whose tail prefix flirts with the closer's lead,
admission-prefix mimicry on valid continuation lines, marks that exist only
inside certified interiors, boundary offsets at the document's edges, and
same-spelling region families that must refuse together.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import LexicError
from lexic.parsing.parallel.orchestrate import (
    _cut_offsets,
    _safe_plans,
    _split_plans,
)
from lexic.parsing.parallel.policy import MIN_CHUNK
from lexic.parsing.parallel.pool import PoolLease
from tests.split_helpers import engages

_CORES = (2, 3, 8)
"""Worker counts every faithfulness case is driven at — two is the smallest
split, three makes middle pieces exist, eight exceeds most cases' capacity so
the floor cap must do its work."""


def _outcome(compiled, text: str, cores: int):
    """``("ok", bytes)`` or ``("refused", type, message)`` — the comparable."""
    try:
        return ("ok", compiled.parse(text, cores=cores).to_text())
    except LexicError as exc:
        return ("refused", type(exc).__name__, str(exc))


def assert_faithful(
    source: str, text: str, key: str, *, engaged: bool | None = None
) -> None:
    """The universal invariant, sequential vs every worker count.

    :param engaged: ``True``/``False`` asserts the split entry's verdict at
        eight workers — non-vacuity for the torture cases, honest decline for
        the designed ones. ``None`` leaves it unasserted (refusal cases,
        where a failed piece parse declines en route to the shared refusal).
    """
    compiled = compile_text(source, cache_key=f"adv-faith-{key}")
    sequential = _outcome(compiled, text, 1)
    if sequential[0] == "ok":
        assert sequential[1] == text  # round-trip is part of the baseline
    if engaged is not None:
        assert engages(compiled, text) is engaged, (key, "engagement")
    for cores in _CORES:
        split = _outcome(compiled, text, cores)
        assert split == sequential, (key, cores, sequential[0], split[0])


# ── escape runs straddling cut candidates ──────────────────────────────────

_QUOTED = (
    "root ::= entry+\n"
    'entry ::= name "=" value nl\n'
    "name ::= [a-z]+\n"
    "value ::= quoted | word\n"
    "quoted ::= dq qchar* dq\n"
    'qchar ::= [^"\\\\\\n] | esc\n'
    'esc ::= "\\\\" [^\\n]\n'
    "word ::= [a-z0-9]+\n"
    'dq ::= "\\""\n'
    'nl ::= "\\n"\n'
)
"""Entries whose quoted values carry escape RUNS — the parity the interior
skip counts. A cut candidate right after an odd or even backslash run is
exactly where a parity slip would silently mis-skip."""


def _escape_torture(runs: int) -> str:
    """Entries whose values end in growing backslash runs before the quote."""
    out = []
    for n in range(runs):
        backslashes = "\\\\" * (n % 4 + 1)  # 1..4 ESCAPED pairs → 2..8 chars
        key = "k" + "abcdefgh"[: n % 7 + 1]  # [a-z]+ only — no digits
        out.append(f'{key}="v{backslashes}\\""')
    return "\n".join(out) + "\n"


def test_escape_runs_at_every_cut_candidate_are_faithful() -> None:
    """Odd/even escape runs immediately before closing quotes, at document
    scale, so several cut candidates land adjacent to a run."""
    text = _escape_torture(1400)
    assert len(text) > 4 * MIN_CHUNK
    assert_faithful(_QUOTED, text, "escape-runs", engaged=True)


def test_a_value_that_is_one_long_escape_run_is_faithful() -> None:
    """One value holding an unbroken 2,000-character escape run — any window
    or piece boundary inside it must not flip the parity."""
    run = "\\\\" * 1000
    entries = [f'aa{n}="x{run}"' for n in range(9)]
    text = "\n".join(entries) + "\n"
    assert_faithful(_QUOTED, text, "one-long-run")


# ── empty instances beside their own family ────────────────────────────────

_CLASSY = (
    "root ::= line+\n"
    "line ::= item+ nl\n"
    "item ::= cls | tok | word\n"
    'cls ::= "[" cchar+ "]" | "[]"\n'
    'tok ::= "<[" [0-9]+ "]>"\n'
    "cchar ::= [a-z0-9-]\n"
    "word ::= [a-z]+\n"
    'nl ::= "\\n"\n'
)
"""The gbnf trap set in one authored grammar: a class family with a
fully-literal empty instance, and a ``<[``…``]>`` construct whose opening's
second character is the class family's lead."""


def _classy_line(n: int) -> str:
    """One line mixing every collision the family analysis must survive."""
    parts = [
        "[]",  # empty instance
        f"[abc{n % 10}]",  # closed instance
        f"<[{n}]>",  # tok whose "[" must not open a class
        "[]",  # empty instance adjacent to tok
        f"word{'x' * (n % 7)}"[:12].replace("0", "o"),
    ]
    return "".join(p for p in parts if p) or "[]"


def test_empty_instances_and_shared_lead_tokens_are_faithful() -> None:
    """``[]`` beside ``[...]`` beside ``<[...]>``, hundreds of times, at a
    size where the split has real cut candidates."""
    lines = "\n".join(_classy_line(n) for n in range(900))
    text = lines + "\n"
    assert len(text) > 4 * MIN_CHUNK
    assert_faithful(
        _CLASSY, text.replace("wordx", "word"), "empty-instance", engaged=True
    )


def test_adjacent_empty_instances_and_a_tok_at_document_end_are_faithful() -> None:
    """``[][][]`` runs and a ``<[..]>`` as the FINAL item before the last
    newline — the closer search must not read past the document tail."""
    text = ("[][][]<[1]>\n" * 400) + "[][]<[99]>\n"
    assert_faithful(_CLASSY, text, "tail-tok")


# ── trailing-literal closers whose tail prefix flirts with the closer ──────

_TAILED = (
    "root ::= row+\n"
    "row ::= cell+ nl\n"
    "cell ::= span | plain\n"
    'span ::= "<[" digits tail\n'
    'tail ::= "]>" | "-" digits "]>"\n'
    "digits ::= [0-9]+\n"
    "plain ::= [a-z]+\n"
    'nl ::= "\\n"\n'
)
"""The tok-id shape verbatim: the closer ``]>`` is reached through a two-armed
tail whose second arm carries interior content (``-`` digits) before it."""


def test_trailing_literal_closers_with_both_tail_arms_are_faithful() -> None:
    """Both tail arms interleaved densely — every region's interior carries
    the ``-`` prefix content the opacity obligation must cover."""
    rows = []
    for n in range(700):
        rows.append(f"ab<[{n}]>cd<[{n}-{n * 7}]>ef")
    text = "\n".join(rows) + "\n"
    assert len(text) > 4 * MIN_CHUNK
    assert_faithful(_TAILED, text, "tail-arms", engaged=True)


def test_an_unclosed_span_refuses_identically_everywhere() -> None:
    """A ``<[`` that never closes: sequential refuses; every worker count
    must refuse with the same exception and message, never hang or accept."""
    good = "\n".join(f"ab<[{n}]>" for n in range(600))
    text = good + "\nzz<[123\n"
    assert_faithful(_TAILED, text, "unclosed-span")


# ── admission mimicry on valid continuation lines ──────────────────────────

_RULEY = (
    "root ::= defn+\n"
    "defn ::= name colons body nl\n"
    "name ::= [a-z] [a-z0-9]*\n"
    'colons ::= " ::= "\n'
    "body ::= piece morep*\n"
    "morep ::= sep piece\n"
    'sep ::= "\\n  | "\n'
    "piece ::= [a-z]+ | lit\n"
    "lit ::= dq [a-z:= ]* dq\n"
    'dq ::= "\\""\n'
    'nl ::= "\\n"\n'
)
"""Multi-line definitions whose continuation lines BEGIN with noise then
lowercase — near-misses for the ``H+ noise* L`` admission — and whose quoted
literals may spell ``::=`` outright. Only real definition heads may admit."""


def _ruley_doc(defs: int) -> str:
    """A document of multi-line definitions — three continuations each.

    Alternative names are letters, not digits: ``piece ::= [a-z]+`` derives no
    digit, so ``alt0`` made the whole document unparseable and the test
    compared two REFUSALS rather than two parses.
    """
    out = []
    for n in range(defs):
        name = f"rule{n:04d}"
        cont = "\n  | ".join(f"alt{c}" for c in "abc")
        out.append(f'{name} ::= {cont}\n  | " ::= inside a literal "')
    return "\n".join(out) + "\n"


def test_continuation_lines_and_quoted_definition_mimics_are_faithful() -> None:
    """Two-thirds of all newlines here are continuations, and every fourth
    definition carries a quoted ``::=`` — the admission must land only on
    genuine heads, and the result must be byte-exact regardless.

    The unit emits its own mark, so ``terminates_once`` rightly refuses — but
    the unit ANNOUNCES itself (``name " ::= "``), so the boundary proof
    certifies and the terminated plan filters candidates through the same
    admission the envelope path runs. Of this document's 1,040 newlines only
    ~260 begin a definition; the rest are continuations, and a match starting
    after one begins on a space, which the head charset rejects."""
    text = _ruley_doc(260)
    assert len(text) > 4 * MIN_CHUNK
    assert_faithful(_RULEY, text, "mimic-heads", engaged=True)


# ── marks that exist only inside certified interiors ───────────────────────


def test_a_document_whose_only_marks_are_inside_strings_declines_exactly() -> None:
    """Every newline lives inside a quoted value except the final one: zero
    usable candidates. The split must decline to sequential — and prove it by
    producing the identical model, not by erroring."""
    body = "".join(f"line{n}\\n" for n in range(1200))  # ESCAPED newlines
    text = f'k="{body}"\n'
    source = (
        "root ::= entry+\n"
        'entry ::= name "=" quoted nl\n'
        "name ::= [a-z]+\n"
        "quoted ::= dq qchar* dq\n"
        'qchar ::= [^"\\\\] | esc\n'
        'esc ::= "\\\\" [^\\n]\n'
        'dq ::= "\\""\n'
        'nl ::= "\\n"\n'
    )
    assert_faithful(source, text, "marks-in-strings", engaged=False)


# ── edges: marks at offset zero, the tail, and single-unit documents ───────

_LINES = 'root ::= line+\nline ::= [a-z0-9]* nl\nnl ::= "\\n"\n'


def test_empty_first_units_and_a_mark_at_offset_zero_are_faithful() -> None:
    """The document STARTS with its mark (an empty first line), repeats empty
    lines mid-document, and ends on the mark — every off-by-one a cut
    selection could make is adjacent to a real boundary here."""
    text = "\n" + "\n".join(f"l{n}" if n % 5 else "" for n in range(2600)) + "\n"
    assert len(text) > 4 * MIN_CHUNK
    assert_faithful(_LINES, text, "edge-marks", engaged=True)


def test_a_single_unit_document_above_the_floor_declines_exactly() -> None:
    """One unit larger than every floor multiple: nothing to cut, at any
    worker count — the decline must be silent and exact."""
    text = "x" * (6 * MIN_CHUNK) + "\n"
    assert_faithful(_LINES, text, "single-unit", engaged=False)


# ── same-spelling families must refuse together, and stay exact ────────────

_TWINS = (
    "root ::= item+\n"
    "item ::= a | b | plain\n"
    'a ::= "%" [a-z]+ ";"\n'
    'b ::= "%" [0-9]+ "!"\n'
    "plain ::= [a-z0-9 ]+ nl\n"
    'nl ::= "\\n"\n'
)
"""Two constructs with the IDENTICAL opening spelling and different closers —
certification must refuse both (no region may be skipped), and the split must
remain faithful with the interiors READ, not skipped."""


def test_identical_openings_with_different_closers_stay_faithful() -> None:
    """``engaged=False`` is an HONEST DECLINE, and the reason is the grammar's
    own: the unit's arms end ``;``, ``!`` and a newline, so no terminator
    exists for any conjunction over them to agree on — not at one character
    and not at any wider spelling. The twin regions also correctly refuse
    certification (identical opening, different closers) and nothing
    separates. A unit whose arms genuinely end three ways has no boundary to
    cut on; the faithfulness half is the live assertion.

    The document DERIVES, which is what makes that half say anything: ``plain``
    carries its own newline, so a bare run of text between two twins is not an
    item and a document written that way compares two refusals rather than two
    parses."""
    text = "".join(f"%abc;%{n}!post {n} here\n" for n in range(800))
    assert len(text) > 4 * MIN_CHUNK
    compiled = compile_text(_TWINS, cache_key="adv-faith-twin-openers")
    assert compiled.parse(text, cores=1).to_text() == text
    assert_faithful(_TWINS, text, "twin-openers", engaged=False)


# ── malformed documents refuse identically at every count ──────────────────


@pytest.mark.parametrize(
    "corrupt",
    ["truncate-mid-escape", "truncate-mid-span", "junk-tail"],
)
def test_corrupted_documents_refuse_identically(corrupt: str) -> None:
    """Refusal parity is half the faithfulness contract; these documents die
    at three different phases of a piece parse."""
    base = "\n".join(f"ab<[{n}]>" for n in range(600)) + "\n"
    if corrupt == "truncate-mid-escape":
        source, text = _QUOTED, ('aa="v\\\\')
    elif corrupt == "truncate-mid-span":
        source, text = _TAILED, base[:-1] + "<["
    else:
        source, text = _TAILED, base + "\x00\x00"
    assert_faithful(source, text, f"corrupt-{corrupt}")


# ── multi-character marks: assembled boundaries and their counterexample ───

_ASSEMBLING = (
    'doc ::= para (bl para)*\nbl ::= "\\n\\n"\npara ::= line+\nline ::= [a-z]* "\\n"\n'
)
"""Lines may be EMPTY, so two of them stand as the separator's own spelling.
No ATOM of ``para`` spells ``"\\n\\n"`` — an atom-wise proof certifies this
owner — and ``para`` derives it at the join, which is what makes the wrong cut
produce two individually valid pieces that stitch to a model sequential does
not build. Piece validity cannot catch it; only the junction analysis can."""

_SAFE = _ASSEMBLING.replace("[a-z]*", "[a-z]+")
"""One character apart: every line opens with a letter, so the join cannot
assemble the separator and every occurrence of it is a real boundary."""


def _paragraphs(count: int, lines: int = 6) -> str:
    """Paragraphs of non-empty lines, joined by the two-character separator."""
    words = [
        "".join(
            "abcdefghijklmnopqrstuvwxyz"[(n + k) % 26] * (3 + k % 5) + "\n"
            for k in range(lines)
        )
        for n in range(count)
    ]
    return "\n\n".join(words)


def test_an_assembling_owner_declines_and_stays_faithful() -> None:
    """The permanent adversarial pair, first half. Every paragraph boundary
    here is a valid cut candidate the atom-wise proof would admit; the
    assembly analysis refuses the owner, so the split declines outright and
    the document parses sequentially — byte- and model-identical."""
    text = _paragraphs(400)
    assert len(text) > 4 * MIN_CHUNK
    assert_faithful(_ASSEMBLING, text, "assembling", engaged=False)


def test_a_safe_owner_engages_on_the_two_character_separator() -> None:
    """The pair's second half, and the non-vacuity that makes the first half
    mean something: the same document under the grammar whose join cannot
    assemble the mark ENGAGES, and every boundary here reads as a run of three
    newlines whose last occurrence is the separator."""
    text = _paragraphs(400)
    assert len(text) > 4 * MIN_CHUNK
    assert_faithful(_SAFE, text, "safe-assembly", engaged=True)


_PROSE = (
    "doc ::= block (sep block)*\n"
    'sep ::= "\\n\\n"\n'
    "block ::= word (sp word)*\n"
    "word ::= [a-z0-9]+\n"
    'sp ::= " "\n'
)
"""Prose blocks separated by a blank line — the boundary is TWO characters,
which is the whole reason this shape derived no plan at all before."""


def test_prose_blocks_separated_by_a_blank_line_engage() -> None:
    """The D2 witness that was blocked by mark ARITY, not by the absence of an
    announcing prefix: nothing about the analysis of this grammar was hard,
    its boundary was simply unspellable."""
    text = "\n\n".join(" ".join(f"w{n}x{k}" for k in range(20)) for n in range(300))
    assert len(text) > 4 * MIN_CHUNK
    assert_faithful(_PROSE, text, "prose-blocks", engaged=True)


_FREE_LINES = (
    "doc ::= para+\n"
    "para ::= line+ blank\n"
    "line ::= [a-z0-9 ]+ nl\n"
    "blank ::= nl\n"
    'nl ::= "\\n"\n'
)
"""Free-text lines closed by a blank line. The paragraph's terminator is
ASSEMBLED — the last line's own newline plus the blank one — so it is the
wider spelling that certifies, not the newline every line carries."""


def _free_text(paras: int, lines: int = 5) -> str:
    """Paragraphs of free-text lines, each closed by a blank line."""
    return "".join(
        "".join(f"line {n} of para {p}\n" for n in range(lines)) + "\n"
        for p in range(paras)
    )


def test_free_text_lines_with_a_blank_line_boundary_engage() -> None:
    """``terminates_once`` refuses the newline — every line carries one — and
    certifies the blank-line spelling, whose only occurrence in a paragraph is
    its closing edge."""
    text = _free_text(300)
    assert len(text) > 4 * MIN_CHUNK
    assert_faithful(_FREE_LINES, text, "free-text-lines", engaged=True)


def test_free_text_lines_that_may_be_empty_decline() -> None:
    """One character apart again: allow an empty line and the paragraph
    assembles its own terminator internally, so the wider spelling stops being
    a boundary and the plan declines."""
    source = _FREE_LINES.replace("line ::= [a-z0-9 ]+ nl", "line ::= [a-z0-9 ]* nl")
    text = _free_text(300)
    assert_faithful(source, text, "free-text-empty-lines", engaged=False)


def test_runs_of_the_mark_never_cut_adjacent_or_empty() -> None:
    """Overlapping occurrences at every cut target. Under the SAFE grammar a
    paragraph ends with a newline and the separator is two, so EVERY boundary
    reads as a run of three and offers two occurrences — one of them false.
    Naive left-to-right scanning would take both and leave an empty piece
    between them; the run thins to one boundary, and the pieces prove it."""
    text = _paragraphs(400)
    compiled = compile_text(_SAFE, cache_key="adv-faith-mark-runs")
    plans = _safe_plans(
        _split_plans(compiled.codegen_grammar),
        compiled.split_analysis or compiled.grammar,
    )
    assert len(plans) == 1 and plans[0].trailing
    with PoolLease(8) as pool:
        cuts = _cut_offsets(plans[0], text, 8, pool)
    assert len(cuts) > 1
    assert all(text.startswith("\n\n", at) for at in cuts)
    assert all(later - earlier >= MIN_CHUNK for earlier, later in zip(cuts, cuts[1:]))
    assert_faithful(_SAFE, text, "mark-runs", engaged=True)


_HIDDEN_BLANKS = (
    "root ::= entry+\n"
    "entry ::= lb piece* rb\n"
    'lb ::= "<"\n'
    'rb ::= ">\\n\\n"\n'
    "piece ::= word | nl\n"
    "word ::= [a-z]+\n"
    'nl ::= "\\n"\n'
)
"""A certified interior whose body can spell the two-character mark: the
newlines between pieces are TEXT, and only the closer's own pair is a
boundary. The interior is what the scan must skip whole at the new arity —
reading into it would offer a cut in the middle of an entry."""


def test_a_two_character_mark_inside_a_certified_interior_stays_skipped() -> None:
    """Every entry here carries a blank line INSIDE its delimited body and one
    at its close. The interior skip must cover the wider mark exactly as it
    covers a character, or the interior blanks become cut candidates."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    text = "".join(
        f"<{letters[n % 26] * 4}\n\n{letters[(n + 3) % 26] * 3}\n>\n\n"
        for n in range(900)
    )
    assert len(text) > 4 * MIN_CHUNK
    # Half of every blank line in this document stands INSIDE an interior.
    assert text.count("\n\n") == 2 * text.count(">\n\n")
    assert_faithful(_HIDDEN_BLANKS, text, "interior-blanklines", engaged=True)


def test_an_ambiguous_document_refuses_identically_at_every_count() -> None:
    """Two arms deriving the same strings: sequential refuses rather than
    picking, and the split must reach the SAME refusal at every worker count.
    It does so by declining — a piece that refuses is a verdict on the split,
    never on the input, so the caller's sequential parse is what raises."""
    source = (
        "doc ::= item (sep item)*\n"
        'sep ::= "\\n\\n"\n'
        "item ::= one | two\n"
        "one ::= [a-z]+\n"
        "two ::= [a-z]+\n"
    )
    text = "\n\n".join("word" * 40 for _n in range(200))
    compiled = compile_text(source, cache_key="adv-faith-ambiguous-blocks")
    with pytest.raises(LexicError, match="ambiguous"):
        compiled.parse(text, cores=1)
    assert_faithful(source, text, "ambiguous-blocks", engaged=False)


# ── the review's own counterexample, pinned at document scale ─────────────
#
# ``proto/proto17_assembly.py`` (under the gitignored work directory, not a
# package a committed test may import) is what refuted the design's original
# soundness claim. Its grammar and document are restated here rather than
# imported. The engagement claims themselves — the assembling owner declines
# and stays faithful, the safe control engages — are already pinned above by
# ``test_an_assembling_owner_declines_and_stays_faithful`` and
# ``test_a_safe_owner_engages_on_the_two_character_separator`` using the same
# grammars at stress-test scale; this pin is the complementary one: the
# review's own WRONG-CUT demonstration, encoded as an assertion instead of a
# printed narrative.

_REVIEW_ASSEMBLING = (
    'doc ::= para (bl para)*\nbl ::= "\\n\\n"\npara ::= line+\nline ::= [a-z]* "\\n"\n'
)
_REVIEW_MARK = "\n\n"
_REVIEW_DOC = "a\n\n\nb\n"
"""Two overlapping occurrences of the mark, at offsets 1 and 2."""


def test_the_reviews_wrong_cut_produces_two_individually_valid_pieces() -> None:
    """The counterexample's own point. ``"\\n\\n"`` occurs at offsets 1 and 2;
    offset 1 self-rejects (its head piece, ``"a"``, carries no line's own
    newline at all), but offset 2 does NOT — ``"a\\n"`` and ``"b\\n"`` BOTH
    parse on their own, even though sequential builds ONE para holding the
    interior empty lines, not two. Piece validity cannot tell this cut from
    a real boundary; that is exactly why the assembly analysis exists, and
    exactly why the grammar must decline at the public seam rather than ever
    risk taking it (the engagement pin below is what enforces that)."""
    compiled = compile_text(_REVIEW_ASSEMBLING, cache_key="i17-pin-review-wrong-cut")

    self_rejecting_head = _REVIEW_DOC[:1]
    with pytest.raises(LexicError):
        compiled.parse(self_rejecting_head, cores=1)

    wrong_head = _REVIEW_DOC[:2]
    wrong_tail = _REVIEW_DOC[2 + len(_REVIEW_MARK) :]
    compiled.parse(wrong_head, cores=1)  # does not raise: a valid piece
    compiled.parse(wrong_tail, cores=1)  # does not raise: a valid piece — the trap


def test_the_reviews_document_never_engages_at_any_worker_count() -> None:
    """The document is far below the 2 KiB split floor, so it never engages
    for size alone — but the assembly declines it independently, and the
    small scale is what makes the wrong-cut pieces above checkable by hand.
    Sequential is the only path this document ever takes, at any requested
    worker count, and every count agrees with it."""
    compiled = compile_text(_REVIEW_ASSEMBLING, cache_key="i17-pin-review-engage")
    sequential = compiled.parse(_REVIEW_DOC, cores=1)
    for cores in (2, 3, 8):
        assert not engages(compiled, _REVIEW_DOC, cores)
        assert compiled.parse(_REVIEW_DOC, cores=cores) == sequential
