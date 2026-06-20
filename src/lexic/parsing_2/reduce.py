"""Forest → IR reduction — the seam where a flavour's meaning attaches.

Recognition proves a derivation exists; reduction turns the derivation into the
target :class:`~lexic.ir.nodes.IrAst`. A flavour's "meta notation" is a reduction
table — an :class:`~lexic.ir.mapping.IrMap` from a rule's
:class:`~lexic.ir.nodes.IrRuleRef` to a body that folds the rule's matched
children into an IR node — paired with a **cleaning policy**: which children are
noise (whitespace, delimiters) and so dropped before a body sees them.

:class:`Reducer` overrides ``eval``: the entry is the inherited
:meth:`~lexic.ir.walk.IrDispatch.apply`, recursion flows back through ``eval``.
Child resolution lives in :data:`RESOLVE_CHILDREN`, a flat-map where each child
contributes :data:`DROP` (nothing), :data:`KEEP_RAW`/:data:`KEEP_REDUCED` (one),
or a spliced synthetic sub-tree (many). The ``noise`` / ``literal`` policy picks
the contribution per child; its defaults reproduce a plain reduce, so a flavour
opts into cleaning by overriding them. :data:`YIELD` recovers a subtree's source
text (skipping non-semantic spans) for rules that yield text rather than build.
"""

from __future__ import annotations

from typing import Sequence, cast

from lexic.ir.base import IrLambda, IrLeaf, IrSelf, IrStr, IrTuple
from lexic.ir.mapping import IR_DEFAULT, IrMap
from lexic.ir.walk import IrDispatch
from lexic.parsing_2.forest import ParseTree
from lexic.parsing_2.normalize import SYNTHETIC_PREFIX

# ── Child contributions ───────────────────────────────────────────────
# Each body returns its contribution to the parent's argument channel as an
# IrTuple: drop = zero elements, keep = one, splice = many.

DROP = IrLambda(lambda d, n, nc: IrTuple())
"""Contribute nothing — a non-semantic rule or an inline-literal terminal."""

KEEP_RAW = IrLambda(lambda d, n, nc: IrTuple(n))
"""Contribute the node unchanged — a terminal leaf passed straight through."""

KEEP_REDUCED = IrLambda(lambda d, n, nc: IrTuple(d.eval(d, n, ())))
"""Contribute the reduced node — a semantic sub-rule folded to its IR."""


# ── Subtree text ──────────────────────────────────────────────────────


class Yield(IrLeaf[IrSelf, IrSelf]):
    """Source text of a parse subtree, skipping non-semantic sub-rule spans.

    Collects ``n``'s consumed characters in source order, recursing into
    sub-trees but skipping any whose rule the reducer's ``noise`` policy marks
    :data:`DROP` (e.g. ABNF ``DQUOTE`` delimiters). Inline-literal terminals are
    kept — so a numeric token like ``%x41-5A`` survives intact while a quoting
    rule's characters drop out. The text-yielding mirror of building from ``nc``.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """Concatenate the subtree's kept leaf characters.

        :param d: The driving :class:`Reducer` (supplies the ``noise`` policy).
        :param n: The parse node (or terminal leaf) whose text to recover.
        :returns: The subtree source text as an :class:`IrStr`.
        """
        if not isinstance(n, ParseTree):
            return IrStr(str(n))
        parts: list[str] = []
        for k in n.kids:
            if (
                isinstance(k, ParseTree)
                and cast("Reducer", d).noise.resolve(k.symbol) is DROP
            ):
                continue
            parts.append(str(self.eval(d, k, ())))
        return IrStr("".join(parts))


YIELD = Yield()
"""Shared subtree-text node — stateless, so one instance."""


# ── Child resolution ──────────────────────────────────────────────────


class ResolveChildren(IrLeaf[IrSelf, IrSelf]):
    """A parse node's children resolved onto the parent's argument channel.

    Flat-maps each child to its contribution: a synthetic sub-tree splices its
    own resolved children in place; a terminal leaf is handled by the reducer's
    ``literal`` policy; any other sub-tree by the ``noise`` policy keyed on its
    rule. The defaults (``literal=KEEP_RAW``, ``noise`` → ``KEEP_REDUCED``)
    reproduce a plain reduce — a flavour overrides them to drop whitespace and
    delimiters.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Resolve ``n``'s children in source order.

        :param d: The driving :class:`Reducer` (supplies the cleaning policy).
        :param n: The parse node whose children to resolve.
        :returns: The resolved children as an :class:`IrTuple`.
        """
        out: list[IrSelf] = []
        policy = cast("Reducer", d)
        for k in cast(ParseTree, n).kids:
            if isinstance(k, ParseTree) and str(k.symbol).startswith(SYNTHETIC_PREFIX):
                out.extend(cast(Sequence[IrSelf], self.eval(d, k, ())))
                continue
            body = (
                policy.literal
                if not isinstance(k, ParseTree)
                else policy.noise.resolve(k.symbol)
            )
            out.extend(cast(Sequence[IrSelf], body.eval(d, k, ())))
        return IrTuple(*out)


RESOLVE_CHILDREN = ResolveChildren()
"""Shared child-resolution node — stateless, so one instance."""


# ── Reducer ───────────────────────────────────────────────────────────


class Reducer(IrDispatch):
    """Bottom-up fold of a :class:`ParseTree` into IR, driven by ``reductions``.

    Each node's children are resolved first (see :data:`RESOLVE_CHILDREN`,
    governed by ``noise`` / ``literal``), then the body bound to the node's
    ``symbol`` is evaluated with those resolved children on the argument channel
    (``nc``) and the tree as ``n``. Dispatch is on ``tree.symbol`` (a *value*,
    :class:`~lexic.ir.nodes.IrRuleRef`) via the ``reductions`` :class:`IrMap` —
    correct because every node is a ``ParseTree``, which is why this overrides
    ``eval`` rather than reusing the type-keyed table.

    :ivar reductions: Rule ref → reduction body, resolved with ``IR_DEFAULT``
        fallback (a flavour points it at ``YIELD`` for its text rules); a miss
        with no default raises.
    :ivar noise: Rule ref → child-contribution body (``DROP``/``KEEP_REDUCED``),
        defaulting (``IR_DEFAULT``) to ``KEEP_REDUCED``.
    :ivar literal: Contribution body for terminal-leaf children (default
        ``KEEP_RAW``).
    """

    reductions: IrMap = IrMap()
    noise: IrMap = IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
    literal: IrSelf = KEEP_RAW

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Reduce ``n`` (a :class:`ParseTree`) to its IR node.

        :param d: The dispatcher (this reducer).
        :param n: The derivation to fold.
        :param nc: Unused at entry — children are resolved here.
        :returns: The IR node the matched rule reduces to.
        :raises IrKeyError: If no reduction matches and no ``IR_DEFAULT`` is set.
        """
        tree = cast(ParseTree, n)
        reduced = cast(Sequence[IrSelf], RESOLVE_CHILDREN.eval(self, tree, ()))
        body = self.reductions.resolve(tree.symbol)
        return body.eval(self, tree, reduced)
