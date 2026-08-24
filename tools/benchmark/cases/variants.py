"""Directive variants derived from each benchmark grammar."""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, IrRuleRef, census, inline_refs

_NOISE_NAMES = frozenset({"ws", "sp", "wsp", "c-wsp", "c-nl", "nl"})
"""The benchmark's authored noise vocabulary — rule names the `-ns` variant
marks `@non-semantic` where the grammar spells one. Authored HERE, per fixture
set, exactly as a grammar's author would write the directive; a grammar with no
such rule gets an empty set and its `-ns` engine honestly equals its `-lex`
one. Never consulted by engine code — noise is a declaration, not a heuristic.
"""


def _refs_of(rule) -> set[str]:
    """The rule names ``rule``'s body references."""
    return {
        str(entry.node)
        for entry in census(rule.body)
        if isinstance(entry.node, IrRuleRef)
    }


def variant_marks(ast: IrAst) -> tuple[frozenset[str], frozenset[str]]:
    """The variant engines' directive sets, derived from the grammar alone.

    The ``@lexical`` set is SELECTIVE, matching where the directive measurably
    pays: a rule is marked iff it has refs (there is something to inline), its
    every ref targets a LEAF rule with no refs of its own (one level of lexical
    depth — the tier whose per-occurrence models are pure overhead), and
    :func:`~lexic.ir.inline_refs` accepts it. Marking maximally was measured
    SLOWER on the deep self-grammars: wholesale inlining bloats alternation
    bodies and degrades the PDA's decisions, so breadth costs what depth buys.
    The ``@non-semantic`` set is the noise vocabulary above intersected with
    the grammar's own rule names.

    :param ast: The bench's canonical grammar.
    :returns: ``(lexical, non_semantic)`` rule-name sets.
    """
    refs = {str(rule.name): _refs_of(rule) for rule in ast.rules}
    leaves = {name for name, targets in refs.items() if not targets}
    lexical: set[str] = set()
    for rule in ast.rules:
        name = str(rule.name)
        if not refs[name] or not refs[name] <= leaves:
            continue
        try:
            inline_refs(ast, frozenset({name}))
        except UnsupportedConstructError:
            continue
        lexical.add(name)
    names = {str(rule.name) for rule in ast.rules}
    return frozenset(lexical), frozenset(_NOISE_NAMES & names)
