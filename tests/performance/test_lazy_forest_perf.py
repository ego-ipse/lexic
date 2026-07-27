"""Performance / laziness benchmarks for the parsing lazy SPPF forest.

Every test is marked ``performance`` and prints a timing table when run with
``-s``. Tests MUST pass in the default ``pytest tests/ -q`` run (generous
guards); they also serve as a benchmark when run with ``-m performance -s -v``.

Key invariant under test: ``parse`` and ``is_ambiguous`` short-circuit and
are polynomial in input length even when the full derivation forest is
exponentially large (e.g. the sss grammar over 'a'*40 has Catalan(39)
derivations — an astronomical number — yet the short-circuit path is fast).
"""

from __future__ import annotations

import sys

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrLiteral
from lexic.parsing import derivations, is_ambiguous, parse
from lexic.parsing.earley.forest import ParseTree
from tests.unit.lexic.parsing.ir_fixtures import sss_grammar

from .conftest import MEMORY_EXCEEDED, TIMED_OUT, guarded, rep_grammar, timed

# ── Shared fixtures ───────────────────────────────────────────────────

GIB = 1024 * 1024 * 1024


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.performance
def test_parse_fast_on_exponential_ambiguity() -> None:
    """parse(sss, 'a'*40) raises ambiguity fast — polynomial, not exponential.

    Catalan(39) is astronomical, so an eager enumerator would never finish.
    This proves the short-circuit path is the load-bearing one.
    """
    grammar = sss_grammar()
    text = "a" * 40

    def _run() -> str:
        try:
            parse(grammar, text)
        except UnsupportedConstructError:
            return "ambiguous"
        return "ok"

    result, elapsed = timed(_run)
    print(f"\n  parse(sss, 'a'*40): {elapsed:.3f}s (result={result!r})")

    assert result == "ambiguous", "Expected ambiguity error for sss 'a'*40"

    # Generous wall-clock bound: must complete within 30s on any CI machine
    assert elapsed < 30.0, f"parse(sss, 'a'*40) took {elapsed:.1f}s — too slow"

    # Also verify under the subprocess guard (proves no OOM either)
    guarded_result = guarded(_run, seconds=30, mem_bytes=int(1.5 * GIB))
    assert guarded_result not in (TIMED_OUT, MEMORY_EXCEEDED), (
        f"parse(sss, 'a'*40) timed out or OOM'd under guard: {guarded_result!r}"
    )


@pytest.mark.performance
def test_is_ambiguous_fast_on_exponential() -> None:
    """is_ambiguous(sss, 'a'*40) returns 1 fast — polynomial short-circuit."""
    grammar = sss_grammar()
    text = "a" * 40

    def _run() -> int:
        return int(is_ambiguous(grammar, text))

    result, elapsed = timed(_run)
    print(f"\n  is_ambiguous(sss, 'a'*40): {elapsed:.3f}s (result={result})")

    assert result == 1
    assert elapsed < 30.0, f"is_ambiguous(sss, 'a'*40) took {elapsed:.1f}s — too slow"

    guarded_result = guarded(_run, seconds=30, mem_bytes=int(1.5 * GIB))
    assert guarded_result not in (TIMED_OUT, MEMORY_EXCEEDED), (
        f"is_ambiguous(sss, 'a'*40) timed out or OOM'd: {guarded_result!r}"
    )


@pytest.mark.performance
def test_eager_derivations_blows_up_guarded() -> None:
    """derivations(sss, 'a'*30) times out or OOMs under a tight guard.

    Catalan(29) is ~5.9 × 10^18. This CONTRAST test proves that the eager
    full-enumeration path IS genuinely exponential, making the laziness
    load-bearing — not just an optimisation.
    """
    grammar = sss_grammar()
    text = "a" * 30

    def _run() -> int:
        return len(derivations(grammar, text))

    result = guarded(_run, seconds=8, mem_bytes=GIB)
    print(f"\n  derivations(sss, 'a'*30) guarded result: {result!r}")
    assert result in (TIMED_OUT, MEMORY_EXCEEDED), (
        f"Expected timeout or OOM for derivations(sss, 'a'*30) but got: {result!r}\n"
        "This means the eager enumerator completed — that is unexpected for n=30 "
        "(Catalan(29) ≈ 5.9e18). Check if the grammar is correct or the guard is too generous."
    )


@pytest.mark.performance
def test_short_circuit_scaling() -> None:
    """parse(sss, 'a'*n) raises time stays polynomial (sub-exponential) as n doubles.

    Prints a (n, elapsed) table. Asserts:
    - each measurement < a generous absolute bound
    - the doubling ratio stays sub-exponential (ratio < 100 for 2n vs n)
    """
    grammar = sss_grammar()
    sizes = [10, 20, 40, 80]
    timings: list[tuple[int, float]] = []

    for n in sizes:
        text = "a" * n

        def _run(t: str = text) -> None:
            try:
                parse(grammar, t)
            except UnsupportedConstructError:
                pass

        _, elapsed = timed(_run)
        timings.append((n, elapsed))

    print("\n  short-circuit scaling (parse raises on sss ambiguity):")
    print(f"  {'n':>6}  {'elapsed':>10}")
    for n, t in timings:
        print(f"  {n:>6}  {t:>10.4f}s")

    for n, t in timings:
        assert t < 30.0, (
            f"parse(sss,'a'*{n}) took {t:.2f}s — exceeds 30s absolute bound"
        )

    # Sub-exponential growth: ratio of consecutive measurements must be < 100
    for (n1, t1), (n2, t2) in zip(timings, timings[1:]):
        if t1 > 0:
            ratio = t2 / t1
            assert ratio < 100, (
                f"Time growth from n={n1} ({t1:.4f}s) to n={n2} ({t2:.4f}s) "
                f"is {ratio:.1f}× — looks exponential (bound: 100×)"
            )


@pytest.mark.performance
def test_rep_grammar_parse_scaling_baseline() -> None:
    """Baseline: parse(rep_grammar, 'a'*n) correctness and timing for F1 comparison.

    The current right-recursive shape is O(n²) in chart steps — this test
    records the baseline so the F1 optimisation can be compared against it.
    Does NOT assert linearity (current behaviour is quadratic).
    Asserts correctness (round-trip) and a generous upper bound to catch hangs.
    """
    # Increase recursion limit: tree traversal recurses proportional to input length
    orig_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(orig_limit, 10000))

    grammar = rep_grammar()
    sizes = [50, 100, 200, 400]
    timings: list[tuple[int, float]] = []

    def _to_text(node: object) -> str:
        if isinstance(node, ParseTree):
            return "".join(_to_text(k) for k in node.kids)
        if isinstance(node, IrLiteral):
            return str(node)
        return ""

    try:
        for n in sizes:
            text = "a" * n

            def _run(t: str = text) -> str:
                tree = parse(grammar, t)
                return _to_text(tree)

            result, elapsed = timed(_run)
            timings.append((n, elapsed))
            # Correctness assertion: round-trip
            assert result == text, (
                f"rep_grammar round-trip failed for n={n}: got {result[:20]!r}..."
            )
    finally:
        sys.setrecursionlimit(orig_limit)

    print("\n  rep_grammar parse scaling baseline (right-recursive, O(n²) expected):")
    print(f"  {'n':>6}  {'elapsed':>10}")
    for n, t in timings:
        print(f"  {n:>6}  {t:>10.4f}s")

    # Generous absolute bound: must complete within 120s each (catches hangs)
    for n, t in timings:
        assert t < 120.0, (
            f"rep_grammar parse n={n} took {t:.1f}s — exceeds 120s bound (hung?)"
        )
