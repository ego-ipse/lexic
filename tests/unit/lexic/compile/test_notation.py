"""Tests for compile/notation.py — the IR-constructor notation.

The gate is the round-trip fixpoint ``repr(load_ir(repr(x))) == repr(x)`` over
the whole ``lexic.ir`` node vocabulary (ported from ``demo_05``'s full real
payload suite plus a grammar-AST/string battery), the ``Yield()`` → ``YIELD``
identity pin (F-INTERN-1), the SYMBOLS whitelist drift-pin (the no-exec
boundary), and the ``grammars/json.ir`` conformance twin — plus the emit half
(``emit_ir``), the layout twin of ``repr`` and the exact inverse of
``load_ir``: ``load_ir(emit_ir(x)) == x``.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

import lexic.ir.action as ir_action
import lexic.ir.base as ir_base
import lexic.ir.flavour as ir_flavour
import lexic.ir.mapping as ir_mapping
import lexic.ir.nodes as ir_nodes
import lexic.ir.operators as ir_operators
from lexic.compile import compile_from_path
from lexic.compile.notation import (
    INTERN,
    NOTATION_GRAMMAR,
    SYMBOLS,
    emit_ir,
    load_ir,
    load_ir_from_path,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf import (
    ABNF_ACTIONS,
    ABNF_GRAMMAR,
    ABNF_PREFIX_QUANTIFIER,
    ABNF_REDUCTIONS,
)
from lexic.grammars.gbnf import (
    GBNF_ACTIONS,
    GBNF_GRAMMAR,
    GBNF_QUANTIFIERS,
    GBNF_REDUCTIONS,
)
from lexic.grammars.json import JSON_GRAMMAR
from lexic.ir.action import IrAction
from lexic.ir.base import IrChr, IrInt, IrLambda, IrNone, IrSelf
from lexic.ir.mapping import IR_DEFAULT
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot, IrOp
from lexic.parsing.earley.reduce import YIELD, Yield
from tests.paths import GBNF_GRAMMARS, GROUND_TRUTH

GRAMMARS = Path(__file__).resolve().parents[4] / "src" / "lexic" / "grammars"


def payloads() -> dict[str, object]:
    """The lambda-free flavour payloads — the full real manifest data set."""
    return {
        "GBNF_GRAMMAR": GBNF_GRAMMAR,
        "GBNF_REDUCTIONS": GBNF_REDUCTIONS,
        "GBNF_QUANTIFIERS": GBNF_QUANTIFIERS,
        "GBNF_ACTIONS": GBNF_ACTIONS,
        "ABNF_GRAMMAR": ABNF_GRAMMAR,
        "ABNF_REDUCTIONS": ABNF_REDUCTIONS,
        "ABNF_PREFIX_QUANTIFIER": ABNF_PREFIX_QUANTIFIER,
        "ABNF_ACTIONS": ABNF_ACTIONS,
        "JSON_GRAMMAR": JSON_GRAMMAR,
    }


# ── payload suite (demo_05 ported) ────────────────────────────────────


@pytest.mark.parametrize("name", list(payloads()))
def test_full_payload_canonical_repr_roundtrips(name: str) -> None:
    """Every lambda-free flavour payload canonical-repr round-trips."""
    obj = payloads()[name]
    text = repr(obj)
    assert repr(load_ir(text)) == text


def test_grammar_payloads_reconstruct_equal() -> None:
    """The payload grammars (payload-carrying records) reconstruct ``==``."""
    for authored in (GBNF_GRAMMAR, ABNF_GRAMMAR, JSON_GRAMMAR):
        loaded = load_ir(repr(authored))
        assert isinstance(loaded, IrAst)
        assert loaded == authored
        assert loaded.non_semantic == authored.non_semantic


# ── vocabulary + string battery ───────────────────────────────────────

VOCAB_BATTERY = [
    IrLiteral("a"),
    IrLiteral("it's"),
    IrLiteral('say "hi"'),
    IrLiteral("both ' and \" here"),
    IrLiteral("\n\t\r\\"),
    IrLiteral("\x00\x1b\x7f"),
    IrLiteral("あ𝕏é"),
    IrRuleRef("some-rule"),
    IrChr(0),
    IrChr(0x10FFFF),
    IrInt(-42),
    IrOp("=="),
    IrRange(IrChr("a"), IrChr("z")),
    IrCharClass(IrRange(IrChr("0"), IrChr("9")), IrChr("_")),
    IrQuantifier(1, 1),
    IrQuantifier(0, IrNone),
    IrQuantifier(-1, 3),
    IrItem(IrLiteral("x")),
    IrItem(IrRuleRef("r"), IrQuantifier(0, IrNone)),
    IrNot(IrCharClass(IrChr("q"))),
    IrSequence(IrItem(IrLiteral("a")), IrItem(IrRuleRef("b"))),
    IrAlternation(IrSequence(IrItem(IrLiteral("a"))), IrSequence()),
    IrRule("noise", IrAlternation(IrSequence(IrItem(IrLiteral(" ")))), False),
    IrAst(
        ir_base.IrSeq(
            IrRule("root", IrAlternation(IrSequence(IrItem(IrLiteral("a")))))
        ),
        "root",
    ),
]


@pytest.mark.parametrize("node", VOCAB_BATTERY, ids=lambda n: type(n).__name__)
def test_vocabulary_canonical_repr_roundtrips(node: object) -> None:
    """Each representative node round-trips exactly (canonical spelling)."""
    got = load_ir(repr(node))
    assert got == node and type(got) is type(node)
    assert repr(got) == repr(node)


def test_superset_non_canonical_spellings_converge() -> None:
    """Non-canonical spellings parse and converge to the canonical node.

    Repr elides trailing-default fields; the notation is a superset that
    accepts the explicit spelling and canonicalizes it on re-repr.
    """
    got = load_ir("IrItem(IrRuleRef('x'), IrQuantifier(1, 1))")
    assert got == IrItem(IrRuleRef("x"))
    assert repr(got) == "IrItem(IrRuleRef('x'))"


def test_generous_whitespace_and_comments_converge() -> None:
    """Newlines, indentation and ``#`` line comments are structural noise."""
    text = (
        "# a manifest comment\n"
        "IrItem(\n"
        "    IrLiteral('a'),  # the atom\n"
        "    IrQuantifier( 0 , IrNone )\n"
        ")\n"
    )
    assert load_ir(text) == IrItem(IrLiteral("a"), IrQuantifier(0, IrNone))


# ── the intern contract (F-INTERN-1) ──────────────────────────────────


def test_yield_zero_arg_call_is_the_singleton_by_identity() -> None:
    """``Yield()`` yields THE ``YIELD`` singleton — identity, not repr-equality."""
    assert load_ir("Yield()") is YIELD


def test_intern_table_maps_yield_to_yield() -> None:
    """The intern table is exactly the documented F-INTERN-1 contract."""
    assert INTERN == {Yield: YIELD}


# ── SYMBOLS drift-pin: the no-exec boundary ────────────────────────────

IR_MODULES = (ir_base, ir_nodes, ir_operators, ir_action, ir_mapping, ir_flavour)

# The non-IR-node names the whitelist admits — pinned as a name set (not a
# value mapping) so this drift-pin does not re-declare notation's own extras
# literal; the value identities are asserted separately below. ``Yield`` is
# itself an ``IrSelf`` subclass, so it sits on the IR-node side of the partition
# (added manually, but a legitimate node constructor).
EXTRA_NAMES = frozenset(
    {"IrNone", "IR_DEFAULT", "YIELD", "UnsupportedConstructError", "True", "False"}
)


def is_ir_node(val: object) -> bool:
    """Whether ``val`` is an IrSelf-subclass class object."""
    return inspect.isclass(val) and issubclass(val, IrSelf)


def test_symbols_cover_every_public_ir_node_class() -> None:
    """The whitelist registers every public ``IrSelf``-subclass node.

    This is the open-vocabulary guarantee: a new IR node joins the notation's
    vocabulary automatically, and this pin fails loudly if the filter ever
    stops covering the module surface (the fixpoint would silently regress).
    """
    for mod in IR_MODULES:
        for name, val in vars(mod).items():
            if name.startswith("_"):
                continue
            if is_ir_node(val):
                assert SYMBOLS.get(name) is val, f"{name} missing from SYMBOLS"


def test_symbols_boundary_is_ir_nodes_plus_named_extras() -> None:
    """Nothing reachable but IR node constructors and the fixed extras.

    The no-exec boundary: every whitelisted name is either an ``IrSelf``
    subclass or one of the named extras — no bare function, module, or arbitrary
    callable can be spelled. The extras are pinned by name here and by value
    identity below.
    """
    non_ir_names = {name for name, val in SYMBOLS.items() if not is_ir_node(val)}
    assert non_ir_names == EXTRA_NAMES


def test_symbols_extras_resolve_to_the_canonical_values() -> None:
    """Each extra name binds THE singleton / class / bool it must (by identity)."""
    assert SYMBOLS["IrNone"] is IrNone
    assert SYMBOLS["IR_DEFAULT"] is IR_DEFAULT
    assert SYMBOLS["YIELD"] is YIELD
    assert SYMBOLS["Yield"] is Yield
    assert SYMBOLS["UnsupportedConstructError"] is UnsupportedConstructError
    assert SYMBOLS["True"] is True and SYMBOLS["False"] is False


def test_unknown_symbol_raises_unsupported() -> None:
    """A name outside the whitelist is a loud parser error, never a silent miss."""
    with pytest.raises(UnsupportedConstructError):
        load_ir("NotARealSymbol('x')")


def test_no_exec_no_eval_in_source() -> None:
    """The notation module contains no ``exec``/``eval`` (USER DECISION 4)."""
    src = (
        Path(__file__).resolve().parents[4]
        / "src"
        / "lexic"
        / "compile"
        / "notation.py"
    ).read_text()
    tree = ast.parse(src)
    banned = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"exec", "eval"}
    }
    assert not banned


# ── the notation grammar is well-formed data ──────────────────────────


def test_notation_grammar_is_an_irast() -> None:
    """The authored notation grammar is an ``IrAst`` starting at ``start``."""
    assert isinstance(NOTATION_GRAMMAR, IrAst)
    assert NOTATION_GRAMMAR.start == "start"
    assert "ws" in NOTATION_GRAMMAR.non_semantic
    assert "comment" in NOTATION_GRAMMAR.non_semantic


# ── json.ir conformance twin (exit criterion 2) ────────────────────────


def test_json_ir_data_file_equals_authored_grammar() -> None:
    """``grammars/json.ir`` loads to an ``IrAst`` ``==`` today's JSON_GRAMMAR.

    ``non_semantic`` is compared explicitly (C11 — ``IrRule.__eq__`` excludes
    ``semantic``, so ``IrAst ==`` is blind to the noise flags).
    """
    loaded = load_ir_from_path(GRAMMARS / "json.ir")
    assert isinstance(loaded, IrAst)
    assert loaded == JSON_GRAMMAR
    assert loaded.non_semantic == JSON_GRAMMAR.non_semantic


# ── the emit half: load_ir(emit_ir(x)) == x ─────────────────────────────


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
