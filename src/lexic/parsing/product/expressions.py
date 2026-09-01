"""The reducer-expression layer — the reducer's own algebra, in flat form.

A fused target constructs its codomain directly; the DEFAULT product instead
evaluates the reducer's own algebra, and this is that algebra's authored
shape. Its own module because it is a distinct layer with a distinct table: a
rule runs an expression range or a fused range, and the two lower into
physically separate instruction tables, which is what makes "never both" a
property of the program rather than a convention.

Imports nothing from :mod:`~lexic.parsing.product.records` — every expression
record's fields are lane indices, so the layer stands alone and ``records``
depends on it rather than the reverse.
"""

from __future__ import annotations

from enum import IntEnum
from typing import NamedTuple

__all__ = [
    "ArgExpr",
    "ArgsExpr",
    "BuildExpr",
    "CondExpr",
    "ConstantExpr",
    "ContributeExpr",
    "ExprCode",
    "ExprOp",
    "ExprProgram",
    "JoinExpr",
    "LookupExpr",
    "PipeExpr",
    "RaiseExpr",
]


class ExprCode(IntEnum):
    """The typed reducer-expression vocabulary, by category.

    A fused target constructs its codomain directly; the DEFAULT product
    instead evaluates the reducer's own algebra, and this is that algebra's
    flat form. The categories are the ones a reducer body actually uses:
    access, build, compute, control, lookup, refusal, and contribution.

    A rule runs an expression range or a fused range, never both — which is
    why these codes index a table physically separate from :class:`OpCode`'s.
    """

    ARG = 0
    ARGS = 1
    CONSTANT = 2
    JOIN = 3
    BUILD = 4
    PIPE = 5
    COND = 6
    LOOKUP = 7
    RAISE = 8
    CONTRIBUTE = 9


class ArgExpr(NamedTuple):
    """Access: one slot of the argument channel."""

    slot: int


class ArgsExpr(NamedTuple):
    """Access: the whole argument channel."""

    channel: int = 0


class ConstantExpr[Carry](NamedTuple):
    """Build: one typed constant from the operand table."""

    constant: int


class JoinExpr(NamedTuple):
    """Compute: join the channel under a separator constant."""

    separator: int


class BuildExpr[Carry](NamedTuple):
    """Build: construct through a binding-owned constructor."""

    constructor: int


class PipeExpr(NamedTuple):
    """Control: feed one expression's value into the next."""

    first: int
    then: int


class CondExpr(NamedTuple):
    """Control: branch on a test expression."""

    test: int
    then_at: int
    else_at: int


class LookupExpr(NamedTuple):
    """Lookup: value-keyed dispatch through a route table."""

    subject: int
    table: int


class RaiseExpr(NamedTuple):
    """Refusal: refuse with the words a constant carries."""

    message: int


class ContributeExpr(NamedTuple):
    """Contribution: what this occurrence hands its parent's channel."""

    policy: int


type ExprOp[Carry] = (
    ArgExpr
    | ArgsExpr
    | ConstantExpr[Carry]
    | JoinExpr
    | BuildExpr[Carry]
    | PipeExpr
    | CondExpr
    | LookupExpr
    | RaiseExpr
    | ContributeExpr
)
"""One authored expression operation."""


class ExprProgram[Carry](NamedTuple):
    """One rule's reducer-expression body, as an ordered operation list.

    Distinct from a bare :data:`RuleCompletion` so a rule's single body field
    says WHICH table it lowers into by its own type — the alternative would be
    two fields on a rule, which is a rule that could execute twice.
    """

    ops: tuple[ExprOp[Carry], ...]
