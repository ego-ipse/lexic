"""Tests for ``lexic.parsing.parallel.orchestrate`` — the split parse.

The contract is equality, not speed: a split parse produces the model the
sequential parse produces, or it IS the sequential parse. Every shape the
stitch does not support, and every failing chunk, falls back — so what an
input MEANS never depends on how many workers ran.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing import parse_model
from lexic.parsing.parallel import orchestrate, split_model, split_plan
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.parallel.policy import AUTO, MIN_CHUNK

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
            Request(text, compiled.fold),
            cores,
        )
        is None
    )


def test_split_equals_sequential_and_round_trips():
    """The headline: same model, exactly, and the text comes back."""
    compiled = compile_text(LEAD_RULE)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    text = _doc(1000)
    parallel = split_model(parse_model, grammar, Request(text, fold), 4)
    assert parallel is not None
    assert parallel == parse_model(grammar, text, fold)
    assert parallel.to_text() == text
    assert compiled.parse(text) == parallel


def test_one_work_pool_is_reused_for_scan_and_parse(monkeypatch: pytest.MonkeyPatch):
    """The split phases share one WorkPool lifetime and executor."""
    compiled = compile_text(LEAD_RULE)
    text = _doc(1000)
    created = 0
    map_calls = 0

    class RecordingPool:
        """Public WorkPool seam that executes mapped work synchronously."""

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

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return None

    monkeypatch.setattr(orchestrate, "WorkPool", RecordingPool)
    parallel = orchestrate.split_model(
        parse_model,
        compiled.codegen_grammar,
        Request(text, compiled.fold),
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
    grammar, fold = compiled.codegen_grammar, compiled.fold
    text = _doc(1000)
    assert split_model(parse_model, grammar, Request(text, fold), cores) == parse_model(
        grammar, text, fold
    )


def test_terminated_plain_tuple_chunks_stitch_without_list_coercion():
    """Terminated chunks merge their exact plain-tuple repeated field."""
    compiled = compile_text(TERMINATED)
    text = "one\n" * 2000
    sequential = compiled.parse(text, cores=1)
    parallel = split_model(
        parse_model,
        compiled.codegen_grammar,
        Request(text, compiled.fold),
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
    grammar, fold = compiled.codegen_grammar, compiled.fold
    plan = split_plan(grammar)
    sequential = parse_model(grammar, text, fold)
    parallel = split_model(parse_model, grammar, Request(text, fold), 2)

    assert plan is not None and plan.sep is None
    assert parallel is not None
    assert parallel == sequential
    assert parallel.to_text() == text


def test_direct_group_recurrence_stitches_below_a_wrapper_start():
    """A bracket recurrence can replace its outer model through ``doc``."""
    compiled = compile_text(DIRECT_GROUP)
    text = "(" + ",".join("a" * 20 for _ in range(1000)) + ")"
    grammar, fold = compiled.codegen_grammar, compiled.fold
    sequential = parse_model(grammar, text, fold)
    parallel = split_model(parse_model, grammar, Request(text, fold), 8)

    assert parallel is not None
    assert parallel == sequential
    assert parallel.to_text() == text


def test_true_root_group_recurrence_has_no_replaceable_route():
    """A region that is itself the start model declines without a wrapper."""
    compiled = compile_text(TRUE_GROUP)
    text = "(" + ",".join("a" * 20 for _ in range(1000)) + ")"
    grammar, fold = compiled.codegen_grammar, compiled.fold

    assert split_model(parse_model, grammar, Request(text, fold), 8) is None
    assert compiled.parse(text, cores=2).to_text() == text


def test_a_bare_literal_lead_splits_too():
    """``more ::= "|" word`` has no lead RULE — the cut text is the literal."""
    compiled = compile_text(BARE_LEAD)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    text = "|".join(f"word{'x' * (i % 3)}" for i in range(2000)).replace("0", "")
    assert split_model(parse_model, grammar, Request(text, fold), 4) == parse_model(
        grammar, text, fold
    )


def test_separator_alternatives_split_below_a_sole_wrapper():
    """A routed repeated child stitches back into its unchanged root wrapper."""
    compiled = compile_text(ROUTED_ALTERNATIVES)
    text = "+".join(str(index % 10) * 12 for index in range(1200))
    grammar, fold = compiled.codegen_grammar, compiled.fold
    plan = split_plan(grammar)
    sequential = parse_model(grammar, text, fold)
    parallel = split_model(parse_model, grammar, Request(text, fold), 8)

    assert plan is not None and plan.wrappers == ("root",)
    assert plan.mark in {"+", "-"}
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
        Request(text, compiled.fold),
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
        Request(text, compiled.fold),
        8,
    )

    assert parallel is not None
    assert parallel == parse_model(compiled.codegen_grammar, text, compiled.fold)
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
    sequential = parse_model(compiled.codegen_grammar, text, compiled.fold)
    parallel = split_model(
        parse_model,
        compiled.codegen_grammar,
        Request(text, compiled.fold),
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
        Request(text, compiled.fold),
        4,
    )
    chunks = [size for size in sizes if size >= MIN_CHUNK]

    assert split == parse_model(compiled.codegen_grammar, text, compiled.fold)
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
        Request(text, compiled.fold),
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
        Request(text, compiled.fold),
        2,
    )

    assert plan is not None and plan.sep is None
    assert parallel is None
    assert not calls
    assert compiled.parse(text, cores=2) == sequential


def test_a_grammar_without_a_separated_start_has_no_plan():
    """No plan is an answer: ``None`` tells the caller to parse sequentially."""
    compiled = compile_text(NO_SPLIT)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    assert split_plan(grammar) is None
    assert split_model(parse_model, grammar, Request("abc", fold), 4) is None


def test_a_bad_input_declines_rather_than_inventing_a_refusal():
    """A failing chunk is a verdict on the SPLIT, not on the input: the
    split declines and the caller's sequential parse is what raises."""
    compiled = compile_text(LEAD_RULE)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    bad = _doc() + ", 12:not-a-pair"
    assert split_plan(grammar) is not None, "the decline must not be 'no plan'"
    assert split_model(parse_model, grammar, Request(bad, fold), 4) is None
    with pytest.raises(UnsupportedConstructError):
        compiled.parse(bad)


def test_too_few_separators_declines():
    """No cut points, no split — and the artefact still parses it."""
    compiled = compile_text(LEAD_RULE)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    text = "only:1"
    assert split_model(parse_model, grammar, Request(text, fold), 8) is None
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
    grammar, fold = compiled.codegen_grammar, compiled.fold
    text = "ua = a\nub = b\n" * 2000

    assert split_plan(grammar) is not None

    monkeypatch.setattr(orchestrate, "unit_witness", lambda *_a, **_k: None)
    declined = split_model(parse_model, grammar, Request(text, fold), 8)
    assert declined is None

    sequential = parse_model(grammar, text, fold)
    assert compiled.parse(text, cores=8) == sequential
