"""Session-scoped grammar-rule fixtures for all 7 ground-truth grammars."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexic.compile import (
    CompiledGrammar,
    canonical_grammar,
    compile_from_path,
    compile_text,
)
from lexic.grammars.gbnf import GBNF_FLAVOUR
from tests.paths import GROUND_TRUTH

ALL_GRAMMARS = ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]


@pytest.fixture(scope="session")
def all_grammar_specs() -> dict[str, dict]:
    """Compile all ground-truth grammars once, returning {name: {rule_name: IrRule}}.

    The inner mapping is the rules-by-name view :func:`lexic.generate.generate`
    walks (canonical grammar, directives applied).

    Also warms ``compile_from_path``'s process-wide cache here, at fixture
    setup, for every grammar: ``test_roundtrip._roundtrip`` calls
    ``parse(text, gpath)`` (``compile_from_path`` under the hood) on its
    first hypothesis example. In the full suite that path is already warm by
    the time these tests run (earlier integration tests compile the same
    grammars); run in isolation (e.g. ``-k "json_ws or json_arr"``), the
    first example instead pays the full cold-compile cost — codegen plus two
    ``ruff`` subprocess spawns (``codegen/__init__.py``'s ``_ruff_format``)
    — inside hypothesis's default 200ms per-example deadline. That cost is
    normally ~50-60ms but subprocess spawn latency is sensitive to system
    contention (measured ~115ms under moderate concurrent load), which is
    what turned it into an intermittent ``DeadlineExceeded`` flake. Warming
    outside the timed example removes the cost from the measured window.
    """
    result = {}
    for name in ALL_GRAMMARS:
        text = (GROUND_TRUTH / f"{name}.gbnf").read_text()
        ast = canonical_grammar(text, GBNF_FLAVOUR)
        result[name] = {r.name: r for r in ast.rules}
        compile_from_path(GROUND_TRUTH / f"{name}.gbnf")
    return result


@pytest.fixture(scope="session")
def grammar_dir() -> Path:
    """Return the ground-truth grammars directory."""
    return GROUND_TRUTH


@pytest.fixture(scope="session")
def c_statement_grammar() -> tuple[CompiledGrammar, dict]:
    """c.gbnf compiled with an injected ``@start statement`` directive.

    ``root ::= (declaration)*`` has ``lo=0``, so generating from "root" is empty
    most of the time (``_pick_count`` rolls the lower bound at 70%) and sparse
    otherwise — thin coverage of the interesting surface. Compiling with
    "statement" as the start rule drives generation straight over the statement
    surface (if/while/for/return/assignment/function-call/comments) on every
    seed instead.
    """
    text = (GROUND_TRUTH / "c.gbnf").read_text() + "\n# @start statement\n"
    ast = canonical_grammar(text, GBNF_FLAVOUR)
    specs = {r.name: r for r in ast.rules}
    cg = compile_text(text, cache_key="property-c-statement-start")
    return cg, specs
