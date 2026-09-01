"""Census the two authored surfaces' completions against the product ABI.

The merged step-3 pass requires `notation/parse.py` and `module/selfgrammar.py`
to author `RuleProduct`s in the final vocabulary. Whether that is one new ABI
concept or eight depends on a number nobody has counted: how many of their
completions the existing operation vocabulary can already express.

This counts it. Every authored body is classified by what its constructor IS —
a pass-through, a registry symbol on the no-`eval` channel, an alternation, or
a surface-specific Python transform — and mapped to the operation that would
carry it. What comes out is the exact size of the remaining gap, per surface
and per distinct transform, rather than an impression of it.

One measured fact frames the whole census: NEITHER surface grants a single
`FastCtor`, so today's bake writes empty `fields`/`plan`/`fast`/`defaults` for
every one of their clones and reads only their capture layout. Their products
need captures; the completions are the entire open question.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from lexic.compile.foldkit import FOLD_SYMBOLS, IrNamed, absent_tail, passthrough
from lexic.compile.module.selfgrammar import MODULE_FOLD
from lexic.compile.notation.parse import NOTATION_FOLD
from lexic.ir import IrLambda, IrNone

EXPRESSIBLE = {
    "alternation": "the rule kind — no completion operation at all",
    "passthrough": "ArgExpr(0) — one channel slot, unchanged",
    "int": "DecodeOp(text, DecodeCode.INTEGER) — an engine-owned decoder",
    "first_rest": "no operation today — head-plus-tail list construction",
}
"""What the shared vocabulary maps onto, and where it stops. `first_rest` is
listed to be counted, not because it is covered."""


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s4 authored census: {claim}")


def _constructor(body: Any) -> tuple[str, str]:
    """One body's constructor as ``(category, name)``.

    Four categories, and the split is the finding: an alternation needs no
    operation, a pass-through and a registry symbol are already expressible or
    nearly so, and a surface-specific Python transform is the gap.
    """
    ctor = body.ctor
    if ctor is IrNone:
        return "alternation", "-"
    if isinstance(ctor, IrNamed):
        return "symbol", str(ctor.key)
    if isinstance(ctor, IrLambda):
        target = ctor.eval
        name = getattr(target, "__name__", type(target).__name__)
        if target is passthrough:
            return "passthrough", name
        if target is absent_tail:
            return "shared-idiom", name
        if name == "<lambda>":
            return "surface-python", f"<lambda {getattr(target, '__qualname__', '')}>"
        return "surface-python", name
    return "ir-body", type(ctor).__name__


def _census(label: str, fold: Any) -> tuple[Counter, dict[str, int]]:
    """Classify every authored body of one surface."""
    categories: Counter = Counter()
    transforms: dict[str, int] = {}
    licensed = sum(1 for rule in fold.baked.values() if rule.fast is not None)
    captures = sum(len(rule.fields) for rule in fold.baked.values())
    _check(
        f"{label}: {licensed} rules are licensed — the bake would need their "
        f"constructors after all",
        licensed == 0,
    )
    for _ref, body in fold.bodies.items():
        category, name = _constructor(body)
        categories[category] += 1
        if category in ("surface-python", "symbol", "shared-idiom"):
            transforms[name] = transforms.get(name, 0) + 1
    print(
        f"{label}\trules={sum(categories.values())}\tlicensed={licensed}\t"
        f"captures={captures}"
    )
    for category, count in sorted(categories.items()):
        print(f"  {category:<16}\t{count}")
    return categories, transforms


def the_authored_surfaces_need_only_captures_from_a_product() -> None:
    """Neither surface grants a licence, so the bake reads no constructor."""
    notation, notation_transforms = _census("notation", NOTATION_FOLD)
    module, module_transforms = _census("selfgrammar", MODULE_FOLD)

    distinct = sorted(set(notation_transforms) | set(module_transforms))
    covered = [name for name in distinct if name in EXPRESSIBLE]
    uncovered = [name for name in distinct if name not in EXPRESSIBLE]
    print(
        f"\ntransforms\tdistinct={len(distinct)}\texpressible-today={len(covered)}"
        f"\tgap={len(uncovered)}"
    )
    for name in uncovered:
        seen = notation_transforms.get(name, 0) + module_transforms.get(name, 0)
        print(f"  gap  {name:<28}\t{seen} rule(s)")
    for name in covered:
        print(f"  ok   {name:<28}\t{EXPRESSIBLE[name]}")

    total = sum(notation.values()) + sum(module.values())
    passthroughs = notation["passthrough"] + module["passthrough"]
    alternations = notation["alternation"] + module["alternation"]
    print(
        f"\nsummary\tbodies={total}\tneeding-no-operation={alternations}"
        f"\tneeding-ArgExpr={passthroughs}"
        f"\tneeding-a-transform={total - alternations - passthroughs}"
    )
    _check(
        "every authored body is already expressible — there is no gap to rule on",
        bool(uncovered),
    )


def the_symbol_channel_is_the_registry_the_effort_must_preserve() -> None:
    """`FOLD_SYMBOLS` is the no-`eval` channel §4 requires kept intact."""
    print(f"\nsymbols\tFOLD_SYMBOLS names {sorted(FOLD_SYMBOLS)}")
    _check(
        "the registry is empty — the no-eval channel has nothing to preserve",
        bool(FOLD_SYMBOLS),
    )


def main() -> None:
    """Run the census; any broken claim raises."""
    the_authored_surfaces_need_only_captures_from_a_product()
    the_symbol_channel_is_the_registry_the_effort_must_preserve()
    print("\ns4 authored census\tPASS\tthe gap is counted, not estimated")


if __name__ == "__main__":
    main()
