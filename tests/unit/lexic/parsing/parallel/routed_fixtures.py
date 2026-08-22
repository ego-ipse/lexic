"""The routed-interior grammar fixture shared by the plan and stitch tests.

A generic ``start ::= head* envelope body? "\\n"?`` shape, small enough to
hand-derive the plan and region on: ``body`` names two alternatives, and
``block`` is the one a character sweep cannot find — it opens with the same
newline that ends every ``head`` and ``block-item`` line.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrAst
from lexic.parsing.parallel.discovery.regions import Region
from lexic.parsing.parallel.plan.routed import RoutedPlan, divide, locate, routed_plan

ROUTED_GRAMMAR = (
    'start ::= head* envelope body? "\\n"?\n'
    'head ::= "H" [a-z]* "\\n"\n'
    'envelope ::= "!" [A-Z]\n'
    "body ::= inline | block\n"
    'inline ::= " " item (" " item)* " " ">"\n'
    'block ::= "\\n" block-item* ">"\n'
    'block-item ::= line "\\n"\n'
    "line ::= [a-z]+\n"
    "item ::= [a-z]+\n"
)
"""``block`` is the delimited interior: opens ``\\n``, closes ``>``, each
``block-item`` terminates once at its own ``\\n``. ``inline`` is the sibling
arm ``body`` also offers, opening with a space instead."""


def routed_document(rows: int) -> str:
    """A document under :data:`ROUTED_GRAMMAR` with ``rows`` block lines."""
    letters = "abcdefghijklmnopqrstuvwxyz"

    def word(i: int) -> str:
        return "".join(letters[(i + j) % 26] for j in range(6))

    lines = "\n".join(word(i) for i in range(rows))
    return "Hhead\n!A\n" + lines + "\n>"


class RoutedPieces(NamedTuple):
    """The plan, the located region, and its divided pieces — or ``None``
    fields when any of the three declines."""

    plan: RoutedPlan
    region: Region
    parts: list[str]


def routed_pieces(grammar: IrAst, text: str, workers: int) -> RoutedPieces | None:
    """The plan, region and pieces for one document, or ``None`` on decline."""
    plan = routed_plan(grammar)
    region = locate(text, plan) if plan is not None else None
    parts = divide(text, region, workers) if region is not None else None
    if plan is None or region is None or parts is None:
        return None
    return RoutedPieces(plan, region, parts)
