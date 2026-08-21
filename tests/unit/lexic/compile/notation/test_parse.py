"""Tests for compile/notation.py — the IR-constructor notation.

The gate is the round-trip fixpoint ``repr(load_ir(repr(x))) == repr(x)`` over
the whole ``lexic.ir`` node vocabulary (ported from ``demo_05``'s full real
payload suite plus a grammar-AST/string battery), the ``Yield()`` → ``YIELD``
sentinel identity pin, the SYMBOLS whitelist drift-pin (the no-exec
boundary), and the ``grammars/json.ir`` conformance twin.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import lexic.ir.action.access as ir_access
import lexic.ir.action.build as ir_build
import lexic.ir.action.compute as ir_compute
import lexic.ir.action.control as ir_control
import lexic.ir.action.mapping as ir_mapping
import lexic.ir.flavour as ir_flavour
import lexic.ir.grammar.alignment as ir_alignment
import lexic.ir.grammar.nodes as ir_nodes
import lexic.ir.grammar.operators as ir_operators
import lexic.ir.identity as ir_identity
import lexic.ir.spine.records as ir_records
import lexic.ir.spine.scalars as ir_scalars
import lexic.ir.spine.spine as ir_spine
import lexic.ir.text.spans as ir_spans
from lexic.api.pretokens import IrByteLevel
from lexic.compile.notation.parse import (
    NOTATION_GRAMMAR,
    SYMBOLS,
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
from lexic.ir import (
    DROP,
    KEEP_RAW,
    KEEP_REDUCED,
    YIELD,
    IR_DEFAULT,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrInt,
    IrItem,
    IrLiteral,
    IrMap,
    IrNone,
    IrNot,
    IrOp,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSequence,
    IrStr,
    IrTokenizer,
    IrTokenPipeline,
    IrTuple,
    Yield,
)

GRAMMARS = Path(__file__).resolve().parents[5] / "src" / "lexic" / "grammars"


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
        ir_records.IrSeq(
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


# ── engine sentinels are singletons ───────────────────────────────────


def test_yield_zero_arg_call_is_the_singleton_by_identity() -> None:
    """``Yield()`` yields THE ``YIELD`` singleton — identity, not repr-equality."""
    assert load_ir("Yield()") is YIELD


@pytest.mark.parametrize("sentinel", (YIELD, DROP, KEEP_RAW, KEEP_REDUCED))
def test_every_reduce_sentinel_round_trips_by_identity(sentinel: object) -> None:
    """The engine identity-checks these, so a spelled one must BE the engine's.

    Held by construction — each is an ``IrSingleton``, so its zero-arg call is
    the canonical instance — rather than by a table naming which classes to
    intern, which is one missing entry away from a silent wrong answer: a
    repr-equal twin passes every ``==`` and fails every ``is``.
    """
    assert load_ir(repr(sentinel)) is sentinel


# ── SYMBOLS drift-pin: the no-exec boundary ────────────────────────────

IR_MODULES = (
    ir_spine,
    ir_scalars,
    ir_records,
    ir_nodes,
    ir_operators,
    ir_access,
    ir_compute,
    ir_control,
    ir_build,
    ir_mapping,
    ir_flavour,
    ir_spans,
    ir_identity,
    ir_alignment,
)

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


# ── arglist strictness — trailing comma parses, a stray one refuses ────


def test_load_ir_accepts_a_trailing_comma() -> None:
    """A single trailing comma before ``)`` is the gateable arg-tail shape —
    it folds to the shared ``ABSENT`` marker and drops, dropping cleanly."""
    assert load_ir("IrRange(IrChr(0), IrChr(9),)") == IrRange(IrChr(0), IrChr(9))


def test_load_ir_refuses_a_stray_non_trailing_comma() -> None:
    """A bare comma anywhere but last (``,,``) is a stray comma — ``_arglist``
    refuses it at fold time rather than silently dropping an argument."""
    with pytest.raises(UnsupportedConstructError, match="stray"):
        load_ir("IrRange(IrChr(0),, IrChr(9))")


def test_no_exec_no_eval_in_source() -> None:
    """The notation module contains no ``exec``/``eval`` (USER DECISION 4)."""
    pkg = Path(__file__).resolve().parents[5] / "src" / "lexic" / "compile" / "notation"
    src = "\n".join(f.read_text() for f in sorted(pkg.glob("*.py")))
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


# ── saving and loading ANY parsed value, not just a grammar ──────────────


def test_an_encoding_family_value_round_trips() -> None:
    """``lexic.ir.encoding``'s nodes were absent from the vocabulary entirely.

    Saving is ``repr``; loading is this. The notation built its table from a
    fixed list of IR modules and that list omitted ``encoding``, so thirteen
    node types could be written and never read back — lexic could save a
    value it could not load. Nothing tokenizer-specific: the same hole would
    swallow anything added to that module.
    """
    tok = IrTokenizer.from_vocab(
        "demo", IrMap(IrTuple(IrStr("a"), IrChr(0)), IrTuple(IrStr("b"), IrChr(1)))
    )
    assert load_ir(repr(tok)) == tok
    assert IrTokenizer.ensure(load_ir(repr(tok))).tokenize("ab") == [0, 1]


def test_a_value_naming_out_of_spine_nodes_needs_its_vocabulary() -> None:
    """A format's own families live beside its reader, so the spine cannot know them.

    They are supplied per call rather than registered: a boundary any import
    can widen is not a boundary.
    """
    outside = IrTokenizer.from_vocab(
        "demo",
        IrMap(IrTuple(IrStr("a"), IrChr(0))),
        pipeline=IrTokenPipeline(pretokens=IrTuple(IrByteLevel())),
    )
    with pytest.raises(UnsupportedConstructError, match="unknown symbol"):
        load_ir(repr(outside))
    assert load_ir(repr(outside), {"IrByteLevel": IrByteLevel}) == outside


def test_supplied_symbols_must_be_ir_nodes() -> None:
    """The whitelist IS the no-exec boundary, so the extension keeps it.

    Admitting a plain callable would turn a data format back into evaluation.
    """
    with pytest.raises(UnsupportedConstructError, match="no-exec boundary"):
        load_ir("IrStr('x')", {"os_system": __import__("os").system})


def test_the_extra_vocabulary_does_not_outlive_the_call() -> None:
    """Per call, so one load cannot widen the boundary for the next."""
    tok = IrTokenizer.from_vocab(
        "demo",
        IrMap(IrTuple(IrStr("a"), IrChr(0))),
        pipeline=IrTokenPipeline(pretokens=IrTuple(IrByteLevel())),
    )
    assert load_ir(repr(tok), {"IrByteLevel": IrByteLevel}) == tok
    with pytest.raises(UnsupportedConstructError, match="unknown symbol"):
        load_ir(repr(tok))


# ── plain tuples: the notation's one non-call composite ────────────────────


@pytest.mark.parametrize(
    "text,want",
    [
        ("()", ()),
        ("(1,)", (1,)),
        ("(1, 2)", (1, 2)),
        ("(1, 2,)", (1, 2)),
        ("('a', 'b')", ("a", "b")),
        ("(IrStr('a'),)", (IrStr("a"),)),
        ("((1, 2), (3,))", ((1, 2), (3,))),
        ("( 1 , 2 )", (1, 2)),
    ],
)
def test_load_ir_reads_a_plain_tuple(text: str, want: tuple) -> None:
    """A plain tuple is a value: parens, comma-separated, trailing comma ok."""
    assert load_ir(text) == want


def test_load_ir_refuses_a_parenthesised_single_value() -> None:
    """``(1)`` must REFUSE — it is not a one-tuple in Python either.

    Two loaders read a notation artefact: CPython and this parse half. If the
    grammar accepted ``(1)`` as a one-tuple they would return different values
    for one file, and nothing would report it. ``tuplist ::= value tup-tail+``
    makes the refusal structural — there is no derivation without a comma.
    """
    with pytest.raises(UnsupportedConstructError):
        load_ir("(1)")


def test_load_ir_refuses_a_tuple_of_nothing_but_a_comma() -> None:
    """``(,)`` has no first value, so no derivation."""
    with pytest.raises(UnsupportedConstructError):
        load_ir("(,)")


def test_load_ir_refuses_a_stray_comma_inside_a_tuple() -> None:
    """``(1,,2)`` parses leniently and the FOLD refuses it, as in an arg list."""
    with pytest.raises(UnsupportedConstructError, match="stray"):
        load_ir("(1,,2)")


def test_load_ir_reads_a_plain_tuple_inside_a_spine_node() -> None:
    """The shape that motivated the arm: a variadic field holding a raw tuple."""
    node = IrTuple(IrStr("x"), (IrStr("y"), IrStr("z")))
    assert load_ir(repr(node)) == node
