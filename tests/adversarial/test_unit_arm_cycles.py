"""Adversarial codegen tests — unit-arm cycles must produce loadable classes.

A rule that is a unit arm of itself (``s ::= s | "a"``), or rules that are
unit arms of each other, are valid CFGs; the multiple-inheritance codegen
used to emit ``class S(S):`` / circularly inheriting classes and die with
``NameError`` at module exec. Cycle members all derive the same language, so
the parent graph breaks the cycle (members become siblings) and every
concrete arm carries every cycle member as a base — ``isinstance`` keeps
working for fields typed with any member.
"""

from __future__ import annotations

from lexic.compile import compile_text


def test_self_unit_arm_compiles_and_round_trips() -> None:
    """s ::= s | "a" — the self-arm shape that emitted ``class S(S):``."""
    compiled = compile_text('s ::= s | "a"\n', cache_key="adv-cyc-self")
    model = compiled.parse("a")
    assert model.to_text() == "a"


def test_self_arm_with_left_recursion_round_trips() -> None:
    """s ::= s "b" | s | "a" — self arm mixed with a left-recursive arm."""
    compiled = compile_text('s ::= s "b" | s | "a"\n', cache_key="adv-cyc-mix")
    model = compiled.parse("ab")
    assert model.to_text() == "ab"


def test_mutual_unit_arms_compile_and_round_trip() -> None:
    """a ::= b | "x" / b ::= a | "y" — mutually inheriting alternations."""
    compiled = compile_text(
        'a ::= b | "x"\nb ::= a | "y"\n', cache_key="adv-cyc-mutual"
    )
    for text in ("x", "y"):
        assert compiled.parse(text).to_text() == text


def test_cycle_arm_instances_carry_every_cycle_member() -> None:
    """A concrete arm of either cycle member is an instance of BOTH classes.

    ``a`` and ``b`` derive the same language, so a field typed with either
    alternation class must accept a parse that went through the other.
    """
    compiled = compile_text('a ::= b | "x"\nb ::= a | "y"\n', cache_key="adv-cyc-iso")
    a_cls = compiled.classes["A"]
    b_cls = compiled.classes["B"]
    for text in ("x", "y"):
        model = compiled.parse(text)
        assert isinstance(model, a_cls)
        assert isinstance(model, b_cls)
