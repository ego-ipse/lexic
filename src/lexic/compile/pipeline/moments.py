"""The compile moments — every stage the pipeline passed through, retained.

A compilation is not one step. The canonical grammar becomes the codegen
grammar through three rewrites, is resolved against a vocabulary when one is
bound, yields a binding view, and only then classes. Each of those states is a
thing a caller can want to see, and each was previously a local variable that
died with the call.

The moments ARE those locals, named and kept. That is the whole cost: the
pipeline computes every one of them anyway, so retaining them is a tuple of
references, and a caller who never asks pays a tuple.

**One composition.** :meth:`GrammarMoments.of` is the only place the three
grammar passes are chained, and :func:`build_codegen_grammar` — the fused form
the rest of the package uses — reads its last grammar rather than repeating
the chain. A retaining product that RE-RAN the passes beside the real pipeline
would be a second composition, and it would drift the first time a pass is
added.

**A no-op is a fact.** Whether a moment changed anything is grammar-contingent
— ``chess.gbnf`` has one pass of three that does anything, and a
``@non-semantic`` rule that is not nullable relaxes nothing at all
(deliberately: over a non-nullable rule the relaxation would widen the
language). :meth:`GrammarMoments.no_ops` names those moments rather than
omitting them, so a consumer can draw "this stage did nothing" instead of
silently skipping a stage that ran.
"""

from __future__ import annotations

from typing import ClassVar, Self

from lexic.compile.pipeline.passes import hoist_arms, hoist_groups, relax_non_semantic
from lexic.compile.pipeline.rulemap import RuleMap, compute_binding
from lexic.compile.pipeline.synthesis import synthesize
from lexic.ir import IrAst, IrMap, IrNamedTuple, concretize

GRAMMAR_MOMENTS: tuple[str, ...] = (
    "canonical",
    "grouped",
    "armed",
    "relaxed",
    "resolved",
)
"""The grammar moments, in pipeline order — the field order of
:class:`GrammarMoments`, named so a consumer reads the sequence off the product
instead of re-deriving it."""


class GrammarMoments(IrNamedTuple[IrAst, IrAst, IrAst, IrAst, IrAst]):
    """The grammar half of a compilation: five states, in order.

    The record IS the sequence, so adjacent moments are ``self[i]`` and
    ``self[i + 1]`` — which is what a diff between two stages needs.

    :ivar canonical: What the front half produced — canonicalised, with the
        directive flags bound. The pipeline's starting state.
    :ivar grouped: After ``hoist_groups``: quantified ref-bearing groups have
        become named helper rules.
    :ivar armed: After ``hoist_arms``: every non-empty alternation arm is a
        single unit ruleref.
    :ivar relaxed: After ``relax_non_semantic``: refs to NULLABLE noise rules
        carry ``min=0``. THE codegen grammar, in its authored spelling.
    :ivar resolved: After ``concretize``, when a vocabulary was bound —
        otherwise ``relaxed`` itself. What the engine parses against; the
        authored form is kept beside it because resolution is lossy.
    """

    canonical: IrAst
    grouped: IrAst
    armed: IrAst
    relaxed: IrAst
    resolved: IrAst

    @classmethod
    def of(cls, ast: IrAst, registry: IrMap | None = None) -> Self:
        """Run the grammar half and keep every state it passes through.

        :param ast: The canonical grammar with its directive flags bound.
        :param registry: The resolved name → encoding registry, or ``None``
            for a plain char grammar (then ``resolved`` is ``relaxed``).
        :returns: The five moments.
        """
        grouped = hoist_groups(ast)
        armed = hoist_arms(grouped)
        relaxed = relax_non_semantic(armed)
        resolved = relaxed if registry is None else concretize(relaxed, registry)
        return cls(ast, grouped, armed, relaxed, resolved)

    def no_ops(self) -> tuple[str, ...]:
        """The moments whose stage left the grammar exactly as it found it.

        ``canonical`` is never named: it is the state the pipeline was handed,
        not the product of a stage it ran.

        :returns: The no-op moments' names, in pipeline order.
        """
        return tuple(
            name
            for name, before, after in zip(
                GRAMMAR_MOMENTS[1:], self[:-1], self[1:], strict=True
            )
            if before == after
        )


class CompileMoments(IrNamedTuple[GrammarMoments, list[RuleMap], dict[str, type]]):
    """One compilation, from its canonical grammar to its classes.

    The retaining product the pipeline itself runs through: ``_assemble_core``
    builds one and reads the artefact out of it, so there is no route to a
    compiled grammar that skips a moment or computes one twice.

    :ivar grammar: The five grammar moments.
    :ivar binding: The binding view of ``grammar.resolved`` — one
        :class:`~lexic.compile.pipeline.rulemap.RuleMap` per rule, parents
        before subclasses.
    :ivar classes: The synthesized model classes by class name — the final
        moment, and what ``compile_text`` is after.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("grammar",)
    grammar: GrammarMoments
    binding: list[RuleMap]
    classes: dict[str, type]

    @classmethod
    def of(cls, ast: IrAst, registry: IrMap | None, identity: str) -> Self:
        """Run the whole pipeline and keep every moment of it.

        Synthesis reads the AUTHORED grammar (``relaxed``) while the binding
        reads the resolved one: a vocabulary is a lens for matching, so a
        class's own ``__grammar__`` must not carry baked ordinals.

        :param ast: The canonical grammar with its directive flags bound.
        :param registry: The resolved name → encoding registry, or ``None``.
        :param identity: The grammar's content identity, for the synthetic
            module name the classes carry.
        :returns: The moments, classes last.
        """
        grammar = GrammarMoments.of(ast, registry)
        binding = compute_binding(grammar.resolved)
        return cls(grammar, binding, synthesize(grammar.relaxed, binding, identity))


def build_codegen_grammar(ast: IrAst) -> IrAst:
    """THE codegen grammar: groups hoisted, arms hoisted, noise refs relaxed.

    The fused form, and the moments' own ``relaxed`` — one composition of the
    three passes exists, so the fused answer and the retained one cannot
    disagree.

    :param ast: The canonical grammar with semantic flags bound.
    :returns: The grammar codegen, emission and the instance fold all share.
    """
    return GrammarMoments.of(ast).relaxed
