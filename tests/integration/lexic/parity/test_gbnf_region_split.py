"""End-to-end differential for the gbnf region-family activation (I14/I14b).

A grammar shaped like GBNF's own self-grammar — multi-line rules separated by
a noise run, character classes with a fully-literal empty-instance sibling
(``"[]"`` beside ``"[" … "]"``), and a ``tok-id``-shaped ``<[`` … ``]>``
construct whose closer is reached through a two-armed tail reference — used
to certify NO region at all (I2b's wall): ``tok-id`` had no derivable closer,
its visible ``"<["`` blocked the ``[``-led classes, and their dropped bodies
de-certified the quote and the comment in turn. With the region family read
correctly, all of it certifies and the envelope split engages. This is the
public seam (``compiled.parse(text, cores=N)``), not the discovery internals
those are pinned at directly in ``discovery/test_interiors.py`` and
``plan/test_envelope.py``.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing import parse_model
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.orchestrate import Request
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.parallel.envelope_fixtures import GBNF_REGION_SOURCE

_WORKERS = (1, 2, 8)


def _rule_line(i: int) -> str:
    letters = f"{chr(97 + i % 26)}{chr(97 + (i // 26) % 26)}"
    kind = i % 5
    if kind == 0:
        body = f'"lit{letters}"'
    elif kind == 1:
        body = "[abcXYZ019]"
    elif kind == 2:
        body = "[]"
    elif kind == 3:
        body = f"<[{i}>"
    else:
        body = f"<[{i}-{i}>"
    return f"{letters} ::= {body}"


def _document(count: int) -> str:
    """``count`` rules, every arm shape represented, comments interleaved."""
    parts = [_rule_line(0)]
    for i in range(1, count):
        sep = "\n" if i % 6 else "\n# a comment here\n"
        parts.append(sep + _rule_line(i))
    return "".join(parts)


DOCUMENT = _document(600)


@pytest.fixture(scope="module", name="compiled")
def _compiled():
    return compile_text(GBNF_REGION_SOURCE, cache_key="test-gbnf-region-split")


@pytest.mark.parametrize("workers", _WORKERS)
def test_worker_counts_match_sequential_and_round_trip(compiled, workers: int) -> None:
    """Exact model, byte-identical text, at every worker count."""
    sequential = compiled.parse(DOCUMENT, cores=1)
    parallel = compiled.parse(DOCUMENT, cores=workers)

    assert type(parallel) is type(sequential)
    assert parallel == sequential
    assert parallel.to_text() == DOCUMENT


def test_the_split_is_not_vacuous(compiled) -> None:
    """The instrumented seam proves several workers actually parsed — not a
    sequential fallback dressed as a split."""
    grammar, binding = compiled.codegen_grammar, compiled.product
    sequential = parse_model(grammar, DOCUMENT, binding)
    calls: list[int] = []

    def recording_parse(g, source, f, resolve=None):
        calls.append(len(source))
        return parse_model(g, source, f, resolve)

    split = split_model(recording_parse, grammar, Request(DOCUMENT, binding), 8)

    assert split is not None, "the region-family activation must carry this split"
    assert split == sequential
    assert split.to_text() == DOCUMENT
    assert len(calls) >= 2, "only one worker actually parsed"


def test_a_corrupted_document_refuses_identically_at_every_worker_count(
    compiled,
) -> None:
    """Splitting never rescues, or re-labels, a document the grammar refuses."""
    bad = DOCUMENT.replace("ba ::= [abcXYZ019]", "ba := [abcXYZ019]", 1)
    assert bad != DOCUMENT

    for cores in _WORKERS:
        with pytest.raises(UnsupportedConstructError):
            compiled.parse(bad, cores=cores)


def test_the_real_gbnf_self_grammar_engages_if_quick() -> None:
    """The real bench witness, kept small: GBNF's own self-grammar parsing a
    real ground-truth file repeated a handful of times."""
    source = str(GBNF_FLAVOUR.apply(GBNF_FLAVOUR.grammar))
    compiled = compile_text(
        source, cache_key="test-gbnf-meta-region-split", flavour="gbnf"
    )
    text = (GROUND_TRUTH / "json.gbnf").read_text(encoding="utf-8") * 12
    assert len(text) >= 16 * 1024

    sequential = compiled.parse(text, cores=1)
    for workers in (8, 16):
        parallel = compiled.parse(text, cores=workers)
        assert parallel == sequential
        assert parallel.to_text() == text
