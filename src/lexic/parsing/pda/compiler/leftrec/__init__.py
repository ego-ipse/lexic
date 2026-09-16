"""The left-recursion fold — parse `A ::= A β | γ` as `(γ)(β)*`, build it back.

The package's one entry, because the three halves are only sound together: the
SHAPE says which rules the fold can take, the REWRITE turns those into loops the
predictive descent can run, and the BUILD folds the iterations back through the
rule's own arms so the model is unchanged. A caller that took the rewrite
without the build would parse the same language into a different model, so
there is one door and it hands back both.
"""

from __future__ import annotations

from typing import Any

from lexic.ir import IrAst
from lexic.parsing.executable import ModelExecutable
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.leftrec.build import fold_build
from lexic.parsing.pda.compiler.leftrec.rewrite import fold_grammar
from lexic.parsing.pda.compiler.leftrec.shape import any_candidate, foldable

__all__ = ["folded_grammar"]


def folded_grammar(
    lifted: IrAst, binding: ModelExecutable
) -> tuple[IrAst, dict[str, Any]]:
    """``lifted`` with its foldable left recursion rewritten, and the folds.

    A rule the predictive descent cannot run is rewritten into one it can —
    `A ::= A β | γ` parsed as `(γ)(β)*` — and each rewritten rule's
    per-iteration build is returned beside it, so the value is the one the
    original arms build.

    **A rule is rewritten only if its VALUE can be folded.** The shape and the
    build are asked in that order and both must answer: a rule whose arms have
    the right shape but whose routine the fold cannot call through is left
    exactly as it was, and islands as before. Rewriting it on the strength of
    the shape alone would parse it faster and build it wrong.

    :param lifted: The lifted codegen grammar the PDA compiles.
    :param binding: The bound model product, for the routines the fold calls.
    :returns: ``(grammar, folds by rule name)``.
    """
    rules = {str(rule.name): rule for rule in lifted.rules}
    # The analysis is built ONLY where a rule could fold. It is a full second
    # pass over every rule, and paying it to be told "nothing here" cost 9-13%
    # of the compile on grammars that fold nothing — which is all but two rules
    # in the roster and the ground truth combined.
    if not any_candidate(rules):
        return lifted, {}
    analysis = GrammarAnalysis(lifted)
    shapes = {}
    builds: dict[str, Any] = {}
    for name, rule in rules.items():
        shape = foldable(name, rule, rules, analysis.item_nullable)
        if shape is None:
            continue
        build = fold_build(shape, binding.routines)
        if build is None:
            continue  # the shape folds, the VALUE cannot — leave it islanding
        shapes[name] = shape
        builds[name] = build
    return fold_grammar(lifted, shapes), builds
