"""Nullability is one fact, the grammar's own, and every reader answers it.

``IrAst.nullable()`` is the exact least fixpoint. The PDA analysis, the
optional-nullable lift, the Earley tables and the parallel layer's
``derives_empty`` all read it, where each once computed its own — and one of
those, a walk that answered a cycle with "maybe", said a rule derived ε when
no derivation of it does. The witness is that cycle: ``r ::= "a" | s`` /
``s ::= r | "x"`` ends every derivation on a letter.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.ir import IrAst, IrItem, IrRuleRef
from lexic.parsing import compile_tables, lift_optional_nullables, normalize
from lexic.parsing.parallel.discovery.shapes import derives_empty, rule_table
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis

WITNESS = 'root ::= r? ";" ws\nr ::= "a" | s\ns ::= r | "x"\nws ::= " "*\n'
"""The cycle, referenced optionally, beside one rule that is nullable."""


def _codegen() -> IrAst:
    return compile_text(WITNESS, cache_key="nullability-witness").codegen_grammar


def test_the_grammar_says_only_ws_derives_empty() -> None:
    """The fixpoint never admits the cycle; ``ws`` it admits."""
    assert _codegen().nullable() == frozenset({"ws"})


def test_the_pda_analysis_reads_the_same_set() -> None:
    """The analysis of the lifted grammar holds exactly the grammar's set."""
    lifted = lift_optional_nullables(_codegen())
    assert GrammarAnalysis(lifted).nullable == lifted.nullable() == frozenset({"ws"})


def test_the_lift_keeps_an_optional_reference_to_the_cycle_optional() -> None:
    """``r?`` is lifted to ``r`` only where ``r`` is nullable; it is not."""
    lifted = lift_optional_nullables(_codegen())
    root = next(rule for rule in lifted.rules if rule.name == "root")
    first = root.body[0][0]
    assert first.atom == IrRuleRef("r")
    assert int(first.quantifier.lo) == 0


def test_the_parallel_layer_reads_the_same_set() -> None:
    """``derives_empty`` over the grammar's table: the cycle never vanishes."""
    grammar = _codegen()
    table = rule_table(grammar)
    answers = {
        name: derives_empty(IrItem(IrRuleRef(name)), table) for name in ("r", "s", "ws")
    }
    assert answers == {"r": False, "s": False, "ws": True}


def test_the_earley_tables_read_the_same_set() -> None:
    """A rule completes empty in the tables exactly when the grammar says so."""
    grammar = normalize(lift_optional_nullables(_codegen()))
    tables = compile_tables(grammar)
    completes = {
        str(name)
        for name, done in zip(
            tables.decode.rule_names, tables.codes.nullable_completes, strict=True
        )
        if done
    }
    assert completes == grammar.nullable()
    assert not {"r", "s"} & completes
