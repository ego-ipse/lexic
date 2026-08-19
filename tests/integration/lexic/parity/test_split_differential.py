"""A split parse means what the sequential parse means — on every grammar.

The orchestration is only ever allowed two outcomes: the exact model the
sequential product builds, or the sequential parse itself. This differential
runs the ground-truth corpus through both at several worker counts, so a
grammar that gains a split plan later is covered the day it does — including
the ones that fall back today, which is what keeps fallback honest.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing import parse_model
from lexic.parsing.parallel import split_model, split_plan
from lexic.parsing.parallel.orchestrate import Request
from tests.paths import GROUND_TRUTH

CORPUS: tuple[tuple[str, str], ...] = (
    ("list.gbnf", "".join(f"- entry number {i}\n" for i in range(40))),
    ("json.gbnf", '{"a": [1, 2], "b": {"c": "d"}, "e": null}'),
    ("arithmetic.gbnf", "x=1\ny=2\n"),
    ("chess.gbnf", "1. e4 e5\n2. Nf3 Nc6\n"),
)
"""Ground-truth grammars paired with an input each accepts.

``list.gbnf`` (``root ::= item+``, the item ending in a newline) is the row
that genuinely SPLITS today; the rest currently fall back, and are here
because a fallback that silently stopped producing the sequential model
would be exactly as wrong as a bad stitch.
"""

WORKERS = (2, 3, 7)


def _pairs() -> list[tuple[str, str, int]]:
    return [(name, text, n) for name, text in CORPUS for n in WORKERS]


@pytest.mark.parametrize("name,text,workers", _pairs())
def test_split_parse_equals_sequential(name: str, text: str, workers: int):
    """Same value, same class, exact round-trip — whatever the worker count."""
    path = GROUND_TRUTH / name
    if not path.exists():
        pytest.skip(f"fixture absent: {name}")
    compiled = compile_from_path(path)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    sequential = parse_model(grammar, text, fold)
    parallel = split_model(parse_model, grammar, Request(text, fold), workers)
    if parallel is not None:  # None = this grammar/input does not split
        assert parallel == sequential
        assert type(parallel) is type(sequential)
        assert parallel.to_text() == text
    assert compiled.parse(text) == sequential  # the user entry, either way


@pytest.mark.parametrize("name,text", CORPUS)
def test_a_bad_input_refuses_on_both_paths(name: str, text: str):
    """Refusal parity: splitting never rescues, or re-labels, a bad input."""
    path = GROUND_TRUTH / name
    if not path.exists():
        pytest.skip(f"fixture absent: {name}")
    compiled = compile_from_path(path)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    bad = text + "\x00 not in this language"
    assert split_model(parse_model, grammar, Request(bad, fold), 4) is None
    with pytest.raises(UnsupportedConstructError):
        parse_model(grammar, bad, fold)
    with pytest.raises(UnsupportedConstructError):
        compiled.parse(bad)


def test_the_differential_is_not_vacuous():
    """At least one fixture must really split — otherwise every row above
    passes by falling back and the stitch is never exercised at all."""
    path = GROUND_TRUTH / "list.gbnf"
    if not path.exists():
        pytest.skip("fixture absent: list.gbnf")
    plan = split_plan(compile_from_path(path).codegen_grammar)
    assert plan is not None and plan.sep is None  # the terminated shape
