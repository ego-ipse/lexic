"""Model-path differential for region splitting.

Section 2 splits the model product, not the reduction product.  The input is
deliberately a small tokenizer-shaped JSON document: the outer object is not a
valid model root for a region piece, while its nested object and array runs
are.  That makes a passing differential prove both selection and rerooting,
instead of passing because every split attempt declined.
"""

from __future__ import annotations

import json

import pytest

from lexic.compile import CompiledGrammar, compile_ast, compile_from_path
from lexic.compile.artifact import _reduce_entry
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.parsing import parse_model
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.orchestrate import Request
from tests.paths import GROUND_TRUTH

FORMULATIONS = ("native", "json.gbnf", "json.abnf", "json.ebnf")
WORKERS = (2, 4, 8)
ITEMS = 1000


def _document() -> str:
    """A nested document with two same-leading objects and an array run."""
    left = ['"shared": 0'] + [f'"left{i:04d}": {i}' for i in range(ITEMS)]
    right = ['"shared": 0'] + [f'"right{i:04d}": {i}' for i in range(ITEMS)]
    merges = ",".join(f'["a{i:04d}", "b{i:04d}"]' for i in range(ITEMS))
    return (
        '{"left": {'
        + ", ".join(left)
        + '}, "right": {'
        + ", ".join(right)
        + '}, "merges": ['
        + merges
        + '], "tail": {"ok": true}}'
    )


DOCUMENT = _document()


def _compiled(name: str) -> CompiledGrammar:
    if name == "native":
        return compile_ast(JSON_GRAMMAR)
    return compile_from_path(GROUND_TRUTH / name)


@pytest.fixture(scope="module", params=FORMULATIONS, name="json_compiled")
def _compiled_case(request: pytest.FixtureRequest) -> tuple[str, CompiledGrammar]:
    """Compile one of the four equivalent JSON grammar formulations."""
    name = request.param
    return name, _compiled(name)


@pytest.mark.parametrize("workers", WORKERS)
def test_nested_model_split_equals_sequential_and_round_trips(
    json_compiled: tuple[str, CompiledGrammar], workers: int
) -> None:
    """Every formulation and explicit worker count produces one exact model."""
    name, compiled = json_compiled
    grammar, fold = compiled.codegen_grammar, compiled.fold
    sequential = parse_model(grammar, DOCUMENT, fold)
    split = split_model(parse_model, grammar, Request(DOCUMENT, fold), workers)

    assert split is not None, f"{name}: nested differential became vacuous"
    assert type(split) is type(sequential)
    assert split == sequential
    assert split.to_text() == DOCUMENT

    public = compiled.parse(DOCUMENT, cores=workers)
    assert type(public) is type(sequential)
    assert public == sequential
    assert public.to_text() == DOCUMENT


def test_nested_differential_is_not_vacuous(
    json_compiled: tuple[str, CompiledGrammar],
) -> None:
    """The gate is independent of the worker-count rows above."""
    name, compiled = json_compiled
    split = split_model(
        parse_model,
        compiled.codegen_grammar,
        Request(DOCUMENT, compiled.fold),
        WORKERS[-1],
    )
    assert split is not None, f"{name}: no nested region was actually split"
    assert split.to_text() == DOCUMENT


@pytest.mark.parametrize("workers", WORKERS)
def test_reducer_derived_variant_really_splits(
    json_compiled: tuple[str, CompiledGrammar], workers: int
) -> None:
    """The reducer's pruned variant reaches the same model split seam."""
    name, compiled = json_compiled
    entry = _reduce_entry(compiled, JSON_REDUCER)
    grammar, fold = entry.variant.codegen_grammar, entry.variant.fold
    sequential = parse_model(grammar, DOCUMENT, fold)
    split = split_model(parse_model, grammar, Request(DOCUMENT, fold), workers)

    assert split is not None, f"{name}: reducer variant split became vacuous"
    assert type(split) is type(sequential)
    assert split == sequential
    # The derived variant intentionally elides DROP/noise fields, so its
    # model text is a pruned semantic stream rather than the source document.


@pytest.mark.parametrize("workers", WORKERS)
def test_public_reduce_worker_counts_equal_sequential(
    json_compiled: tuple[str, CompiledGrammar], workers: int
) -> None:
    """Thin folding after a split is byte-for-byte equal to cores=1."""
    name, compiled = json_compiled
    sequential = compiled.reduce(DOCUMENT, JSON_REDUCER, cores=1)
    parallel = compiled.reduce(DOCUMENT, JSON_REDUCER, cores=workers)

    assert type(parallel) is type(sequential), name
    assert parallel == sequential


def test_reducer_variant_uses_source_interiors_for_region_discovery() -> None:
    """Elided quote models must not expose structural-looking string text."""
    compiled = compile_ast(JSON_GRAMMAR)
    entry = _reduce_entry(compiled, JSON_REDUCER)
    entries = ",".join(
        f"{json.dumps(f'key{{,[{chr(34)}{i:04d}')}:{i}" for i in range(1000)
    )
    text = '{"vocab":{' + entries + '},"tail":0}'
    grammar, fold = entry.variant.codegen_grammar, entry.variant.fold

    assert entry.variant.split_analysis is compiled.grammar
    split = split_model(
        parse_model,
        grammar,
        Request(text, fold),
        4,
        analysis=entry.variant.split_analysis,
    )
    sequential = parse_model(grammar, text, fold)
    assert split is not None
    assert split == sequential
    assert entry.variant.parse(text, cores=4) == sequential


def test_nested_region_shell_does_not_reparse_delegated_interior() -> None:
    """The root shell is small; only the region workers see the large body."""
    marker = "DISTINCTIVE_DELEGATED_INTERIOR"
    items = ["0"] + [f'"{marker}_{i}"' for i in range(700)]
    text = '{"head": 0, "items": [' + ", ".join(items) + '], "tail": 1}'
    compiled = compile_ast(JSON_GRAMMAR)
    root = compiled.codegen_grammar
    calls: list[tuple[str, str]] = []

    def recording_parse(grammar, source, fold, resolve=None):
        calls.append((str(grammar.start), source))
        return parse_model(grammar, source, fold, resolve)

    split = split_model(
        recording_parse,
        root,
        Request(text, compiled.fold),
        4,
    )
    assert split is not None
    assert split == parse_model(root, text, compiled.fold)
    assert split.to_text() == text

    root_calls = [source for start, source in calls if start == str(root.start)]
    region_calls = [source for start, source in calls if start == "array"]
    assert len(root_calls) == 1
    assert len(root_calls[0]) < len(text) // 2
    assert marker not in root_calls[0]
    assert any(marker in source for source in region_calls)


def test_outer_region_owns_nested_child_territory() -> None:
    """A chosen outer object delegates its child array as one territory."""
    fields = ", ".join(f'"key{i:04d}": {i}' for i in range(700))
    inner = ", ".join(str(i) for i in range(700))
    text = '{"box": {' + fields + ', "inner": [' + inner + ']}, "tail": 1}'
    compiled = compile_ast(JSON_GRAMMAR)
    root = compiled.codegen_grammar
    calls: list[tuple[str, str]] = []

    def recording_parse(grammar, source, fold, resolve=None):
        calls.append((str(grammar.start), source))
        return parse_model(grammar, source, fold, resolve)

    split = split_model(recording_parse, root, Request(text, compiled.fold), 4)
    assert split is not None
    assert split == parse_model(root, text, compiled.fold)
    assert split.to_text() == text
    assert any(start == "object" and '"inner"' in source for start, source in calls)
    assert not any(start == "array" for start, _source in calls)


def test_a_whole_document_run_declines_and_public_parse_falls_back(
    json_compiled: tuple[str, CompiledGrammar],
) -> None:
    """A top-level JSON array is a region, but its pieces have the wrong root."""
    name, compiled = json_compiled
    text = "[" + ",".join(str(i) for i in range(2500)) + "]"
    grammar, fold = compiled.codegen_grammar, compiled.fold

    assert split_model(parse_model, grammar, Request(text, fold), WORKERS[-1]) is None
    expected = parse_model(grammar, text, fold)
    actual = compiled.parse(text, cores=WORKERS[-1])
    assert actual == expected
    assert actual.to_text() == text
    assert name in FORMULATIONS


def test_malformed_nested_input_declines_then_sequentially_refuses(
    json_compiled: tuple[str, CompiledGrammar],
) -> None:
    """A malformed candidate must fall back; the public refusal remains CATCH."""
    name, compiled = json_compiled
    bad = DOCUMENT.replace('"shared": 0', '"shared": ]', 1)
    grammar, fold = compiled.codegen_grammar, compiled.fold

    assert split_model(parse_model, grammar, Request(bad, fold), WORKERS[-1]) is None
    with pytest.raises(UnsupportedConstructError):
        compiled.parse(bad, cores=WORKERS[-1])
    assert name in FORMULATIONS
