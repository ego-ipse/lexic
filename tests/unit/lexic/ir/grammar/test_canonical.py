"""Tests for ir/canonical.py — the language-preserving canonical-form rewrites.

Each rewrite (1-9, per the module docstring) is isolated to a minimal grammar
so a failure points at the exact pass that broke, rather than a real
ground-truth fixture where several rewrites fire together (that coverage
lives in tests/integration/test_canonical_fixpoint.py).
"""

from __future__ import annotations

import time

import pytest

from lexic.compile import canonical_grammar, compile_from_path, compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import census, inline_refs
from lexic.ir.grammar.canonical import canonicalize, fold_name
from lexic.ir.grammar.nodes import (
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.grammar.operators import IrNot
from lexic.ir.spine.records import IrSeq
from tests.paths import GROUND_TRUTH

MAX_CODEPOINT = 0x10FFFF


def ast_for(body, start: str = "r", extra: tuple[IrRule, ...] = ()) -> IrAst:
    """A single-rule (plus optional extra rules) IrAst wrapping ``body``."""
    return IrAst(IrSeq(IrRule("r", body), *extra), start)


def canon_body(body, start: str = "r", extra: tuple[IrRule, ...] = ()):
    """canonicalize(ast_for(body, ...)) and return rule "r"'s canonical body."""
    ast = canonicalize(ast_for(body, start, extra))
    return next(rule.body for rule in ast.rules if rule.name == "r")


# ── rewrite 1: one-member char class -> literal ─────────────────────────


def test_rewrite1_one_member_charclass_becomes_literal():
    """A single-code-point char class collapses to an IrLiteral."""
    result = canon_body(IrCharClass(IrChr("x")))
    assert result == IrAlternation(IrSequence(IrItem(IrLiteral("x"))))


def test_rewrite1_multi_member_charclass_stays_a_charclass():
    """A multi-member char class is untouched by rewrite 1."""
    result = canon_body(IrCharClass(IrChr("x"), IrChr("y")))
    assert isinstance(result[0][0].atom, IrCharClass)


# ── rewrite 2: single-char/range arm merge ──────────────────────────────


def test_rewrite2_merges_single_char_literal_arms_into_one_charclass():
    """Adjacent single-char literal alternation arms fuse into one char class."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))), IrSequence(IrItem(IrLiteral("b")))
    )
    result = canon_body(body)
    assert len(result) == 1
    atom = result[0][0].atom
    assert isinstance(atom, IrCharClass)
    assert atom.members() == [ord("a"), ord("b")]


def test_rewrite2_does_not_merge_a_multi_char_arm():
    """An arm covering more than one item is not char-class material — kept apart."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))),
        IrSequence(IrItem(IrRuleRef("thing")), IrItem(IrLiteral("b"))),
    )
    result = canon_body(body, extra=(IrRule("thing", IrLiteral("T")),))
    assert len(result) == 2


def test_rewrite2_merges_charclass_arms_via_intervals():
    """Two char-class arms fuse by interval math into one coalesced class."""
    body = IrAlternation(
        IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("4"))))),
        IrSequence(IrItem(IrCharClass(IrRange(IrChr("5"), IrChr("9"))))),
    )
    result = canon_body(body)
    assert result == IrAlternation(
        IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))
    )


def test_rewrite2_does_not_merge_a_multi_char_literal_arm():
    """A multi-char literal arm is not char-class material — a mergeable run
    on either side of it stays separate (two flushes, not one)."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))),
        IrSequence(IrItem(IrLiteral("b"))),
        IrSequence(IrItem(IrLiteral("cd"))),
        IrSequence(IrItem(IrLiteral("e"))),
        IrSequence(IrItem(IrLiteral("f"))),
    )
    result = canon_body(body)
    assert len(result) == 3
    assert isinstance(result[0][0].atom, IrCharClass)
    assert result[0][0].atom.members() == [ord("a"), ord("b")]
    assert result[1] == IrSequence(IrItem(IrLiteral("cd")))
    assert isinstance(result[2][0].atom, IrCharClass)
    assert result[2][0].atom.members() == [ord("e"), ord("f")]


def test_rewrite2_unmergeable_middle_arm_splits_into_two_flushes():
    """Two mergeable runs separated by an unmergeable arm merge independently."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))),
        IrSequence(IrItem(IrLiteral("b"))),
        IrSequence(IrItem(IrRuleRef("thing"))),
        IrSequence(IrItem(IrLiteral("c"))),
        IrSequence(IrItem(IrLiteral("d"))),
    )
    result = canon_body(body, extra=(IrRule("thing", IrLiteral("T")),))
    assert len(result) == 3
    first, ref_arm, last = result
    assert isinstance(first[0].atom, IrCharClass)
    assert first[0].atom.members() == [ord("a"), ord("b")]
    assert ref_arm == IrSequence(IrItem(IrRuleRef("thing")))
    assert isinstance(last[0].atom, IrCharClass)
    assert last[0].atom.members() == [ord("c"), ord("d")]


def test_rewrite2_does_not_merge_a_quantified_charclass_arm():
    """A quantified char-class arm is excluded from the interval-merge run."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))),
        IrSequence(IrItem(IrCharClass(IrChr("b")), IrQuantifier(0, 1))),
    )
    result = canon_body(body)
    assert len(result) == 2
    assert str(result[0][0].atom) == "a"
    assert result[1][0].quantifier == IrQuantifier(0, 1)


def test_rewrite2_merge_collapsing_to_a_single_point_becomes_a_literal():
    """Two arms of the identical single char merge to a one-member class,
    which then collapses to an IrLiteral via the same flush path (rewrite 1)."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))), IrSequence(IrItem(IrLiteral("a")))
    )
    result = canon_body(body)
    assert result == IrAlternation(IrSequence(IrItem(IrLiteral("a"))))


def test_rewrite2_merges_a_unicode_complement_arm_without_materialising():
    """A ``[^a]`` complement arm (rewrite 4 → ~1.1M-point cover) merges by interval.

    The merge path must stay in the interval domain — enumerating the
    complement's members would build a million-entry list. The result is the
    complement class itself (the single-char literal arm falls inside it).
    """
    body = IrAlternation(
        IrSequence(IrItem(IrNot(IrCharClass(IrChr("a"))))),
        IrSequence(IrItem(IrLiteral("a"))),
    )
    result = canon_body(body)
    assert len(result) == 1
    atom = result[0][0].atom
    assert isinstance(atom, IrCharClass)
    assert atom == IrCharClass(IrRange(IrChr(0), IrChr(MAX_CODEPOINT)))


def test_rewrite2_unicode_complement_merge_stays_interval_native():
    """The whole canonicalize pass over a ``[^a]`` alternation arm is fast.

    A time bound (not a structural one) here guards the full pipeline —
    canonicalize() dispatching down through _merge_arms/flush — against a
    regression that reintroduces per-point materialisation (the Task 1 defect
    was ~1.1M IrChr constructions for exactly this shape).
    """
    body = IrAlternation(IrSequence(IrItem(IrNot(IrCharClass(IrChr("a"))))))
    start = time.perf_counter()
    canon_body(body)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, (
        f"canonicalize of a Unicode-complement arm took {elapsed:.3f}s"
    )


# ── rewrite 3: adjacent literal run merge ───────────────────────────────


def test_rewrite3_merges_adjacent_unquantified_literals():
    """A run of adjacent unquantified literal items folds to one multi-char literal."""
    body = IrSequence(
        IrItem(IrLiteral("a")), IrItem(IrLiteral("b")), IrItem(IrLiteral("c"))
    )
    result = canon_body(body)
    assert result == IrAlternation(IrSequence(IrItem(IrLiteral("abc"))))


def test_rewrite3_does_not_merge_across_a_quantified_literal():
    """A quantified literal breaks the run — it does not fold into its neighbours."""
    body = IrSequence(
        IrItem(IrLiteral("a")),
        IrItem(IrLiteral("b"), IrQuantifier(0, 1)),
        IrItem(IrLiteral("c")),
    )
    result = canon_body(body)
    items = result[0]
    assert [str(item.atom) for item in items] == ["a", "b", "c"]
    assert items[1].quantifier == IrQuantifier(0, 1)


# ── rewrite 4: IrNot(charclass) -> positive complement ──────────────────


def test_rewrite4_not_charclass_becomes_positive_complement():
    """IrNot of a char class rewrites to its positive Unicode-complement spans."""
    body = IrItem(IrNot(IrCharClass(IrChr("a"))))
    result = canon_body(body)
    atom = result[0][0].atom
    assert isinstance(atom, IrCharClass)
    assert atom == IrCharClass(IrChr("a")).complement()


# ── rewrite 5: redundant single-arm/single-item group inline ────────────


def test_rewrite5_inlines_a_redundant_unquantified_group():
    """A single-arm, single-item, unquantified group splices into its parent sequence."""
    body = IrSequence(
        IrItem(IrAlternation(IrSequence(IrItem(IrLiteral("a"))))),
        IrItem(IrRuleRef("thing")),
    )
    result = canon_body(body, extra=(IrRule("thing", IrLiteral("T")),))
    assert result == IrAlternation(
        IrSequence(IrItem(IrLiteral("a")), IrItem(IrRuleRef("thing")))
    )


def test_rewrite5_does_not_inline_a_multi_arm_group():
    """A group with more than one arm is not redundant — left as a group atom.

    The arms are a literal and a ruleref (not char-class material), so
    rewrite 2's arm merge does not collapse them into a single-member
    class first — this isolates rewrite 5's own single-arm precondition.
    """
    body = IrItem(
        IrAlternation(
            IrSequence(IrItem(IrLiteral("a"))), IrSequence(IrItem(IrRuleRef("thing")))
        )
    )
    result = canon_body(body, extra=(IrRule("thing", IrLiteral("T")),))
    atom = result[0][0].atom
    assert isinstance(atom, IrAlternation)
    assert len(atom) == 2


# ── rewrite 6: quantifier pushed onto the inner atom ────────────────────


def test_rewrite6_pushes_quantifier_through_single_item_group():
    """``("!")?`` collapses to the plain quantified literal ``"!"?``."""
    body = IrItem(IrAlternation(IrSequence(IrItem(IrLiteral("!")))), IrQuantifier(0, 1))
    result = canon_body(body)
    item = result[0][0]
    assert item.atom == IrLiteral("!")
    assert item.quantifier == IrQuantifier(0, 1)


def test_rewrite6_leaves_a_quantified_inner_item_untouched():
    """A group whose inner item is itself quantified is not collapsed."""
    body = IrItem(
        IrAlternation(IrSequence(IrItem(IrLiteral("!"), IrQuantifier(0, 1)))),
        IrQuantifier(0, 1),
    )
    result = canon_body(body)
    atom = result[0][0].atom
    assert isinstance(atom, IrAlternation)


# ── rewrite 7: name folding + collision detection ───────────────────────


def test_rewrite7_folds_rule_names_and_refs_to_lowercase_hyphenated():
    """Rule names and refs fold: lowercase, ``_`` -> ``-``."""
    ast = IrAst(
        IrSeq(
            IrRule("My_Rule", IrRuleRef("Other_Thing")),
            IrRule("Other_Thing", IrLiteral("x")),
        ),
        "My_Rule",
    )
    result = canonicalize(ast)
    names = {rule.name for rule in result.rules}
    assert names == {"my-rule", "other-thing"}
    assert result.start == "my-rule"


def test_rewrite7_distinct_rule_name_collision_raises():
    """Two distinct rules folding to the same canonical name is an error."""
    ast = IrAst(
        IrSeq(IrRule("Foo", IrLiteral("a")), IrRule("foo", IrLiteral("b"))), "Foo"
    )
    with pytest.raises(UnsupportedConstructError):
        canonicalize(ast)


def test_fold_name_is_lowercase_underscore_to_hyphen():
    """fold_name is the raw name-folding function rewrite 7 applies."""
    assert fold_name("My_Rule_Name") == "my-rule-name"


# ── rewrite 8: char-class normal form ────────────────────────────────────


def test_rewrite8_charclass_deduped_sorted_and_coalesced():
    """A charclass with duplicate/unsorted/coalescible members normalises."""
    body = IrCharClass(IrChr("c"), IrChr("a"), IrChr("b"))
    result = canon_body(body)
    atom = result[0][0].atom
    assert atom == IrCharClass(IrChr("a"), IrChr("b"), IrChr("c")).normalized()


# ── rewrite 8b: empty-literal item elimination ───────────────────────────


def test_rewrite8b_drops_empty_literal_item_preserving_arm_shape():
    """An ``IrLiteral('')`` (epsilon) item is dropped; the arm shape stays."""
    body = IrSequence(IrItem(IrLiteral("")), IrItem(IrLiteral("x")))
    result = canon_body(body)
    assert result == IrAlternation(IrSequence(IrItem(IrLiteral("x"))))


# ── rewrite 9: canonical rule order ──────────────────────────────────────


def test_rewrite9_reorders_rules_start_first_by_reference():
    """Rules reorder start-first, then breadth-first by reference (RuleOrder)."""
    ast = IrAst(
        IrSeq(
            IrRule("unrelated", IrLiteral("z")),
            IrRule("b", IrLiteral("y")),
            IrRule("root", IrRuleRef("b")),
        ),
        "root",
    )
    result = canonicalize(ast)
    assert [rule.name for rule in result.rules] == ["root", "b", "unrelated"]


# ── idempotence over a composite grammar ─────────────────────────────────


def test_canonicalize_is_idempotent_on_a_composite_grammar():
    """canonicalize(canonicalize(ast)) == canonicalize(ast) across several rewrites at once."""
    ast = IrAst(
        IrSeq(
            IrRule(
                "Root",
                IrSequence(
                    IrItem(IrAlternation(IrSequence(IrItem(IrLiteral("a"))))),
                    IrItem(IrLiteral("")),
                    IrItem(IrLiteral("b")),
                    IrItem(IrNot(IrCharClass(IrChr("c"))), IrQuantifier(0, 1)),
                    IrItem(IrRuleRef("Digit")),
                ),
            ),
            IrRule("Digit", IrCharClass(IrChr("3"), IrChr("1"), IrChr("2"))),
        ),
        "Root",
    )
    once = canonicalize(ast)
    twice = canonicalize(once)
    assert twice == once


# ── IrAlphabet fencing (a foreign encoding — the UTF passes must not touch it) ──


def _alpha_item(inner, quant: IrQuantifier = IrQuantifier()) -> IrItem:
    """A sequence item wrapping ``inner`` in a token-encoding alphabet."""
    return IrItem(IrAlphabet("tok", inner), quant)


def test_canonicalize_does_not_collapse_id_form_token_to_a_glyph():
    """A lone token id stays an ordinal class, not a UTF glyph literal."""
    body = IrSequence(_alpha_item(IrCharClass(IrChr(1000))))
    inner = canon_body(body)[0][0].atom.inner
    assert inner == IrCharClass(IrChr(1000))


def test_canonicalize_does_not_complement_a_negated_token():
    """A negated token keeps its ``IrNot`` — no ``MAX_CODEPOINT`` blow-up."""
    body = IrSequence(_alpha_item(IrNot(IrCharClass(IrChr(1001)))))
    inner = canon_body(body)[0][0].atom.inner
    assert inner == IrNot(IrCharClass(IrChr(1001)))


def test_canonicalize_leaves_text_form_token_literal_verbatim():
    """A text-form token literal is preserved as-is."""
    body = IrSequence(_alpha_item(IrLiteral("<think>")))
    inner = canon_body(body)[0][0].atom.inner
    assert inner == IrLiteral("<think>")


def test_canonicalize_does_not_merge_token_and_char_arms():
    """A token arm and a char arm must never fuse into one class."""
    body = IrAlternation(
        IrSequence(_alpha_item(IrCharClass(IrChr(1)))),
        IrSequence(IrItem(IrCharClass(IrChr(97)))),
    )
    canon = canon_body(body)
    assert len(canon) == 2  # two distinct arms, not one merged class
    assert canon[0][0].atom == IrAlphabet("tok", IrCharClass(IrChr(1)))
    assert canon[1][0].atom == IrLiteral("a")  # the char arm still canonicalises


def test_canonicalize_still_canonicalises_around_an_alphabet():
    """Fencing the alphabet does not stop the rest of the rule normalising."""
    body = IrSequence(
        IrItem(IrCharClass(IrChr(48), IrChr(49), IrChr(50))),  # [012] -> [0-2]
        _alpha_item(IrCharClass(IrChr(5))),
    )
    canon = canon_body(body)
    assert canon[0][0].atom == IrCharClass(IrRange(IrChr(48), IrChr(50)))
    assert canon[0][1].atom == IrAlphabet("tok", IrCharClass(IrChr(5)))


# ── inline_refs — the @lexical transform (lives in canonical.py) ──

PAIR = 'root ::= word "=" word\nword ::= letter+\nletter ::= [a-z]\n'


def grammar(text: str = PAIR) -> IrAst:
    """The canonical AST of a GBNF source."""
    return canonical_grammar(text, GBNF_FLAVOUR)


def refs_of(ast: IrAst, name: str) -> set[str]:
    """The rule names ``name``'s body still references."""
    body = next(rule.body for rule in ast.rules if str(rule.name) == name)
    return {
        str(node)
        for node in (entry.node for entry in census(body))
        if isinstance(node, IrRuleRef)
    }


def test_a_marked_rules_body_becomes_ref_free() -> None:
    """The whole point: nothing left to descend into."""
    assert refs_of(grammar(), "word") == {"letter"}
    assert refs_of(inline_refs(grammar(), frozenset({"word"})), "word") == set()


def test_an_unmarked_rule_is_untouched() -> None:
    """Declared, never inferred — a rule nobody marked keeps its references."""
    inlined = inline_refs(grammar(), frozenset({"word"}))
    assert refs_of(inlined, "root") == {"word"}


def test_inlining_nothing_returns_the_grammar() -> None:
    """The no-op case is the identity, not a rebuild."""
    ast = grammar()
    assert inline_refs(ast, frozenset()) is ast


def test_an_unknown_name_is_ignored() -> None:
    """The directive contract: naming a rule the grammar lacks does nothing."""
    assert inline_refs(grammar(), frozenset({"nope"})) == grammar()


def test_a_cycle_refuses_with_words() -> None:
    """A recursive rule has no finite inlining, and the words say so."""
    recursive = grammar('root ::= list\nlist ::= "a" list?\n')
    with pytest.raises(UnsupportedConstructError, match="cycle has no finite"):
        inline_refs(recursive, frozenset({"list"}))


def test_a_token_terminal_refuses_with_words() -> None:
    """A token id is not a character run — its interior cannot be inlined."""
    tokens = grammar("root ::= chunk\nchunk ::= <t> body\nbody ::= [a-z]+\n")
    with pytest.raises(UnsupportedConstructError, match="token terminal"):
        inline_refs(tokens, frozenset({"chunk"}))


# ── the directive, end to end ─────────────────────────────────────────


def marked(source: str, names: str) -> str:
    """A grammar source with a ``@lexical`` directive prepended."""
    return f"# @lexical {names}\n{source}"


def test_the_directive_makes_the_rule_a_value_str() -> None:
    """``classify_rule`` sees a ref-free body and says value_str — by shape."""
    plain = compile_text(PAIR, cache_key="t9-plain")
    lexical = compile_text(marked(PAIR, "word"), cache_key="t9-lexical")
    kinds = {b.rule_name: b.kind for b in plain.moments.binding}
    after = {b.rule_name: b.kind for b in lexical.moments.binding}
    assert kinds["word"] == "sequence"
    assert after["word"] == "value_str"
    assert after["root"] == kinds["root"]  # unmarked rules keep their shape


def test_the_language_is_unchanged() -> None:
    """Language-preserving: the same text parses and round-trips either way."""
    plain = compile_text(PAIR, cache_key="t9-plain2")
    lexical = compile_text(marked(PAIR, "word"), cache_key="t9-lexical2")
    for text in ("ab=cd", "x=y", "hello=world"):
        assert plain.parse(text).to_text() == text
        assert lexical.parse(text).to_text() == text


def test_the_model_differs_exactly_at_the_declared_rule() -> None:
    """What changes is what the author declared, and nothing else."""
    plain = compile_text(PAIR, cache_key="t9-plain3").parse("ab=cd").dump()
    lexical = compile_text(marked(PAIR, "word"), cache_key="t9-lexical3")
    assert lexical.parse("ab=cd").dump() != plain


def test_an_explicit_argument_overrides_the_directive() -> None:
    """Precedence identical to non_semantic: the argument wins."""
    source = marked(PAIR, "word")
    ast = canonical_grammar(source, GBNF_FLAVOUR, lexical_rules=frozenset())
    assert refs_of(ast, "word") == {"letter"}


def test_the_corpus_grammar_takes_the_directive() -> None:
    """json.gbnf marked: string keeps its text, and the document round-trips."""
    source = (GROUND_TRUTH / "json.gbnf").read_text(encoding="utf-8")
    lexical = compile_text(marked(source, "string number"), cache_key="t9-json")
    plain = compile_from_path(GROUND_TRUTH / "json.gbnf")
    text = '{"a": [1, 2], "b": "x"}'
    assert lexical.parse(text).to_text() == text == plain.parse(text).to_text()
    kinds = {b.rule_name: b.kind for b in lexical.moments.binding}
    assert kinds["string"] == "value_str"
    assert kinds["member"] == "sequence"
