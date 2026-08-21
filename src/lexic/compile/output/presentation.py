"""Presentation tables — what a grammar's rules DRAW as, authored as data.

A ceiling is a rule-keyed table, in the transpile tradition: rows keyed by the
grammar's own canonical rule names, bodies spelled in ordinary IR algebra,
baked once against a compiled artifact, gated, and travelling through the
notation like a grammar or a transpile table does.

What a body PRODUCES is a :class:`Row` — a role the ceiling's author chose, the
:class:`~lexic.ir.text.spans.IrAddress` of the occurrence that produced it, the
:class:`~lexic.ir.text.spans.IrSpan` its spelling covers, and its nested rows.
Nothing here is geometry. There is no pixel, no column, no box: a row says what
stands where in the DOCUMENT, and arranging that on a surface belongs to
whatever draws it. A record that carried a width would be lexic guessing at a
screen it cannot see.

**The key domain is canonical rule names.** Never the codegen helper names
(``array-item``, ``char-arm2``) — those are minted by the pipeline's own passes
and are not a contract anyone authored against. An occurrence of a helper class
routes to the row of the canonical rule it was hoisted out of, derived from the
grammar rather than restated: declare one name, derive the rest.

**Two gates say where a ceiling applies.** MEMBERSHIP: every row names a rule
the grammar actually draws. COMPLETENESS: every drawable rule has a row — the
semantic ones that are not pass-through alternations, since noise draws nothing
and an alternation's arm is the value that stands. A table with a hole is
refused with the uncovered rules named, because a ceiling that silently draws
nothing for a construct is worse than one that says it does not apply: a
consumer can fall back to a floor it knows about, not to a gap it cannot see.

**A ceiling is formulation-bound, and a pure rename is not a formulation.**
Rule names belong to the grammar that declared them, so a table does not
transport to a differently-factored grammar and says so. But a renaming is no
real difference: :meth:`~lexic.ir.grammar.transform.alignment.IrRenaming.rekeyed` carries
a table across one, so the same ceiling serves every renaming of its grammar.
"""

from __future__ import annotations

from typing import Any, Callable, ClassVar, Self, Sequence, cast

from lexic.compile.artifact import CompiledGrammar
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAction,
    IrAddress,
    IrLeaf,
    IrMap,
    IrNamedTuple,
    IrSelf,
    IrSeq,
    IrSpan,
    IrStr,
    IrTypeMap,
    fold_name,
    refs_in_order,
)
from lexic.model import GrammarModel

__all__ = ["Draw", "Presentation", "Row", "Rows", "present"]


class Row(IrNamedTuple[str, IrAddress, IrSpan, "Rows"]):
    """One drawn thing — a role, where it stands, and what stands inside it.

    :ivar role: What the ceiling's author calls this. A ceiling's own word, not
        a rule name: two rules may draw as one role, which is most of why a
        table is worth authoring.
    :ivar address: The occurrence that produced it — the emission's own
        address, so a row and an extent name the same occurrence.
    :ivar span: What its spelling covers in the document, in code units.
    :ivar parts: The rows nested inside it, in document order.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("address", "span", "parts")
    role: str
    address: IrAddress
    span: IrSpan
    parts: Rows


class Rows(IrSeq[Row]):
    """Rows in document order — a ceiling's product, and any row's parts."""


class Draw(IrNamedTuple[IrSelf], init=False):
    """Draw the focus as ``role`` — the one row-building body.

    The address, the span and the nested rows come from the occurrence being
    drawn, not from the author: they are facts about the document, and a body
    that could state them could state them wrongly. What the author supplies is
    the role, which may be a constant or any algebra producing one — an
    ``IrCond`` over the focus draws one rule as two roles.
    """

    role: IrSelf

    def __new__(cls, role: IrSelf | str) -> Self:
        """Lift a plain string role to an ``IrStr`` leaf.

        :param role: The role, or algebra producing one.
        :returns: The body.
        """
        lifted = IrStr(role) if isinstance(role, str) else role
        return cast(Callable[..., Self], super().__new__)(cls, lifted)

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Row:
        """Build the focus's row.

        :param d: The occurrence cursor — carries the address and the span.
        :param n: The focus model.
        :param nc: The rows already built for what stands inside it.
        :returns: The row.
        :raises UnsupportedConstructError: If the dispatcher is not a
            presentation cursor, or the role's algebra produced no string.
        """
        if not isinstance(d, _Focus):
            raise UnsupportedConstructError(
                f"presentation: Draw needs the ceiling's own cursor, got "
                f"{type(d).__name__}"
            )
        role = self.role.eval(d, n, nc)
        if not isinstance(role, str):
            raise UnsupportedConstructError(
                f"presentation: a role must be a string, got {type(role).__name__}"
            )
        return Row(str(role), d.address, d.span, Rows(*(_row(part) for part in nc)))


class _Focus(IrLeaf[IrSelf, IrSelf]):
    """The occurrence being drawn — per-run cursor, mutated as the walk moves.

    One per :meth:`Presentation.apply` call: the address and span change per
    occurrence, and an artifact is shared, so this rides the walk rather than
    the table.
    """

    __slots__ = ("address", "span")

    address: IrAddress
    span: IrSpan

    def __init__(self) -> None:
        """Start at the root's empty address and a zero span."""
        self.address = IrAddress()
        self.span = IrSpan(0, 0)


class Presentation(IrNamedTuple[CompiledGrammar, IrMap, IrTypeMap]):
    """A ceiling baked against one grammar — bake once, draw many.

    :ivar grammar: The artifact the table was baked against.
    :ivar rows: The table as authored — rule names to bodies. Kept because it
        is what travels: through the notation, and across a renaming.
    :ivar bodies: The baked table — model class to body, helper classes routed
        to their canonical rule's row.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    grammar: CompiledGrammar
    rows: IrMap
    bodies: IrTypeMap

    def apply(self, model: GrammarModel) -> Rows:
        """Draw a parsed model — every occurrence its row, in document order.

        The walk is the emission's own: :meth:`~lexic.model.GrammarModel
        .emit_addressed` already visits every occurrence in document order with
        its address and span, so a ceiling needs no traversal of its own and
        cannot disagree with the addresses a consumer co-selects through.

        :param model: A model parsed under :attr:`grammar`.
        :returns: The top-level rows; each carries its own nested rows.
        """
        focus = _Focus()
        stack: list[tuple[tuple[Any, ...], IrAddress, IrSpan, GrammarModel, list[Row]]]
        stack, roots = [], []
        for extent in model.emit_addressed().extents:
            part = model.occurrence(extent.address)
            if not isinstance(part, GrammarModel):
                continue
            if self.bodies.get(type(part)) is None:
                continue
            path = tuple(extent.address)
            while stack and path[: len(stack[-1][0])] != stack[-1][0]:
                _close(self.bodies, focus, stack, roots)
            stack.append((path, extent.address, extent.span, part, []))
        while stack:
            _close(self.bodies, focus, stack, roots)
        return Rows(*roots)


def _row(part: IrSelf) -> Row:
    """Narrow a body's child product to a row.

    :param part: What a nested occurrence's body produced.
    :returns: It, as a row.
    :raises UnsupportedConstructError: When a body produced something else.
    """
    if isinstance(part, Row):
        return part
    raise UnsupportedConstructError(
        f"presentation: a row's parts must be rows, got {type(part).__name__}"
    )


def _close(
    bodies: IrTypeMap,
    focus: _Focus,
    stack: list[tuple[tuple[Any, ...], IrAddress, IrSpan, GrammarModel, list[Row]]],
    roots: list[Row],
) -> None:
    """Finish the innermost open occurrence: run its body, file its row."""
    _path, address, span, part, kids = stack.pop()
    focus.address, focus.span = address, span
    body = bodies[type(part)]
    row = _row(body.eval(focus, part, tuple(kids)))
    (stack[-1][4] if stack else roots).append(row)


def _by_rule(compiled: CompiledGrammar) -> dict[str, type]:
    """Each synthesized class under its own rule's name."""
    return {
        fold_name(str(cls.__grammar__.name)): cls for cls in compiled.classes.values()
    }


def _drawable(compiled: CompiledGrammar) -> list[str]:
    """The canonical rules a ceiling has to answer for, in the grammar's order.

    A rule is one when it is SEMANTIC (structural noise draws nothing) and its
    binding is not an alternation (a pass-through never stands anywhere: the
    arm's model is the value, and the arms have rows of their own). Both facts
    are read off the compilation rather than asked of the author.

    :param compiled: The artifact.
    :returns: The rule names a complete table must cover.
    """
    kinds = {bound.rule_name: bound.kind for bound in compiled.moments.binding}
    return [
        fold_name(str(rule.name))
        for rule in compiled.moments.grammar.canonical.rules
        if rule.semantic and kinds.get(str(rule.name)) != "alternation"
    ]


def _owners(compiled: CompiledGrammar) -> dict[str, str]:
    """Each codegen helper rule under the canonical rule it was hoisted from.

    Derived, not restated: a helper is whatever the codegen grammar has and the
    canonical grammar does not, and its owner is the canonical rule whose body
    reaches it through helpers alone. The two grammars are both moments of the
    same compilation, so neither has to be recomputed to ask.

    :param compiled: The artifact.
    :returns: Helper rule name → its canonical rule name.
    :raises UnsupportedConstructError: If a helper is reachable from two
        canonical rules — it would have no single row to route to.
    """
    moments = compiled.moments.grammar
    canonical = {fold_name(str(rule.name)) for rule in moments.canonical.rules}
    bodies = {fold_name(str(rule.name)): rule.body for rule in moments.resolved.rules}
    owner: dict[str, str] = {}
    for name in (fold_name(str(rule.name)) for rule in moments.resolved.rules):
        if name not in canonical:
            continue
        reach = _refs(bodies[name])
        while reach:
            helper = reach.pop()
            if helper in canonical or helper not in bodies:
                continue
            seen = owner.get(helper)
            if seen == name:
                continue
            if seen is not None:
                raise UnsupportedConstructError(
                    f"presentation: helper rule {helper!r} is reached from both "
                    f"{seen!r} and {name!r} — it has no single row to route to"
                )
            owner[helper] = name
            reach.extend(_refs(bodies[helper]))
    return owner


def _refs(body: IrSelf) -> list[str]:
    """The rule names a body references, folded, in body order."""
    out: list[str] = []
    refs_in_order(body, out)
    return [fold_name(name) for name in out]


def present(compiled: CompiledGrammar, rows: IrMap) -> Presentation:
    """Bake a rule-keyed ceiling against a grammar, gated.

    :param compiled: The grammar the ceiling is authored against.
    :param rows: The table — canonical RULE NAMES to bodies. A body is
        ordinary IR algebra whose product is a :class:`Row`, which in practice
        means a :class:`Draw` (possibly under an ``IrCond``/``IrPipe``).
    :returns: The baked ceiling.
    :raises UnsupportedConstructError: On a row naming no rule of the grammar
        (membership), or a semantic rule with no row (completeness).
    """
    classes = _by_rule(compiled)
    wanted = _drawable(compiled)
    authored = {fold_name(str(key)): body for key, body in rows.items()}
    unknown = sorted(set(authored) - set(wanted))
    if unknown:
        raise UnsupportedConstructError(
            f"presentation: row(s) {unknown} name no drawable rule of the "
            f"grammar — it draws {sorted(wanted)}"
        )
    missing = [name for name in wanted if name not in authored]
    if missing:
        raise UnsupportedConstructError(
            f"presentation: the table has {len(missing)} hole(s) — "
            f"{missing} have no row, and a ceiling with a hole draws nothing "
            "where it should draw something"
        )
    baked = [
        IrAction(classes[name], body)
        for name, body in authored.items()
        if name in classes
    ]
    baked += [
        IrAction(classes[helper], authored[owner])
        for helper, owner in _owners(compiled).items()
        if helper in classes and owner in authored
    ]
    return Presentation(compiled, rows, IrTypeMap(*baked))
