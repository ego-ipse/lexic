"""Tests for ``lexic.compile.artifact`` — the ``CompiledGrammar`` artefact.

The class moved here from ``compile/__init__`` (260718: ``export`` imports
it cycle-free); the behavioral surface — ``parse`` delegating to the engine
product and the model narrowing — stays pinned via the public
``lexic.compile`` import, plus the artefact's own identity fields.

Also carries the full-grammar round-trip tests exercising
``compile_from_path(...).parse(...)`` (ported from the removed
``test_artifact_parse.py``): parse → to_text → parse → dump() equality,
via the shared :func:`tests.unit.lexic.compile.compile_helpers.roundtrip` helper.

Grammar input notes:
- arithmetic: root is (expr "=" term "\\n")+.  RHS is *term*, not *expr*, so
  "a+b" is not a valid term — use "x=1\\n", "a=b\\n", or "x=(a+b)\\n".
- chess: root requires "1. " <move> " " <move> "\\n" followed by one or more
  numbered continuation lines, so a minimum of 2 lines is required.
- json_ws: root is object (not value), so "[]" is not a valid top-level input.
"""

from __future__ import annotations

import gc

import pytest

import lexic.compile.artifact as artifact_module
from lexic.compile import (
    CompiledGrammar,
    Vocabulary,
    _assemble_core,
    canonical_grammar,
    compile_from_path,
    compile_text,
    reset_cache_for_tests,
)
from lexic.compile.artifact import CompiledGrammar as ArtifactCompiledGrammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrChr, IrMap, IrStr, IrTokenizer, IrTuple
from lexic.model import GrammarModel
from lexic.parsing import PdaTables
from lexic.parsing.caches import _CLAIMED, _MEMOS, cached_entries, reset_caches
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.compile.compile_helpers import roundtrip


def test_the_package_root_reexports_the_artifact_class():
    """`lexic.compile.CompiledGrammar` IS the artifact module's class."""
    assert CompiledGrammar is ArtifactCompiledGrammar


def test_parse_returns_a_grammar_model_instance():
    """The artefact's parse drives the engine product to a model."""
    cg = compile_text('root ::= "hi"\n')
    inst = cg.parse("hi")
    assert isinstance(inst, GrammarModel)
    assert inst.to_text() == "hi"


def test_parse_refuses_text_outside_the_grammar():
    """A non-deriving input surfaces the engine's UnsupportedConstructError."""
    cg = compile_text('root ::= "hi"\n')
    with pytest.raises(UnsupportedConstructError):
        cg.parse("nope")


def test_compile_from_path_threads_flavour_and_stem():
    """The artefact records its source flavour and stem (export identity)."""
    cg = compile_from_path(GROUND_TRUTH / "json.gbnf")
    assert cg.flavour == "gbnf"
    assert cg.stem == "json"


def test_compile_text_threads_the_content_stem():
    """compile_text stems by content hash — the anon_<sha> identity."""
    cg = compile_text('root ::= "hi"\n')
    assert cg.stem.startswith("anon_")


def test_pda_tables_returns_pda_tables():
    """CompiledGrammar.pda_tables() reaches the engine's compiled predictive
    tables for this artefact's (codegen_grammar, fold)."""
    cg = compile_text('root ::= "hi"\n')
    assert isinstance(cg.pda_tables(), PdaTables)


def test_pda_tables_is_hot_across_calls():
    """Repeated calls return the same tables object — no recompilation."""
    cg = compile_text('root ::= "hi"\n')
    assert cg.pda_tables() is cg.pda_tables()


def test_pda_tables_is_the_same_object_the_parse_path_used():
    """The tables a parse compiled are the exact object pda_tables() returns —
    the artefact and the parse share one memo entry."""
    cg = compile_text('root ::= "hi"\n')
    before = cg.pda_tables()
    cg.parse("hi")
    assert cg.pda_tables() is before


def test_anchors_surfaces_the_engine_analysis():
    """CompiledGrammar.anchors() answers over the codegen grammar: the char a
    co-finite class covers is de-certified, the excluded closer stays, and the
    engine memo makes repeated calls identical."""
    cg = compile_text('root ::= "{" [^}]* "}"\n')
    assert cg.anchors() == frozenset("}")
    assert cg.anchors() is cg.anchors()


# ── arithmetic ────────────────────────────────────────────────────────────────


def test_arithmetic_simple():
    """Minimal: single-char ident assigned a single-digit number."""
    roundtrip("x=1\n", "arithmetic")


def test_arithmetic_ident_rhs():
    """Ident on both sides of the assignment."""
    roundtrip("a=b\n", "arithmetic")


def test_arithmetic_paren_expr():
    """Parenthesised expression as the term on the RHS."""
    roundtrip("x=(a+b)\n", "arithmetic")


# ── list ─────────────────────────────────────────────────────────────────────


def test_list_single_item():
    """Round-trip a single list item."""
    roundtrip("- foo\n", "list")


def test_list_multiple_items():
    """Round-trip multiple list items."""
    roundtrip("- foo\n- bar\n- baz\n", "list")


# ── json_ws ───────────────────────────────────────────────────────────────────


def test_json_ws_empty_object():
    """Simplest valid json_ws input: an empty object."""
    roundtrip("{}", "json_ws")


def test_json_ws_simple_object():
    """Object with one string key and a number value."""
    roundtrip('{"a":1}', "json_ws")


def test_json_ws_nested_object():
    """Nested object — exercises the value→object recursion."""
    roundtrip('{"x":{}}', "json_ws")


# ── chess ─────────────────────────────────────────────────────────────────────


def test_chess_two_move_pairs():
    """Two move pairs (minimum valid chess input: first line + one continuation)."""
    roundtrip("1. e4 e5\n2. d4 d5\n", "chess")


def test_chess_three_move_pairs():
    """Three move pairs — exercises the root_item list."""
    roundtrip("1. e4 e5\n2. d4 d5\n3. Nc3 Nf6\n", "chess")


# ── japanese ─────────────────────────────────────────────────────────────────


def test_japanese_hiragana():
    """Hiragana sequence round-trips exactly."""
    roundtrip("あいう", "japanese")


def test_japanese_single_char():
    """Single hiragana character."""
    roundtrip("あ", "japanese")


# ── Parametrized smoke round-trip ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "grammar,text",
    [
        ("arithmetic", "x=1\n"),
        ("arithmetic", "a=b\n"),
        ("list", "- item\n"),
        ("json_ws", "{}"),
        ("json_ws", '{"a":1}'),
        ("chess", "1. e4 e5\n2. d4 d5\n"),
        ("japanese", "あ"),
    ],
)
def test_roundtrip_parametrized(grammar: str, text: str):
    """Parametrized round-trip test for all grammars."""
    roundtrip(text, grammar)


# ── Negative: bad input raises ────────────────────────────────────────────────


def test_parse_invalid_raises():
    """Completely invalid input for arithmetic must raise a parse error."""
    with pytest.raises(UnsupportedConstructError):
        compile_from_path(GROUND_TRUTH / "arithmetic.gbnf").parse(
            "THIS IS NOT VALID ARITHMETIC !!!\n"
        )


def test_the_table_seam_refuses_a_vocabularyless_grammar_in_words() -> None:
    """`pda_tables` says what `parse` says, not what the dispatcher hit.

    A token-segmented grammar has no engine until a vocabulary is bound. The
    table seam used to surface the atom dispatcher's own miss
    (``IrTypeMap: no entry for IrAlphabet``), which names an internal table
    instead of the thing the caller must do.
    """
    compiled = compile_from_path(GROUND_TRUTH / "think.gbnf")
    with pytest.raises(UnsupportedConstructError, match="needs a vocabulary"):
        compiled.pda_tables()


# ── cache lifetime — the artefact end of lexic.parsing.caches ──────────────
#
# The registry's own verbs (memo/adopt/track/release/reset_caches) are pinned
# directly in tests/unit/lexic/parsing/test_caches.py. These pin the same
# machinery driven by a REAL CompiledGrammar, end to end.

_DRAIN_GRAMMAR = 'root ::= item+\nitem ::= [a-z]+ ","\n'
_DRAIN_TEXT = "abcdefgh," * 4000  # well past the 2 KiB / worker split floor

_BIND_VOCAB = {"a": 0, "b": 1, ",": 2}


def _bind_tokenizer() -> IrTokenizer:
    return IrTokenizer.from_vocab(
        "tokens", IrMap(*(IrTuple(IrStr(t), IrChr(i)) for t, i in _BIND_VOCAB.items()))
    )


def _warm_drain_grammar() -> None:
    """Prime the flavour's OWN self-grammar artefact (a permanent memo entry
    per the module's own design -- ``lexic.compile``'s content cache is
    deliberately unbounded) so a test's baseline measurement, taken right
    after this call, does not mistake that one-time warm-up cost for a leak
    from the artefact under test."""
    canonical_grammar(_DRAIN_GRAMMAR, GBNF_FLAVOUR)


def _fresh_artifact(text: str, stem: str) -> CompiledGrammar:
    """Compile WITHOUT the content-addressed ``lexic.compile`` cache, so the
    result is collectible the moment the caller drops it -- the public
    ``compile_ast``/``compile_text`` route pins every artefact it returns
    alive forever unless the caller separately evicts it, which would fold
    two different things (the compile memo, the identity memos this file
    exists to pin) into one assertion."""
    ast = canonical_grammar(text, GBNF_FLAVOUR)
    return _assemble_core(
        ast, stem=stem, source=text, flavour_name="gbnf", vocabulary=Vocabulary()
    )


def _memo_lengths() -> tuple[int, ...]:
    """Per-registered-memo entry counts, in registration order.

    A stronger check than the aggregate :func:`cached_entries` sum: a memo
    that grew while a sibling shrank by the same amount would pass an
    aggregate comparison and fail this one.
    """
    return tuple(len(entry.entries) for entry in _MEMOS)


def _owned_count(owner: object) -> int:
    """How many entries across every registered memo name ``id(owner)``."""
    oid = id(owner)
    total = 0
    for entry in _MEMOS:
        for key in entry.entries:
            if not entry.ids:
                total += key == oid
            else:
                total += any(key[at] == oid for at in entry.ids)
    return total


def _drain_round(cores: int, tracking: bool) -> tuple[int, int]:
    """Compile, parse and release one artefact; return (baseline, after)."""
    reset_cache_for_tests()
    real_track = artifact_module.track
    if not tracking:
        artifact_module.track = lambda *_a, **_k: None
    try:
        _warm_drain_grammar()
        baseline = cached_entries()
        cg = _fresh_artifact(_DRAIN_GRAMMAR, f"drain-{cores}-{tracking}")
        assert cg.parse(_DRAIN_TEXT, cores=cores).to_text() == _DRAIN_TEXT
        del cg
        gc.collect()
        return baseline, cached_entries()
    finally:
        artifact_module.track = real_track
        reset_cache_for_tests()


@pytest.mark.parametrize("cores", [1, 4])
def test_dropping_an_artefact_drains_its_memo_entries_to_baseline(cores: int) -> None:
    """compile -> parse -> drop -> gc returns registered entries to baseline,
    both sequential (cores=1) and a split-eligible worker count."""
    baseline, after = _drain_round(cores, tracking=True)
    assert after == baseline


@pytest.mark.parametrize("cores", [1, 4])
def test_without_tracking_at_its_use_site_the_dropped_entries_persist(
    cores: int,
) -> None:
    """Control row: disabling ``lexic.compile.artifact.track`` (the USE site
    ``CompiledGrammar.__post_init__`` actually calls) is what proves the
    finalizer drains the entries — patching ``lexic.parsing.caches.track``
    instead would be a no-op, since the name is bound into ``artifact``'s
    namespace at import time."""
    baseline, after = _drain_round(cores, tracking=False)
    assert after > baseline


def test_a_derived_bind_does_not_steal_the_sources_claim() -> None:
    """``bind()`` shares its source's ``grammar`` and ``fold`` identity — a
    CHAR grammar's route keys its model-product memo on fold identity too
    (a token grammar's does not, since ``token_model`` never touches the
    fold-keyed memo — this needs the char route to exercise it). Releasing
    the SHORT-lived derived artefact must not evict entries the LONGER-lived
    source still relies on. Asserted via entry survival, not timing: the
    source's own memo entries are the same count before and after the
    derived artefact is dropped."""
    reset_cache_for_tests()
    tok = _bind_tokenizer()
    source = _fresh_artifact(_DRAIN_GRAMMAR, "claim-source")
    source.parse(_DRAIN_TEXT, cores=1)
    assert id(source.grammar) in _CLAIMED
    assert id(source.product) in _CLAIMED
    before = _owned_count(source.product)
    assert before > 0  # the parse actually populated product-identity-keyed entries

    derived = source.bind(tok)
    assert derived.grammar is source.grammar
    assert derived.product is source.product
    derived.parse(_DRAIN_TEXT, cores=1)
    del derived
    gc.collect()

    assert id(source.grammar) in _CLAIMED  # still claimed -- by source
    assert id(source.product) in _CLAIMED
    assert _owned_count(source.product) == before  # nothing the source owns was evicted
    reset_cache_for_tests()


def test_the_adoption_chain_drains_every_registered_memo_on_release() -> None:
    """The chain a parse mints (model cache -> compiled tables -> lexrun run
    candidates) drains fully when its one owning artefact releases -- no
    orphaned entry survives in ANY registered memo, not just in aggregate."""
    reset_cache_for_tests()
    _warm_drain_grammar()
    baseline = _memo_lengths()
    cg = _fresh_artifact(_DRAIN_GRAMMAR, "transitivity")
    assert cg.parse(_DRAIN_TEXT, cores=1).to_text() == _DRAIN_TEXT
    assert _memo_lengths() != baseline  # the parse actually populated the chain

    del cg
    gc.collect()
    assert _memo_lengths() == baseline
    reset_cache_for_tests()


def test_reset_cache_for_tests_empties_every_registered_memo() -> None:
    """The public test seam reaches ``reset_caches`` -- the isolation every
    other test in this module (and file) implicitly relies on."""
    cg = _fresh_artifact(_DRAIN_GRAMMAR, "reset-seam")
    cg.parse(_DRAIN_TEXT, cores=1)
    assert cached_entries() > 0

    reset_cache_for_tests()
    assert cached_entries() == 0


def test_eviction_is_safe_a_live_artefact_recomputes_cold_but_exact() -> None:
    """Every registered memo is a PURE memo: wiping every entry out from
    under a still-live artefact costs a recomputation and changes no
    answer -- the eviction case a bare id()-keyed cache could not survive."""
    reset_cache_for_tests()
    cg = compile_text(_DRAIN_GRAMMAR, cache_key="cold-recompute")
    warm = cg.parse(_DRAIN_TEXT, cores=1)
    warm_tables = cg.pda_tables()

    reset_caches()  # evict everything, including this live artefact's own
    assert cached_entries() == 0

    cold_tables = cg.pda_tables()
    assert cold_tables is not warm_tables  # genuinely recomputed, not still warm
    cold = cg.parse(_DRAIN_TEXT, cores=1)
    assert cold.to_text() == warm.to_text() == _DRAIN_TEXT
    assert cold.dump() == warm.dump()
    reset_cache_for_tests()
