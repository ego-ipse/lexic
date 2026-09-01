"""End-to-end differential for the envelope split — abnf-meta engaging.

ABNF's own self-grammar (``rulelist ::= filler* rule rl-cont* c-wsp* c-nl?``)
wraps its repeated ``rule``/``rl-cont`` core in optional head and tail items,
and ``rl-cont``'s lead is a noise RUN (blank lines, comments) rather than a
single mark character. That shape only engages the parallel split through the
envelope container plan and the boundary certification proof — this is the
public seam (``compiled.parse(text, cores=N)``) proving it does, exactly,
across worker counts, a malformed document, and a lex-ns variant.
"""

from __future__ import annotations

import pytest

from lexic.compile import Directives, compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR
from lexic.parsing import parse_model
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.orchestrate import Request
from tests.paths import GROUND_TRUTH

_SOURCE = str(ABNF_FLAVOUR.apply(ABNF_FLAVOUR.grammar))

# A handful of the native grammar's own leaf-adjacent rules (every one of
# their refs a leaf with no refs of its own) and its noise vocabulary — a
# lex-ns-style directive pair, named directly rather than re-derived, since
# ABNF_FLAVOUR's self-grammar is a fixed, versioned shape.
_LEXICAL_NAMES = frozenset({"crlf", "cchar", "namechar", "hexdig"})
_NOISE_NAMES = frozenset({"c-wsp", "c-nl", "wsp", "sp"})


def _document() -> str:
    """A real ABNF document, repeated to clear the 16-worker split floor.

    ``resources/ground_truth/json.abnf`` is one grammar file; the abnf-meta
    grammar only describes ABNF's own SYNTAX, so repeating it is still a
    syntactically valid (if semantically redundant) rulelist — a bigger
    document in the same language, not a different one.
    """
    fragment = (GROUND_TRUTH / "json.abnf").read_text(encoding="utf-8")
    text = fragment * 20
    assert len(text) >= 32 * 1024
    return text


DOCUMENT = _document()


@pytest.fixture(scope="module", name="abnf_meta")
def _abnf_meta():
    """The compiled abnf-meta grammar, cached once for every test below."""
    return compile_text(_SOURCE, flavour="abnf", cache_key="test-abnf-meta-e2e")


def test_the_split_actually_engages_and_reaches_the_lead_grammar(abnf_meta) -> None:
    """Non-vacuity: several distinct-sized ``rulelist`` pieces are parsed in
    parallel, and the separator spans reparse under the item grammar
    (``rl-cont``) — proof the envelope plan, not a sequential fallback, is
    what produced the answer."""
    calls: list[tuple[str, int]] = []

    def recording_parse(grammar, source, fold, resolve=None):
        calls.append((str(grammar.start), len(source)))
        return parse_model(grammar, source, fold, resolve)

    split = split_model(
        recording_parse,
        abnf_meta.codegen_grammar,
        Request(DOCUMENT, abnf_meta.product),
        8,
    )

    assert split is not None
    piece_sizes = {size for start, size in calls if start == "rulelist"}
    lead_calls = [size for start, size in calls if start == "rl-cont"]
    assert len(piece_sizes) >= 4, "the document must have split into several pieces"
    assert lead_calls, "at least one separator span must have reparsed"
    assert split == parse_model(abnf_meta.codegen_grammar, DOCUMENT, abnf_meta.product)


@pytest.mark.parametrize("cores", [2, 3, 5, 8, 16])
def test_every_worker_count_matches_sequential_and_round_trips(
    abnf_meta, cores: int
) -> None:
    """Model equality and byte-identical ``to_text()`` at every worker count
    the policy will actually choose between."""
    sequential = abnf_meta.parse(DOCUMENT, cores=1)
    parallel = abnf_meta.parse(DOCUMENT, cores=cores)

    assert parallel == sequential
    assert parallel.to_text() == DOCUMENT


def test_a_malformed_document_refuses_identically_at_every_worker_count(
    abnf_meta,
) -> None:
    """A document the grammar cannot derive must refuse the same way whether
    or not the split engaged — the split is a performance path, not a second
    definition of the language."""
    bad = DOCUMENT.replace("JSON-text = ws value ws", "JSON-text ((( ws value ws", 1)

    for cores in (1, 8, 16):
        with pytest.raises(UnsupportedConstructError):
            abnf_meta.parse(bad, cores=cores)


def test_a_lex_ns_variant_engages_with_the_same_plan_and_equal_results() -> None:
    """``Directives(lexical=..., non_semantic=...)`` changes what the codegen
    grammar looks like, not the language — the envelope plan still derives
    the same unit/mark and the variant still engages, model-equal and
    byte-identical to its own cores=1 parse."""
    variant = compile_text(
        _SOURCE,
        flavour="abnf",
        cache_key="test-abnf-meta-e2e-lex-ns",
        directives=Directives(lexical=_LEXICAL_NAMES, non_semantic=_NOISE_NAMES),
    )

    sequential = variant.parse(DOCUMENT, cores=1)
    for cores in (8, 16):
        parallel = variant.parse(DOCUMENT, cores=cores)
        assert parallel == sequential
        assert parallel.to_text() == DOCUMENT

    split = split_model(
        parse_model,
        variant.codegen_grammar,
        Request(DOCUMENT, variant.product),
        8,
    )
    assert split is not None
    assert split == sequential
