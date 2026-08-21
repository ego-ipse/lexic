"""Equality up to renaming — and the bijection that witnesses it.

:func:`~lexic.ir.grammar.transform.canonical.canonicalize` folds spelling but never
quotients names, so two grammars that differ only in what their rules are
CALLED canonicalise to two different ASTs. They are the same grammar: a pure
rename is no real difference, and every rule-keyed table written against one of
them — a transpile table, a presentation table — should transport to the other.

That is what this module decides, and what it hands back is the transport
itself: an :class:`IrRenaming` per valid bijection. Where a grammar's rules make
several bijections valid (two rules with identical bodies admit both pairings),
ALL of them come back. The choice belongs to whoever asked; picking one quietly
is the same silent pick the engines refuse everywhere else.

**What is decided, and what is not.** Two grammars align when some bijection of
rule names carries one canonical rule set onto the other exactly. That is
decidable, and it is strictly narrower than language equality — which is
undecidable in general and is NOT attempted here. Two grammars describing the
same language by different factorings do not align, and the empty alignment
says only that: no renaming relates them, never that their languages differ.
"""

from __future__ import annotations

from itertools import permutations, product
from typing import ClassVar, Mapping

from lexic.ir.action.mapping import IrMap
from lexic.ir.grammar.nodes import IrAlternation, IrAst, IrRule, IrRuleRef
from lexic.ir.grammar.transform.canonical import canonicalize
from lexic.ir.spine.records import IrNamedTuple, IrSeq, IrTuple
from lexic.ir.spine.scalars import IrStr
from lexic.ir.spine.spine import IrSelf

CANDIDATE_CAP = 256
"""How many candidate bijections one alignment will examine.

A grammar with *k* mutually interchangeable rules admits *k!* bijections, so
the enumeration is bounded and the bound is a drawn fact: an alignment that
stopped here says so in :attr:`IrAlignment.capped` rather than passing off a
truncated list as the complete one."""

_COLOUR = "\x00"
"""Prefix marking a refinement colour, which no grammar rule name can carry —
so a colour can stand in a rule-ref position without ever colliding with a real
name that happens to be spelled like one."""


class IrRename(IrNamedTuple[str, str]):
    """One rule renamed — a pair, so ``dict(renaming)`` is the table.

    :ivar source: The rule's name in the grammar the alignment read first.
    :ivar target: Its name in the second.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    source: str
    target: str


class IrRenaming(IrSeq[IrRename]):
    """One complete rule-name bijection, sorted by source name.

    Total on both sides by construction: every rule of either grammar appears
    exactly once, which is what makes it a witness rather than a partial map.
    """

    def renamed(self, ast: IrAst) -> IrAst:
        """``ast`` with every rule name and rule ref carried across.

        The transport: a table keyed by ``ast``'s rule names is re-keyed by
        running its keys through this, and the grammar itself is re-keyed by
        running it through here.

        :param ast: The grammar to rename — the alignment's source side.
        :returns: The renamed grammar; a name this renaming does not mention
            is left as it stands.
        """
        table: dict[str, str] = dict(self)
        rules = [
            IrRule(
                _moved(table, str(rule.name)),
                IrAlternation.ensure(_renamed_node(rule.body, table)),
                rule.semantic,
            )
            for rule in ast.rules
        ]
        return IrAst(IrSeq(*rules), _moved(table, str(ast.start)))

    def rekeyed(self, rows: IrMap) -> IrMap:
        """A rule-keyed table, re-keyed for the grammar this renaming targets.

        The reason the witness is worth handing back: a transpile table, a
        presentation ceiling — anything keyed by rule names — crosses a pure
        renaming by running its KEYS through here, unchanged in every other
        respect.

        :param rows: A table whose keys are rule names.
        :returns: The same bodies under the target's names; a key this
            renaming does not mention is left as it stands.
        :raises UnsupportedConstructError: If two keys land on one name, which
            would silently drop a row.
        """
        table = dict(self)
        moved = [
            IrTuple(IrStr(_moved(table, str(key))), body) for key, body in rows.items()
        ]
        return type(rows)(*moved)


class IrRenamings(IrSeq[IrRenaming]):
    """Every bijection that aligns one grammar with another, in a stable order."""


class IrAlignment(IrNamedTuple[IrRenamings, bool]):
    """Whether two grammars are one grammar up to renaming, and by which maps.

    :ivar renamings: The valid bijections. Empty means no renaming relates the
        two grammars — they differ in structure, not just in names.
    :ivar capped: ``True`` when the enumeration stopped at
        :data:`CANDIDATE_CAP` and further bijections may exist. The listed ones
        are all valid either way.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("renamings",)
    renamings: IrRenamings
    capped: bool = False


def _moved(table: Mapping[str, str], name: str) -> str:
    """``name`` carried across the renaming — an unlisted one stands as it is."""
    return table.get(name, name)


def _renamed_node(node: IrSelf, table: Mapping[str, str]) -> IrSelf:
    """A rule body with every ``IrRuleRef`` the table names carried across.

    :param node: The subtree to rewrite.
    :param table: Source name → target name; an unlisted ref is left alone.
    :returns: The rewritten subtree.
    """
    if isinstance(node, IrRuleRef):
        return IrRuleRef(table.get(str(node), str(node)))
    children = node.children()
    if not children:
        return node
    return node.rebuild([_renamed_node(child, table) for child in children])


def _signature(name: str, body: IrAlternation, colours: Mapping[str, str]) -> str:
    """A rule's own colour, plus its spelling with each ref replaced by its.

    Name-blind by construction: what survives is structure plus the colours of
    the rules the body points at, which is exactly what two rules must share to
    be candidates for one another. The rule's OWN colour leads, so a round can
    only split a class and never merge two — which is what makes the round
    count a fixpoint test and keeps the start rule apart to the end.

    :param name: The rule's name, for its current colour.
    :param body: The rule body.
    :param colours: Rule name → its current colour.
    :returns: The signature.
    """
    return colours[name] + repr(_renamed_node(body, colours))


def _bodies(ast: IrAst) -> dict[str, IrAlternation]:
    """The grammar's rules as a name → body table."""
    return {str(rule.name): rule.body for rule in ast.rules}


def _seed(names: Mapping[str, IrAlternation], start: str) -> dict[str, str]:
    """The initial colouring — the start rule apart, everything else alike."""
    return {name: _COLOUR + ("1" if name == start else "0") for name in names}


def _refine(left: IrAst, right: IrAst) -> tuple[dict[str, str], dict[str, str]]:
    """Colour both grammars' rules until the partition stops splitting.

    Each round recolours a rule by its own structure plus the colours of the
    rules it references, so a distinction anywhere propagates to everything
    that can reach it. Colours are assigned over BOTH grammars at once, which
    is what makes two rules from different grammars comparable at all.

    :param left: One canonical grammar.
    :param right: The other.
    :returns: The two final colourings, name → colour.
    """
    left_bodies, right_bodies = _bodies(left), _bodies(right)
    colours_l = _seed(left_bodies, str(left.start))
    colours_r = _seed(right_bodies, str(right.start))
    classes = len(set(colours_l.values()) | set(colours_r.values()))
    for _ in range(len(left_bodies) + 1):
        sigs_l = {n: _signature(n, b, colours_l) for n, b in left_bodies.items()}
        sigs_r = {n: _signature(n, b, colours_r) for n, b in right_bodies.items()}
        ids = {
            sig: _COLOUR + str(i)
            for i, sig in enumerate(sorted(set(sigs_l.values()) | set(sigs_r.values())))
        }
        colours_l = {n: ids[sig] for n, sig in sigs_l.items()}
        colours_r = {n: ids[sig] for n, sig in sigs_r.items()}
        if len(ids) == classes:  # a round only splits, so no new class is a fixpoint
            break
        classes = len(ids)
    return colours_l, colours_r


def _cells(colours: Mapping[str, str]) -> dict[str, list[str]]:
    """The colouring inverted — colour → its rule names, sorted."""
    cells: dict[str, list[str]] = {}
    for name in sorted(colours):
        cells.setdefault(colours[name], []).append(name)
    return cells


def _bijectable(left: Mapping[str, list[str]], right: Mapping[str, list[str]]) -> bool:
    """Can these two cell tables biject at all — same colours, same sizes?"""
    return set(left) == set(right) and all(
        len(left[colour]) == len(right[colour]) for colour in left
    )


def _renaming(
    cells: list[list[str]], pairing: tuple[tuple[str, ...], ...]
) -> IrRenaming:
    """One candidate bijection: each cell's sources against one target order."""
    return IrRenaming(
        *sorted(
            IrRename(source, target)
            for sources, targets in zip(cells, pairing, strict=True)
            for source, target in zip(sources, targets, strict=True)
        )
    )


def _rule_set(ast: IrAst) -> dict[str, tuple[IrAlternation, bool]]:
    """The grammar as a name → (body, semantic) table — order-free."""
    return {str(rule.name): (rule.body, rule.semantic) for rule in ast.rules}


def align_names(left: IrAst, right: IrAst) -> IrAlignment:
    """Are these two grammars one grammar up to renaming, and by which maps?

    Both sides are canonicalised first, so the answer is about structure rather
    than spelling, and rule ORDER never enters it — a renaming may reorder the
    canonical rule list, and two orderings of one rule set are one grammar.

    :param left: One grammar AST.
    :param right: The other.
    :returns: The alignment. Empty :attr:`~IrAlignment.renamings` means no
        bijection exists; see the module docstring for what that does and does
        not claim.
    :raises UnsupportedConstructError: If either grammar cannot be
        canonicalised (a name-folding collision).
    """
    left, right = canonicalize(left), canonicalize(right)
    colours_l, colours_r = _refine(left, right)
    left_cells, right_cells = _cells(colours_l), _cells(colours_r)
    if len(left.rules) != len(right.rules) or not _bijectable(left_cells, right_cells):
        return IrAlignment(IrRenamings())
    colours = sorted(left_cells)
    cells = [left_cells[colour] for colour in colours]
    wanted, found, examined = _rule_set(right), [], 0
    for pairing in product(*(permutations(right_cells[c]) for c in colours)):
        if examined == CANDIDATE_CAP:
            return IrAlignment(IrRenamings(*found), True)
        examined += 1
        renaming = _renaming(cells, pairing)
        moved = renaming.renamed(left)
        if _rule_set(moved) == wanted and str(moved.start) == str(right.start):
            found.append(renaming)
    return IrAlignment(IrRenamings(*found))
