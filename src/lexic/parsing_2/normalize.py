"""Desugar an IR grammar into classical Earley shape.

The IR is richer than textbook BNF, so a few canonicalisations precede Earley:

1. **Split multi-char literals.** Scannerless Earley scans one character per
   column, so ``IrLiteral("false")`` becomes five single-char items. Implemented
   here (:func:`split_literals`).

2. **Desugar quantifiers.** ``IrItem(atom, IrQuantifier(lo, hi))`` with a
   non-``(1, 1)`` quantifier becomes a synthetic right-recursive rule
   (``*`` → ``X = "" / elem X``; ``+`` → ``X = elem / elem X``; ``{m,n}`` →
   an unrolled chain). Sketched below — the transform is standard but introduces
   nullable rules, which the completer must then handle (see
   :class:`~lexic.parsing_2.ops.Complete`).

3. **Flatten inline groups.** An :class:`~lexic.ir.nodes.IrAlternation` used as
   an atom (a parenthesised group) is hoisted to a fresh synthetic rule so every
   atom after the dot is a ruleref or a terminal.

Only (1) is wired; (2) and (3) are documented stubs that raise rather than
silently pass through, so an un-normalised grammar fails loudly.
"""

from __future__ import annotations

from lexic.ir.base import IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrSequence,
)

_ONE = IrQuantifier(1, 1)


def split_literals(grammar: IrAst) -> IrAst:
    """Rewrite every multi-char :class:`IrLiteral` atom into single-char items.

    Only unquantified literals are split (a quantified multi-char literal must
    first be desugared to a synthetic rule by :func:`desugar_quantifiers`).

    :param grammar: The grammar to rewrite.
    :returns: An equivalent grammar with one character per literal item.
    """
    rules = tuple(
        IrRule(rule.name, _split_alternation(rule.body)) for rule in grammar.rules
    )
    return IrAst(rules=IrSeq(*rules), start=grammar.start)


def _split_alternation(alt: IrAlternation) -> IrAlternation:
    """Split literals within every arm of ``alt``.

    :param alt: The alternation to rewrite.
    :returns: The rewritten alternation.
    """
    return IrAlternation(*(_split_sequence(arm) for arm in alt))


def _split_sequence(seq: IrSequence) -> IrSequence:
    """Expand multi-char literal items in ``seq`` into single-char items.

    :param seq: The sequence to rewrite.
    :returns: The rewritten sequence.
    """
    out: list[IrItem] = []
    for item in seq:
        if _is_multichar_literal(item):
            out.extend(IrItem(IrLiteral(ch)) for ch in str(item.atom))
        else:
            out.append(item)
    return IrSequence(*out)


def _is_multichar_literal(item: IrItem) -> bool:
    """Whether ``item`` is an unquantified literal longer than one character.

    :param item: The item to test.
    :returns: Whether it should be split.
    """
    return (
        isinstance(item.atom, IrLiteral)
        and item.quantifier == _ONE
        and len(str(item.atom)) > 1
    )


def desugar_quantifiers(_grammar: IrAst) -> IrAst:
    """Replace non-``(1, 1)`` quantifiers with synthetic recursive rules.

    :param _grammar: The grammar to rewrite.
    :returns: An equivalent grammar with only ``(1, 1)`` quantifiers.
    :raises NotImplementedError: Sketched, not yet wired.
    """
    raise NotImplementedError("quantifier desugaring is the next normalize increment")


def flatten_groups(_grammar: IrAst) -> IrAst:
    """Hoist inline :class:`IrAlternation` atoms into fresh synthetic rules.

    :param _grammar: The grammar to rewrite.
    :returns: An equivalent grammar with no group atoms.
    :raises NotImplementedError: Sketched, not yet wired.
    """
    raise NotImplementedError("group flattening is the next normalize increment")
