"""Binding view — the codegen grammar's per-rule class/kind/parent/field map.

``compute_binding(ast)`` reads the codegen grammar (canonical AST after the
:mod:`lexic.compile.passes` rewrites) and produces one :class:`RuleBinding`
per rule, in emission order (parents before subclasses via
:class:`~lexic.ir.grammar.transform.order.RuleOrder`'s parent-edge policy). This is the
open-table successor of ``derive_specs``'s classify/parents/naming jobs:
consumer policy lives in :class:`~lexic.ir.action.walk.IrDispatch` tables whose
defaults refuse unknown atom types — no closed ``isinstance`` ladders, no
``dict[type, ...]`` keying.

Field naming keeps the three-tier cascade:

1. rule ref → the rule name (hyphens to underscores);
2. pattern library — the :data:`CHARCLASS_NAMES` / :data:`LITERAL_NAMES`
   lookup tables (hosted in this module; keyed by canonical char-class form);
3. positional — first unmatched pattern field ``head``, then ``part_N``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from lexic.compile.pipeline.naming import (
    RESERVED_FIELD_NAMES,
    TIER2,
    class_name_for,
    has_ruleref,
)
from lexic.ir import (
    IrAction,
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrBind,
    IrCharClass,
    IrDispatch,
    IrItem,
    IrLambda,
    IrLiteral,
    IrNone,
    IrNoneType,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSequence,
    IrStr,
    IrTypeMap,
    RuleOrder,
)

RuleKind = Literal["sequence", "alternation", "value_str"]

_UNIT = IrQuantifier(1, 1)


# ── field-naming lookup tables ────────────────────────────────────────
#
# Keys are canonical char-class patterns — the codegen grammar the binding
# view reads is post-canonicalize, so members are deduped, ranges coalesced
# and sorted by codepoint. The pre-canonical hex spellings (``[0-9a-fA-F]`` /
# ``[a-fA-F0-9]``) and the mixed-case ``letter``/``alnum`` forms folded to one
# normal-form key each when derive's non-canonical gate was removed (Task 6).


# ── ruleref detection ─────────────────────────────────────────────────


@dataclass(frozen=True)
class RuleBinding:
    """One rule's codegen identity: class, kind, parents, bound fields.

    ``fields`` maps each generated field name to its :class:`IrBind`, in
    declaration order — required first, optional after, each group in item
    order (see :func:`bind_fields`); only ``sequence``-kind rules carry
    fields (``value_str`` emits the implicit ``value`` field,
    ``alternation`` is a field-less pass-through).

    ``parent_class_names`` holds every alternation the rule is a unit-ref arm of
    (deterministically ordered — see :func:`_parent_rules`); an empty tuple
    means the class subclasses :class:`~lexic.model.GrammarModel` directly.
    """

    rule_name: str
    class_name: str
    parent_class_names: tuple[str, ...]
    kind: RuleKind
    fields: dict[str, IrBind]


# ── class naming (absorbed to_pascal) ─────────────────────────────────


# ── kind classification ───────────────────────────────────────────────


def non_empty_arms(body: IrAlternation) -> list[IrSequence]:
    """The arms of ``body`` that carry at least one item.

    :param body: A rule body.
    :returns: The non-empty arms, in body order.
    """
    return [arm for arm in body if arm]


def classify_rule(rule: IrRule) -> RuleKind:
    """Classify a rule into its codegen kind.

    ``value_str`` when no ``IrRuleRef`` occurs anywhere in the body;
    ``alternation`` when more than one non-empty arm remains; ``sequence``
    otherwise.

    :param rule: The rule to classify.
    :returns: The rule's kind.
    """
    if not has_ruleref(rule.body):
        return "value_str"
    if len(non_empty_arms(rule.body)) > 1:
        return "alternation"
    return "sequence"


# ── parent inference ──────────────────────────────────────────────────


def unit_ref_arm(arm: IrSequence) -> IrRuleRef | IrNoneType:
    """The ref of a single-item, unit-quantified ruleref arm, else ``IrNone``.

    :param arm: An alternation arm.
    :returns: The arm's lone ``IrRuleRef``, or :data:`IrNone`.
    """
    if len(arm) != 1 or arm[0].quantifier != _UNIT:
        return IrNone
    atom = arm[0].atom
    return atom if isinstance(atom, IrRuleRef) else IrNone


def _direct_parents(rules: Sequence[IrRule]) -> dict[str, list[str]]:
    """Map each unit-ref alternation arm to its owning alternations, in grammar order.

    Post arm-hoisting every non-empty arm of an ``alternation``-kind rule is a
    unit ref, so this covers original single-ref arms and synthesized
    ``-arm<N>`` rules alike. A rule that is a unit-ref arm of several
    alternations lists all of them (multiple inheritance). Helper rules never
    appear as arms and stay absent (``GrammarModel``).

    :param rules: The codegen grammar's rules.
    :returns: Child rule name → its owning alternation names, in grammar order.
    """
    parents_of: dict[str, list[str]] = {}
    for rule in rules:
        if classify_rule(rule) != "alternation":
            continue
        for arm in non_empty_arms(rule.body):
            ref = unit_ref_arm(arm)
            if isinstance(ref, IrNoneType):
                continue
            parents = parents_of.setdefault(str(ref), [])
            if str(rule.name) not in parents:
                parents.append(str(rule.name))
    return parents_of


def _reach_closure(direct: dict[str, list[str]]) -> dict[str, set[str]]:
    """Full transitive parent reachability, cycle-tolerant.

    Chaotic iteration to the least fixpoint, so a unit-arm cycle yields
    complete (mutually containing) reach sets — unlike the memoised
    :func:`_ancestor_closure`, whose cycle seed leaves them order-dependent.

    :param direct: Child → direct parent alternations (see :func:`_direct_parents`).
    :returns: Each rule name → every rule reachable through parent edges.
    """
    reach: dict[str, set[str]] = {child: set(ps) for child, ps in direct.items()}
    changed = True
    while changed:
        changed = False
        for targets in reach.values():
            step: set[str] = set()
            for parent in targets:
                step |= reach.get(parent, set())
            if not step <= targets:
                targets |= step
                changed = True
    return reach


def _break_cycles(
    direct: dict[str, list[str]], grammar_order: dict[str, int]
) -> dict[str, list[str]]:
    """Reduce the parent graph to an acyclic one with unchanged field typing.

    A unit-arm cycle (``s ::= s | "a"``; mutual ``a ::= b | "x"`` /
    ``b ::= a | "y"``) would emit self-/circularly-inheriting classes. Every
    cycle member derives the same language, so: an edge into the child's own
    cycle is dropped (members become siblings), and an edge to an outside
    parent widens to that parent's whole cycle — every concrete arm then
    carries every cycle member as a base, preserving ``isinstance`` for a
    field typed with any member. A widened edge cannot re-close a cycle:
    mutual reachability between child and any added member would put them in
    one cycle, which the drop clause already excludes.

    :param direct: Child → direct parent alternations, possibly cyclic.
    :param grammar_order: Rule name → its index in the codegen grammar.
    :returns: Child → acyclic parent list, grammar-ordered; children whose
        every edge was intra-cycle are omitted (their class gets
        ``GrammarModel``).
    """
    reach = _reach_closure(direct)

    def cycle_of(name: str) -> set[str]:
        mutual = {m for m in reach.get(name, ()) if name in reach.get(m, ())}
        return mutual | {name}

    out: dict[str, list[str]] = {}
    for child, parents in direct.items():
        own = cycle_of(child)
        acc: list[str] = []
        for parent in parents:
            if parent in own:
                continue
            acc.extend(m for m in cycle_of(parent) if m not in acc)
        if acc:
            out[child] = sorted(acc, key=grammar_order.__getitem__)
    return out


def _ancestor_closure(direct: dict[str, list[str]]) -> dict[str, set[str]]:
    """Transitive parent-alternation closure of each rule.

    :param direct: Child → direct parent alternations (see :func:`_direct_parents`).
    :returns: Each rule name → the set of all its (transitive) parent names.
    """
    closure: dict[str, set[str]] = {}

    def ancestors(name: str) -> set[str]:
        cached = closure.get(name)
        if cached is not None:
            return cached
        closure[name] = set()  # seed first — terminates on an accidental cycle
        acc: set[str] = set()
        for parent in direct.get(name, ()):
            acc.add(parent)
            acc |= ancestors(parent)
        closure[name] = acc
        return acc

    for name in direct:
        ancestors(name)
    return closure


def _order_bases(
    parents: list[str], ancestors: dict[str, set[str]], grammar_order: dict[str, int]
) -> tuple[str, ...]:
    """Order a rule's parent alternations most-derived first (MRO-linearizable).

    Python's C3 linearization rejects bases ``(B1, B2)`` where ``B2`` is a base
    of ``B1``, so a parent that is itself a (transitive) unit-ref arm of another
    parent must precede it. Repeatedly emit the parents that are an ancestor of
    no other remaining parent (the most-derived ones), grammar order breaking
    ties.

    :param parents: The owning alternations, in grammar order.
    :param ancestors: The transitive parent closure (see :func:`_ancestor_closure`).
    :param grammar_order: Rule name → its index in the codegen grammar.
    :returns: The bases tuple, most-derived first.
    """
    remaining = list(parents)
    result: list[str] = []
    while remaining:
        derived = [
            p
            for p in remaining
            if not any(p in ancestors.get(q, ()) for q in remaining if q != p)
        ]
        pick = min(derived, key=lambda name: grammar_order[name])
        result.append(pick)
        remaining.remove(pick)
    return tuple(result)


def _parent_rules(rules: Sequence[IrRule]) -> dict[str, tuple[str, ...]]:
    """Map each unit-ref alternation arm to its owning alternations, MRO-ordered.

    A rule that is a unit-ref arm of several alternations subclasses all of
    them; the tuple is ordered most-derived first so the emitted multi-base
    class linearizes (see :func:`_order_bases`). Unit-arm cycles are broken
    first (see :func:`_break_cycles`) so the emitted hierarchy always loads.

    :param rules: The codegen grammar's rules.
    :returns: Child rule name → its parent alternation names, MRO-ordered.
    """
    grammar_order = {str(rule.name): index for index, rule in enumerate(rules)}
    direct = _break_cycles(_direct_parents(rules), grammar_order)
    ancestors = _ancestor_closure(direct)
    return {
        child: _order_bases(parents, ancestors, grammar_order)
        for child, parents in direct.items()
    }


# ── field naming: tier-2 lookup bodies ────────────────────────────────


def _alphabet_mode(_d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf]) -> IrStr:
    """Mode of a token atom: ``text`` — its token's chars."""
    return IrStr("text")


# _HINT always yields a name (used to label literal-only group content);
# TIER2 may yield IrNone, routing the field to the tier-3 positional names.
# Both inherit IrDispatch's raising default: an unregistered atom type fails
# loudly instead of silently dropping a field.


# ── fold-mode derivation ──────────────────────────────────────────────


def _many(item: IrItem) -> bool:
    """Whether the item repeats (``hi`` unbounded or above one)."""
    hi = item.quantifier.hi
    return isinstance(hi, IrNoneType) or int(hi) > 1


def _ref_mode(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf]) -> IrStr:
    """Mode body: a rule ref folds to its sub-model(s)."""
    item = nc[0]
    assert isinstance(item, IrItem)
    return IrStr("models" if _many(item) else "model")


def _all_unit_ref_arms(alt: IrAlternation) -> bool:
    """True when every arm is a single unit-quantified ruleref item.

    The only group shape that folds cleanly to a sub-model (or list of them):
    each arm yields exactly one child model that identifies itself. An empty
    arm, a multi-item arm, or any literal arm fails the test (``unit_ref_arm``
    returns :data:`IrNone` for each), routing the group to ``gtext``.

    :param alt: The inline group alternation.
    :returns: ``True`` when all arms are unit-ref arms (and there is at least
        one arm).
    """
    return len(alt) > 0 and all(
        not isinstance(unit_ref_arm(arm), IrNoneType) for arm in alt
    )


def _group_mode(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> IrStr:
    """Mode body: an all-unit-ref group folds like a ref, anything else gtext.

    A mixed literal/ref group or a multi-item ref arm cannot fold to a model
    union (a literal arm yields no sub-model, a multi-item arm more than one),
    so those fold as ``gtext`` — the group's matched text, verbatim.
    """
    assert isinstance(n, IrAlternation)
    if _all_unit_ref_arms(n):
        return _ref_mode(d, n, nc)
    return IrStr("gtext")


# Dispatched on the atom; the owning IrItem rides the argument channel so the
# ref/group bodies can read the quantifier.
_MODE: IrDispatch = IrDispatch(
    actions=IrTypeMap(
        IrAction(IrLiteral, IrLiteral("text")),
        IrAction(IrCharClass, IrLiteral("text")),
        IrAction(IrAlphabet, IrLambda(_alphabet_mode)),
        IrAction(IrRuleRef, IrLambda(_ref_mode)),
        IrAction(IrAlternation, IrLambda(_group_mode)),
    ),
)


def mode_for(item: IrItem) -> str:
    """The fold mode of a field-bearing item, from its atom and quantifier.

    :param item: The bound item.
    :returns: One of :data:`~lexic.ir.spine.bind.BIND_MODES`.
    :raises UnsupportedConstructError: On an atom type outside the mode table.
    """
    return str(_MODE.eval(_MODE, item.atom, (item,)))


# ── field binding ─────────────────────────────────────────────────────


def _is_structural_literal(item: IrItem) -> bool:
    """Unit-quantified literal — matched text with no field of its own."""
    return isinstance(item.atom, IrLiteral) and item.quantifier == _UNIT


def _is_semantic_field(item: IrItem, non_semantic: frozenset[str]) -> bool:
    """False when the item refs a structural-noise rule."""
    return not (isinstance(item.atom, IrRuleRef) and item.atom in non_semantic)


def _is_optional_bind(bind: IrBind, item: IrItem) -> bool:
    """Whether the field defaults to ``None`` on its own — the emitters' rule.

    A non-``models`` field whose item can match nothing (``lo == 0``) is
    optional; ``models`` fields stay a required list. The empty-alternate-arm
    force (every field optional) is a rule-level fact the emitters apply on
    top — it defaults ALL fields, so declaration order is unconstrained there.
    """
    return bind.mode != "models" and item.quantifier.lo == 0


def bind_fields(
    items: Sequence[IrItem], non_semantic: frozenset[str]
) -> dict[str, IrBind]:
    """Bind a sequence arm's items to named fields via the three-tier cascade.

    Structural literals produce no field. A reserved name (Python keyword or
    a ``GrammarModel`` public-surface name) gets a ``_`` suffix; name
    collisions get a numeric suffix in occurrence order (``ws``, ``ws2``, …) —
    naming always runs in item order.

    The returned mapping is in **declaration order**: required fields first,
    optional (``None``-defaulted) fields after, each group in item order — so
    the record's constructor signature is well-formed (a defaulted field never
    precedes a required one; the ``NamedTuple`` convention). Item slots ride
    each :class:`IrBind`; slot-keyed consumers (``__binds__``, the fold) are
    order-independent.

    **So this is not the grammar's item order.** Wherever an optional item
    precedes a required one, the two disagree — ``ws? value`` declares
    ``value`` first — and it is the language's rule that wins, not the
    grammar's. Read a field's position in the source from its
    :class:`IrBind`, never from where it appears in ``_fields``.

    :param items: The rule's single sequence arm.
    :param non_semantic: Names of the grammar's structural-noise rules.
    :returns: Field name → :class:`IrBind`, required-first declaration order.
    """
    fields: dict[str, IrBind] = {}
    counts: defaultdict[str, int] = defaultdict(int)
    pattern_pos = 0
    for index, item in enumerate(items):
        if _is_structural_literal(item):
            continue
        base = TIER2.apply(item.atom)
        if isinstance(base, IrNoneType):
            pattern_pos += 1
            name = "head" if pattern_pos == 1 else f"part_{pattern_pos}"
        else:
            name = str(base)
        if name in RESERVED_FIELD_NAMES:
            name += "_"
        counts[name] += 1
        if counts[name] > 1:
            name = f"{name}{counts[name]}"
        fields[name] = IrBind(
            index, mode_for(item), _is_semantic_field(item, non_semantic)
        )
    required = {
        name: bind
        for name, bind in fields.items()
        if not _is_optional_bind(bind, items[bind.item])
    }
    optional = {name: bind for name, bind in fields.items() if name not in required}
    return required | optional


# ── the binding view ──────────────────────────────────────────────────


def _bind_rule(
    rule: IrRule,
    parent_rules: dict[str, tuple[str, ...]],
    non_semantic: frozenset[str],
) -> RuleBinding:
    """Build one rule's binding."""
    kind = classify_rule(rule)
    arms = non_empty_arms(rule.body)
    fields = bind_fields(arms[0], non_semantic) if kind == "sequence" else {}
    parents = parent_rules.get(str(rule.name), ())
    return RuleBinding(
        rule_name=str(rule.name),
        class_name=class_name_for(str(rule.name)),
        parent_class_names=tuple(class_name_for(p) for p in parents),
        kind=kind,
        fields=fields,
    )


def compute_binding(ast: IrAst) -> list[RuleBinding]:
    """Compute the binding view of a codegen grammar.

    Expects the post-pass grammar (groups hoisted, arms hoisted, non-semantic
    refs relaxed — see :mod:`lexic.compile.passes`). Rules come back in
    emission order: start rule's ancestry first, then grammar order, each rule
    after its inheritance parent.

    :param ast: The codegen grammar.
    :returns: One :class:`RuleBinding` per rule, parents before subclasses.
    """
    rules = list(ast.rules)
    parent_rules = _parent_rules(rules)
    non_semantic = ast.non_semantic
    by_name = {
        str(rule.name): _bind_rule(rule, parent_rules, non_semantic) for rule in rules
    }

    def parent_edge(name: str) -> list[str]:
        return list(parent_rules.get(name, ()))

    order = RuleOrder(by_name, ast.start, parent_edge).ordered_parents_first()
    return [by_name[name] for name in order]
