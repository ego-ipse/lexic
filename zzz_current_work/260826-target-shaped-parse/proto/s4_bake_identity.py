"""Bake a clone's build state BOTH ways and prove the flat outputs identical.

§4 step 2 derives the predictive runtime's build state from the model product
instead of the model fold. The step's opcode account is structural rather than
timed: if the flat clone the product bakes is the flat clone the fold bakes,
then the paid loop executes the same instructions on the same data and no
timing argument is needed to say the step added nothing.

This runs that comparison over every clone of every ground-truth grammar and
insists on exact equality of `fields`, `plan`, `fast`, `defaults` and
`needs_ends`, with two normalizations stated and PROVED rather than waived:

* **`lo`.** The flat `lo` is read at exactly three places, all zero-tests
  inside a text branch. The product-side bake therefore writes `0` when the
  ABI says a capture may be absent and `1` otherwise, instead of restating a
  quantifier nothing can consult. Proved behaviourally: every row's field
  VALUE agrees through each side's own branch, for an empty and a non-empty
  span alike; and the exhaustiveness of the three-site trace is pinned, so a
  fourth reader breaks this witness rather than the parse.
* **The text family.** The fold held `text` and `gtext` apart and then asked
  `lo` which it meant; the ABI has one TEXT capture carrying the absence
  question, so a required `gtext` bind bakes as `M_TEXT`. The two branches
  compute the same value for every non-zero `lo` — which is exactly the case
  in which they differ — and the rows are counted, not glossed.

No consumer is switched here: both bakes run into fresh shells and the live
program is untouched.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

import io
import tokenize
from pathlib import Path
from typing import Any

from lexic.compile import compile_from_path
from lexic.compile.pipeline.synthesis import ModelPlan, model_plan
from lexic.compile.product import LoweringOwned, lower_product
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.compiler.program.flatten import FlatClone
from lexic.parsing.pda.compiler.program.lower import _bake_build
from lexic.parsing.pda.compiler.program.opcodes import M_GTEXT, M_TEXT
from lexic.parsing.pda.compiler.program.product import bake_product_build
from lexic.parsing.product import ExprCode, MeaningOp, OperandTables, RootOp

EMPTY_OPERANDS: OperandTables = OperandTables(
    constants=(),
    constructors=(),
    sequences=(),
    mappings=(),
    meanings=(),
    roots=(),
    routes=(),
    continuations=(),
)
"""The model product builds records and nothing else, so every operand table
but the constructors lowering fills is empty."""

ROOT = Path(__file__).resolve().parents[3]
GROUND_TRUTH = ROOT / "resources" / "ground_truth"
BUILD_SOURCE = ROOT / "src" / "lexic" / "parsing" / "pda" / "runtime" / "build.py"

TEXT_FAMILY = frozenset({M_TEXT, M_GTEXT})
SPANS = ("", "x")
"""An empty and a non-empty capture — the only two cases `lo` can separate."""


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s4 bake identity: {claim}")


# ── the two bakes, into fresh shells ──────────────────────────────────


def _shell() -> FlatClone:
    """An empty clone shell — only the build state is written into it."""
    return FlatClone.__new__(FlatClone)


def _fold_bake(fold: Any) -> FlatClone:
    """The build state today's fold bake produces."""
    clone = _shell()
    _bake_build(clone, fold)
    return clone


def _product_bake(plan: ModelPlan, name: str) -> FlatClone:
    """The build state the product bake produces for the same rule."""
    clone = _shell()
    code = plan.codes.get(name)
    product = None if code is None else plan.rules[code]
    bake_product_build(clone, product, plan.constructors)
    return clone


# ── the comparison, with the two normalizations named ─────────────────


def _same_mode(label: str, fold_mode: int, product_mode: int, fold_lo: int) -> bool:
    """Whether two build modes say the same thing about one capture.

    Equal modes trivially do. The one licensed difference is inside the text
    family: a `gtext` bind that CANNOT be absent (`lo != 0`) is a `text` bind
    wearing another name, and the product bakes it as one.
    """
    if fold_mode == product_mode:
        return True
    pair = {fold_mode, product_mode}
    _check(
        f"{label}: mode {fold_mode} vs {product_mode} is not a text-family pair",
        pair <= TEXT_FAMILY,
    )
    _check(
        f"{label}: the fold's gtext row can be ABSENT (lo=0) and the product "
        f"baked it as plain text",
        fold_lo != 0,
    )
    return True


def _field_value(mode: int, lo: int, span: str, default: object) -> object:
    """One field's value, exactly as `fast_values` computes it.

    Transcribed from the two text branches of
    `pda/runtime/build.py::fast_values`; every other mode ignores `lo`, so a
    row outside the text family cannot be changed by the normalization.
    """
    if mode == M_GTEXT:
        return span if (span or lo) else default
    return span


def _compare_fields(label: str, fold: FlatClone, product: FlatClone) -> tuple[int, int]:
    """`fields` row by row.

    :returns: ``(rows whose lo normalized, rows whose mode normalized)``.
    """
    _check(
        f"{label}: fields {len(fold.fields)} vs {len(product.fields)}",
        len(fold.fields) == len(product.fields),
    )
    los = 0
    modes = 0
    for at, (left, right) in enumerate(zip(fold.fields, product.fields)):
        f_item, f_mode, f_name, f_lo = left
        p_item, p_mode, p_name, p_lo = right
        where = f"{label}.fields[{at}]"
        _check(f"{where}: item {f_item} vs {p_item}", f_item == p_item)
        _check(f"{where}: name {f_name!r} vs {p_name!r}", f_name == p_name)
        _same_mode(where, f_mode, p_mode, f_lo)
        los += int(f_lo != p_lo)
        modes += int(f_mode != p_mode)
    return los, modes


def _compare_plan(label: str, fold: FlatClone, product: FlatClone) -> tuple[int, int]:
    """`plan` entry by entry, each entry's built VALUE asserted equal.

    :returns: ``(entries whose lo normalized, entries whose mode normalized)``.
    """
    _check(
        f"{label}: plan {len(fold.plan)} vs {len(product.plan)}",
        len(fold.plan) == len(product.plan),
    )
    los = 0
    modes = 0
    for at, (left, right) in enumerate(zip(fold.plan, product.plan)):
        f_mode, f_item, f_lo, f_default = left
        p_mode, p_item, p_lo, p_default = right
        where = f"{label}.plan[{at}]"
        _check(f"{where}: item {f_item} vs {p_item}", f_item == p_item)
        _check(
            f"{where}: default {f_default!r} vs {p_default!r}", f_default == p_default
        )
        _same_mode(where, f_mode, p_mode, f_lo)
        _assert_same_value(where, left, right)
        los += int(f_lo != p_lo)
        modes += int(f_mode != p_mode)
    return los, modes


def _assert_same_value(where: str, left: tuple, right: tuple) -> None:
    """The two plan entries build the same field value, empty span included."""
    f_mode, _f_item, f_lo, f_default = left
    p_mode, _p_item, p_lo, p_default = right
    if f_mode not in TEXT_FAMILY:
        return
    for span in SPANS:
        fold_value = _field_value(f_mode, f_lo, span, f_default)
        product_value = _field_value(p_mode, p_lo, span, p_default)
        _check(
            f"{where}: span {span!r} builds {fold_value!r} through the fold "
            f"and {product_value!r} through the product",
            fold_value == product_value,
        )


def _compare(label: str, fold: FlatClone, product: FlatClone) -> dict[str, int]:
    """Every field of one clone's build state, both ways."""
    _check(
        f"{label}: needs_ends {fold.needs_ends} vs {product.needs_ends}",
        fold.needs_ends == product.needs_ends,
    )
    _check(
        f"{label}: fast {fold.fast!r} vs {product.fast!r}", fold.fast == product.fast
    )
    _check(
        f"{label}: defaults {fold.defaults!r} vs {product.defaults!r}",
        fold.defaults == product.defaults,
    )
    field_lo, field_mode = _compare_fields(label, fold, product)
    plan_lo, plan_mode = _compare_plan(label, fold, product)
    return {
        "clones": 1,
        "fields": len(fold.fields),
        "plan": len(fold.plan),
        "lo_normalized": field_lo + plan_lo,
        "mode_normalized": field_mode + plan_mode,
    }


# ── the corpus sweep ──────────────────────────────────────────────────


def _tally(into: dict[str, int], counts: dict[str, int]) -> None:
    """Accumulate one clone's counts."""
    for key, value in counts.items():
        into[key] = into.get(key, 0) + value


def _rule_level(label: str, compiled: Any, totals: dict[str, int]) -> None:
    """Every RULE of one grammar, baked both ways.

    Rule level rather than clone level so a grammar whose terminals name an
    encoding — and which therefore cannot compile predictive tables without a
    vocabulary — is still covered.
    """
    plan = model_plan(
        compiled.codegen_grammar, compiled.moments.binding, compiled.classes
    )
    folds = compiled.fold.baked
    _check(
        f"{label}: the plan covers {len(plan.codes)} rules, the fold {len(folds)}",
        set(plan.codes) == set(folds),
    )
    # `matched_field` is DECLARED, and lowering keeps the derivation — a class
    # field no capture fills and no default covers — as its cross-check. Run
    # the real audit over the real constructors, so the two are shown to agree
    # on the whole corpus rather than on a synthetic record.
    program = lower_product(
        plan.rules,
        EMPTY_OPERANDS,
        owned=LoweringOwned(constructors=plan.constructors),
        root=RootOp(0),
        meaning=MeaningOp(0),
    )
    # The symbol operation exists for the authored compile-time surfaces. The
    # generated-model product completes through inert binding-owned data, and
    # this is what says so about the real corpus rather than by intent: not one
    # symbol op, and not one resolved callable, anywhere in it.
    _check(
        f"{label}: the model product lowered {program.expression_opcodes.count(int(ExprCode.SYMBOL))} "
        f"symbol operations",
        int(ExprCode.SYMBOL) not in program.expression_opcodes,
    )
    _check(
        f"{label}: the model product carries {len(program.operands.symbols)} "
        f"resolved symbol callables",
        not program.operands.symbols,
    )
    totals["audited"] = totals.get("audited", 0) + len(plan.constructors)
    for name, fold in folds.items():
        _tally(
            totals,
            _compare(f"{label}/{name}", _fold_bake(fold), _product_bake(plan, name)),
        )


def _clone_level(label: str, compiled: Any, totals: dict[str, int]) -> bool:
    """Every CLONE of one grammar, baked both ways — contextual copies included.

    :returns: Whether the grammar's predictive tables could be compiled.
    """
    try:
        tables = compiled.pda_tables()
    except UnsupportedConstructError:
        return False
    plan = model_plan(
        compiled.codegen_grammar, compiled.moments.binding, compiled.classes
    )
    for key, spec in tables.clones.items():
        name = spec.name
        _check(
            f"{label}/{key}: clone {name!r} has a fold and no product",
            (spec.fold is None) or (name in plan.codes),
        )
        _tally(
            totals,
            _compare(
                f"{label}/clone {name or '<group>'}",
                _fold_bake(spec.fold),
                _product_bake(plan, name),
            ),
        )
    return True


def every_clone_bakes_the_same_build_state() -> dict[str, int]:
    """The sweep: both bakes, every rule and every clone of the whole corpus."""
    rules: dict[str, int] = {}
    clones: dict[str, int] = {}
    tabled = 0
    grammars = sorted(GROUND_TRUTH.glob("*.gbnf"))
    grammars += sorted(GROUND_TRUTH.glob("*.abnf")) + sorted(
        GROUND_TRUTH.glob("*.ebnf")
    )
    for path in grammars:
        compiled = compile_from_path(path)
        _rule_level(path.name, compiled, rules)
        tabled += int(_clone_level(path.name, compiled, clones))
    print(
        f"rules\t{len(grammars)} grammars\trules={rules['clones']}\t"
        f"fields={rules['fields']}\tplan={rules['plan']}\t"
        f"constructors audited={rules['audited']}"
    )
    print(
        f"clones\t{tabled} grammars\tclones={clones['clones']}\t"
        f"fields={clones['fields']}\tplan={clones['plan']}"
    )
    print(
        f"normalized\tlo={clones['lo_normalized']}\t"
        f"mode={clones['mode_normalized']}\t(of {clones['fields'] + clones['plan']} rows)"
    )
    _check(
        "no row normalized — the lo normalization is untested by this corpus",
        clones["lo_normalized"] > 0,
    )
    return clones


# ── the exhaustiveness pin ────────────────────────────────────────────

EXPECTED_LO_READS = (
    "values.append(span if (span or lo) else default)",
    "if span or lo != 0:",
    "key_parts.append(span if (span or lo != 0) else None)",
)
"""The three predicates that consult a bound field's `lo` at run time. The
normalization is only sound because this list is the whole of them."""

EXPECTED_LO_BINDS = (
    "for mode, item, lo, default in clone.plan:",
    "for item, mode, name, lo in fold.fields:",
)
"""The two places `lo` enters a runtime scope at all."""


def the_lo_readers_are_exactly_three() -> None:
    """Pin every `lo` occurrence in the runtime build, binds included.

    Read off the source with the tokenizer rather than a grep, so a `lo`
    inside a string or a comment cannot pad the count and a fourth genuine
    reader cannot hide behind one. A future reader breaks this line loudly
    instead of silently consuming a value the ABI no longer states.
    """
    source = BUILD_SOURCE.read_text(encoding="utf-8")
    lines = source.splitlines()
    sites = [
        token.start[0]
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.NAME and token.string == "lo"
    ]
    texts = [lines[number - 1].strip() for number in sites]
    binds = [text for text in texts if text.startswith("for ")]
    reads = [text for text in texts if not text.startswith("for ")]
    _check(
        f"build.py mentions `lo` at {len(sites)} places: {texts}",
        len(sites) == len(EXPECTED_LO_BINDS) + len(EXPECTED_LO_READS),
    )
    _check(f"the binds moved: {binds}", tuple(binds) == EXPECTED_LO_BINDS)
    _check(f"the readers moved: {reads}", tuple(reads) == EXPECTED_LO_READS)
    print(
        f"lo trace\t{len(EXPECTED_LO_BINDS)} binds + {len(EXPECTED_LO_READS)} "
        f"readers, all zero-tests in a text branch"
    )


def the_plan_lo_has_one_other_consumer_and_it_discards_it() -> None:
    """`vstr_model` unpacks the plan and throws `lo` away — pin that it still does."""
    flatten = (
        ROOT
        / "src"
        / "lexic"
        / "parsing"
        / "pda"
        / "compiler"
        / "program"
        / "flatten.py"
    )
    source = flatten.read_text(encoding="utf-8")
    _check(
        "vstr_model no longer discards the plan's lo",
        "for mode, _i, _lo, default in plan" in source,
    )
    print("lo trace\tvstr_model unpacks the plan and discards lo")


def main() -> None:
    """Run the sweep and the pins; any disagreement raises."""
    counts = every_clone_bakes_the_same_build_state()
    the_lo_readers_are_exactly_three()
    the_plan_lo_has_one_other_consumer_and_it_discards_it()
    print(
        f"s4 bake identity\tPASS\t{counts['clones']} clones bake one build state "
        f"two ways"
    )


if __name__ == "__main__":
    main()
