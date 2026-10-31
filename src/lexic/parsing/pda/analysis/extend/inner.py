"""NON_INITIAL — every character a string can carry past its first."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Sequence, cast

from lexic.ir import (
    IrAction,
    IrAlphabet,
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLambda,
    IrLiteral,
    IrNot,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
)
from lexic.parsing.pda.analysis.extend.maps import (
    Extensions,
    anything,
    found_ruleref,
    nothing,
)
from lexic.parsing.pda.analysis.predicates import (
    arms_union,
    atom_alphabet,
    grow_charsets,
    seq_alphabet,
)
from lexic.parsing.pda.core.charsets import CharSet

# ── NON-INITIAL — what can stand anywhere but first ────────────────────
#
# NON_INITIAL(L) holds every character some string of L carries at a position
# past its first. Every rule below over-approximates it, with ALPHABET as the
# bound, so a caller can only ever prove too LITTLE with it: the one use is
# that a character outside it, met past the start of such a string, begins one.


def _inner_literal(_d: object, n: IrSelf, _nc: object) -> CharSet:
    """A literal's characters past its first."""
    tail = str(n)[1:]
    return CharSet.from_chars(*set(tail)) if tail else CharSet.EMPTY


def _inner_alternation(_d: object, n: IrSelf, nc: Sequence[object]) -> CharSet:
    """A group's is the union of its arms'."""
    assert isinstance(n, IrAlternation)
    return arms_union(n, lambda arm: seq_non_initial(arm, cast(Extensions, nc)))


def seq_non_initial(items: Sequence[IrItem], maps: Extensions) -> CharSet:
    """NON_INITIAL of a sequence: every item past the first contributes its
    whole ALPHABET (an earlier item may have consumed text), and so does a
    first item that can repeat (its second occurrence stands past the first).

    :param items: The sequence's items.
    :param maps: ``found`` the rules' NON_INITIAL so far, ``alphabets`` their
        ALPHABET.
    """
    if not items:
        return CharSet.EMPTY
    head, hi = items[0], items[0].quantifier.upper()
    first = (
        atom_alphabet(head.atom, (maps.alphabets,))
        if hi is None or hi > 1
        else cast(CharSet, NON_INITIAL.resolve(head.atom).eval(None, head.atom, maps))
    )
    return first.union(seq_alphabet(items[1:], maps.alphabets))


def rule_non_initials(rules: Mapping[str, IrRule]) -> Extensions:
    """Every rule's NON_INITIAL — the least fixpoint, grown from empty.

    Monotone and bounded by ALPHABET, so the iteration terminates; a
    left-recursive rule grows into its own answer as :func:`rule_alphabets`'
    does.

    :param rules: The grammar's rules by name.
    :returns: ``found`` each rule's NON_INITIAL, beside the ALPHABET it reads.
    """
    maps = Extensions.empty(rules)
    grow_charsets(
        maps.found,
        rules,
        lambda rule: arms_union(rule.body, lambda arm: seq_non_initial(arm, maps)),
    )
    return maps


NON_INITIAL: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_inner_literal)),
    IrAction(IrCharClass, IrLambda(nothing)),
    IrAction(IrNot, IrLambda(nothing)),
    IrAction(IrAlphabet, IrLambda(anything)),
    IrAction(IrRuleRef, IrLambda(found_ruleref)),
    IrAction(IrAlternation, IrLambda(_inner_alternation)),
)
