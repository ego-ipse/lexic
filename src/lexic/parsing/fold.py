"""Positional ParseTree → object fold — the instance-parsing bridge.

The successor of the retired wrapper-rule ``ModelFold``: instance parsing runs
over the *real* codegen grammar and field extraction is positional.
``normalize()`` replaces items in place, so an original item is always exactly
one symbol slot in the normalized arm — for a rule's :class:`ParseTree` node,
``kids[i] ↔ items[i]``. No ``--f<idx>`` wrapper rules, no name protocol.

Config is plain data built by the compile seam (:mod:`lexic.compile`):
per rule a :class:`RuleFold` — ``(kind, ctor, n_items, fields)`` with each
field a ``(item, mode, name, lo)`` :class:`FieldFold`. Constructors are opaque
callables; modes are the :data:`~lexic.ir.bind.BIND_MODES` vocabulary. This
module never sees ``RuleSpec``, pydantic, or :mod:`lexic.codegen`.

Fold behavior per kind:

- ``value_str`` → ``ctor(value=<subtree text>)``;
- ``alternation`` → pass-through to the single sub-model under the node
  (the matched arm's model identifies itself);
- ``sequence`` → per field, ``kids[item]``: ``text``/``gtext`` take the slot's
  consumed text, ``model``/``models`` collect folded sub-models through
  synthetic (normalize) layers; ``None`` values are omitted from kwargs.
  A zero-kid node when ``n_items > 0`` is the rule's empty alternate arm —
  ``ctor()`` with no kwargs (an all-nullable full arm would make the empty
  match ambiguous; :func:`~lexic.parsing.parse_first` resolves it to the
  first derivation, deterministically).

Instance parsing runs :func:`~lexic.parsing.parse_first` (deterministic first
derivation; e.g. json_ws's ``int`` is genuinely ambiguous).
"""

from __future__ import annotations

from typing import Callable, Iterator, Mapping, NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNoneType, IrSeq
from lexic.ir.bind import BIND_MODES
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing.forest import ParseTree
from lexic.parsing.lexruns import collapse_runs, unit_leaves
from lexic.parsing.tables import RUN_STR, ParserTables

FOLD_KINDS: tuple[str, ...] = ("value_str", "sequence", "alternation")
"""The rule-kind vocabulary a :class:`RuleFold` may carry."""


class FieldFold(NamedTuple):
    """One bound field: which kid slot it reads and how it folds.

    :ivar item: Positional index into the rule's sequence arm (= kid slot).
    :ivar mode: One of :data:`~lexic.ir.bind.BIND_MODES`.
    :ivar name: The constructor kwarg the folded value binds to.
    :ivar lo: The item's original quantifier ``lo`` — consumed only by
        ``gtext`` (empty text with ``lo == 0`` means absent, not ``""``).
    """

    item: int
    mode: str
    name: str
    lo: int


class RuleFold(NamedTuple):
    """One rule's fold config — plain data, constructor opaque.

    :ivar kind: One of :data:`FOLD_KINDS`.
    :ivar ctor: The rule's model constructor (unused for ``alternation``).
    :ivar n_items: Kid-slot count of the single non-empty sequence arm
        (``0`` for the other kinds; a zero-kid mismatch = empty-arm match).
    :ivar fields: The bound fields, in item order.
    """

    kind: str
    ctor: Callable[..., object]
    n_items: int
    fields: tuple[FieldFold, ...]


def _subtree_text(node: ParseTree | IrLiteral) -> str:
    """All consumed chars under ``node``, in source order (iterative)."""
    parts: list[str] = []
    stack: list[ParseTree | IrLiteral] = [node]
    while stack:
        k = stack.pop()
        if isinstance(k, ParseTree):
            stack.extend(reversed(k.kids))
        else:
            parts.append(str(k))
    return "".join(parts)


class PositionalFold:
    """Bottom-up ParseTree → model-instance fold over per-rule positional config.

    The runtime mirror of :class:`~lexic.parsing.reduce.Reducer`: same
    explicit-stack discipline, but the outputs are opaque constructor results
    rather than IR nodes, so it lives outside the IrSelf dispatch algebra.

    :ivar config: Rule name → its :class:`RuleFold`. Synthetic (``__rep``/
        ``__opt``/``__grp``) nodes are absent from it and looked through.
    """

    __slots__ = ("config",)

    def __init__(self, config: Mapping[str, RuleFold]) -> None:
        """Validate and hold the fold config.

        :param config: Rule name → :class:`RuleFold`.
        :raises UnsupportedConstructError: On a kind outside
            :data:`FOLD_KINDS` or a field mode outside
            :data:`~lexic.ir.bind.BIND_MODES`.
        """
        for rule_name, rule_fold in config.items():
            if rule_fold.kind not in FOLD_KINDS:
                raise UnsupportedConstructError(
                    f"fold: rule {rule_name!r} has unknown kind "
                    f"{rule_fold.kind!r} (expected one of {FOLD_KINDS})"
                )
            for field in rule_fold.fields:
                if field.mode not in BIND_MODES:
                    raise UnsupportedConstructError(
                        f"fold: field {rule_name}.{field.name} has unknown "
                        f"mode {field.mode!r} (expected one of {BIND_MODES})"
                    )
        self.config = dict(config)

    def run_ok(self, tables: ParserTables, unit_rid: int) -> bool:
        """The run-collapse licence: may this lexical run collapse to one leaf?

        A run may collapse iff none of its unit leaves is a constructor-bearing
        rule (a config key) — those subtrees fold to models a single run leaf
        would erase. A bare terminal (``unit_rid < 0``) and any looked-through
        synthetic layer are safe: the fold reconstructs their text from the
        run's leaf.

        :param tables: The plain (uncollapsed) tables under analysis.
        :param unit_rid: The run's repetition-unit rule id (``-1`` = bare
            terminal).
        :returns: ``True`` when collapsing the run preserves the fold's output.
        """
        if unit_rid < 0:  # bare terminal unit — anonymous, no model structure
            return True
        resolved = unit_leaves(tables, unit_rid)
        if resolved is None:
            return False
        leaf_rids, _has_bare = resolved
        names = tables.decode.rule_names
        return not any(names[rid] in self.config for rid in leaf_rids)

    def apply(self, root: ParseTree) -> object:
        """Fold the parse tree of a start-rule match into its model."""
        results: dict[int, object] = {}
        stack: list[tuple[ParseTree, bool]] = [(root, False)]
        while stack:
            node, expanded = stack.pop()
            if not expanded:
                stack.append((node, True))
                stack.extend(
                    (k, False)
                    for k in node.kids
                    if isinstance(k, ParseTree) and id(k) not in results
                )
                continue
            self._fold_node(node, results)
        return results[id(root)]

    # ── per-node folding ────────────────────────────────────────────

    def _fold_node(self, node: ParseTree, results: dict[int, object]) -> None:
        rule_fold = self.config.get(str(node.symbol))
        if rule_fold is None:
            return  # synthetic (__rep/__opt/__grp) — parents look through it
        if rule_fold.kind == "value_str":
            results[id(node)] = rule_fold.ctor(value=_subtree_text(node))
        elif rule_fold.kind == "alternation":
            models = list(self._models_under_kids(node, results))
            results[id(node)] = models[0] if models else None
        else:
            results[id(node)] = self._fold_sequence(node, rule_fold, results)

    def _fold_sequence(
        self, node: ParseTree, rule_fold: RuleFold, results: dict[int, object]
    ) -> object:
        kids = node.kids
        if len(kids) != rule_fold.n_items:
            if kids:
                raise UnsupportedConstructError(
                    f"fold: {node.symbol}: {len(kids)} kids do not match "
                    f"{rule_fold.n_items} items (nor the empty arm)"
                )
            return rule_fold.ctor()  # empty alternate arm matched
        kwargs: dict[str, object] = {}
        for item, mode, name, lo in rule_fold.fields:
            value = self._fold_field(kids[item], mode, lo, results)
            if value is not None:
                kwargs[name] = value
        return rule_fold.ctor(**kwargs)

    def _fold_field(
        self,
        kid: ParseTree | IrLiteral,
        mode: str,
        lo: int,
        results: dict[int, object],
    ) -> object:
        if mode == "text":
            return _subtree_text(kid)
        if mode == "gtext":
            text = _subtree_text(kid)
            return None if (not text and lo == 0) else text
        models = list(self._models_at(kid, results))
        if mode == "models":
            return models
        return models[0] if models else None

    def _models_at(
        self, kid: ParseTree | IrLiteral, results: dict[int, object]
    ) -> Iterator[object]:
        """Folded models at/under a kid slot, looking through synthetic layers."""
        stack: list[ParseTree | IrLiteral] = [kid]
        while stack:
            k = stack.pop()
            if not isinstance(k, ParseTree):
                continue
            if id(k) in results:
                model = results[id(k)]
                if model is not None:
                    yield model
            else:  # synthetic / non-model layer — descend
                stack.extend(reversed(k.kids))

    def _models_under_kids(
        self, node: ParseTree, results: dict[int, object]
    ) -> Iterator[object]:
        for kid in node.kids:
            yield from self._models_at(kid, results)


# ── optional-nullable lift (engine-ambiguity policy) ──────────────────


def _nullable_names(rules: tuple[IrRule, ...]) -> set[str]:
    """Rule names that can derive the empty string (fixpoint)."""

    def item_nullable(item: IrItem, known: set[str]) -> bool:
        if int(item.quantifier.lo) == 0:
            return True
        atom = item.atom
        if isinstance(atom, IrRuleRef):
            return str(atom) in known
        if isinstance(atom, IrLiteral):
            return not str(atom)
        if isinstance(atom, IrAlternation):
            return any(
                all(item_nullable(i, known) for i in arm if isinstance(i, IrItem))
                for arm in atom
            )
        return False

    known: set[str] = set()
    changed = True
    while changed:
        changed = False
        for rule in rules:
            if str(rule.name) in known:
                continue
            if any(
                all(item_nullable(i, known) for i in arm if isinstance(i, IrItem))
                for arm in rule.body
            ):
                known.add(str(rule.name))
                changed = True
    return known


def lift_optional_nullables(grammar: IrAst) -> IrAst:
    """Rewrite ``R?`` to ``R`` where ``R`` is nullable.

    An optional occurrence of a rule that itself derives empty is genuinely
    ambiguous on the empty span (absent vs empty match) — the engine raises on
    it. The lift is language-preserving (``R? == R`` for nullable ``R``) and
    keeps the empty match present as a zero-width kid, so item positions are
    untouched. Applied to the codegen grammar before :func:`normalize`.

    :param grammar: The instance grammar to lift.
    :returns: The lifted grammar (same rule order, same item positions).
    """
    rules = tuple(grammar.rules)
    nullable = _nullable_names(rules)

    def lift_item(item: IrItem) -> IrItem:
        atom = item.atom
        quantifier = item.quantifier
        if (
            isinstance(atom, IrRuleRef)
            and str(atom) in nullable
            and int(quantifier.lo) == 0
            and not isinstance(quantifier.hi, IrNoneType)
            and int(quantifier.hi) == 1
        ):
            return IrItem(atom, IrQuantifier(1, 1))
        return item

    lifted = tuple(
        IrRule(
            rule.name,
            IrAlternation(
                *(
                    IrSequence(*(lift_item(i) for i in arm if isinstance(i, IrItem)))
                    for arm in rule.body
                )
            ),
            rule.semantic,
        )
        for rule in rules
    )
    return IrAst(rules=IrSeq(*lifted), start=grammar.start)


# ── instance-path run collapse (the fold-config licence) ──────────────


_COLLAPSED: dict[tuple[int, int], tuple[PositionalFold, IrAst, ParserTables]] = {}
"""Collapsed instance-tables memo — (id(fold), id(grammar)) → (fold, grammar,
tables). Strong references pin both ids against reuse."""


def collapsed_fold_tables(grammar: IrAst, fold: PositionalFold) -> ParserTables:
    """Instance tables with every fold-safe lexical run collapsed.

    The grammar-side proof (charset, uniqueness, follow disjointness) comes
    from :func:`~lexic.parsing.lexruns.run_candidates`; the fold-side licence
    (:meth:`PositionalFold.run_ok`) keeps only runs whose collapsed multi-char
    leaf hides structure the fold looks through anyway. Every kept run is
    :data:`~lexic.parsing.tables.RUN_STR` (text-preserving): the run text
    stays a leaf in the tree so ``to_text()`` round-trips exactly — never
    ``RUN_DROP``. Memoised per ``(fold, grammar)``.

    :param grammar: The Earley-normalised instance grammar.
    :param fold: The configured :class:`PositionalFold` for that grammar.
    :returns: The collapsed tables (the plain tables when nothing collapses).
    """
    key = (id(fold), id(grammar))
    entry = _COLLAPSED.get(key)
    if entry is not None:
        return entry[2]
    tables = collapse_runs(
        grammar,
        lambda plain, unit_rid: RUN_STR if fold.run_ok(plain, unit_rid) else None,
    )
    _COLLAPSED[key] = (fold, grammar, tables)
    return tables
