"""A split reduction means what the sequential reduction means.

The region split is only ever allowed two outcomes: the exact value
:func:`~lexic.parsing.products.parse_reduced` builds sequentially, or
``None`` — "reduce the whole text yourself". This differential holds every
json formulation to that on a document shaped like the one the split exists
for: a small header beside two big tables, the runs three levels down.

``doc_workers(AUTO)`` is 1 under the GIL, so every case here names its worker
count. Left to the policy the whole path would take its early return and the
file would pass without reducing anything twice.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrAst, IrSelf
from lexic.parsing.parallel.regions import choose, find, split_regions
from lexic.parsing.products import _reduce_one, parse_reduced
from tests.paths import GROUND_TRUTH

FORMULATIONS = ("native", "json.gbnf", "json.abnf", "json.ebnf")
"""Four spellings of one language. The reducer is written against the rule
names they share, so the same reduction is expected from all four — which is
what "no privileged formulation" has to mean for the split as well."""

WORKERS = (2, 4, 8)


def _document() -> str:
    """A header beside two big tables — a ``tokenizer.json`` in miniature.

    The runs are nested two levels below the start rule, which is the whole
    point: a document's parallelism is where its brackets are, not where its
    start rule is.
    """
    vocab = ",".join(f'"tok{i}": {i}' for i in range(4000))
    merges = ",".join(f'["a{i}", "b{i}"]' for i in range(4000))
    return (
        '{"version": "1.0", "model": '
        f'{{"vocab": {{{vocab}}}, "merges": [{merges}]}}, "tail": 1}}'
    )


DOCUMENT = _document()

BAD = '{"version": , ' + DOCUMENT[1:]
"""The document with its first value removed. Broken early on purpose: both
paths have to reach the refusal, and neither should pay for the tables first."""

_GRAMMARS: dict[str, IrAst] = {}


def _grammar(name: str) -> IrAst:
    """The formulation's grammar, compiled once for the whole module.

    The engine memoises its tables per grammar identity, so a fresh compile
    per test would also throw away every table the previous one built.
    """
    if name == "native":
        return JSON_GRAMMAR
    if name not in _GRAMMARS:
        path = GROUND_TRUTH / name
        if not path.exists():
            pytest.skip(f"fixture absent: {name}")
        _GRAMMARS[name] = compile_from_path(path).grammar
    return _GRAMMARS[name]


_REDUCTIONS: dict[str, IrSelf] = {}


def _sequential(name: str) -> IrSelf:
    """The formulation's whole-document reduction, computed once per module.

    It is the answer every case here compares against, and it costs a full
    reduce of the document, so it is not recomputed per parametrisation.
    """
    if name not in _REDUCTIONS:
        _REDUCTIONS[name] = _reduce_one(_grammar(name), DOCUMENT, JSON_REDUCER)
    return _REDUCTIONS[name]


@pytest.mark.parametrize("name", FORMULATIONS)
@pytest.mark.parametrize("workers", WORKERS)
def test_split_reduction_equals_the_sequential_one(name: str, workers: int):
    """The whole contract, at every worker count: the same value, or ``None``."""
    split = split_regions(_reduce_one, _grammar(name), DOCUMENT, JSON_REDUCER, workers)
    if split is not None:  # None = this document does not divide here
        assert split == _sequential(name)


@pytest.mark.parametrize("name", FORMULATIONS)
def test_the_document_really_divides(name: str):
    """The non-vacuity gate. Without it every assertion above passes on a
    ``None`` and the differential defends nothing."""
    grammar = _grammar(name)
    picked = choose(DOCUMENT, find(grammar, DOCUMENT), 8)
    assert picked, f"{name}: nothing chosen — the differential would be vacuous"
    assert split_regions(_reduce_one, grammar, DOCUMENT, JSON_REDUCER, 8) is not None


@pytest.mark.parametrize("name", FORMULATIONS)
def test_a_bad_document_refuses_on_both_paths(name: str):
    """Refusal parity: splitting never rescues a bad input, and never issues
    the refusal itself — it declines, and the sequential reduce raises."""
    grammar = _grammar(name)
    assert split_regions(_reduce_one, grammar, BAD, JSON_REDUCER, 4) is None
    with pytest.raises(UnsupportedConstructError):
        _reduce_one(grammar, BAD, JSON_REDUCER)


def test_the_public_entry_agrees_with_the_sequential_reduction():
    """``parse_reduced`` is where the split is wired in, so it is what a
    caller's answer actually comes from."""
    assert parse_reduced(JSON_GRAMMAR, DOCUMENT, JSON_REDUCER) == _sequential("native")


def test_a_grammar_with_no_divisible_run_declines_cleanly():
    """Grammar text has no big bracketed run of separated items, so the
    flavour's own self-grammar takes the fallback — and a fallback that
    stopped producing the sequential value would be exactly as wrong as a bad
    stitch."""
    source = "".join(f'rule{i} ::= "a" | "b"\n' for i in range(4000))
    grammar, reducer = GBNF_FLAVOUR.grammar, GBNF_FLAVOUR.reducer
    assert split_regions(_reduce_one, grammar, source, reducer, 4) is None
    assert parse_reduced(grammar, source, reducer) == _reduce_one(
        grammar, source, reducer
    )
