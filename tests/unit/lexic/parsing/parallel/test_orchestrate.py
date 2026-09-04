"""Tests for ``lexic.parsing.parallel.orchestrate`` — the split parse.

The contract is equality, not speed: a split parse produces the model the
sequential parse produces, or it IS the sequential parse. Every shape the
stitch does not support, and every failing chunk, falls back — so what an
input MEANS never depends on how many workers ran.
"""

from __future__ import annotations

import string

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing import parse_model
from lexic.parsing.parallel import orchestrate, split_model, split_plan
from lexic.parsing.parallel.orchestrate import (
    Request,
    _certified,
    _split_plans,
)
from lexic.parsing.parallel.plan.cuts import cut_offsets, scan_marks, sole_mark
from lexic.parsing.parallel.plan.envelope import admits
from lexic.parsing.parallel.plan.split import SplitPlan
from lexic.parsing.parallel.policy import AUTO, MIN_CHUNK
from lexic.parsing.parallel.pool import WorkPool
from tests.unit.lexic.parsing.parallel.envelope_fixtures import (
    CONTINUATION_SOURCE,
    TWO_MARK_SOURCE,
)

LEAD_RULE = (
    "root ::= pair tail*\n"
    "tail ::= comma pair\n"
    'comma ::= "," ws\n'
    'pair ::= [a-z]+ ":" [0-9]+\n'
    'ws ::= " "*\n'
)
BARE_LEAD = 'root ::= word more*\nmore ::= "|" word\nword ::= [a-z]+\n'
NO_SPLIT = 'root ::= "a" [b-z]+\n'
TERMINATED = 'root ::= line+\nline ::= [a-z]+ "\\n"\n'
BACKTRACK = """root ::= stmt+
stmt ::= block | bind
block ::= prefix ident open close " {" atom "}" eol
bind ::= prefix ident open close " = " atom ";" eol
prefix ::= "def "
ident ::= [a-z] [a-z0-9]*
atom ::= [a-z0-9]+
open ::= "("
close ::= ")"
eol ::= "\\n"
"""
FENCE = """root ::= fence+
fence ::= "```" nl line* "```" nl
line ::= [a-z]+ nl
nl ::= "\\n"
"""
DIRECT_GROUP = """root ::= doc
doc ::= group
group ::= "(" node ("," node)* ")"
node ::= leaf | group
leaf ::= [a-z]+
"""
TRUE_GROUP = """group ::= "(" node ("," node)* ")"
node ::= leaf | group
leaf ::= [a-z]+
"""
ROUTED_ALTERNATIVES = """root ::= expr
expr ::= number (addop number)*
addop ::= "+" | "-"
number ::= [0-9]+
"""
ARITHMETIC = """root ::= expr
expr ::= term addtail*
addtail ::= addop term
addop ::= "+" | "-"
term ::= factor multail*
multail ::= mulop factor
mulop ::= "*" | "/"
factor ::= [0-9]+
"""


def _doc(count: int = 40) -> str:
    return ", ".join(f"key{'x' * (i % 7)}:{i}" for i in range(count))


ROUTED_GRAMMAR = """root ::= head body? nl?
head ::= "!" word
body ::= inline | block
inline ::= " " word " >"
block ::= nl line* ">"
line ::= word nl
word ::= [a-z]+
nl ::= "\\n"
"""


def test_a_routed_region_split_never_pays_for_the_bracket_sweep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The routed region is certified against the start rule's own shape; the
    sweep's choice is a size heuristic over whatever brackets a document
    happens to hold. Certainty is tried first, so a grammar whose route engages
    never runs the sweep at all."""
    compiled = compile_text(ROUTED_GRAMMAR)
    line = "abcdefghij"
    text = "!abc\n" + "".join(f"{line[i % 10]}wordy\n" for i in range(900)) + ">"
    swept: list[int] = []
    real_find = orchestrate.find

    def counting_find(*args, **kwargs):
        swept.append(1)
        return real_find(*args, **kwargs)

    monkeypatch.setattr(orchestrate, "find", counting_find)
    split = split_model(
        parse_model, compiled.codegen_grammar, Request(text, compiled.product), 8
    )

    assert split is not None, "the routed region must carry this split"
    assert split.to_text() == text
    assert not swept, "a routed split ran the bracket sweep it cannot use"


@pytest.mark.parametrize(
    ("cores", "text"),
    [(1, "x" * (2 * MIN_CHUNK)), (AUTO, "x"), (16, "x")],
)
def test_universal_gates_skip_plan_and_safety_analysis(
    monkeypatch: pytest.MonkeyPatch, cores: int, text: str
) -> None:
    """Policy-declined inputs do not pay for plan, safety, or scan analysis."""
    compiled = compile_text("root ::= [a-z]+\n")

    def unexpected_analysis(*_args, **_kwargs):
        raise AssertionError("parallel analysis ran behind a universal gate")

    monkeypatch.setattr(orchestrate, "_split_plans", unexpected_analysis)
    monkeypatch.setattr(orchestrate, "owner_excludes", unexpected_analysis)
    monkeypatch.setattr(orchestrate, "terminates_once", unexpected_analysis)
    monkeypatch.setattr(orchestrate, "find", unexpected_analysis)

    assert (
        orchestrate.split_model(
            parse_model,
            compiled.codegen_grammar,
            Request(text, compiled.product),
            cores,
        )
        is None
    )


def test_split_equals_sequential_and_round_trips():
    """The headline: same model, exactly, and the text comes back."""
    compiled = compile_text(LEAD_RULE)
    grammar, binding = compiled.codegen_grammar, compiled.product
    text = _doc(1000)
    parallel = split_model(parse_model, grammar, Request(text, binding), 4)
    assert parallel is not None
    assert parallel == parse_model(grammar, text, binding)
    assert parallel.to_text() == text
    assert compiled.parse(text) == parallel


def test_one_work_pool_is_reused_for_scan_and_parse(monkeypatch: pytest.MonkeyPatch):
    """The split phases share one pool lifetime and executor.

    The seam is the LEASE: a split borrows one pool for all of its phases and
    returns it, so intercepting the lease is intercepting every phase. The
    document clears the SCAN floor as well as the chunk floor, so both phases
    are mapped work: below it the scan is one sweep and never reaches a pool.
    """
    compiled = compile_text(LEAD_RULE)
    text = _doc(2000)
    created = 0
    map_calls = 0

    class RecordingPool:
        """Public pool-lease seam that executes mapped work synchronously."""

        def __init__(self, workers: int):
            """Record construction while preserving the worker count."""
            self.workers = workers
            nonlocal created
            created += 1

        def map(self, work, items):
            """Record each phase and preserve WorkPool's ordered result."""
            nonlocal map_calls
            map_calls += 1
            return [work(item) for item in items]

        def slot(self):
            """The one slot this synchronous stand-in ever runs work on."""
            return 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return None

    monkeypatch.setattr(orchestrate, "PoolLease", RecordingPool)
    parallel = orchestrate.split_model(
        parse_model,
        compiled.codegen_grammar,
        Request(text, compiled.product),
        4,
    )

    assert parallel is not None
    assert parallel.to_text() == text
    assert created == 1
    assert map_calls >= 2


@pytest.mark.parametrize("cores", [2, 3, 5, 8])
def test_every_worker_count_gives_one_answer(cores: int):
    """Worker count moves wall-clock, never the value."""
    compiled = compile_text(LEAD_RULE)
    grammar, binding = compiled.codegen_grammar, compiled.product
    text = _doc(1000)
    assert split_model(
        parse_model, grammar, Request(text, binding), cores
    ) == parse_model(grammar, text, binding)


def test_terminated_plain_tuple_chunks_stitch_without_list_coercion():
    """Terminated chunks merge their exact plain-tuple repeated field."""
    compiled = compile_text(TERMINATED)
    text = "one\n" * 2000
    sequential = compiled.parse(text, cores=1)
    parallel = split_model(
        parse_model,
        compiled.codegen_grammar,
        Request(text, compiled.product),
        4,
    )

    assert parallel is not None
    assert tuple(sequential)[0].__class__ is tuple
    assert tuple(parallel)[0].__class__ is tuple
    assert parallel == sequential
    assert parallel.to_text() == text


def test_backtrack_like_terminated_start_split_is_non_vacuous_and_equal():
    """Shared-prefix statement arms still split on their common newline."""
    compiled = compile_text(BACKTRACK)
    text = "".join(
        f"def alpha{i}() {{value}}\ndef beta{i}() = value;\n" for i in range(240)
    )
    grammar, binding = compiled.codegen_grammar, compiled.product
    plan = split_plan(grammar)
    sequential = parse_model(grammar, text, binding)
    parallel = split_model(parse_model, grammar, Request(text, binding), 2)

    assert plan is not None and plan.sep is None
    assert parallel is not None
    assert parallel == sequential
    assert parallel.to_text() == text


def test_direct_group_recurrence_stitches_below_a_wrapper_start():
    """A bracket recurrence can replace its outer model through ``doc``."""
    compiled = compile_text(DIRECT_GROUP)
    text = "(" + ",".join("a" * 20 for _ in range(1000)) + ")"
    grammar, binding = compiled.codegen_grammar, compiled.product
    sequential = parse_model(grammar, text, binding)
    parallel = split_model(parse_model, grammar, Request(text, binding), 8)

    assert parallel is not None
    assert parallel == sequential
    assert parallel.to_text() == text


def test_true_root_group_recurrence_has_no_replaceable_route():
    """A region that is itself the start model declines without a wrapper."""
    compiled = compile_text(TRUE_GROUP)
    text = "(" + ",".join("a" * 20 for _ in range(1000)) + ")"
    grammar, binding = compiled.codegen_grammar, compiled.product

    assert split_model(parse_model, grammar, Request(text, binding), 8) is None
    assert compiled.parse(text, cores=2).to_text() == text


def test_a_bare_literal_lead_splits_too():
    """``more ::= "|" word`` has no lead RULE — the cut text is the literal."""
    compiled = compile_text(BARE_LEAD)
    grammar, binding = compiled.codegen_grammar, compiled.product
    text = "|".join(f"word{'x' * (i % 3)}" for i in range(2000)).replace("0", "")
    assert split_model(parse_model, grammar, Request(text, binding), 4) == parse_model(
        grammar, text, binding
    )


def test_separator_alternatives_split_below_a_sole_wrapper():
    """A routed repeated child stitches back into its unchanged root wrapper."""
    compiled = compile_text(ROUTED_ALTERNATIVES)
    text = "+".join(str(index % 10) * 12 for index in range(1200))
    grammar, binding = compiled.codegen_grammar, compiled.product
    plan = split_plan(grammar)
    sequential = parse_model(grammar, text, binding)
    parallel = split_model(parse_model, grammar, Request(text, binding), 8)

    assert plan is not None and plan.wrappers == ("root",)
    assert plan.mark in ({"+"}, {"-"})
    assert parallel == sequential
    assert parallel is not None and parallel.to_text() == text


def test_empty_outer_arithmetic_tail_routes_to_inner_multiplication():
    """An empty add-tail still exposes the nested multiplication repetition."""
    compiled = compile_text(ARITHMETIC)
    text = "*".join(str(index % 10) * 12 for index in range(1200))
    calls: list[tuple[str, int]] = []

    def recording_parse(grammar, source, fold, resolve=None):
        calls.append((str(grammar.start), len(source)))
        return parse_model(grammar, source, fold, resolve)

    parallel = split_model(
        recording_parse,
        compiled.codegen_grammar,
        Request(text, compiled.product),
        8,
    )

    assert parallel is not None
    assert parallel.to_text() == text
    assert sum(start == "root" for start, _length in calls) == 7
    assert sum(start == "mulop" for start, _length in calls) == 6
    assert not any(start == "addop" for start, _length in calls)


def test_nonempty_outer_arithmetic_tail_uses_outer_separator_route():
    """When add-tail exists, inner multiplication is not split independently."""
    compiled = compile_text(ARITHMETIC)
    terms = ["*".join(str(index % 10) * 12 for index in range(12)) for _ in range(100)]
    text = "+".join(terms)
    calls: list[str] = []

    def recording_parse(grammar, source, fold, resolve=None):
        calls.append(str(grammar.start))
        return parse_model(grammar, source, fold, resolve)

    parallel = split_model(
        recording_parse,
        compiled.codegen_grammar,
        Request(text, compiled.product),
        8,
    )

    assert parallel is not None
    assert parallel == parse_model(compiled.codegen_grammar, text, compiled.product)
    assert parallel.to_text() == text
    assert "addop" in calls
    assert "mulop" not in calls


@pytest.mark.parametrize("cores", [2, 4, 8])
def test_finite_arithmetic_alternatives_preserve_one_document(cores: int):
    """Both finite operator alternatives remain exact at every worker count."""
    compiled = compile_text(ARITHMETIC)
    text = "".join(
        ("" if index == 0 else ("+" if index % 2 == 0 else "-"))
        + f"{index % 10}*{(index + 1) % 10}/{(index + 2) % 10}"
        for index in range(1200)
    )
    sequential = parse_model(compiled.codegen_grammar, text, compiled.product)
    parallel = split_model(
        parse_model,
        compiled.codegen_grammar,
        Request(text, compiled.product),
        cores,
    )

    assert parallel is not None
    assert parallel == sequential
    assert parallel.to_text() == text
    assert any(operator in text for operator in ("+", "-"))
    assert any(operator in text for operator in ("*", "/"))


def test_top_level_cuts_follow_byte_targets_and_clear_the_floor():
    """Variable item sizes still produce byte-balanced full-size chunks."""
    compiled = compile_text(LEAD_RULE)
    lengths = [500] * 4 + [4000] * 4 + [500] * 4 + [4000] * 4
    text = ", ".join("a" * length + ":1" for length in lengths)
    sizes: list[int] = []

    def measured_parse(grammar, part, fold, resolve):
        sizes.append(len(part))
        return parse_model(grammar, part, fold, resolve)

    split = split_model(
        measured_parse,
        compiled.codegen_grammar,
        Request(text, compiled.product),
        4,
    )
    chunks = [size for size in sizes if size >= MIN_CHUNK]

    assert split == parse_model(compiled.codegen_grammar, text, compiled.product)
    assert len(chunks) == 4
    assert max(chunks) - min(chunks) < 2 * MIN_CHUNK


def test_byte_cuts_try_an_adjacent_safe_mark_at_the_floor():
    """A nearest unsafe mark gives way to an adjacent mark and three chunks."""
    compiled = compile_text(LEAD_RULE)

    def item(char: str, body_length: int) -> str:
        return char * body_length + ":1"

    text = ",".join(
        [
            item("a", 1998),
            item("b", 2797),
            item("c", 1397),
            item("d", 1297),
            item("e", 2497),
        ]
    )
    calls: list[int] = []

    def recording_parse(grammar, source, fold, resolve=None):
        if str(grammar.start) == "root":
            calls.append(len(source))
        return parse_model(grammar, source, fold, resolve)

    parallel = orchestrate.split_model(
        recording_parse,
        compiled.codegen_grammar,
        Request(text, compiled.product),
        3,
    )

    assert parallel is not None
    assert parallel.to_text() == text
    assert sorted(calls) == [2499, 2699, 4800]


def test_fence_internal_newlines_decline_without_chunking_inside_the_fence():
    """A final fence newline is unsafe when line newlines occur inside it."""
    compiled = compile_text(FENCE)
    text = "```\na\nb\n```\n```\nc\nd\n```\n"
    calls: list[str] = []

    def recording_parse(grammar, source, fold, resolve=None):
        calls.append(source)
        return parse_model(grammar, source, fold, resolve)

    plan = split_plan(compiled.codegen_grammar)
    sequential = compiled.parse(text, cores=1)
    parallel = split_model(
        recording_parse,
        compiled.codegen_grammar,
        Request(text, compiled.product),
        2,
    )

    assert plan is not None and plan.sep is None
    assert parallel is None
    assert not calls
    assert compiled.parse(text, cores=2) == sequential


def test_a_grammar_without_a_separated_start_has_no_plan():
    """No plan is an answer: ``None`` tells the caller to parse sequentially."""
    compiled = compile_text(NO_SPLIT)
    grammar, binding = compiled.codegen_grammar, compiled.product
    assert split_plan(grammar) is None
    assert split_model(parse_model, grammar, Request("abc", binding), 4) is None


def test_split_model_settles_too_few_workers_before_entering_poollease(
    monkeypatch,
) -> None:
    """Obligation B, the other half (see ``tests/unit/lexic/compile/reduce/
    test_fold.py::test_sub_run_binds_its_sub_parse_at_cores_1`` for the
    first): a reducer fold can issue thousands of tiny ``cores=1`` sub-parses
    from ``_splice_run``, so ``split_model`` must settle "too few workers"
    (``cores=1`` always qualifies) BEFORE it ever takes a pool lease — a fold
    worker's sub-parse must never be the caller that blocks waiting on the
    fold pool's own lease.

    Monkeypatching ``PoolLease.__enter__`` to raise makes "never entered"
    loud: if a future change moved the ``workers < 2`` guard to after the
    lease, this fails outright instead of merely deadlocking under load.
    """

    def _entered_the_lease(self):
        raise AssertionError("PoolLease entered despite workers < 2")

    monkeypatch.setattr(orchestrate.PoolLease, "__enter__", _entered_the_lease)
    compiled = compile_text(LEAD_RULE)
    grammar, binding = compiled.codegen_grammar, compiled.product
    assert split_model(parse_model, grammar, Request(_doc(), binding), 1) is None


def test_a_bad_input_declines_rather_than_inventing_a_refusal():
    """A failing chunk is a verdict on the SPLIT, not on the input: the
    split declines and the caller's sequential parse is what raises."""
    compiled = compile_text(LEAD_RULE)
    grammar, binding = compiled.codegen_grammar, compiled.product
    bad = _doc() + ", 12:not-a-pair"
    assert split_plan(grammar) is not None, "the decline must not be 'no plan'"
    assert split_model(parse_model, grammar, Request(bad, binding), 4) is None
    with pytest.raises(UnsupportedConstructError):
        compiled.parse(bad)


def test_too_few_separators_declines():
    """No cut points, no split — and the artefact still parses it."""
    compiled = compile_text(LEAD_RULE)
    grammar, binding = compiled.codegen_grammar, compiled.product
    text = "only:1"
    assert split_model(parse_model, grammar, Request(text, binding), 8) is None
    assert compiled.parse(text).to_text() == text


def test_plan_is_memoised_per_grammar():
    """The shape analysis runs once per grammar identity."""
    compiled = compile_text(LEAD_RULE)
    grammar = compiled.codegen_grammar
    assert split_plan(grammar) is split_plan(grammar)


ENVELOPE = (
    "root ::= rule cont* tail?\n"
    'rule ::= name ws "=" ws value\n'
    "cont ::= ws crlf rule\n"
    "tail ::= crlf\n"
    "name ::= [a-z]+\n"
    'ws ::= " "*\n'
    "value ::= [a-z]+\n"
    'crlf ::= "\\n"\n'
)


def test_an_ungenerateable_witness_declines_the_envelope_split_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the repeated unit has no derivable witness, the separator span
    cannot be reparsed into a real item model — the split must decline rather
    than reparse without one, and the caller's sequential parse still
    answers correctly."""
    compiled = compile_text(ENVELOPE)
    grammar, binding = compiled.codegen_grammar, compiled.product
    text = "ua = a\nub = b\n" * 2000

    assert split_plan(grammar) is not None

    monkeypatch.setattr(orchestrate, "unit_witness", lambda *_a, **_k: None)
    declined = split_model(parse_model, grammar, Request(text, binding), 8)
    assert declined is None

    sequential = parse_model(grammar, text, binding)
    assert compiled.parse(text, cores=8) == sequential


def test_split_plans_are_memoised_per_grammar_while_cuts_stay_per_document() -> None:
    """The plan tuple is one object per grammar identity — computed once,
    reused — but the cut OFFSETS it produces are a function of the document,
    never cached across two different ones."""
    compiled = compile_text(TWO_MARK_SOURCE, cache_key="two-mark-memo")
    grammar = compiled.codegen_grammar

    assert _split_plans(grammar) is _split_plans(grammar)

    plan = _split_plans(grammar)[1].envelope
    assert plan is not None and plan.mark == "\n"

    short_entries = [f"k{chr(97 + i)} = v" for i in range(26)]
    long_entries = short_entries * 4
    short_text = "\n".join(short_entries)
    long_text = "\n".join(long_entries)

    assert plan.cuts(short_text) != plan.cuts(long_text)


def test_the_orchestrator_engages_a_document_carrying_only_the_second_marks_evidence() -> (
    None
):
    """The tab-marked plan sorts first and finds nothing on a tab-free
    document; the newline-marked plan is what the cascade actually falls
    through to — engaged, exact, and non-vacuous, at the real
    ``split_model`` seam rather than the plan level alone."""
    compiled = compile_text(TWO_MARK_SOURCE, cache_key="two-mark-orchestrate")
    grammar, binding = compiled.codegen_grammar, compiled.product
    entries = [
        f"k{chr(97 + i % 26)}{chr(97 + (i // 26) % 26)} = v" for i in range(2600)
    ]
    text = "\n".join(entries)
    assert len(text) >= 16 * 1024

    sequential = parse_model(grammar, text, binding)
    calls: list[int] = []

    def recording_parse(g, source, f, resolve=None):
        calls.append(len(source))
        return parse_model(g, source, f, resolve)

    split = split_model(recording_parse, grammar, Request(text, binding), 8)
    assert split is not None, "the newline-marked plan must have carried this"
    assert split == sequential
    assert split.to_text() == text
    assert len(calls) >= 2, "only one worker actually parsed"

    assert compiled.parse(text, cores=8) == sequential


# ── the terminated-plan boundary route: SplitPlan.bound ──────────────────

_TWO_ARM_TERMINATOR = (
    "root ::= item+\n"
    "item ::= a nl | b nl\n"
    'a ::= "a" mid\n'
    'b ::= "b" mid\n'
    'mid ::= "\\n" "x"\n'
    'nl ::= "\\n"\n'
)
"""A unit with two arms sharing a final ``nl``: a raw terminated plan
exists, but the unit has no single-arm shape to announce itself, so
``unit_prefix`` returns ``None`` and there is no boundary route either."""


def test_a_terminated_plan_with_an_announcing_prefix_is_certified_with_a_bound() -> (
    None
):
    """``terminates_once`` fails on this unit, but it announces itself, so
    certification takes the boundary route and the certified plan carries
    the proven prefix — the raw (uncertified) plan carries none."""
    compiled = compile_text(CONTINUATION_SOURCE)
    grammar = compiled.codegen_grammar
    plan = split_plan(grammar)

    assert plan is not None and plan.bound is None

    certified = _certified(plan, compiled.split_analysis or compiled.grammar)

    assert certified is not None
    assert certified.bound is not None
    assert certified.bound.literal == " "


def test_a_terminated_plan_without_an_announcing_prefix_is_dropped() -> None:
    """A raw terminated plan exists, but the unit's two arms give
    ``unit_prefix`` no single shape to announce — neither route certifies,
    and the plan is dropped rather than certified with an empty bound."""
    compiled = compile_text(_TWO_ARM_TERMINATOR)
    grammar = compiled.codegen_grammar
    plan = split_plan(grammar)

    assert plan is not None and plan.bound is None
    assert _certified(plan, compiled.split_analysis or compiled.grammar) is None


# ── admission filtering: continuation marks vs genuine heads ─────────────


def _letters(n: int) -> str:
    """A short lowercase-only tag, so a name never carries a digit the
    boundary's ``[a-z]`` head would reject."""
    alpha = string.ascii_lowercase
    return alpha[n % 26] * (n // 26 + 1)


def _continuation_doc(count: int) -> str:
    """Definitions whose bodies carry continuation lines — every mark but
    each definition's own head-announcing newline is a continuation."""
    out = []
    for at in range(count):
        cont = "\n  | ".join(f"alt{c}" for c in "abc")
        out.append(f"rule{_letters(at)} ::= {cont}")
    return "\n".join(out) + "\n"


def _certified_cont_plan() -> SplitPlan:
    """The certified boundary-route plan over :data:`CONTINUATION_SOURCE`."""
    compiled = compile_text(
        CONTINUATION_SOURCE, cache_key="orchestrate-admission-filter"
    )
    grammar = compiled.codegen_grammar
    plan = split_plan(grammar)
    assert plan is not None
    certified = _certified(plan, compiled.split_analysis or compiled.grammar)
    assert certified is not None and certified.bound is not None
    return certified


def test_a_continuation_mark_is_refused_and_a_genuine_head_admits() -> None:
    """``admits`` reads the same ``Boundary`` the static proof certified: a
    mark inside ``sep`` starts on a space, which the ``[a-z]`` head rejects;
    a mark right before the next definition's name admits."""
    certified = _certified_cont_plan()
    assert certified.bound is not None
    text = _continuation_doc(3)

    continuation_mark = text.index("\n  | ")
    assert not admits(
        text, continuation_mark + 1, certified.bound, sole_mark(certified)
    )

    head_mark = text.index("altc\n") + len("altc")
    assert text[head_mark] == "\n"
    assert admits(text, head_mark + 1, certified.bound, sole_mark(certified))


def test_cut_offsets_filters_continuation_marks_out_of_the_candidate_set() -> None:
    """At document scale, every depth-0 mark is a candidate, but only the
    ones that begin a real definition survive the boundary filter — and only
    those ever reach ``_cut_offsets``'s final, floor-balanced result."""
    certified = _certified_cont_plan()
    assert certified.bound is not None
    text = _continuation_doc(500)
    assert len(text) > 2 * MIN_CHUNK

    with WorkPool(2) as pool:
        raw_marks = scan_marks(certified, text, 2, pool)
        cuts = cut_offsets(certified, text, 2, pool)

    admitted = [
        at
        for at in raw_marks
        if admits(text, at + 1, certified.bound, sole_mark(certified))
    ]
    assert len(admitted) < len(raw_marks), "continuation marks must be filtered out"
    assert cuts, "the certified plan must still find a usable cut"
    for cut in cuts:
        assert text[cut + 1 :].startswith("rule"), "a cut must land on a genuine head"
