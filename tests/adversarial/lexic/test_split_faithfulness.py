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
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.parallel.policy import MIN_CHUNK
from lexic.parsing.products import parse_model

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


def _engages(compiled, text: str) -> bool:
    """Whether the split entry itself takes the document at eight workers.

    Faithfulness alone can pass VACUOUSLY — a case that always declines never
    exercises a cut. Each case therefore states whether it expects the split
    to engage, and that expectation is asserted through the real entry.
    """
    found = split_model(
        parse_model,
        compiled.codegen_grammar,
        Request(text, compiled.fold, None),
        8,
        analysis=compiled.split_analysis or compiled.grammar,
    )
    return found is not None


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
        assert _engages(compiled, text) is engaged, (key, "engagement")
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
    out = []
    for n in range(defs):
        name = f"rule{n:04d}"
        cont = "\n  | ".join(f"alt{k}" for k in range(3))
        out.append(f'{name} ::= {cont}\n  | " ::= inside a literal "')
    return "\n".join(out) + "\n"


def test_continuation_lines_and_quoted_definition_mimics_are_faithful() -> None:
    """Two-thirds of all newlines here are continuations, and every fourth
    definition carries a quoted ``::=`` — the admission must land only on
    genuine heads, and the result must be byte-exact regardless.

    ``engaged=False`` is a DOCUMENTED COVERAGE GAP, not a success: the unit
    emits its own mark (continuation newlines), so the terminated plan's
    proof refuses — and the boundary-certified admission that handles exactly
    this for envelope/separated shapes is not wired to terminated plans.
    TODO_p2 2b carries it; flip to ``True`` when it lands."""
    text = _ruley_doc(260)
    assert len(text) > 4 * MIN_CHUNK
    assert_faithful(_RULEY, text, "mimic-heads", engaged=False)


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
    """``engaged=False`` is a DOCUMENTED COVERAGE GAP: the twin regions
    correctly refuse certification (identical opening, different closers),
    the units end differently so no terminator derives, and nothing
    separates — the D2 class TODO_p2 2b/2c is scheduled to cover. The
    faithfulness half is the live assertion; flip when 2b lands."""
    text = "\n".join(f"pre {n} %abc; mid %{n}! post" for n in range(800)) + "\n"
    assert len(text) > 4 * MIN_CHUNK
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
