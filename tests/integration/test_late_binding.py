"""``CompiledGrammar.bind`` — one compiled grammar, many vocabularies.

Compiling is per-grammar; a vocabulary is per-deployment. Binding one at
compile time and then needing another meant recompiling, which is wasteful
and — worse — implied a grammar is somehow *about* its tokenizer. It is not:
the classes, the field bindings and the fold are invariant under which
tokenizer is bound, because field naming dispatches on the atom TYPE
(``IrAlphabet``), and resolution rewrites only the inner ordinals.

So ``bind`` re-resolves a retained unresolved codegen grammar and reuses
everything else, returning a NEW artefact (the engine memoises tables per
grammar identity, and a rebound grammar genuinely is a different identity —
its ids differ).

The trap these tests exist to catch: two vocabularies that happen to assign
the SAME ids make every assertion here pass vacuously. The two below place
the shared tokens at deliberately different ids.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path, compile_text, reset_cache_for_tests
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir.base import IrStr, IrTuple
from lexic.ir.encoding import IrTokenizer
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import IrChr

_GRAMMAR = "root ::= <think> thinking </think>\nthinking ::= !</think>*"

# Same spellings, DIFFERENT ids — without this the whole module is vacuous.
_VOCAB_LOW = {"<think>": 0, "</think>": 1, "a": 2, "b": 3, "<": 4, "/think>": 5}
_VOCAB_HIGH = {"<think>": 7, "</think>": 6, "a": 5, "b": 4, "<": 3, "/think>": 2}


def _tokenizer(vocab: dict[str, int], name: str = "tokens") -> IrTokenizer:
    """A vocab-only tokenizer over ``vocab`` (longest match)."""
    return IrTokenizer.from_vocab(
        name, IrMap(*(IrTuple(IrStr(t), IrChr(i)) for t, i in vocab.items()))
    )


LOW = _tokenizer(_VOCAB_LOW)
HIGH = _tokenizer(_VOCAB_HIGH)
TEXT = "<think>ab</think>"


@pytest.fixture(name="compiled")
def _compiled():
    """The grammar compiled once against LOW."""
    reset_cache_for_tests()
    return compile_text(_GRAMMAR, tokenizer=LOW, cache_key="late-binding")


def test_the_two_fixtures_really_do_differ(compiled) -> None:
    """Guard the guard: rebinding must actually move the codegen grammar.

    If both vocabularies assigned the same ids, every other test here would
    pass without ``bind`` doing anything at all.
    """
    assert compiled.codegen_grammar != compiled.bind(HIGH).codegen_grammar


def test_one_grammar_parses_under_two_vocabularies(compiled) -> None:
    """The headline: same text, same model, two different id spaces."""
    rebound = compiled.bind(HIGH)
    assert compiled.parse(TEXT).to_text() == TEXT
    assert rebound.parse(TEXT).to_text() == TEXT
    assert compiled.parse(TEXT).dump() == rebound.parse(TEXT).dump()


def test_binding_equals_compiling_against_that_vocabulary(compiled) -> None:
    """``bind`` is not an approximation of a recompile — it IS one.

    The artefact a rebind produces must match what compiling from source
    against the same tokenizer produces, or the shortcut has drifted.
    """
    reset_cache_for_tests()
    fresh = compile_text(_GRAMMAR, tokenizer=HIGH, cache_key="late-fresh")
    assert compiled.bind(HIGH).codegen_grammar == fresh.codegen_grammar


def test_classes_binds_and_fold_are_reused_not_rebuilt(compiled) -> None:
    """What makes the shortcut sound — and cheap — is this invariance."""
    rebound = compiled.bind(HIGH)
    assert rebound.classes is compiled.classes
    assert rebound.fold is compiled.fold
    assert sorted(rebound.classes) == sorted(compiled.classes)


def test_the_original_artefact_is_untouched(compiled) -> None:
    """A new artefact, not a mutation — the engine memoises per identity."""
    before = compiled.codegen_grammar
    rebound = compiled.bind(HIGH)
    assert compiled.codegen_grammar == before
    assert compiled.tokens.tokenizer is LOW
    assert rebound.tokens.tokenizer is HIGH
    assert rebound is not compiled


def test_rebinding_is_repeatable_and_reversible(compiled) -> None:
    """Rebinding back gives the original codegen grammar — no accumulated state."""
    assert compiled.bind(HIGH).bind(LOW).codegen_grammar == compiled.codegen_grammar
    assert compiled.bind(HIGH).bind(LOW).parse(TEXT).to_text() == TEXT


def test_bind_carries_the_new_vocabulary_into_constrain(compiled) -> None:
    """Generation follows the rebound vocabulary, not the compile-time one."""
    rebound = compiled.bind(HIGH)
    assert set(compiled.constrain().mask()) != set(rebound.constrain().mask())
    assert set(rebound.constrain().mask()) == {7}  # HIGH's <think>
    assert set(compiled.constrain().mask()) == {0}  # LOW's <think>


def test_a_registry_composes_on_rebind(compiled) -> None:
    """``registry=`` binds the grammar's encoding NAME, as at compile time."""
    other = _tokenizer(_VOCAB_HIGH, name="gpt2")
    rebound = compiled.bind(other, IrMap(IrTuple(IrStr("tokens"), other)))
    assert rebound.parse(TEXT).to_text() == TEXT


def test_one_tokenizer_under_two_names_is_still_one_tokenizer() -> None:
    """``tokenizer=`` and ``registry=`` compose — even onto the same tokenizer.

    Found by the rebind test above, but never rebind-specific: the sole
    tokenizer was counted by ENTRY, so binding one under both its own name
    and the grammar's made it look like "multiple tokenizers", which means
    "no segmentation implied" — and a token grammar silently fell back to a
    char parse. It is one tokenizer; identity is what counts.
    """
    tok = _tokenizer(_VOCAB_LOW, name="gpt2")
    reset_cache_for_tests()
    cg = compile_text(
        _GRAMMAR,
        tokenizer=tok,
        registry=IrMap(IrTuple(IrStr("tokens"), tok)),
        cache_key="late-two-names",
    )
    assert cg.tokens.tokenizer is tok
    assert cg.parse(TEXT).to_text() == TEXT


# ── the additivity invariant still holds under rebinding ─────────────────


def test_binding_a_tokenizer_to_a_char_grammar_stays_a_char_parse() -> None:
    """Additivity (SPECS §8) survives the new entry point.

    ``segmented`` is a property of the GRAMMAR, so a rebind cannot move it —
    which is exactly what the additivity gate pins for the compile path.
    """
    char = compile_text("root ::= [a-z]+", cache_key="late-char")
    rebound = char.bind(HIGH)
    assert not rebound.tokens.segmented
    assert rebound.codegen_grammar == char.codegen_grammar
    assert rebound.parse("abc").to_text() == "abc"


def test_a_char_grammar_rebind_still_refuses_nothing_for_constrain() -> None:
    """A char grammar carries a vocabulary for generation alone."""
    char = compile_text("root ::= [a-z]+", cache_key="late-char2")
    with pytest.raises(UnsupportedConstructError):
        char.constrain()  # nothing bound at compile time
    assert char.bind(LOW).constrain().mask()  # ... but a rebind supplies one


# ── compile_from_path carries the same surface as compile_text ───────────


def test_compile_from_path_binds_a_vocabulary(tmp_path) -> None:
    """A token grammar in a FILE can bind a vocabulary.

    Only ``compile_text`` could, so a file-based token grammar forced the
    caller to read the file and call ``compile_text`` — the shim this effort
    exists to delete. Every token test used ``compile_text``, so nothing
    caught it; ``ex12`` did.
    """
    path = tmp_path / "think.gbnf"
    path.write_text(_GRAMMAR, encoding="utf-8")
    compiled = compile_from_path(path, tokenizer=LOW)
    assert compiled.tokens.segmented
    assert compiled.parse(TEXT).to_text() == TEXT


def test_the_path_cache_keys_the_vocabulary_by_value(tmp_path) -> None:
    """Two vocabularies over one file give two artefacts — never a stale hit.

    The cache key holds the tokenizer BY VALUE. Keying on ``id()`` would be
    unsound: ids are unique only among live objects, so a dropped tokenizer's
    address can be reused and return another vocabulary's artefact.
    """
    path = tmp_path / "think.gbnf"
    path.write_text(_GRAMMAR, encoding="utf-8")
    low = compile_from_path(path, tokenizer=LOW)
    high = compile_from_path(path, tokenizer=HIGH)
    assert low.codegen_grammar != high.codegen_grammar
    assert compile_from_path(path, tokenizer=LOW) is low  # equal vocab ⇒ hit
    assert compile_from_path(path) is not low  # unbound is its own artefact


def test_constraining_a_token_grammar_with_a_foreign_vocabulary_refuses() -> None:
    """The silent-empty-mask trap: refuse, don't return "unsatisfiable".

    A segmented grammar's terminals are already resolved to the BOUND
    vocabulary's ids, so ranging over another matches nothing. That produced
    an empty mask — which a caller reads as "this grammar admits no token",
    i.e. a confidently wrong answer with no error. ``bind`` is the one way to
    change a token grammar's vocabulary.
    """
    reset_cache_for_tests()
    compiled = compile_text(_GRAMMAR, tokenizer=LOW, cache_key="constrain-guard")
    assert sorted(compiled.bind(HIGH).constrain().mask()) == [7]  # the right way
    with pytest.raises(UnsupportedConstructError, match="bind"):
        compiled.constrain(HIGH)


def test_a_char_grammar_still_constrains_with_any_vocabulary() -> None:
    """The guard must not break generation over CHAR grammars.

    A char grammar has no token terminals, so any vocabulary drives it —
    that is capability C as documented, and four callers plus ex07 rely on
    it. The refusal above is specific to a grammar that SEGMENTS.
    """
    char = compile_text("root ::= [a-z]+", cache_key="constrain-char")
    assert char.constrain(LOW).mask()
    assert char.constrain(HIGH).mask()


# ── the emit source is the AUTHORED grammar, never a vocabulary's ids ────


AUTHORED = "root ::= <think> thinking </think>"


def test_to_grammar_emits_the_authored_spelling_not_ids(compiled) -> None:
    """A vocabulary is a lens on a grammar, not part of what it says.

    Binding one used to degrade `to_grammar()` from lossless to lossy — the
    user writes `<think>`, the artefact emitted `<[0]>` — which breaks the
    headline invariant that every class has a lossless `to_grammar`. The
    round-trip through `to_text` passed throughout, which is why it hid.
    """
    emitted = str(compiled.parse(TEXT).to_grammar("gbnf"))
    assert AUTHORED in emitted
    assert "<[0]>" not in emitted


def test_rebound_artefacts_emit_the_same_authored_grammar(compiled) -> None:
    """Both vocabularies emit the SAME text — and it is the authored one.

    The bind-order bug (whichever artefact compiled first won for both) is
    not merely fixed here, it is impossible: the classes no longer carry any
    vocabulary's ids, so there is nothing to be stale.
    """
    low_emit = str(compiled.parse(TEXT).to_grammar("gbnf"))
    high_emit = str(compiled.bind(HIGH).parse(TEXT).to_grammar("gbnf"))
    assert low_emit == high_emit
    assert AUTHORED in low_emit


def test_bind_order_does_not_change_either_artefact() -> None:
    """Reverse the order and both still emit the authored grammar."""
    reset_cache_for_tests()
    high_first = compile_text(_GRAMMAR, tokenizer=HIGH, cache_key="order-high")
    rebound_low = high_first.bind(LOW)
    for artefact in (high_first, rebound_low):
        assert AUTHORED in str(artefact.parse(TEXT).to_grammar("gbnf"))


def test_the_canonical_grammar_is_not_vocabulary_locked(compiled) -> None:
    """`compiled.grammar` is the transpile/re-emit source — it must stay authored.

    `export_module` writes a twin's GRAMMAR from this, so baking ids here put
    one vocabulary into committed source and made the twin unusable with any
    other.
    """
    assert AUTHORED in str(GBNF_FLAVOUR.apply(compiled.grammar))


def test_the_engine_still_matches_on_resolved_ids(compiled) -> None:
    """Guard the guard: resolution must still REACH the engine.

    If it did not, token grammars would stop parsing id-granular and these
    tests would pass over a broken parser.
    """
    matched = compiled.codegen_grammar.rules[0].body[0][0].atom
    assert "IrChr(0)" in repr(matched)  # LOW's <think>
    assert compiled.parse(TEXT).to_text() == TEXT


# ── segmented + no vocabulary: refuse at PARSE, never at compile ─────────


def test_a_token_grammar_compiles_and_emits_with_no_vocabulary() -> None:
    """Capability A: reading and emitting a token grammar needs no tokenizer.

    The plan said to refuse this at COMPILE time. That would have deleted a
    documented capability — README §Tokens: "read/emit token grammars with
    **no** tokenizer at all". Compiling must stay legal; only parsing needs
    a vocabulary.
    """
    reset_cache_for_tests()
    compiled = compile_text(_GRAMMAR, cache_key="cap-a")
    assert compiled.classes
    assert compiled.tokens.segmented
    assert compiled.tokens.tokenizer is None
    assert AUTHORED in str(GBNF_FLAVOUR.apply(compiled.grammar))


def test_parsing_without_a_vocabulary_refuses_instead_of_leaking() -> None:
    """It leaked ``IrKeyError: no entry for IrAlphabet`` from inside dispatch.

    An engine-internal key error tells a caller nothing about what they did
    wrong; the fix is a message naming the missing thing and the two ways to
    supply it.
    """
    reset_cache_for_tests()
    compiled = compile_text(_GRAMMAR, cache_key="cap-a-parse")
    with pytest.raises(UnsupportedConstructError, match="needs a vocabulary"):
        compiled.parse(TEXT)
    assert compiled.bind(LOW).parse(TEXT).to_text() == TEXT  # ... and this is how


def test_two_tokenizers_in_a_registry_refuse_at_parse() -> None:
    """``tokenizer=`` and ``registry=`` compose — onto TWO vocabularies they
    imply no sole one, and that artefact cannot parse.

    Reachable through the documented composing surface, so it must fail with
    a diagnosis rather than an internal key error.
    """
    other = _tokenizer({"x": 0}, name="other")
    reset_cache_for_tests()
    compiled = compile_text(
        _GRAMMAR,
        tokenizer=LOW,
        registry=IrMap(IrTuple(IrStr("other"), other)),
        cache_key="two-toks",
    )
    assert compiled.tokens.tokenizer is None
    with pytest.raises(UnsupportedConstructError, match="needs a vocabulary"):
        compiled.parse(TEXT)


def test_constrain_names_which_wrong_it_is() -> None:
    """Two different wrongs deserve two diagnoses, both pointing at bind().

    Saying "the bound vocabulary" when nothing was bound sends the reader
    looking for something that does not exist.
    """
    reset_cache_for_tests()
    unbound = compile_text(_GRAMMAR, cache_key="diag-unbound")
    with pytest.raises(UnsupportedConstructError, match="no vocabulary yet"):
        unbound.constrain(HIGH)
    bound = compile_text(_GRAMMAR, tokenizer=LOW, cache_key="diag-bound")
    with pytest.raises(UnsupportedConstructError, match="another vocabulary"):
        bound.constrain(HIGH)
