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


def _doc(count: int = 40) -> str:
    return ", ".join(f"key{'x' * (i % 7)}:{i}" for i in range(count))


@pytest.mark.parametrize(
    ("cores", "text"),
    [(1, "x" * (2 * MIN_CHUNK)), (AUTO, "x")],
)
def test_universal_gates_skip_plan_and_safety_analysis(
    monkeypatch: pytest.MonkeyPatch, cores: int, text: str
) -> None:
    """Policy-declined inputs do not pay for plan, safety, or scan analysis."""
    compiled = compile_text("root ::= [a-z]+\n")

    def unexpected_analysis(*_args, **_kwargs):
        raise AssertionError("parallel analysis ran behind a universal gate")

    monkeypatch.setattr(orchestrate, "split_plan", unexpected_analysis)
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
    text = _doc()
    parallel = split_model(parse_model, grammar, Request(text, fold), 4)
    assert parallel is not None
    assert parallel == parse_model(grammar, text, fold)
    assert parallel.to_text() == text
    assert compiled.parse(text) == parallel


@pytest.mark.parametrize("cores", [2, 3, 5, 8])
def test_every_worker_count_gives_one_answer(cores: int):
    """Worker count moves wall-clock, never the value."""
    compiled = compile_text(LEAD_RULE)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    text = _doc()
    assert split_model(parse_model, grammar, Request(text, fold), cores) == parse_model(
        grammar, text, fold
    )


def test_terminated_plain_tuple_chunks_stitch_without_list_coercion():
    """Terminated chunks merge their exact plain-tuple repeated field."""
    compiled = compile_text(TERMINATED)
    text = "one\ntwo\nthree\nfour\n"
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
        f"def alpha{i}() {{value}}\ndef beta{i}() = value;\n" for i in range(40)
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
    text = "|".join(f"word{'x' * (i % 3)}" for i in range(30)).replace("0", "")
    assert split_model(parse_model, grammar, Request(text, fold), 4) == parse_model(
        grammar, text, fold
    )


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
