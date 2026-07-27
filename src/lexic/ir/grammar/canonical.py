"""canonicalize — the language-preserving normal form for a grammar IrAst.

Two grammars describing the same language in different flavours reduce to the
**same** canonical :class:`~lexic.ir.grammar.nodes.IrAst` once each is canonicalised, so
one flavour-agnostic shape drives codegen, parsing, and emission. Every rewrite
here preserves the accepted language; only spelling and structure are
normalised.

Rewrites (bottom-up over each rule body, then two AST-level passes):

1. one-member char class → :class:`~lexic.ir.grammar.nodes.IrLiteral`;
2. an alternation run of single-char/charclass/range arms → one char class;
3. adjacent unquantified literal items → one multi-char literal;
4. :class:`~lexic.ir.grammar.operators.IrNot` of a char class → its positive Unicode
   complement (ABNF cannot spell negation);
5. a single-arm unquantified group → its arm spliced into the parent sequence;
8. char-class normal form (dedupe, sort, coalesce ranges);
8b. empty-literal items (``IrLiteral('')``, epsilon) drop — load-bearing: the
   engine cannot parse a grammar containing a zero-width literal item;
7. rule names + refs fold to lowercase with ``_``→``-`` (post-fold collision of
   distinct rules raises :exc:`~lexic.exceptions.UnsupportedConstructError`);
9. canonical rule order — start first, first-reference order, unreferenced last
   (via :class:`~lexic.ir.grammar.order.RuleOrder`).

Rewrite 6 (quantifier identities) folds in through 5's group inlining; ABNF
``%i`` case expansions are a different language, not a spelling, so they are
left alone.
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action.build import IrAction
from lexic.ir.action.mapping import IrTypeMap
from lexic.ir.action.walk import IrBottomUp
from lexic.ir.grammar.nodes import (
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.grammar.operators import IrNot
from lexic.ir.grammar.order import order_by_refs
from lexic.ir.spine.spine import IrLambda, IrSelf
from lexic.ir.spine.records import IrSeq

_UNIT = IrQuantifier(1, 1)


# ── char-class normal form + single-member literal (rewrites 1, 8) ─────


def _canon_cc(cc: IrCharClass) -> IrCharClass | IrLiteral:
    """Normalise a char class; a single code point collapses to a literal.

    :param cc: The class to canonicalise.
    :returns: The normalised class, or an :class:`IrLiteral` when it is a lone
        code point (rewrite 1).
    """
    norm = cc.normalized()
    first = norm[0] if len(norm) == 1 else None
    if isinstance(first, IrChr):
        return IrLiteral(chr(int(first)))
    return norm


def _canon_charclass(_d: IrSelf, n: IrSelf, _nc: object) -> IrSelf:
    """Transformer body: canonicalise a dispatched :class:`IrCharClass`."""
    assert isinstance(n, IrCharClass)
    return _canon_cc(n)


def _canon_not(_d: IrSelf, n: IrSelf, _nc: object) -> IrSelf:
    """Transformer body: rewrite ``IrNot(charclass)`` to positive spans (rewrite 4).

    The bottom-up driver canonicalises the operand first, so a single-member
    class arrives already collapsed to a one-char literal (rewrite 1) — it
    lifts back to a class here so the complement still applies.
    """
    assert isinstance(n, IrNot)
    operand = n[0]
    if isinstance(operand, IrLiteral) and len(operand) == 1:
        operand = IrCharClass(IrChr(operand))
    if isinstance(operand, IrCharClass):
        return operand.complement()
    return n


# ── alternation arm merge (rewrite 2) ─────────────────────────────────


def _arm_intervals(arm: IrSequence) -> list[tuple[int, int]] | None:
    """Interval cover if ``arm`` is a single unquantified char/charclass item.

    Stays in the interval domain — a Unicode-complement char class (rewrite 4's
    output) contributes a handful of spans, never ~1.1M enumerated points.

    :param arm: The alternation arm (an ``IrSequence``).
    :returns: The covered ``(lo, hi)`` intervals, or ``None`` when the arm is
        not a lone single-char/charclass item.
    """
    if len(arm) != 1:
        return None
    item = arm[0]
    if item.quantifier != _UNIT:
        return None
    atom = item.atom
    if isinstance(atom, IrCharClass):
        return atom.intervals()
    if isinstance(atom, IrLiteral) and len(atom) == 1:
        point = ord(atom)
        return [(point, point)]
    return None


def _merge_arms(alt: IrAlternation) -> IrAlternation:
    """Fuse contiguous single-char/charclass arms into one char-class arm.

    All member math is in the interval domain — pending spans coalesce via
    :meth:`IrCharClass.from_intervals`, never through per-point enumeration.

    :param alt: The alternation whose arms were already canonicalised.
    :returns: The alternation with mergeable runs collapsed.
    """
    new_arms: list[IrSequence] = []
    pending: list[tuple[int, int]] = []

    def flush() -> None:
        if not pending:
            return
        atom = _canon_cc(IrCharClass.from_intervals(pending))
        new_arms.append(IrSequence(IrItem(atom)))
        pending.clear()

    for arm in alt:
        spans = _arm_intervals(arm)
        if spans is not None:
            pending.extend(spans)
        else:
            flush()
            new_arms.append(arm)
    flush()
    return IrAlternation(*new_arms)


def _canon_alternation(_d: IrSelf, n: IrSelf, _nc: object) -> IrSelf:
    """Transformer body: merge char-ish arms (rewrite 2).

    The bottom-up driver hands the alternation over with every arm already
    canonicalised — the body only fuses mergeable runs.
    """
    assert isinstance(n, IrAlternation)
    return _merge_arms(n)


# ── sequence: group inline + literal run merge + empty drop (5, 3, 8b) ──


def _single_arm_group(item: IrItem) -> IrSequence | None:
    """The lone arm of an unquantified single-arm group, else ``None``.

    :param item: A canonicalised sequence item.
    :returns: The inner ``IrSequence`` when ``item`` is a ``(1,1)`` group with
        one arm, else ``None``.
    """
    if item.quantifier != _UNIT:
        return None
    atom = item.atom
    if isinstance(atom, IrAlternation) and len(atom) == 1:
        return atom[0]
    return None


def _collapse_quantified_group(item: IrItem) -> IrItem:
    """Push a quantifier through a single-arm single-item group (rewrite 6).

    ``[minus]`` parses as a ``(0,1)`` group wrapping one unquantified item; the
    quantifier moves onto the inner atom (``minus?``). Groups whose inner item
    is itself quantified, or that hold more than one item, are left intact.

    :param item: A canonicalised sequence item.
    :returns: The collapsed item, or ``item`` unchanged.
    """
    atom = item.atom
    if isinstance(atom, IrAlternation) and len(atom) == 1:
        arm = atom[0]
        if len(arm) == 1 and arm[0].quantifier == _UNIT:
            return IrItem(arm[0].atom, item.quantifier)
    return item


def _is_empty_literal(item: IrItem) -> bool:
    """True if ``item`` is an epsilon literal (``IrLiteral('')``)."""
    return isinstance(item.atom, IrLiteral) and len(item.atom) == 0


def _is_plain_literal(item: IrItem) -> bool:
    """True if ``item`` is an unquantified literal (mergeable in a run)."""
    return isinstance(item.atom, IrLiteral) and item.quantifier == _UNIT


def _merge_literal_runs(items: list[IrItem]) -> list[IrItem]:
    """Fold runs of adjacent unquantified literals into single literals (rewrite 3)."""
    out: list[IrItem] = []
    for item in items:
        if out and _is_plain_literal(out[-1]) and _is_plain_literal(item):
            out[-1] = IrItem(IrLiteral(str(out[-1].atom) + str(item.atom)))
        else:
            out.append(item)
    return out


def _canon_sequence(_d: IrSelf, n: IrSelf, _nc: object) -> IrSelf:
    """Transformer body: splice groups, drop epsilons, merge literal runs.

    The bottom-up driver hands the sequence over with every item already
    canonicalised — the body only restructures this level.
    """
    assert isinstance(n, IrSequence)
    spliced: list[IrItem] = []
    for item in n:
        arm = _single_arm_group(item)
        if arm is not None:
            spliced.extend(arm)
        else:
            spliced.append(_collapse_quantified_group(item))
    kept = [item for item in spliced if not _is_empty_literal(item)]
    return IrSequence(*_merge_literal_runs(kept))


class _CanonDriver(IrBottomUp):
    """Canonicalize's bottom-up driver, fencing :class:`IrAlphabet`.

    An alphabet's inner atom lives in a *foreign* encoding (a token id space,
    not Unicode), so the UTF char-class rewrites here must not touch it — a lone
    token id would collapse to a UTF glyph literal, a negated token would
    complement against ``MAX_CODEPOINT``. Fencing the descent (the ``_descend``
    seam) leaves each alphabet's subtree verbatim while the surrounding grammar
    canonicalises normally; the alphabet is an opaque atom to every outer pass.
    """

    def _descend(self, node: IrSelf) -> "tuple[IrSelf, ...]":
        """Recurse into every node except an :class:`IrAlphabet` (opaque)."""
        if isinstance(node, IrAlphabet):
            return ()
        return tuple(node.children())


_CANON = _CanonDriver(
    actions=IrTypeMap(
        IrAction(IrCharClass, IrLambda(_canon_charclass)),
        IrAction(IrNot, IrLambda(_canon_not)),
        IrAction(IrSequence, IrLambda(_canon_sequence)),
        IrAction(IrAlternation, IrLambda(_canon_alternation)),
    ),
)


# ── name folding (rewrite 7) ──────────────────────────────────────────


def fold_name(name: str) -> str:
    """Fold a rule name/ref to the canonical form: lowercase, ``_`` → ``-``.

    :param name: The source rule name or ref.
    :returns: The canonical name.
    """
    return name.lower().replace("_", "-")


def _rename_ref(_d: IrSelf, n: IrSelf, _nc: object) -> IrSelf:
    """Transformer body: fold an ``IrRuleRef`` name to canonical form."""
    assert isinstance(n, IrRuleRef)
    return IrRuleRef(fold_name(str(n)))


_RENAME = IrBottomUp(actions=IrTypeMap(IrAction(IrRuleRef, IrLambda(_rename_ref))))


def _fold_names(ast: IrAst) -> IrAst:
    """Fold every rule name and ref; raise on a distinct-rule name collision.

    :param ast: The structurally canonicalised AST.
    :returns: The AST with all names folded.
    :raises UnsupportedConstructError: If two distinct source rules fold to the
        same canonical name.
    """
    sources: dict[str, str] = {}
    for rule in ast.rules:
        folded = fold_name(rule.name)
        clash = sources.get(folded)
        if clash is not None and clash != rule.name:
            raise UnsupportedConstructError(
                f"name folding collision: {clash!r} and {rule.name!r} both fold "
                f"to {folded!r}"
            )
        sources[folded] = rule.name
    rules = [
        IrRule(fold_name(rule.name), _RENAME.apply(rule.body), rule.semantic)
        for rule in ast.rules
    ]
    return IrAst(IrSeq(*rules), fold_name(ast.start))


# ── entry point ───────────────────────────────────────────────────────


def canonicalize(ast: IrAst) -> IrAst:
    """Return the canonical form of ``ast`` (see the module docstring).

    :param ast: The parsed grammar AST.
    :returns: The canonicalised, order-normalised AST.
    :raises UnsupportedConstructError: On a name-fold collision (rewrite 7).
    """
    rules = [IrRule(r.name, _CANON.apply(r.body), r.semantic) for r in ast.rules]
    folded = _fold_names(IrAst(IrSeq(*rules), ast.start))
    return order_by_refs(folded)
