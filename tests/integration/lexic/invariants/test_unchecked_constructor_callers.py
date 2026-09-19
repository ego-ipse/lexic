"""Who calls the constructor that does NOT freeze a run.

`_from_values` / `fast_construct` bypass `GrammarModel.__new__`, so they bypass
the coercion that makes a repeated field a tuple. Nothing goes wrong today
because the one caller that CONSTRUCTS passes a matched span string. That is a
property of the callers, not of the constructor, so it is pinned.

**Two routes, and their disagreement is the finding.** A hand enumeration of
these callers was made twice and was wrong twice, in opposite directions: it
named the constructing caller and missed two that read the licence, while a
name-keyed AST scan found those two and missed the constructor — which reaches
it through a local alias. Neither route alone was right, so the test requires
BOTH and fails when they differ.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from lexic.compile import compile_text
from lexic.model import GrammarModel
from lexic.parsing.products import _model_product, pda_model

SRC = Path(__file__).resolve().parents[4] / "src" / "lexic"
UNCHECKED = frozenset({"fast_construct", "_from_values"})

PROBE_GRAMMAR = 'root ::= row+\nrow ::= word nl\nword ::= [a-z]+\nnl ::= "\\n"\n'
"""A grammar with a repeated field and a `value_str` rule — enough to reach it."""


def _aliases(body: ast.AST) -> set[str]:
    """Local names bound by a plain ``name = <something>.attr`` in one function.

    ONE form and no wider: a single assignment, in the same function, whose
    value is an attribute access. `vstr_model` writes `fast = clone.fast` and
    then calls `fast(...)`, and that is the shape a scan must resolve. Anything
    more general starts guessing about aliasing, which a static tool cannot do
    soundly.
    """
    found: set[str] = set()
    for node in ast.walk(body):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target, value = node.targets[0], node.value
        if isinstance(target, ast.Name) and isinstance(value, ast.Attribute):
            if value.attr in UNCHECKED or value.attr == "fast":
                found.add(target.id)
    return found


def _called(node: ast.Call, aliases: set[str]) -> bool:
    """Whether this call reaches an unchecked constructor, alias included."""
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return fn.attr in UNCHECKED or fn.attr == "fast"
    return isinstance(fn, ast.Name) and fn.id in aliases


def _unresolved(node: ast.Call, aliases: set[str]) -> bool:
    """A call this scan cannot decide — reported, never skipped.

    A scan that quietly passes over what it does not understand reports clean
    for the wrong reason. The only honest outcome for an unrecognised callable
    shape is to say so and let the test fail.
    """
    fn = node.func
    if isinstance(fn, (ast.Attribute, ast.Name)):
        return False
    return any(isinstance(one, ast.Name) and one.id in aliases for one in ast.walk(fn))


def by_reading() -> tuple[set[tuple[str, str]], list[str]]:
    """Route 1: `(module, function)` for every call, by AST, on this Python.

    The interpreter matters: the repo uses PEP 758 (`except A, B:`), which only
    3.14 parses. Run under an older one, `ast.parse` calls the source broken.
    """
    found: set[tuple[str, str]] = set()
    unresolved: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            aliases = _aliases(node)
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                where = (path.stem, node.name)
                if _called(sub, aliases):
                    found.add(where)
                elif _unresolved(sub, aliases):
                    unresolved.append(f"{path.stem}:{node.name}:{sub.lineno}")
    return found, unresolved


def by_running() -> tuple[set[tuple[str, str]], int]:
    """Route 2: the callers a real compile-and-parse actually reaches.

    Compiles a grammar FRESH under the interception. The benchmark artefacts
    are built at import, and this constructor is called overwhelmingly at BAKE
    time rather than at parse time, so intercepting around a parse of an
    already-built artefact sees almost nothing. A first version did that and
    the counter below read zero, which is the only reason it was noticed.

    :returns: `(callers, times the interception fired)`. The counter is the
        null rule: a runtime probe that never ran passes by not running.
    """
    # The unchecked constructor and the calling frame are what this route
    # MEASURES; both are private by design and there is no public equivalent.
    # pylint: disable=protected-access
    seen: set[tuple[str, str]] = set()
    fired = 0
    original = GrammarModel._from_values.__func__

    def counting(cls, values):
        nonlocal fired
        fired += 1
        frame = sys._getframe(1)
        seen.add((Path(frame.f_code.co_filename).stem, frame.f_code.co_name))
        return original(cls, values)

    setattr(GrammarModel, "_from_values", classmethod(counting))
    try:
        compiled = compile_text(PROBE_GRAMMAR, cache_key="unchecked-callers")
        product = _model_product(compiled.codegen_grammar, compiled.product)
        pda_model(product.pda, "abc\ndef\n", compiled.product.executor)
    finally:
        setattr(GrammarModel, "_from_values", classmethod(original))
    return seen, fired


def test_the_static_scan_resolves_every_call_it_meets() -> None:
    """An unresolvable aliased call is a SCAN FAILURE, not a silent skip."""
    _found, unresolved = by_reading()

    assert not unresolved, f"the scan cannot decide these calls: {unresolved}"


def test_the_runtime_route_actually_fired() -> None:
    """The null rule: a probe that never ran proves nothing."""
    _seen, fired = by_running()

    assert fired, "the interception never fired — it is measuring nothing"


def test_the_two_routes_agree_on_who_calls_it() -> None:
    """Reading and running must name the same callers.

    Their disagreement is what this test exists for: each route has a blind
    spot the other does not, and only the intersection of their errors is
    invisible to both.
    """
    static, _unresolved = by_reading()
    runtime, _fired = by_running()

    missed_by_reading = {one for one in runtime if one not in static}
    assert not missed_by_reading, (
        f"running found callers the scan did not: {sorted(missed_by_reading)}"
    )


@pytest.mark.parametrize("route", ["reading", "running"])
def test_a_planted_caller_would_be_caught(route: str) -> None:
    """Both routes must SEE a new caller, or the pair is one route.

    Reading sees it in the source; running sees it when it is exercised. The
    planted shape is the aliased one, because that is what a hand enumeration
    and a naive scan both missed.
    """
    source = (
        "def planted(cls, values):\n"
        "    build = cls._from_values\n"
        "    return build(values)\n"
    )
    tree = ast.parse(source)
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)

    aliases = _aliases(function)
    calls = [one for one in ast.walk(function) if isinstance(one, ast.Call)]

    assert "build" in aliases, f"{route}: the alias form is not resolved"
    assert any(_called(one, aliases) for one in calls)
