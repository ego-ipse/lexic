"""The grammar the predictive descent runs — the PDA's own rewrites of the lifted grammar.

Two rewrites, each language-preserving and each applied to the PDA's view alone:
Earley parses the authored grammar and its model is the reference, and the
canonical grammar is the grammar's own normal form. The left-recursion fold
(:mod:`.leftrec`) turns `A ::= A β | γ` into a loop the descent can run and
hands back the build that keeps its model; the fusion (:mod:`.fusion`) makes a
text-only rule's runs of one class one item, so no window places a boundary
its value never reads. The analysis and the clones are cut against what comes
out, so a decision is stored against the item the descent runs.
"""

from __future__ import annotations

from lexic.ir import IrAst
from lexic.parsing.executable import ModelExecutable
from lexic.parsing.pda.compiler.descent.fusion import fused_grammar
from lexic.parsing.pda.compiler.descent.leftrec import folded_grammar
from lexic.parsing.pda.compiler.program.bake.lowering import FoldBuild

__all__ = ["descent_grammar"]


def descent_grammar(
    lifted: IrAst, binding: ModelExecutable
) -> tuple[IrAst, dict[str, FoldBuild]]:
    """``lifted`` as the predictive descent runs it, and the folds' builds.

    :param lifted: The lifted codegen grammar the PDA compiles.
    :param binding: The bound model product, for the routines the fold calls.
    :returns: ``(grammar, folds by rule name)``.
    """
    grammar, folds = folded_grammar(lifted, binding)
    return fused_grammar(grammar), folds
