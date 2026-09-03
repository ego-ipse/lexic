"""The program the verifier passed IS the program that runs.

A review found the completion-range bullet answered by an artefact nothing
executed: the binding lowered and verified a `ProductProgram`, then built its
executor from the AUTHORED rules beside it. The verifier bounded ranges no
execution path indexed, and `RuleProduct.completion` sat next to
`ProductProgram.completions` as exactly the parallel storage the bullet
forbids.

This witness asserts the closure, in three parts:

* **One representation, dynamically.** Every rule the executor completes
  through, every clone the predictive bake fills, and every stitch layout read
  resolves through ONE `RuleRoutine`, and that routine's every field is the
  verified program's own — capture modes, capture slots, arm width, completion
  range index, and the construction its range's instruction names. Compared
  field by field against the program, per rule, over the whole ground-truth
  corpus and both authored surfaces.
* **One representation, statically.** No module under `src/lexic/parsing`
  outside the ABI definition, the lowering input and the binding's own
  constructor parameter so much as names the authored record; `construction_of`
  does not exist; and the binding holds no slot that could carry one.
* **A replica copies what was verified.** A worker's binding is the SAME
  program object with its own routine container — nothing is lowered or
  verified a second time.

Every dynamic claim carries a seeded control: a routine whose completion index
is moved by one must be caught, or the comparison is not watching anything.

Uncommitted evidence, not a test. Luna owns the committed suite.

Run: `uv run python zzz_current_work/260826-target-shaped-parse/proto/s4_verified_completion.py`
"""

from __future__ import annotations

import ast
from pathlib import Path

from lexic.compile import compile_from_path
from lexic.compile.module.selfgrammar import MODULE_BINDING, MODULE_GRAMMAR
from lexic.compile.notation.parse import NOTATION_BINDING, NOTATION_GRAMMAR
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst
from lexic.parsing import ModelExecutable
from lexic.parsing.product import (
    OpCode,
    ProductProgram,
    RangeKind,
    RuleRoutine,
    rule_routines,
)
from lexic.parsing.products import pda_tables

ROOT = Path(__file__).resolve().parents[3]
GROUND_TRUTH = ROOT / "resources" / "ground_truth"
PARSING = ROOT / "src" / "lexic" / "parsing"

AUTHORED_HOMES = frozenset(
    {
        "product/abi/records.py",  # where the authored record is DEFINED
        "product/lower.py",  # where it is CONSUMED, once
        "product/__init__.py",  # the package's one import surface
        "binding.py",  # the constructor parameter it arrives on
    }
)
"""The only files under ``parsing/`` allowed to name the authored record.

Everything else completes, bakes or stitches through a
:class:`~lexic.parsing.product.RuleRoutine`, so naming ``RuleProduct`` outside
these four would be a second representation returning by the back door."""


class Defect(AssertionError):
    """A claim this witness makes that the tree does not support."""


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise Defect(f"s4 verified completion: {claim}")


# ── what the program itself says about one rule ───────────────────────


def _range_instruction(
    program: ProductProgram, at: int
) -> tuple[bool, int, tuple[int, ...]]:
    """``(is an expression range, opcode, operand row)`` for one completion range.

    Read out of the physical tables the verifier bounded, independently of
    :func:`~lexic.parsing.product.rule_routines`, so the two readings can be
    compared rather than one asserted against itself. The kind travels with the
    opcode because the two vocabularies are separate tables that share integers:
    ``ExprCode.SYMBOL`` and ``OpCode.RECORD`` are both 10, and which one an
    instruction is depends on the table its range indexes.
    """
    found = program.completions[at]
    if found.kind == int(RangeKind.EXPRESSION):
        opcode = program.expression_opcodes[found.start]
        rows = program.expression_operand_rows[opcode]
        return True, opcode, rows[program.expression_operands[found.start]]
    opcode = program.fused_opcodes[found.start]
    rows = program.fused_operand_rows[opcode]
    return False, opcode, rows[program.fused_operands[found.start]]


def _check_routine(where: str, program: ProductProgram, code: int, routine) -> None:
    """One rule's routine, field by field, against the program's own record."""
    flat = program.rules[code]
    _check(
        f"{where}: routine names range {routine.completion}, the program "
        f"{flat.completion}",
        routine.completion == flat.completion,
    )
    _check(
        f"{where}: routine captures {routine.modes} under the program's "
        f"{flat.capture_modes}",
        routine.modes == flat.capture_modes,
    )
    _check(
        f"{where}: routine slots {routine.slots} against {flat.capture_slots}",
        routine.slots == flat.capture_slots,
    )
    _check(
        f"{where}: routine arm width {routine.n_items} against {flat.n_items}",
        routine.n_items == flat.n_items,
    )
    expression, opcode, row = _range_instruction(program, flat.completion)
    _check_construction(where, program, routine, (expression, opcode), row)


def _check_construction(
    where: str,
    program: ProductProgram,
    routine,
    instruction: tuple[bool, int],
    row: tuple[int, ...],
) -> None:
    """What the routine builds with IS the operand lane its instruction names."""
    expression, opcode = instruction
    if not expression and opcode == int(OpCode.PASS):
        _check(
            f"{where}: a pass instruction sourcing {row[0]} became source "
            f"{routine.source}",
            routine.source == row[0] and routine.construction is None,
        )
        return
    _check(
        f"{where}: a non-pass instruction kept source {routine.source}",
        routine.source == -1,
    )
    if not expression and opcode == int(OpCode.RECORD):
        declared = program.operands.constructors[row[0]]
        _check(
            f"{where}: builds through something other than constructor lane {row[0]}",
            routine.construction is not None
            and routine.construction.call is declared.cls
            and routine.construction.names == declared.names
            and routine.construction.matched == declared.matched_field,
        )
        return
    if routine.construction is None:
        return
    bound = program.operands.symbols[row[0]]
    _check(
        f"{where}: builds through something other than symbol lane {row[0]}",
        routine.construction.call is bound.apply
        and routine.construction.names == bound.names
        and routine.construction.matched == bound.matched,
    )


# ── the sweep ─────────────────────────────────────────────────────────


def _same_routine(left: RuleRoutine, right: RuleRoutine) -> bool:
    """Whether two readings of one rule agree.

    The resolved construction is a view rather than a record, so it is compared
    by the four things a completion asks it — what to call, which keyword each
    capture fills, which may be absent, and which field the rule's own extent
    fills — instead of by object identity.
    """
    if left[:5] != right[:5]:
        return False
    if left.construction is None or right.construction is None:
        return left.construction is right.construction
    return (
        left.construction.call is right.construction.call
        and left.construction.names == right.construction.names
        and left.construction.optional == right.construction.optional
        and left.construction.matched == right.construction.matched
    )


def _binding_rows(label: str, binding: ModelExecutable) -> int:
    """Every rule of one binding, and the executor's own container with it."""
    fresh = rule_routines(binding.program)
    _check(
        f"{label}: the executor completes through a different container",
        binding.executor.routines is binding.routines,
    )
    for name, code in binding.codes.items():
        routine = binding.routines[name]
        _check_routine(f"{label}/{name}", binding.program, code, routine)
        _check(
            f"{label}/{name}: re-reading the program gives a different routine",
            _same_routine(routine, fresh[code]),
        )
    return len(binding.codes)


def _clone_rows(label: str, tables, binding: ModelExecutable) -> int:
    """Every predictive clone bakes from the binding's own routine object."""
    checked = 0
    for spec in tables.clones.values():
        if spec.routine is None:
            continue
        _check(
            f"{label}/clone {spec.name}: baked from a routine the binding does "
            "not hold",
            spec.routine is binding.routines.get(spec.name),
        )
        checked += 1
    return checked


def _grammars() -> list[Path]:
    """The ground-truth corpus, in a fixed order."""
    found = sorted(
        path
        for suffix in ("*.gbnf", "*.abnf", "*.ebnf")
        for path in GROUND_TRUTH.glob(suffix)
    )
    if len(found) < 8:
        raise Defect(f"s4 verified completion: only {len(found)} fixtures")
    return found


def one_representation_dynamically() -> tuple[int, int, int]:
    """Every rule and every clone, over the corpus and both authored surfaces."""
    rules = 0
    clones = 0
    grammars = 0
    for path in _grammars():
        compiled = compile_from_path(path)
        rules += _binding_rows(path.name, compiled.product)
        grammars += 1
        try:
            tables = compiled.pda_tables()
        except UnsupportedConstructError:
            continue  # a token-terminal grammar compiles no predictive program
        clones += _clone_rows(path.name, tables, compiled.product)
    for label, grammar, binding in _surfaces():
        rules += _binding_rows(label, binding)
        clones += _clone_rows(label, pda_tables(grammar, binding), binding)
        grammars += 1
    print(
        f"one-representation\t{grammars} bindings\trules={rules}\t"
        f"clones={clones}\tevery field read off the verified program"
    )
    return grammars, rules, clones


def _surfaces() -> list[tuple[str, IrAst, ModelExecutable]]:
    """The two authored compile-time surfaces, which complete through symbols."""
    return [
        ("notation", NOTATION_GRAMMAR, NOTATION_BINDING),
        ("selfgrammar", MODULE_GRAMMAR, MODULE_BINDING),
    ]


# ── the static half ───────────────────────────────────────────────────


def _names_used(source: str) -> set[str]:
    """Every identifier one module mentions, from its parsed syntax tree.

    Parsed rather than grepped: a name inside a docstring or a comment is not
    a use, and this claim is about what the code reaches for.
    """
    tree = ast.parse(source)
    found = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    found |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    found |= {
        alias.name.rsplit(".", 1)[-1] or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    return found


def one_representation_statically() -> int:
    """No engine module names the authored record, and nothing resolves one."""
    modules = sorted(PARSING.rglob("*.py"))
    _check(f"only {len(modules)} modules under parsing/", len(modules) > 40)
    offenders = []
    for module in modules:
        where = module.relative_to(PARSING).as_posix()
        names = _names_used(module.read_text())
        if "construction_of" in names:
            offenders.append(f"{where} resolves a construction from an authored record")
        if "RuleProduct" in names and where not in AUTHORED_HOMES:
            offenders.append(f"{where} names the authored RuleProduct")
    _check(f"the authored record survives on an engine path: {offenders}", not offenders)
    _check(
        f"the binding holds {ModelExecutable.__slots__}, which is more than the "
        "verified program and what it derives",
        set(ModelExecutable.__slots__) == {"program", "codes", "routines", "executor"},
    )
    print(
        f"static\t{len(modules)} parsing modules\tRuleProduct confined to "
        f"{len(AUTHORED_HOMES)} files\tconstruction_of gone"
    )
    return len(modules)


# ── the replica ───────────────────────────────────────────────────────


def a_replica_copies_what_was_verified() -> None:
    """A worker's binding shares the verified program and owns its container."""
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    binding = compiled.product
    replica = binding.replica()
    _check("a replica re-lowered its program", replica.program is binding.program)
    _check("a replica re-derived its codes", replica.codes is binding.codes)
    _check(
        "a replica shares the container every completion reads",
        replica.routines is not binding.routines,
    )
    _check("a replica's routines differ by value", replica.routines == binding.routines)
    _check(
        "a replica shares its executor",
        replica.executor is not binding.executor,
    )
    _check(
        "a replica's executor completes through another binding's container",
        replica.executor.routines is replica.routines,
    )
    print(
        f"replica\tsame verified program, own routine container of "
        f"{len(replica.routines)} rules, nothing re-lowered"
    )


# ── the controls ──────────────────────────────────────────────────────


def the_checks_are_live() -> None:
    """Three seeded defects, each caught by the comparison aimed at it."""
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    binding = compiled.product
    name, code = next(iter(binding.codes.items()))
    real = binding.routines[name]
    _seeded("range moved", binding, code, real._replace(completion=real.completion + 1))
    _seeded("slots permuted", binding, code, real._replace(slots=real.slots[::-1] + (9,)))
    _seeded("arm width invented", binding, code, real._replace(n_items=real.n_items + 1))
    _seeded_static("an engine module that names the authored record")
    print("control\tthree seeded routines and one seeded module, four refusals")


def _seeded(
    label: str, binding: ModelExecutable, code: int, routine: RuleRoutine
) -> None:
    """Compare a mutated routine against the real program, insist it refuses."""
    try:
        _check_routine(f"seeded/{label}", binding.program, code, routine)
    except Defect:
        return
    raise Defect(f"s4 verified completion: the seeded defect {label} went uncaught")


SEEDED_MODULE = """
from lexic.parsing.product import RuleProduct, construction_of


def complete(product: RuleProduct, tables) -> None:
    construction_of(product, tables)
"""
"""An engine module written the way the reviewer's finding described.

The static claim is only worth its exit code if the reader can see this, so it
is put through the same reader rather than asserted about."""


def _seeded_static(described: str) -> None:
    """A module outside the authored homes naming the record must be seen."""
    names = _names_used(SEEDED_MODULE)
    _check(
        f"the static reader does not see the authored record ({described})",
        "RuleProduct" in names and "construction_of" in names,
    )
    _check(
        f"the reader sees a record in every module ({described})",
        "RuleProduct" not in _names_used("x = 1\n"),
    )


def main() -> None:
    """Run every claim; any disagreement raises."""
    print("s4 verified completion — the executed program is the verified one\n")
    one_representation_dynamically()
    one_representation_statically()
    a_replica_copies_what_was_verified()
    the_checks_are_live()
    print("\ns4 verified completion\tPASS\tone representation, and it is the verified one")


if __name__ == "__main__":
    main()
