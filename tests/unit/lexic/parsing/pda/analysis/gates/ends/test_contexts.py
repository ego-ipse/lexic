"""Tests for lexic.parsing.pda.analysis.gates.ends.contexts — a loop decided where its
run ends, compiled once per context its rule is cloned for.

The gates are keyed by item identity on the analysis' side, so the pins are on
the compiled artefact: the clone the context needs carries the k-window gate,
the one it does not keeps a plain stop-set, a grammar with no decided loop
keys every clone as before — and a worker's replica, whose tables are a copy,
parses the same model.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.ir import IrAst
from lexic.parsing.pda.compiler.program.flatten import all_clones, clone_arms
from lexic.parsing.pda.compiler.program.opcodes import GATE_KWIN
from lexic.parsing.pda.compiler.specs import CloneKey, KTupleGate, LoopGate, StopGate
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.products import declare_replica, model_product, parse_model
from tests.unit.lexic.parsing.parsing_helpers import clone_specs

WITNESS = 'root ::= entry+\nentry ::= e ";" tail*\ntail ::= "," e\ne ::= [a-z]+\n'
TEXT = "abc;,de,fghij;,k,lm;" * 20


def _e_gates(text: str) -> dict[CloneKey, LoopGate]:
    """Each clone of ``e`` and its one item's loop gate."""
    compiler = clone_specs(compile_text(text))
    return {
        key: spec.arms[0].specs[0].gate
        for key, spec in compiler.clones.items()
        if key.name == "e"
    }


def test_the_tail_clone_reads_the_run_end_and_the_entry_clone_does_not() -> None:
    """Before ``;`` the run is the loop's whole; at a tail's end the next entry
    needs one of it, so that clone's gate reads two characters."""
    gates = _e_gates(WITNESS)
    assert len(gates) == 2
    kinds = sorted(type(gate).__name__ for gate in gates.values())
    assert kinds == ["KTupleGate", "StopGate"]
    for key, gate in gates.items():
        assert key.runs, "both of e's clones carry their context"
        if isinstance(gate, KTupleGate):
            assert max(len(window) for window in gate.windows) == 2
        else:
            assert isinstance(gate, StopGate)


def test_a_grammar_with_no_decided_loop_keys_its_clones_as_before() -> None:
    """An unclosed follower decides nothing: no clone key carries a context."""
    grammar = (
        'root ::= item+\nitem ::= head tail*\ntail ::= "," e\n'
        'e ::= [a-z]+\nhead ::= [a-z]* "x" ";"\n'
    )
    compiler = clone_specs(compile_text(grammar))
    assert all(key.runs == () for key in compiler.clones)


def _has_window_gate(tables: PdaTables) -> bool:
    """Whether any arm of the compiled program reads a k-window loop gate."""
    return any(
        GATE_KWIN in arm.gate_kinds
        for clone in all_clones([tables.program.start])
        for arm in clone_arms(clone)
    )


def test_a_worker_replica_parses_the_same_model_on_its_copied_tables() -> None:
    """A replica's tables are a copy of the original's: the run-end gate
    survives the copy, and the model is the original's."""
    compiled = compile_text(WITNESS, cache_key="run-end-replica")
    grammar, binding = compiled.codegen_grammar, compiled.product
    view = (IrAst(grammar.rules, grammar.start), binding.replica())
    declare_replica(grammar, binding, *view)
    original = parse_model(grammar, TEXT, binding)

    model = parse_model(view[0], TEXT, view[1])

    replica = model_product(*view).pda
    assert replica is not model_product(grammar, binding).pda
    assert _has_window_gate(replica)
    assert model == original
    assert model.to_text() == TEXT
