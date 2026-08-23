"""Tests for ``compile/output/transpile.py`` — the retained transpilation product.

The tables here are static module constants: rows keyed by SOURCE RULE
NAMES, targets built by name through ``Make``, no class object anywhere —
which is what lets a transform travel through the notation like a grammar
or a reducer does. ``transpile()`` bakes a table against the two artifacts.
"""

import pytest

from lexic.compile import (
    Flat,
    Is,
    Make,
    Spelled,
    compile_text,
    load_ir,
    transpile,
)
from lexic.compile.notation import emit_ir
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrArg,
    IrLiteral,
    IrMap,
    IrPipe,
    IrRuleRef,
    IrThis,
    IrTuple,
)
from lexic.model import GrammarModel

SOURCE = """root ::= pair+
pair ::= key "=" num nl
key ::= [a-z]+
num ::= [0-9]+
nl ::= "\\n"
"""

TARGET = """doc ::= line+
line ::= name ": " val "\\n"
name ::= [a-z]+
val ::= [0-9]+
"""

RULES = IrMap(
    IrTuple(IrRuleRef("key"), Make("name", IrTuple(Spelled()))),
    IrTuple(IrRuleRef("num"), Make("val", IrTuple(Spelled()))),
    IrTuple(IrRuleRef("pair"), Make("line", IrTuple(IrArg(0), IrArg(1)))),
    IrTuple(IrRuleRef("root"), Make("doc", IrTuple(IrArg(0)))),
)
"""The whole transform — pure data, no class objects, a module constant."""


def _pair() -> tuple:
    """The compiled (source, target) fixture pair."""
    return (
        compile_text(SOURCE, cache_key="transpile-src"),
        compile_text(TARGET, cache_key="transpile-tgt"),
    )


def test_run_transpiles_and_the_product_round_trips() -> None:
    """The whole path: parse under A, transform, emit in B's language."""
    a, b = _pair()
    out = transpile(a, b, RULES).run("x=1\ny=22\n")
    assert out == "x: 1\ny: 22\n"
    assert b.parse(out).to_text() == out


def test_a_transform_table_is_a_value_the_notation_carries() -> None:
    """Emit the table as notation, load it back, run the loaded one.

    No class objects in the table is what buys this: the only symbols a
    reader needs are the transpile vocabulary's own.
    """
    a, b = _pair()
    text = emit_ir(RULES, width=88)
    back = IrMap.ensure(load_ir(text, symbols={"Make": Make, "Spelled": Spelled}))
    assert back == RULES
    assert transpile(a, b, back).run("x=1\n") == "x: 1\n"


def test_make_grows_a_hoisted_chain_from_one_flat_tuple() -> None:
    """The list story, both halves: ``Flat`` reads A's chain, ``Make`` grows B's.

    ``x ::= y (sep y)*`` hoists on both sides; the authored table never
    spells either chain — the bake supplies the inverse of lexic's own
    hoisting.
    """
    a = compile_text('root ::= key ("," key)*\nkey ::= [a-z]+\n', cache_key="grow-src")
    b = compile_text(
        'doc ::= name ("; " name)*\nname ::= [a-z]+\n', cache_key="grow-tgt"
    )
    rules = IrMap(
        IrTuple(IrRuleRef("key"), Make("name", IrTuple(Spelled()))),
        IrTuple(IrRuleRef("root-item"), IrArg(-1)),
        IrTuple(IrRuleRef("root"), Make("doc", Flat())),
    )
    assert transpile(a, b, rules).run("x,y,z") == "x; y; z"
    assert transpile(a, b, rules).run("x") == "x"


def test_rows_and_makes_refuse_unknown_rule_names() -> None:
    """A misspelled name refuses at BAKE time, listing what exists."""
    a, b = _pair()
    with pytest.raises(UnsupportedConstructError, match="names no rule of the source"):
        transpile(a, b, IrMap(IrTuple(IrRuleRef("nope"), IrThis())))
    with pytest.raises(UnsupportedConstructError, match="names no rule of the target"):
        transpile(a, b, IrMap(IrTuple(IrRuleRef("key"), Make("nope"))))


def test_an_unbaked_table_cannot_run() -> None:
    """``Make`` and ``Is`` refuse evaluation outside a bake — loudly."""
    make = Make("line")
    with pytest.raises(UnsupportedConstructError, match="unbaked"):
        make.eval(make, make, ())
    test = Is("line")
    with pytest.raises(UnsupportedConstructError, match="unbaked"):
        test.eval(test, test, ())


def test_apply_gates_completeness_naming_the_foreign_class() -> None:
    """A table with a hole refuses — a source class survived to the product.

    An incomplete transpilation emitted as text may or may not mean
    something; the gate names the class the table forgot instead.
    """
    a, b = _pair()
    holed = IrMap(
        # pair and root pass through as A's own classes — two missing rows
        IrTuple(IrRuleRef("pair"), IrThis()),
        IrTuple(IrRuleRef("root"), IrThis()),
    )
    with pytest.raises(UnsupportedConstructError, match="no.*row|not a class"):
        transpile(a, b, holed).apply(a.parse("x=1\n"))


def test_run_gates_membership_under_the_target() -> None:
    """A product whose spelling is not in B's language refuses at reparse.

    A pattern value_str is deliberately unchecked at construction (the R7
    hole), so the gate that catches it is the run's own reparse.
    """
    a, b = _pair()
    bad = IrMap(
        IrTuple(IrRuleRef("key"), Make("name", IrTuple(IrLiteral("UPPER")))),
        IrTuple(IrRuleRef("num"), Make("val", IrTuple(Spelled()))),
        IrTuple(IrRuleRef("pair"), Make("line", IrTuple(IrArg(0), IrArg(1)))),
        IrTuple(IrRuleRef("root"), Make("doc", IrTuple(IrArg(0)))),
    )
    with pytest.raises(UnsupportedConstructError):
        transpile(a, b, bad).run("x=1\n")


def test_apply_refuses_a_non_model_product() -> None:
    """The product must be a model — B's ``to_text`` is the emitter."""
    a, b = _pair()
    stringy = IrMap(IrTuple(IrRuleRef("root"), IrLiteral("nope")))
    with pytest.raises(UnsupportedConstructError, match="product"):
        transpile(a, b, stringy).apply(a.parse("x=1\n"))


def test_untargeted_noise_never_needs_a_row() -> None:
    """Structural classes (``nl``) pass the walk untouched and unread —
    they are consumed by the bodies above them, never reaching the product."""
    a, b = _pair()
    product = transpile(a, b, RULES).apply(a.parse("x=1\n"))
    assert isinstance(product, GrammarModel)
    assert product.__class__ is b.classes["Doc"]


def test_make_binds_by_slot_order_not_declaration_order() -> None:
    """The channel is in ITEM SLOT order; a class declares defaults-last.

    A target with an optional slot BEFORE a required one (``mid?`` before
    ``tail``) declares its fields reordered — a positional splat would
    scramble them silently, since the checked constructor only tests the
    spine. The bake binds by name through the binds table instead.
    """
    a = compile_text('root ::= key "!" key\nkey ::= [a-z]+\n', cache_key="slot-src")
    b = compile_text(
        'doc ::= name mid? tail\nname ::= [a-z]+\nmid ::= "~"\ntail ::= [a-z]+\n',
        cache_key="slot-tgt",
    )
    rules = IrMap(
        IrTuple(IrRuleRef("key"), Make("name", IrTuple(Spelled()))),
        IrTuple(
            IrRuleRef("root"),
            Make(
                "doc",
                IrTuple(
                    IrArg(0),
                    Make("mid", IrTuple(IrLiteral("~"))),
                    IrPipe(IrArg(1), Make("tail", IrTuple(Spelled()))),
                ),
            ),
        ),
    )
    # mid rides slot 1 as a literal "~"; tail is built from the second key.
    out = transpile(a, b, rules)
    text = out.run("ab!cd")
    assert text == "ab~cd"
