"""Adversarial tests — reserved rule names must not poison models.

Field and class names derive from rule names; without mangling, a rule named
``import`` would produce an invalid Python identifier, and ``to-text`` /
``semantic-dump`` would shadow a ``GrammarModel`` method. Reserved names —
Python keywords, ``GrammarModel``'s public surface, and the reserved
class-name bindings — mangle with a trailing underscore (the ``True_``
class-name precedent).
"""

from __future__ import annotations

import warnings

import pytest

from lexic.compile import compile_text

# Each rule name is referenced as a field of ``r`` and must round-trip with no
# error and no shadowing warning. ``annotated`` PascalCases onto the header's
# ``typing.Annotated`` import, breaking every later annotation resolution.
_RESERVED = ["import", "class", "to-text", "semantic-dump", "model-fields", "annotated"]


@pytest.mark.parametrize("rule", _RESERVED)
def test_reserved_rule_name_round_trips_cleanly(rule: str) -> None:
    """A reserved-name rule compiles, parses, round-trips — warning-free."""
    grammar = f'r ::= {rule} "!"\n{rule} ::= "m"\n'
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        compiled = compile_text(grammar, cache_key=f"adv-rsv-{rule}")
        model = compiled.parse("m!")
    assert model.to_text() == "m!"
    assert model.semantic_dump()  # the method, not a field, and it works


def test_module_namespace_rule_name_compiles() -> None:
    """A rule PascalCasing to a header binding must not shadow it.

    ``grammar-model`` → a class that would be named ``GrammarModel``,
    clobbering the emitted module's own base-class import.
    """
    grammar = 'r ::= grammar-model "!"\ngrammar-model ::= "m"\n'
    compiled = compile_text(grammar, cache_key="adv-rsv-gm")
    assert compiled.parse("m!").to_text() == "m!"
