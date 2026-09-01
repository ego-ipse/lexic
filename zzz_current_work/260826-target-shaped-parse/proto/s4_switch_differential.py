"""Run the real PDA over a product-baked program and compare the models.

The bake-identity witness compares the two bakes field by field. This one asks
the question that decides the switch: if the whole flat program is built from
the product instead of the fold, does the predictive engine still parse real
documents into the same models?

The substitution happens HERE, not in `src` — the proto rebinds the module
global `flatten_clones` looks up, so the shipped lowering is untouched and no
signature changes. What runs afterwards is the real thing: the real clone
compiler, the real flat program, the real `pda_model` kernel, on documents the
repo's own generator produced for every ground-truth grammar.

`pda_model` is driven directly rather than through `parse()`, because `parse()`
falls back to Earley on a `PdaFail` and Earley completes through the fold —
which would make a broken predictive build look like agreement. A document the
PDA declines is counted and reported, never silently absorbed.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import lexic.parsing.pda.compiler.program.lower as lowering
from lexic.compile import compile_from_path
from lexic.compile.pipeline.synthesis import ModelPlan, model_plan
from lexic.exceptions import UnsupportedConstructError
from lexic.generate import generate
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.caches import reset_caches
from lexic.parsing.pda.compiler.program.product import bake_product_build
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.products import reset_product_cache

ROOT = Path(__file__).resolve().parents[3]
GROUND_TRUTH = ROOT / "resources" / "ground_truth"
SEEDS = (0, 1, 2, 3, 4, 5, 6, 7)
"""Fixed seeds, so a disagreement is replayable rather than anecdotal."""

_BAKE = lowering._bake_build
"""The shipped bake, kept so the substitution is reversible within the run."""

_PLAN: ModelPlan | None = None
"""The grammar whose product the patched bake reads. One at a time: the clone
compiler runs per grammar, so there is nothing to key."""


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s4 switch: {claim}")


def _product_baked(clone: Any, fold: Any) -> None:
    """Bake the clone's lifecycle as shipped, its BUILD STATE from the product.

    The lifecycle half — the fold reference, the leaf licence, the char table
    and the run arm — is not what step 2 replaces, so it stays exactly as the
    shipped bake writes it. Everything the build reads is overwritten from the
    product, so the program that runs afterwards is product-built.
    """
    _BAKE(clone, fold)
    plan = _PLAN
    if plan is None:
        return
    code = plan.codes.get(clone.name)
    product = None if code is None else plan.rules[code]
    bake_product_build(clone, product, plan.constructors)


def _cold() -> None:
    """Drop every memo, so the next parse recompiles under the live bake."""
    reset_product_cache()
    reset_caches()


def _models(compiled: Any, documents: list[str]) -> tuple[list[Any], int]:
    """Parse each document through the PREDICTIVE engine only.

    :returns: ``(models, declines)`` — a declined document contributes
        ``None`` and is counted, so an all-declining grammar cannot pass by
        agreeing about nothing.
    """
    tables = compiled.pda_tables()
    models: list[Any] = []
    declines = 0
    for text in documents:
        try:
            models.append(pda_model(tables, text, compiled.fold))
        except PdaFail:
            models.append(None)
            declines += 1
    return models, declines


def _documents(compiled: Any) -> list[str]:
    """Real documents for one grammar, from the repo's own generator."""
    ast = compiled.grammar
    rules = {str(rule.name): rule for rule in ast.rules}
    texts = [generate(str(ast.start), rules, rng=random.Random(seed)) for seed in SEEDS]
    return [text for text in texts if text]


def _one_grammar(path: Path) -> tuple[int, int]:
    """Both programs, both parses, one comparison.

    :returns: ``(documents compared, documents the PDA declined)``.
    """
    global _PLAN  # the patched bake's one input, set per grammar
    compiled = compile_from_path(path)
    documents = _documents(compiled)
    _check(f"{path.name}: the generator produced no document", bool(documents))

    _cold()
    expected, declined = _models(compiled, documents)

    _PLAN = model_plan(
        compiled.codegen_grammar, compiled.moments.binding, compiled.classes
    )
    _cold()
    lowering._bake_build = _product_baked
    try:
        actual, declined_again = _models(compiled, documents)
    finally:
        lowering._bake_build = _BAKE
        _PLAN = None
        _cold()

    _check(
        f"{path.name}: the fold-built program declined {declined} documents and "
        f"the product-built one {declined_again}",
        declined == declined_again,
    )
    for at, (want, got) in enumerate(zip(expected, actual)):
        _check(
            f"{path.name}/doc {at}: the product-built program parsed "
            f"{got!r}, the fold-built one {want!r}",
            want == got,
        )
        if want is not None:
            _check(
                f"{path.name}/doc {at}: the product-built model does not "
                f"round-trip to its own document",
                got.to_text() == documents[at],
            )
    return len(documents), declined


def every_grammar_parses_the_same_through_a_product_built_program() -> None:
    """The sweep: every ground-truth grammar, both programs, real PDA parses."""
    grammars = sorted(GROUND_TRUTH.glob("*.gbnf"))
    grammars += sorted(GROUND_TRUTH.glob("*.abnf")) + sorted(
        GROUND_TRUTH.glob("*.ebnf")
    )
    compared = 0
    declined = 0
    skipped: list[str] = []
    for path in grammars:
        try:
            documents, declines = _one_grammar(path)
        except UnsupportedConstructError as refusal:
            skipped.append(f"{path.name} ({refusal.args[0][:40]}…)")
            continue
        compared += documents
        declined += declines
        print(f"same\t{path.name:<20}\tdocuments={documents}\tdeclined={declines}")
    _check(
        f"the PDA declined every one of {compared} documents — the comparison "
        f"would be vacuous",
        declined < compared,
    )
    print(
        f"total\t{len(grammars) - len(skipped)} grammars\tdocuments={compared}\t"
        f"pda-declined={declined}\tskipped={skipped or 'none'}"
    )


def the_substitution_is_reversible() -> None:
    """The shipped bake is back in place — a proto must not leak its patch."""
    _check(
        "the patched bake outlived the comparison",
        lowering._bake_build is _BAKE,
    )
    print("restored\tthe shipped bake is the live one again")


def main() -> None:
    """Run the differential; any disagreement raises."""
    every_grammar_parses_the_same_through_a_product_built_program()
    the_substitution_is_reversible()
    print("s4 switch\tPASS\ta product-built program parses to the same models")


if __name__ == "__main__":
    main()
