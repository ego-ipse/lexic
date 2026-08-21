"""Tests for lexic.parsing.trace — the watched run and what it says."""

from __future__ import annotations

import pytest

from lexic.compile import CompiledGrammar, compile_from_path, compile_text
from lexic.ir import IrSpan
from lexic.parsing import (
    TRACE_CAP,
    TRACE_KINDS,
    Trace,
    TraceEvent,
    WatchedKernel,
    WatchedRun,
    watch,
)
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from tests.paths import GROUND_TRUTH, PROJECT_ROOT

# `item` overlaps `tail` by an unbounded prefix, so the analysis cannot settle
# the arm by lookahead and the runtime has to TRY both — the one shape that
# exercises probe and rollback rather than the deterministic straight line.
FORKING = 'root ::= item tail\nitem ::= "a" | "ab"\ntail ::= "bc" | "c"\n'

JSON_DOC = '{"a": 1, "b": [2, 3]}'


@pytest.fixture(name="json_grammar", scope="module")
def json_grammar_fixture() -> CompiledGrammar:
    """The ground-truth JSON grammar, compiled once."""
    return compile_from_path(GROUND_TRUTH / "json.gbnf")


def forking() -> CompiledGrammar:
    """The overlap grammar, compiled under its own cache key."""
    return compile_text(FORKING, cache_key="trace-forking")


def watched(compiled: CompiledGrammar, text: str, cap: int = TRACE_CAP) -> WatchedRun:
    """Watch a parse of ``text`` under ``compiled``."""
    return watch(compiled.pda_tables(), text, compiled.fold, cap=cap)


# ── the stream ────────────────────────────────────────────────────────


def test_a_watched_run_yields_ordered_events(json_grammar: CompiledGrammar) -> None:
    """Order IS the content: the field is the index, with no gaps."""
    run = watched(json_grammar, JSON_DOC)
    assert [event.order for event in run.events] == list(range(len(run.events)))


def test_every_event_is_one_of_the_four_kinds(json_grammar: CompiledGrammar) -> None:
    """The vocabulary is closed — a fifth kind would be a new word."""
    run = watched(json_grammar, JSON_DOC)
    assert {event.kind for event in run.events} <= set(TRACE_KINDS)


def test_the_scans_tile_the_document(json_grammar: CompiledGrammar) -> None:
    """Every character the machine consumed is attributed exactly once.

    The coverage claim is what makes a scan stream an ACCOUNT rather than a
    sample: no gap, no overlap, ending at the end of the input.
    """
    run = watched(json_grammar, JSON_DOC)
    at = 0
    for event in run.events.of_kind("scan"):
        assert event.span.start == at, f"gap or overlap at {at}"
        at = event.span.end
    assert at == len(JSON_DOC)


def test_a_scans_verdict_is_the_text_it_consumed(
    json_grammar: CompiledGrammar,
) -> None:
    """The span and the words agree — one slices back to the other."""
    run = watched(json_grammar, JSON_DOC)
    for event in run.events.of_kind("scan"):
        assert event.span.of(JSON_DOC) == event.verdict


def test_a_forking_input_probes_and_rolls_back() -> None:
    """The stream tells the story: a gate, the entries tried, a refusal.

    The THIRD probe is the split fix earning its keep. A repeat no longer
    treats its own next occurrence as a follower, so the boundary that used to
    be settled by stopping early is now explored — an arm has a family of
    extents, and the run tries one more of them before refusing. The claim the
    test makes is unchanged: speculation happens, nothing is derived from it,
    and the gate still names the two entries it chose between.
    """
    run = watched(forking(), "abc")
    assert [event.kind for event in run.events] == [
        "gate",
        "probe",
        "scan",
        "probe",
        "scan",
        "probe",
        "rollback",
        "rollback",
    ]
    assert run.events[0].verdict == "attempt over 2 entries"
    assert not run.derived


def test_a_deterministic_input_needs_no_probe() -> None:
    """Nothing speculative happens where the gates settle it."""
    run = watched(forking(), "ac")
    assert not run.events.of_kind("probe")
    assert run.derived


# ── the honest facts ──────────────────────────────────────────────────


def test_the_cap_is_a_drawn_fact(json_grammar: CompiledGrammar) -> None:
    """A truncated account says so — never a silent short stream."""
    run = watched(json_grammar, JSON_DOC, cap=3)
    assert run.capped
    assert len(run.events) == 3
    assert run.cap == 3


def test_an_uncapped_run_says_that_too(json_grammar: CompiledGrammar) -> None:
    """The negative is drawn as well, so 'not capped' is a claim."""
    run = watched(json_grammar, JSON_DOC)
    assert not run.capped
    assert run.cap == TRACE_CAP


def test_the_cap_never_truncates_the_parse(json_grammar: CompiledGrammar) -> None:
    """Recording stops; the machine does not. The run still derives."""
    assert watched(json_grammar, JSON_DOC, cap=1).derived


def test_a_refusal_is_the_last_event_not_an_exception() -> None:
    """The run worth watching is the one that fails — so it comes back."""
    run = watched(forking(), "abc")
    last = run.events[-1]
    assert last.kind == "rollback"
    assert "arm choice spans two ends" in last.verdict
    assert not run.derived


def test_the_product_carries_no_model() -> None:
    """A watched run is a DIFFERENT execution; it hands back no second model."""
    assert set(WatchedRun._fields) == {"events", "cap", "capped", "derived"}


# ── reference fidelity ────────────────────────────────────────────────


def test_every_span_lies_within_the_document(json_grammar: CompiledGrammar) -> None:
    """No event points outside the text it was measured against."""
    for event in watched(json_grammar, JSON_DOC).events:
        assert 0 <= event.span.start <= event.span.end <= len(JSON_DOC)


def test_every_rule_resolves_against_the_compiled_grammar(
    json_grammar: CompiledGrammar,
) -> None:
    """A rule name is the grammar's own, not a label the trace invented."""
    known = {str(rule.name) for rule in json_grammar.codegen_grammar.rules}
    for event in watched(json_grammar, JSON_DOC).events:
        assert event.rule in known or event.rule == "", event.rule


def test_a_decision_is_a_zero_width_span(json_grammar: CompiledGrammar) -> None:
    """A gate is taken AT a position; only a scan covers one."""
    for event in watched(json_grammar, JSON_DOC).events.of_kind("gate"):
        assert event.span.start == event.span.end


# ── determinism ───────────────────────────────────────────────────────


def test_two_watched_runs_are_the_same_stream(json_grammar: CompiledGrammar) -> None:
    """Byte-identical, because a trace nobody can reproduce is not evidence."""
    assert (
        watched(json_grammar, JSON_DOC).events == watched(json_grammar, JSON_DOC).events
    )


def test_two_watched_runs_of_a_forking_input_agree() -> None:
    """Determinism where it is hardest: the speculative path repeats too."""
    assert watched(forking(), "abc") == watched(forking(), "abc")


# ── pay to watch: the hot path carries nothing ────────────────────────


def test_the_kernel_has_no_watch_state() -> None:
    """``PdaKernel``'s slots are its own — no trace field rides the cursor."""
    assert "events" not in PdaKernel.__slots__
    assert "capped" not in PdaKernel.__slots__


def test_the_kernels_own_methods_mention_nothing_of_the_watch() -> None:
    """The decisive structural gate: no branch in the paid loop.

    Read off the compiled code objects rather than the source, so an
    ``if self.watching:`` added anywhere in the kernel fails this test even if
    it is spelled differently.
    """
    watch_words = {"_note", "_flush", "events", "capped", "_scanned", "cap"}
    for name, member in vars(PdaKernel).items():
        code = getattr(member, "__code__", None)
        if code is None:
            continue
        touched = watch_words & (set(code.co_names) | set(code.co_varnames))
        assert not touched, f"PdaKernel.{name} mentions {sorted(touched)}"


def test_the_watcher_is_a_subclass_not_a_patch() -> None:
    """Instrumentation lives in the subclass; the base keeps its own methods."""
    assert issubclass(WatchedKernel, PdaKernel)
    for name in ("_enter", "_complete", "_attempt_run", "_run_leaf"):
        assert name in vars(WatchedKernel), f"{name} is not overridden"
        origin = getattr(PdaKernel, name).__qualname__.split(".", maxsplit=1)[0]
        assert origin in (
            "PdaKernel",
            "Attempting",
            "KernelExecutionMixin",
        )


def test_the_pda_package_does_not_import_the_trace() -> None:
    """The arrow proves the cost model: the hot path cannot see the watch."""
    root = PROJECT_ROOT / "src" / "lexic" / "parsing" / "pda"
    for path in root.rglob("*.py"):
        assert "parsing.trace" not in path.read_text(encoding="utf-8"), path


# ── the records ───────────────────────────────────────────────────────


def test_an_event_is_its_field_tuple() -> None:
    """A spine record: read by name or by index, no accessors."""
    event = TraceEvent(0, "scan", "root", "x", IrSpan(0, 1))
    assert tuple(event) == (0, "scan", "root", "x", IrSpan(0, 1))
    assert event.span.of("xy") == "x"


def test_the_position_leaf_is_the_emissions_own_record() -> None:
    """The shared-leaves ruling: a trace and an extent point with one type."""
    run = watched(forking(), "ac")
    assert all(isinstance(event.span, IrSpan) for event in run.events)


def test_a_sub_stream_keeps_its_type_and_order(json_grammar: CompiledGrammar) -> None:
    """``of_kind`` is a view, not a list — the product stays readable."""
    scans = watched(json_grammar, JSON_DOC).events.of_kind("scan")
    assert isinstance(scans, Trace)
    assert [event.order for event in scans] == sorted(event.order for event in scans)
