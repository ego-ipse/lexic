"""Does the generated-model product lower and verify as it stands?

The completion-range bullet requires every binding to lower once through
`lower_product` and pass `verify_program` cold at bind. Nothing does that
today: the model product is carried in its AUTHORED tier and both engines
read those records directly, so `lower_product` has no source caller outside
its own package re-export and `verify_program` has none at all.

Before designing where the lowering goes, this establishes whether it is even
possible for the generated-model product as authored — over the whole
ground-truth corpus, not one grammar. It reports, per grammar, whether the
authored rules lower, whether the resulting program verifies, and the three
facts the bullet asserts about the result:

* **one completion range per rule**, tagged, non-empty, and in bounds;
* **zero symbol operations** — the generated model completes through inert
  binding-owned construction data and reaches no callable table;
* **not stateful** — the model product allocates no `ParseState`.

Run: `uv run python zzz_current_work/260826-target-shaped-parse/proto/s4_model_lowering.py`
"""

from __future__ import annotations

from pathlib import Path

from lexic.compile import compile_from_path
from lexic.compile.pipeline.synthesis import model_plan
from lexic.exceptions import LexicError
from lexic.model import GrammarModel
from lexic.parsing.product import (
    ExprCode,
    LoweringOwned,
    MeaningOp,
    OperandTables,
    RangeKind,
    RootOp,
    lower_product,
    verify_program,
)

GROUND_TRUTH = Path(__file__).resolve().parents[3] / "resources" / "ground_truth"
"""The corpus every claim below is made over."""


class Defect(AssertionError):
    """A claim this witness makes that the corpus does not support."""


def _finish_root(carry: GrammarModel, _verdicts: tuple[object, ...]) -> GrammarModel:
    """The model product's root finalizer — the start rule's value, as-is."""
    return carry


def _same_meaning(left: GrammarModel, right: GrammarModel) -> bool:
    """The model product's meaning comparator — model value equality."""
    return left == right


def _grammars() -> list[Path]:
    """Every ground-truth fixture, in a stable order."""
    found = sorted(
        path
        for suffix in ("*.gbnf", "*.abnf", "*.ebnf")
        for path in GROUND_TRUTH.glob(suffix)
    )
    if len(found) < 8:
        raise Defect(
            f"s4 model lowering: only {len(found)} fixtures under {GROUND_TRUTH} "
            "— the sweep is not reading the real corpus"
        )
    return found


def _lowered(path: Path) -> tuple[str, int, int, bool, str]:
    """Lower and verify one grammar's model product; never raise for a decline."""
    compiled = compile_from_path(path)
    # The AUTHORED rules, from the plan a binding is built out of: a binding
    # keeps only what the verifier passed, so the authored tier is read where
    # it is written rather than off the artefact.
    plan = model_plan(
        compiled.codegen_grammar, compiled.moments.binding, compiled.classes
    )
    ordered = list(plan.rules)
    # Lowering is the SOLE writer of the constructor, route and symbol lanes:
    # each needs checking or resolving before an engine may index it, so they
    # are handed in authored form and come back lowered.
    operands: OperandTables[GrammarModel, GrammarModel] = OperandTables(
        (), (), (), (), (_same_meaning,), (_finish_root,), (), ()
    )
    owned = LoweringOwned(constructors=plan.constructors)
    try:
        program = lower_product(
            ordered, operands, owned=owned, root=RootOp(0), meaning=MeaningOp(0)
        )
        verify_program(program)
    except LexicError as exc:
        return path.name, len(ordered), 0, False, f"DECLINED: {exc}"
    symbol_ops = sum(
        1 for code in program.expression_opcodes if code == int(ExprCode.SYMBOL)
    )
    if symbol_ops:
        raise Defect(
            f"s4 model lowering: {path.name} lowered {symbol_ops} symbol ops — "
            "the generated model must complete through inert construction data"
        )
    _ranges_are_sound(path.name, program)
    return path.name, len(ordered), len(program.completions), program.stateful, "ok"


def _ranges_are_sound(name: str, program: object) -> None:
    """Every rule names one tagged, non-empty, in-bounds completion range."""
    rules = getattr(program, "rules")
    completions = getattr(program, "completions")
    kinds = {int(kind) for kind in RangeKind}
    for at, rule in enumerate(rules):
        if not 0 <= rule.completion < len(completions):
            raise Defect(
                f"s4 model lowering: {name} rule {at} names completion "
                f"{rule.completion} of {len(completions)}"
            )
        found = completions[rule.completion]
        if found.length <= 0 or found.kind not in kinds:
            raise Defect(
                f"s4 model lowering: {name} rule {at} resolves to {found}, which "
                "is empty or untagged"
            )


def main() -> None:
    """Lower every ground-truth grammar's model product and report."""
    rows = [_lowered(path) for path in _grammars()]
    declined = [row for row in rows if row[4] != "ok"]
    print(f"{'grammar':<22}{'rules':>7}{'ranges':>8}{'stateful':>10}  verdict")
    for name, rules, ranges, stateful, verdict in rows:
        short = verdict if len(verdict) < 60 else verdict[:57] + "..."
        print(f"{name:<22}{rules:>7}{ranges:>8}{str(stateful):>10}  {short}")
    print(f"\nlowered\t{len(rows) - len(declined)} of {len(rows)} grammars")
    if any(row[3] for row in rows if row[4] == "ok"):
        raise Defect(
            "s4 model lowering: a generated-model program reported stateful — it "
            "has no mutable builder and must allocate no ParseState"
        )
    print("stateful\tno generated-model program is stateful")
    print("symbols\tno generated-model program lowered a symbol operation")
    if declined:
        print(f"\nDECLINED {len(declined)} — the gap this bullet must close:")
        for name, _r, _c, _s, verdict in declined:
            print(f"  {name}\t{verdict}")


if __name__ == "__main__":
    main()
