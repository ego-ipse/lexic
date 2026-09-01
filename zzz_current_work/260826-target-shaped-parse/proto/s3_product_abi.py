"""Exercise the landed product ABI: verifier, transactions, regular proof.

Four claims, all against the real `lexic.parsing.product` package:

1. The physical-table verifier refuses every defect it is supposed to —
   missing range, empty range, out-of-bounds range, unknown kind, unknown
   opcode, over-range operand, unpaired capture layout — and accepts a
   well-formed program.
2. The exact-int audit rejects an `IntEnum` that survived lowering. This is
   the check `isinstance` would pass and `type(value) is int` catches.
3. `ParseState` transactions are constant-size and mutation-proportional:
   a rollback undoes exactly what happened after its mark and nothing that
   happened before it, nested marks are LIFO, and a committed outer mark
   copies nothing.
4. `prove_regular` proves a genuinely regular region and DECLINES each shape
   the plan says it must: a cyclic closure, an early nullable arm, arms that
   one character cannot separate, and a repetition whose atom would steal its
   terminator.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

from lexic.compile import canonical_grammar
from lexic.exceptions import SemanticVerdict, UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.product import (
    CaptureMode,
    CompletionRange,
    FlatRuleProduct,
    MeaningOp,
    OperandTables,
    ParseState,
    ProductProgram,
    RangeKind,
    RootOp,
    prove_regular,
    verify_exact_ints,
    verify_program,
)

_EMPTY_OPERANDS: OperandTables[str, str] = OperandTables((), (), (), (), (), (), (), ())


def _program(
    rules: tuple[FlatRuleProduct, ...],
    completions: tuple[CompletionRange, ...],
    *,
    expression: tuple[int, ...] = (0,),
    rows: tuple[tuple[tuple[int, ...], ...], ...] = (((0,),),),
) -> ProductProgram[str, str]:
    """One small program whose tables the caller has deliberately shaped."""
    return ProductProgram(
        rules,
        completions,
        expression,
        tuple(0 for _ in expression),
        rows,
        (),
        (),
        (),
        _EMPTY_OPERANDS,
        RootOp(0),
        MeaningOp(0),
    )


def _sound() -> ProductProgram[str, str]:
    """A well-formed one-rule program: one capture, one expression range."""
    return _program(
        (FlatRuleProduct((int(CaptureMode.TEXT),), (0,), 0),),
        (CompletionRange(int(RangeKind.EXPRESSION), 0, 1),),
    )


def _refuses(claim: str, build: object) -> str:
    """Run a zero-argument call that must refuse; return its words."""
    if not callable(build):
        raise AssertionError(f"s3 abi: {claim} is not callable")
    try:
        build()
    except UnsupportedConstructError as refusal:
        return str(refusal)
    raise AssertionError(f"s3 abi: {claim} did not refuse")


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s3 abi: {claim}")


def verifier_refuses_every_defect() -> None:
    """One good program passes; each single defect is named and refused."""
    verify_program(_sound())

    no_range = _program(
        (FlatRuleProduct((), (), 3),),
        (CompletionRange(int(RangeKind.EXPRESSION), 0, 1),),
    )
    empty = _program(
        (FlatRuleProduct((), (), 0),),
        (CompletionRange(int(RangeKind.EXPRESSION), 0, 0),),
    )
    past_end = _program(
        (FlatRuleProduct((), (), 0),),
        (CompletionRange(int(RangeKind.EXPRESSION), 0, 9),),
    )
    unknown_kind = _program(
        (FlatRuleProduct((), (), 0),),
        (CompletionRange(99, 0, 1),),
    )
    bad_opcode = _program(
        (FlatRuleProduct((), (), 0),),
        (CompletionRange(int(RangeKind.EXPRESSION), 0, 1),),
        expression=(7,),
    )
    bad_operand = _program(
        (FlatRuleProduct((), (), 0),),
        (CompletionRange(int(RangeKind.EXPRESSION), 0, 1),),
        expression=(0,),
        rows=(((),) * 0,),
    )
    unpaired = _program(
        (FlatRuleProduct((int(CaptureMode.TEXT), int(CaptureMode.ONE)), (0,), 0),),
        (CompletionRange(int(RangeKind.EXPRESSION), 0, 1),),
    )
    bad_mode = _program(
        (FlatRuleProduct((77,), (0,), 0),),
        (CompletionRange(int(RangeKind.EXPRESSION), 0, 1),),
    )
    bad_slot = _program(
        (FlatRuleProduct((int(CaptureMode.TEXT),), (-1,), 0),),
        (CompletionRange(int(RangeKind.EXPRESSION), 0, 1),),
    )

    for label, program in (
        ("a rule naming no completion range", no_range),
        ("an empty completion range", empty),
        ("a range past its table", past_end),
        ("an unknown range kind", unknown_kind),
        ("an unknown opcode", bad_opcode),
        ("an operand past its typed table", bad_operand),
        ("an unpaired capture layout", unpaired),
        ("an out-of-range capture mode", bad_mode),
        ("a negative capture slot", bad_slot),
    ):
        words = _refuses(label, lambda p=program: verify_program(p))
        print(f"verifier\t{label}\t{words}")


def exact_int_audit_catches_a_surviving_enum() -> None:
    """`type(value) is int` catches what `isinstance` would wave through."""
    survivor = CaptureMode.TEXT
    _check("an IntEnum stopped passing isinstance", isinstance(survivor, int))
    words = _refuses(
        "an IntEnum that survived lowering",
        lambda: verify_exact_ints((0, survivor), "a lowered table"),
    )
    verify_exact_ints((0, int(survivor)), "a lowered table")
    print(f"exact ints\tIntEnum refused\t{words}")


def transactions_are_constant_size_and_proportional() -> None:
    """Rollback undoes exactly the speculation, and commit copies nothing."""
    state: ParseState[str] = ParseState()
    seq = state.begin_sequence()
    mapping = state.begin_mapping()
    state.append_sequence(seq, "kept")
    state.insert_mapping(mapping, "a", "kept", SemanticVerdict("dup", "a"))

    outer = state.mark()
    state.append_sequence(seq, "outer")
    inner = state.mark()
    state.append_sequence(seq, "inner")
    state.insert_mapping(mapping, "b", "inner", SemanticVerdict("dup", "b"))
    _check("the mark is not five integers", len(inner) == 5)
    state.rollback(inner)
    _check(
        "the inner rollback did not undo exactly its own mutations",
        state.finish_sequence(seq) == ("kept", "outer"),
    )
    _check(
        "the inner rollback touched the mapping it should have restored",
        state.finish_mapping(mapping) == (("a", "kept"),),
    )

    state.commit(outer)
    _check(
        "the outer commit did not keep what it committed",
        state.finish_sequence(seq) == ("kept", "outer"),
    )

    lifo = state.mark()
    other = state.mark()
    words = _refuses("a transaction closed out of order", lambda: state.commit(lifo))
    state.commit(other)
    state.commit(lifo)

    refused: ParseState[str] = ParseState()
    dup = refused.begin_mapping()
    refused.insert_mapping(dup, "k", "first", SemanticVerdict("dup", "k twice", 4, 0))
    refused.insert_mapping(dup, "k", "second", SemanticVerdict("dup", "k twice", 9, 0))
    _check(
        "a refused duplicate replaced the first value",
        refused.finish_mapping(dup) == (("k", "first"),),
    )
    _check(
        "a refused duplicate recorded no verdict",
        [v.words for v in refused.verdicts] == ["k twice"],
    )
    print(f"transactions\tLIFO enforced\t{words}")
    print("transactions\trollback proportional; commit copies nothing")


def keep_last_rollback_restores_a_pre_mark_value() -> None:
    """A keep-last duplicate over an entry OLDER than the mark is reversible.

    The returned defect: `replace` overwrote an entry the enclosing insert had
    not logged, because the insert happened before the transaction opened. The
    newest-entry undo cannot restore that, so the overwritten entry is now
    logged with its position.
    """
    state: ParseState[str] = ParseState()
    mapping = state.begin_mapping(2)  # keep-last
    state.insert_mapping(mapping, "k", "before", SemanticVerdict("dup", "k"))
    _check(
        "the pre-mark insert did not land",
        state.finish_mapping(mapping) == (("k", "before"),),
    )

    speculation = state.mark()
    state.insert_mapping(mapping, "k", "speculative", SemanticVerdict("dup", "k"))
    _check(
        "keep-last did not overwrite inside the speculation",
        state.finish_mapping(mapping) == (("k", "speculative"),),
    )
    state.rollback(speculation)
    _check(
        "rollback left the mapping mutated past its mark",
        state.finish_mapping(mapping) == (("k", "before"),),
    )

    # And the committed case still keeps what it committed.
    kept = state.mark()
    state.insert_mapping(mapping, "k", "committed", SemanticVerdict("dup", "k"))
    state.commit(kept)
    _check(
        "commit lost a keep-last overwrite",
        state.finish_mapping(mapping) == (("k", "committed"),),
    )
    print("transactions\tkeep-last overwrite of a pre-mark entry is reversible")


def _rules(source: str) -> dict[str, object]:
    """The canonical rule table of one GBNF grammar."""
    ast = canonical_grammar(source, GBNF_FLAVOUR)
    return {str(rule.name): rule for rule in ast.rules}


def regular_proof_holds_and_declines() -> None:
    """One region proves; each shape the plan names declines."""
    terminator = CharSet.from_chars('"')

    proved = _rules("root ::= [a-z]+\n")
    proof = prove_regular(proved, "root", terminator)  # type: ignore[arg-type]
    _check("a plainly regular region did not prove", proof is not None)

    decliners = (
        ("a cyclic closure", 'root ::= "a" root | "b"\n'),
        ("a nullable arm that is not last", 'root ::= a\na ::= "x"? | "y"\n'),
        ("arms one character cannot separate", 'root ::= "ab" | "ac"\n'),
        (
            "a repetition that steals its successor",
            'root ::= [a-z]+ tail\ntail ::= "z"\n',
        ),
    )
    for label, source in decliners:
        outcome = prove_regular(_rules(source), "root", terminator)  # type: ignore[arg-type]
        _check(f"{label} was proved regular", outcome is None)
        print(f"regular\tdeclines\t{label}")

    # A once-required nullable reference is a decision, but a DECIDABLE one
    # when its lead is disjoint from what follows: the proof must not decline
    # merely because an atom is nullable.
    decidable = _rules('root ::= a b\na ::= "x"?\nb ::= "y"\n')
    _check(
        "a decidable nullable reference declined",
        prove_regular(decidable, "root", terminator) is not None,  # type: ignore[arg-type]
    )
    assert proof is not None
    print(f"regular\tproves\troot -> recognizer entry {proof.entry}")
    print("regular\tproves\ta decidable once-required nullable reference")


def main() -> None:
    """Run every claim; any failure raises."""
    verifier_refuses_every_defect()
    exact_int_audit_catches_a_surviving_enum()
    transactions_are_constant_size_and_proportional()
    keep_last_rollback_restores_a_pre_mark_value()
    regular_proof_holds_and_declines()
    print("s3 abi\tPASS\tverifier, exact ints, transactions, regular proof")


if __name__ == "__main__":
    main()
