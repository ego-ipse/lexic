"""The windowed find answers exactly what the serial walk answers.

`par_find` divides a document into arithmetic windows, walks each with a stack
that may underflow, and replays the events it could not settle against one
stack. That is a different algorithm reaching the same answer, so the only
acceptable evidence is region-for-region equality with `find` — count, offsets,
rule, separators and ORDER — over every shape the roster and the ground truth
can produce, at several window counts, with the windows deliberately falling in
the middle of regions.

Vacuity is the failure mode this kind of differential invites, and in two ways
here. Two empty lists compare equal; and a grammar whose vocabulary carries an
opaque interior is REFUSED the windows by design, so comparing it proves only
that the refusal returns the serial answer. Both ground-truth json grammars
quote their strings and are refused — so the windowed path is exercised through
grammars asserted to be skip-free, and `test_the_windowed_path_is_taken` fails
if that ever stops being true.
"""

from __future__ import annotations

import random

import pytest

from lexic.compile import compile_from_path, compile_text
from lexic.parsing.parallel.discovery import regions
from lexic.parsing.parallel.discovery.regions import _vocabulary, find, par_find
from tests.paths import GROUND_TRUTH
from tools.benchmark.cases.grammars import BENCHES

SKIPPING_GRAMMARS = ("json.gbnf", "json.abnf")
"""Both ground-truth json formulations. Both quote strings, so both are
refused the windows — which is what they are here to pin."""

WINDOWS = (1, 2, 3, 5, 8, 16)
"""Six counts, including one and two primes, so no result rests on an even
division of the document."""

MIN_SPANS = (0, 64)
"""The floor a scheduling caller passes, and no floor at all."""

BRACKETS = (
    "root ::= obj\n"
    'obj ::= "{" entry ("," entry)* "}"\n'
    "entry ::= word | arr | obj\n"
    'arr ::= "[" entry ("," entry)* "]"\n'
    "word ::= [a-z0-9]+\n"
)
"""A nested bracket grammar with NO opaque interior, so it is windowed.

Authored here rather than borrowed: the ground-truth json grammars quote their
strings and take the serial walk, so they cannot exercise this path at all.
"""


OVERLAP = (
    'root ::= "[" items "]"\n'
    'items ::= item ("|" item)*\n'
    'item ::= "(" inner "|"\n'
    "inner ::= [a-z0-9]+\n"
)
"""A grammar whose SEPARATOR is also a CLOSER: ``|`` ends an item and divides
the list.

The first fixture cannot catch a sweep that visits a two-role character twice,
because its roles are disjoint and so is every eligible bench grammar's. This
one holds the property on purpose, and `test_the_overlap_fixture_really_overlaps`
fails if it ever stops holding it.
"""


def overlap_document(items: int) -> str:
    """A document of the overlap grammar — every ``|`` wears both roles."""
    return "[" + "|".join(f"(w{i}|" for i in range(items)) + "]"


def bracket_document(records: int) -> str:
    """One long object over many nested short ones."""
    body = ",".join(
        f"k{i},[a{i},b{i},[c{i},d{i}]],{{e{i},f{i}}}" for i in range(records)
    )
    return "{" + body + "}"


def ragged(seed: int) -> str:
    """A fuzzed bracket soup — nesting, imbalance and stray separators.

    Deliberately not a sentence of any grammar: `find` is a SCAN, it runs on
    whatever bytes arrive, and the windowed form has to agree with it on
    malformed input too. Imbalance is where underflow actually happens.
    """
    rng = random.Random(seed)
    alphabet = ["{", "}", "[", "]", ",", "a", "bb", " ", "\n"]
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(200, 600)))


def windowed(grammar) -> bool:
    """Whether this grammar's vocabulary is eligible for the windows."""
    return not _vocabulary(grammar).skips


def both_finds(grammar, text: str, min_span: int, windows: int):
    """`(serial, windowed)` over one grammar, document and window count."""
    return find(grammar, text, min_span), par_find(grammar, text, min_span, windows)


# ── the windowed path itself ──────────────────────────────────────────────


def test_the_windowed_path_is_taken() -> None:
    """The grammars this file windows really are eligible, and bear regions.

    If this fails, every equality below is comparing the serial walk with
    itself and the file is worth nothing.
    """
    fixture = compile_text(BRACKETS).codegen_grammar
    assert windowed(fixture), "the authored fixture grew an opaque interior"
    assert len(find(fixture, bracket_document(40), 0)) >= 40

    eligible = {
        b.name: len(find(b.compiled.codegen_grammar, b.corpus))
        for b in BENCHES
        if windowed(b.compiled.codegen_grammar)
        and find(b.compiled.codegen_grammar, b.corpus)
    }
    assert len(eligible) >= 2, f"only {eligible} are both windowed and bearing"
    assert sum(eligible.values()) >= 100, f"too few regions to compare: {eligible}"


@pytest.mark.parametrize("windows", WINDOWS)
@pytest.mark.parametrize("min_span", MIN_SPANS)
def test_the_bracket_fixture_windows_identically(min_span: int, windows: int) -> None:
    """A skip-free nested grammar, both floors, six window counts."""
    fixture = compile_text(BRACKETS).codegen_grammar
    serial, parallel = both_finds(fixture, bracket_document(60), min_span, windows)
    assert parallel == serial
    assert serial, "the fixture found no regions — the comparison proved nothing"


@pytest.mark.parametrize("windows", WINDOWS)
@pytest.mark.parametrize("min_span", MIN_SPANS)
@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_every_bench_grammar_windows_identically(
    bench, min_span: int, windows: int
) -> None:
    """Every benchmark grammar over its own corpus, eligible or not."""
    serial, parallel = both_finds(
        bench.compiled.codegen_grammar, bench.corpus, min_span, windows
    )
    assert parallel == serial


@pytest.mark.parametrize("windows", WINDOWS)
@pytest.mark.parametrize("seed", range(12))
def test_ragged_documents_window_identically(seed: int, windows: int) -> None:
    """Fuzzed bracket soup — imbalance is where the merge earns its keep."""
    fixture = compile_text(BRACKETS).codegen_grammar
    serial, parallel = both_finds(fixture, ragged(seed), 0, windows)
    assert parallel == serial, f"seed {seed}, {windows} windows"


def test_the_ragged_corpus_reaches_the_merge() -> None:
    """The fuzz produces regions at all, rather than passing on empty lists."""
    fixture = compile_text(BRACKETS).codegen_grammar
    found = sum(len(find(fixture, ragged(seed), 0)) for seed in range(12))
    assert found >= 12, f"the ragged corpus produced only {found} regions"


@pytest.mark.parametrize("windows", (2, 5, 16))
def test_a_window_boundary_inside_a_region_is_handled(windows: int) -> None:
    """The cut lands mid-region by construction, not by luck."""
    fixture = compile_text(BRACKETS).codegen_grammar
    text = bracket_document(200)
    serial = find(fixture, text, 0)
    widest = max(serial, key=lambda region: region.span)
    assert widest.opener < len(text) // windows < widest.closer, (
        "the fixture must straddle the first boundary"
    )
    assert par_find(fixture, text, 0, windows) == serial


def test_one_window_and_many_agree() -> None:
    """One window is the serial answer; the division is not what finds regions."""
    fixture = compile_text(BRACKETS).codegen_grammar
    text = bracket_document(120)
    assert par_find(fixture, text, 0, 1) == par_find(fixture, text, 0, 9)


# ── a character that is BOTH a closer and a separator ─────────────────────


def test_the_overlap_fixture_really_overlaps() -> None:
    """The fixture holds the property the sweep bug needs to show itself.

    Without a character in both roles the windowed sweep and the serial sweep
    cannot disagree, and every case below would pass on a broken sweep.
    """
    vocab = _vocabulary(compile_text(OVERLAP).codegen_grammar)
    both = set(vocab.closers) & set(vocab.marks)
    assert both, f"no character is both closer and separator: {vocab}"
    assert windowed(compile_text(OVERLAP).codegen_grammar)


@pytest.mark.parametrize("windows", WINDOWS)
@pytest.mark.parametrize("min_span", MIN_SPANS)
def test_a_two_role_character_windows_identically(min_span: int, windows: int) -> None:
    """A separator that is also a closer, every window count, both floors."""
    fixture = compile_text(OVERLAP).codegen_grammar
    serial, parallel = both_finds(fixture, overlap_document(80), min_span, windows)
    assert parallel == serial
    assert serial, "the overlap fixture found no regions"


@pytest.mark.parametrize("windows", WINDOWS)
@pytest.mark.parametrize("seed", range(8))
def test_ragged_two_role_documents_window_identically(seed: int, windows: int) -> None:
    """The fuzz, under the overlap grammar — imbalance plus a doubled role."""
    fixture = compile_text(OVERLAP).codegen_grammar
    rng = random.Random(seed)
    alphabet = ["[", "]", "(", "|", "a", "wq", " ", "\n"]
    text = "".join(rng.choice(alphabet) for _ in range(rng.randint(200, 600)))
    serial, parallel = both_finds(fixture, text, 0, windows)
    assert parallel == serial, f"seed {seed}, {windows} windows"


# ── the refusal: an opaque interior takes the serial walk ─────────────────


@pytest.mark.parametrize("windows", (2, 8))
@pytest.mark.parametrize("min_span", MIN_SPANS)
@pytest.mark.parametrize("name", SKIPPING_GRAMMARS)
def test_a_quoted_grammar_is_refused_and_still_answers(
    name: str, min_span: int, windows: int
) -> None:
    """Both ground-truth json grammars carry a skip, so both take the walk.

    Pinned through the public entry: whatever route it takes, the answer is
    the serial one, and the eligibility is asserted rather than assumed.
    """
    grammar = compile_from_path(GROUND_TRUTH / name).codegen_grammar
    assert not windowed(grammar), f"{name} no longer carries an opaque interior"
    document = (
        "{"
        + ", ".join(f'"k{i}": [1, 2, {{"b": "x, y"}}, "]"]' for i in range(40))
        + ', "e": "{"}'
    )  # one long outer object, so a 64-character floor discriminates
    serial, parallel = both_finds(grammar, document, min_span, windows)
    assert parallel == serial
    assert serial, f"{name} found no regions — the comparison proved nothing"


# ── the differential can fail ─────────────────────────────────────────────


@pytest.mark.parametrize("windows", (2, 4, 8))
def test_a_sabotaged_merge_diverges(windows: int) -> None:
    """Replaying the windows out of order must NOT pass.

    Order is the merge's whole contract; a comparison that cannot see it
    broken is not evidence that it holds.
    """
    fixture = compile_text(BRACKETS).codegen_grammar
    text = bracket_document(60)
    honest = par_find(fixture, text, 0, windows)
    assert honest == find(fixture, text, 0)
    assert honest, "the fixture must produce regions for sabotage to mean anything"

    real = regions.merge_windows
    try:
        regions.merge_windows = lambda chunks, min_span: real(chunks[::-1], min_span)
        assert par_find(fixture, text, 0, windows) != honest
    finally:
        regions.merge_windows = real


@pytest.mark.parametrize("windows", (2, 8))
def test_dropping_underflow_events_diverges(windows: int) -> None:
    """A window that kept its unresolved events to itself must NOT pass.

    The events ARE the mechanism: without them each window answers only about
    brackets it both opened and closed, which is a different question.
    """
    fixture = compile_text(BRACKETS).codegen_grammar
    text = bracket_document(60)
    honest = par_find(fixture, text, 0, windows)
    assert honest, "the fixture must produce regions for sabotage to mean anything"

    real = regions.merge_windows
    try:
        regions.merge_windows = lambda chunks, min_span: real(
            [[e for e in chunk if e[0] == regions.R_DONE] for chunk in chunks],
            min_span,
        )
        assert par_find(fixture, text, 0, windows) != honest
    finally:
        regions.merge_windows = real
