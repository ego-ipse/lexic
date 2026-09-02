"""The LIVE predictive engine against the Earley + fold oracle, on real documents.

The bake is switched: `_bake_build` derives every clone's build state from its
`RuleProduct`, so the flat program the predictive kernel walks is already
product-built and there is no second program to substitute. What is left to
prove is the thing the switch was for — that the product-built program parses
real documents into the models the grammar means.

The oracle is the OTHER ENGINE. `earley_model` completes a real Earley
derivation through the model fold, which the product bake never touches, so a
mistake in the bake shows up as a disagreement rather than as two copies of the
same mistake. `pda_model` is driven directly rather than through `parse()`,
because `parse()` falls back to Earley on a `PdaFail` — which would let a
predictive build that cannot parse at all look like agreement. A document the
PDA declines is counted and reported, never silently absorbed.

`the_comparison_is_live` then seeds three defects into the live bake — the
gtext absence rule, the value_str extent, and the kept item ends — and insists
each one produces a disagreeing parse. Without those, "the two engines agree"
is a claim about a comparison nobody has shown can fail.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Callable

import lexic.parsing.pda.compiler.program.lower as lowering
from lexic.compile import compile_from_path
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.generate import generate
from lexic.parsing.caches import reset_caches
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.pda.compiler.program.flatten import FlatClone
from lexic.parsing.pda.compiler.program.opcodes import M_CONST, M_GTEXT, M_VALUE
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.products import (
    _model_product,
    earley_model,
    reset_product_cache,
)

ROOT = Path(__file__).resolve().parents[3]
GROUND_TRUTH = ROOT / "resources" / "ground_truth"
SEEDS = (0, 1, 2, 3, 4, 5, 6, 7)
"""Fixed seeds, so a disagreement is replayable rather than anecdotal."""

_BAKE = lowering.bake_product_build
"""The shipped build bake, kept so a control's defect is reversible."""


class Vacuous(Exception):
    """A seeded defect the comparison was supposed to catch, and did not."""


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s4 switch: {claim}")


def _cold() -> None:
    """Drop every memo, so the next parse recompiles under the live bake."""
    reset_product_cache()
    reset_caches()


def _documents(compiled: Any) -> list[str]:
    """Real documents for one grammar, from the repo's own generator."""
    ast = compiled.grammar
    rules = {str(rule.name): rule for rule in ast.rules}
    texts = [generate(str(ast.start), rules, rng=random.Random(seed)) for seed in SEEDS]
    return [text for text in texts if text]


def _pda(compiled: Any, text: str) -> Any:
    """One document through the PREDICTIVE engine only, or ``None`` on a decline."""
    product = _model_product(
        compiled.codegen_grammar, compiled.product, tier_for(len(text))
    )
    try:
        return pda_model(product.pda, text, compiled.executor)
    except PdaFail:
        return None


def _earley(compiled: Any, text: str) -> Any:
    """The same document through the gated engine and the model fold — the oracle."""
    product = _model_product(
        compiled.codegen_grammar, compiled.product, tier_for(len(text))
    )
    return earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )


def _one_grammar(path: Path) -> tuple[int, int]:
    """Both engines over one grammar's documents, model by model.

    :returns: ``(documents compared, documents the PDA declined)``.
    """
    compiled = compile_from_path(path)
    documents = _documents(compiled)
    _check(f"{path.name}: the generator produced no document", bool(documents))
    _cold()
    declined = 0
    for at, text in enumerate(documents):
        got = _pda(compiled, text)
        if got is None:
            declined += 1
            continue
        want = _earley(compiled, text)
        _check(
            f"{path.name}/doc {at}: the predictive engine built {got!r} and the "
            f"gated engine {want!r}",
            got == want,
        )
        _check(
            f"{path.name}/doc {at}: the model does not round-trip to its own document",
            got.to_text() == text,
        )
    return len(documents), declined


def _grammars() -> list[Path]:
    """The ground-truth corpus, in a fixed order."""
    paths = sorted(GROUND_TRUTH.glob("*.gbnf"))
    return (
        paths
        + sorted(GROUND_TRUTH.glob("*.abnf"))
        + sorted(GROUND_TRUTH.glob("*.ebnf"))
    )


def both_engines_build_the_same_model() -> list[Path]:
    """The sweep: every ground-truth grammar, both engines, real documents.

    :returns: The grammars that compared CLEANLY, which is the set a control
        may seed a defect into — a grammar the corpus already cannot drive
        would "catch" every defect by failing the way it already failed.
    """
    compared = 0
    declined = 0
    skipped: list[str] = []
    clean: list[Path] = []
    grammars = _grammars()
    for path in grammars:
        try:
            documents, declines = _one_grammar(path)
        except UnsupportedConstructError as refusal:
            skipped.append(f"{path.name} ({refusal.args[0][:40]}…)")
            continue
        clean.append(path)
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
    return clean


# ── the seeded defects ────────────────────────────────────────────────


def _drop_absence(clone: FlatClone) -> None:
    """Turn every absence-bearing capture into a required one.

    The gtext trap: an optional group that matched nothing then builds the
    EMPTY STRING where the class's default belongs.
    """
    clone.plan = tuple(
        (row[0], row[1], 1, row[3]) if row[0] == M_GTEXT else row for row in clone.plan
    )


def _drop_value(clone: FlatClone) -> None:
    """Fill a value_str rule's own field from its default, not its matched extent.

    Deleting the row instead would empty the plan, and an empty plan sends
    `vstr_model` down its validated path — which builds the RIGHT model and
    hides the defect. Retargeting the row is the defect that stays visible.
    """
    clone.plan = tuple(
        (M_CONST, row[1], row[2], row[3]) if row[0] == M_VALUE else row
        for row in clone.plan
    )


def _drop_ends(clone: FlatClone) -> None:
    """Stop keeping per-item end positions a text capture reads back."""
    clone.needs_ends = False


def _defective(defect: Callable[[FlatClone], None]) -> Callable[..., None]:
    """The shipped bake, with one property of its output broken afterwards."""

    def bake(clone: FlatClone, product: Any, constructors: Any) -> None:
        _BAKE(clone, product, constructors)
        defect(clone)

    return bake


def _disagrees(path: Path) -> bool:
    """Whether one grammar's documents now parse differently, or not at all."""
    try:
        _one_grammar(path)
    except AssertionError, LexicError, IndexError, TypeError, ValueError:
        return True
    return False


def _seeded(name: str, defect: Callable[[FlatClone], None], clean: list[Path]) -> None:
    """Break one property of the live bake and insist some document notices."""
    lowering.bake_product_build = _defective(defect)
    try:
        caught = next((path.name for path in clean if _disagrees(path)), "")
    finally:
        lowering.bake_product_build = _BAKE
        _cold()
    if not caught:
        raise Vacuous(f"s4 switch: the seeded defect {name} changed no parse")
    print(f"control\t{name:<24}\tcaught on {caught}")


def the_comparison_is_live(clean: list[Path]) -> None:
    """Three seeded defects, three disagreements — on grammars that just passed."""
    _seeded("gtext absence dropped", _drop_absence, clean)
    _seeded("value_str extent dropped", _drop_value, clean)
    _seeded("item ends dropped", _drop_ends, clean)
    _check(
        "the patched bake outlived the controls",
        lowering.bake_product_build is _BAKE,
    )


def main() -> None:
    """Run the differential and the controls; any disagreement raises."""
    the_comparison_is_live(both_engines_build_the_same_model())
    print("s4 switch\tPASS\tthe product-built program parses what the grammar means")


if __name__ == "__main__":
    main()
