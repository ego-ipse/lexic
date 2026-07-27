"""Tests for ``lexic.compile.notation.emit`` — the notation's emit half.

``emit_ir`` is the layout twin of ``repr`` and the exact inverse of
``load_ir``: ``load_ir(emit_ir(x)) == x`` (the repr-fixpoint for
identity-eq-leaf payloads), width-compliant at the default width, black-style
trailing commas on broken calls and never on flat ones, eager ``IrLambda``
refusal.
"""

from __future__ import annotations

import re

import pytest

from lexic import ir
from lexic.compile import compile_from_path, compile_text
from lexic.compile.notation.emit import emit_ir, ir_doc
from lexic.compile.notation.parse import load_ir
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf import ABNF_GRAMMAR, ABNF_REDUCTIONS
from lexic.grammars.gbnf import GBNF_GRAMMAR, GBNF_REDUCTIONS
from lexic.ir import (
    IR_DEFAULT,
    IrAction,
    IrAst,
    IrInt,
    IrItem,
    IrLambda,
    IrLiteral,
    IrMap,
    IrNone,
    IrQuantifier,
    IrRuleRef,
    IrSequence,
    IrStr,
    IrTuple,
    render,
)
from lexic.parsing.earley.reduce.policy import (
    DROP,
    KEEP_REDUCED,
    YIELD,
    Drop,
    KeepReduced,
)
from tests.paths import GBNF_GRAMMARS, GROUND_TRUTH


@pytest.mark.parametrize("stem", GBNF_GRAMMARS)
def test_emit_ir_round_trips_every_ground_truth_canonical_grammar(stem: str) -> None:
    """Every ground-truth grammar's canonical AST survives emit → load exactly."""
    compiled = compile_from_path(GROUND_TRUTH / stem)
    loaded = load_ir(emit_ir(compiled.grammar))
    assert isinstance(loaded, IrAst)
    assert loaded == compiled.grammar
    assert loaded.non_semantic == compiled.grammar.non_semantic


@pytest.mark.parametrize("grammar", [GBNF_GRAMMAR, ABNF_GRAMMAR])
def test_emit_ir_round_trips_the_flavour_self_grammars(grammar: IrAst) -> None:
    """Each flavour's own self-grammar survives emit → load exactly."""
    loaded = load_ir(emit_ir(grammar))
    assert isinstance(loaded, IrAst)
    assert loaded == grammar
    assert loaded.non_semantic == grammar.non_semantic


@pytest.mark.parametrize("name", ["GBNF_REDUCTIONS", "ABNF_REDUCTIONS"])
def test_emit_ir_repr_fixpoint_for_the_reduction_maps(name: str) -> None:
    """The reduction maps carry identity-eq leaves (structural ``==`` is not
    the right bar there — see the payload suite's own docstring); the repr
    fixpoint is the documented contract instead."""
    obj = {"GBNF_REDUCTIONS": GBNF_REDUCTIONS, "ABNF_REDUCTIONS": ABNF_REDUCTIONS}[name]
    assert repr(load_ir(emit_ir(obj))) == repr(obj)


# ── emit_ir width compliance + determinism ──────────────────────────────


def test_emit_ir_is_deterministic() -> None:
    """The same value emits to the same text on repeated calls."""
    assert emit_ir(GBNF_GRAMMAR) == emit_ir(GBNF_GRAMMAR)


@pytest.mark.parametrize("stem", GBNF_GRAMMARS)
def test_emit_ir_default_width_has_no_overlong_line(stem: str) -> None:
    """At the default width, every ground-truth grammar's emitted text stays
    within the target width on every line (each breaks cleanly at that
    width — no atomic run forces an overflow for these grammars)."""
    compiled = compile_from_path(GROUND_TRUTH / stem)
    text = emit_ir(compiled.grammar)
    assert all(len(line) <= 88 for line in text.split("\n"))


def test_emit_ir_width_bound_on_a_breakable_shape() -> None:
    """A shape with a break opportunity at every level stays within width —
    each single-char literal item is short enough that a chosen width with
    real break points never forces an overlong line."""
    node = IrSequence(*(IrItem(IrLiteral(c)) for c in "abcdefgh"))
    text = emit_ir(node, width=30)
    assert all(len(line) <= 30 for line in text.split("\n"))
    assert load_ir(text) == node


# ── emit_ir refuses IrLambda-bearing values ─────────────────────────────


def lambda_body(_d: object, n: object, _nc: object) -> object:
    """A stand-in emitter body — never called; only its presence is tested."""
    return n


def test_emit_ir_refuses_a_bare_irlambda() -> None:
    """An ``IrLambda`` has no notation spelling — emit refuses it eagerly."""
    with pytest.raises(UnsupportedConstructError):
        emit_ir(IrLambda(lambda_body))


def test_emit_ir_refuses_an_irlambda_nested_inside_a_record() -> None:
    """The refusal fires however deep the ``IrLambda`` sits in the tree."""
    action = IrAction(IrLiteral, IrLambda(lambda_body))
    with pytest.raises(UnsupportedConstructError):
        emit_ir(action)


# ── scalar / interned / singleton tiers ─────────────────────────────────


def test_emit_ir_irnone_spells_as_the_bare_name() -> None:
    """The absence sentinel spells as its bare class name, not a call."""
    assert emit_ir(IrNone) == "IrNone"


def test_emit_ir_ir_default_spells_as_the_bare_name() -> None:
    """``IR_DEFAULT`` spells as its bare name too."""
    assert emit_ir(IR_DEFAULT) == "IR_DEFAULT"


def test_emit_ir_yield_interning_round_trips_by_identity() -> None:
    """The interned YIELD singleton emits as ``Yield()`` and loads back to
    THE canonical instance, not a fresh repr-equal object (F-INTERN-1)."""
    text = emit_ir(YIELD)
    assert text == "Yield()"
    assert load_ir(text) is YIELD


def test_emit_ir_scalar_leaves_spell_as_type_call() -> None:
    """A value-leaf spells as ``TypeName(payload)``, double-quote-preferring
    (the black/ruff convention — emitted notation is a formatter fixpoint)."""
    assert emit_ir(IrLiteral("a")) == 'IrLiteral("a")'
    assert emit_ir(IrLiteral('say "hi"')) == "IrLiteral('say \"hi\"')"
    assert emit_ir(IrInt(-3)) == "IrInt(-3)"


# ── trailing commas: broken calls carry them, flat calls never ───────────

TRAILING_COMMA = re.compile(r",\s*\)")


@pytest.mark.parametrize("stem", GBNF_GRAMMARS)
def test_emit_ir_broken_calls_carry_trailing_commas_and_round_trip(stem: str) -> None:
    """Narrow-width (forced-break) output uses black-style trailing commas —
    and the notation's arg-tail rules read them back to the same AST."""
    compiled = compile_from_path(GROUND_TRUTH / stem)
    text = emit_ir(compiled.grammar, width=30)
    assert TRAILING_COMMA.search(text)  # broken multi-arg calls end ",\n...)"
    assert load_ir(text) == compiled.grammar


def test_emit_ir_flat_calls_never_carry_a_trailing_comma() -> None:
    """A call that fits flat has NO trailing comma (black semantics)."""
    node = IrSequence(IrItem(IrLiteral("a")), IrItem(IrLiteral("b")))
    text = emit_ir(node, width=200)
    assert "\n" not in text
    assert not TRAILING_COMMA.search(text)


def test_emit_ir_small_broken_shape_round_trips_with_trailing_commas() -> None:
    """The small synthetic shape, forced fully broken, still round-trips."""
    node = IrSequence(*(IrItem(IrLiteral(c)) for c in "abcdefgh"))
    text = emit_ir(node, width=20)
    assert TRAILING_COMMA.search(text)
    assert load_ir(text) == node


# ── what emission SPELLED (the header's source of truth) ─────────────────

_SPELLED = re.compile(r"\bIr[A-Za-z0-9]*\b|\bIR_DEFAULT\b")


def _rendered_symbols(text: str) -> set[str]:
    """The public-surface identifiers actually present in rendered notation.

    Reading the page is exactly what the header must stop doing, so this lives
    in the TEST: it is the independent answer that ``ir_doc``'s report is
    checked against, not a second implementation of it.
    """
    return {n for n in _SPELLED.findall(text) if n in ir.__all__}


@pytest.mark.parametrize("stem", GBNF_GRAMMARS)
def test_ir_doc_reports_the_symbols_it_spelled(stem: str) -> None:
    """The report equals what got rendered — no extras, nothing missing."""
    compiled = compile_from_path(GROUND_TRUTH / stem)
    notation = ir_doc(compiled.grammar)
    assert set(notation.symbols) == _rendered_symbols(render(notation.doc, 88))


def test_ir_doc_does_not_report_an_elided_default() -> None:
    """``root ::= "a" "b"`` holds a unit ``IrQuantifier`` per item that is never
    spelled, so a value-walk over-imports it and emission does not."""
    compiled = compile_text('root ::= "a" "b"\n', cache_key="emit-elision-probe")
    notation = ir_doc(compiled.grammar)
    text = render(notation.doc, 88)
    assert "IrQuantifier" not in text
    assert "IrQuantifier" not in notation.symbols
    assert set(notation.symbols) == _rendered_symbols(text)


def test_ir_doc_reports_a_bare_name_singleton_by_its_value() -> None:
    """``IrNone`` is the importable name; ``IrNoneType`` is not what is spelled."""
    notation = ir_doc(IrItem(IrLiteral("a"), IrQuantifier(0, IrNone)))
    assert "IrNone" in notation.symbols
    assert "IrNoneType" not in notation.symbols


# ── plain tuples: the one composite that is not a call ────────────────────

TUPLE_VALUES = [
    IrTuple(IrStr("x"), ()),
    IrTuple(IrStr("x"), (IrStr("y"),)),
    IrTuple(IrStr("x"), (IrStr("y"), IrStr("z"))),
    IrTuple((IrInt(1), IrInt(2))),
    IrTuple(((IrInt(1),), (IrInt(2), IrInt(3)))),
    IrTuple(IrStr("a"), (IrStr("b"),), IrStr("c")),
    IrTuple((IrStr("only"),)),
]


@pytest.mark.parametrize("width", [200, 20])
@pytest.mark.parametrize("value", TUPLE_VALUES, ids=range(len(TUPLE_VALUES)))
def test_emit_ir_round_trips_a_plain_tuple(value: IrTuple, width: int) -> None:
    """Flat and width-forced-broken, a plain tuple survives the round trip."""
    assert load_ir(emit_ir(value, width=width)) == value


def test_emit_ir_spells_a_one_tuple_comma_flat() -> None:
    """A one-tuple's comma is the VALUE, not a break artefact.

    In a call the trailing comma appears only when the call breaks (the black
    form). In a one-tuple it is what makes the value a tuple at all, so it is
    unconditional — and ``(x)`` would be a different value that the parse half
    refuses.
    """
    text = emit_ir(IrTuple((IrStr("only"),)), width=200)
    assert text == 'IrTuple((IrStr("only"),))'
    assert "\n" not in text


def test_emit_ir_spells_an_empty_tuple() -> None:
    """``()`` renders as itself, with nothing to break."""
    assert emit_ir(IrTuple(IrStr("x"), ()), width=200) == 'IrTuple(IrStr("x"), ())'


def test_emit_ir_two_tuple_has_no_trailing_comma_when_flat() -> None:
    """A flat multi-element tuple carries no trailing comma (black semantics)."""
    text = emit_ir(IrTuple((IrInt(1), IrInt(2))), width=200)
    assert text == "IrTuple((IrInt(1), IrInt(2)))"


def test_emit_ir_broken_tuple_carries_a_trailing_comma() -> None:
    """Forced broken, it takes the trailing comma and still round-trips."""
    value = IrTuple((IrStr("aaaaaaaa"), IrStr("bbbbbbbb"), IrStr("cccccccc")))
    text = emit_ir(value, width=20)
    assert TRAILING_COMMA.search(text)
    assert load_ir(text) == value


def test_ir_doc_reports_no_symbol_for_the_parens() -> None:
    """A plain tuple spells no importable name — the parens are syntax."""
    assert set(ir_doc((IrStr("a"), IrStr("b"))).symbols) == {"IrStr"}


def test_a_reduction_policy_emits_and_reads_back() -> None:
    """A noise map is IR, so it must survive the notation like any other value.

    It could not before: the policy sentinels were ``IrLambda`` closures whose
    repr is lambda SOURCE, which emit refuses eagerly — so the one value a
    manifest would need to carry a reduction was the one it could not spell.
    """
    noise = IrMap(
        IrTuple(IrRuleRef("ws"), DROP),
        IrTuple(IR_DEFAULT, KEEP_REDUCED),
    )
    text = emit_ir(noise, 76)
    back = load_ir(text, symbols={"Drop": Drop, "KeepReduced": KeepReduced})
    assert isinstance(back, IrMap)  # a policy reads back AS a policy
    assert back == noise
    # Identity, not equality: the engine asks `body is DROP`, and a repr-equal
    # twin would pass every comparison the tests make and none the engine makes.
    assert back.resolve(IrRuleRef("ws")) is DROP
