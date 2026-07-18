"""Binding view — the codegen grammar's per-rule class/kind/parent/field map.

``compute_binding(ast)`` reads the codegen grammar (canonical AST after the
:mod:`lexic.compile.passes` rewrites) and produces one :class:`RuleBinding`
per rule, in emission order (parents before subclasses via
:class:`~lexic.ir.order.RuleOrder`'s parent-edge policy). This is the
open-table successor of ``derive_specs``'s classify/parents/naming jobs:
consumer policy lives in :class:`~lexic.ir.walk.IrDispatch` tables whose
defaults refuse unknown atom types — no closed ``isinstance`` ladders, no
``dict[type, ...]`` keying.

Field naming keeps the three-tier cascade:

1. rule ref → the rule name (hyphens to underscores);
2. pattern library — the :data:`CHARCLASS_NAMES` / :data:`LITERAL_NAMES`
   lookup tables (hosted in this module; keyed by canonical char-class form);
3. positional — first unmatched pattern field ``head``, then ``part_N``.
"""

from __future__ import annotations

import inspect
import keyword
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from typing import Literal

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction, IrReturn
from lexic.ir.base import IrLambda, IrNode, IrNone, IrNoneType, IrSelf, IrStr
from lexic.ir.bind import IrBind
from lexic.ir.mapping import IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.order import RuleOrder
from lexic.ir.walk import IrDispatch, IrVisitor

RuleKind = Literal["sequence", "alternation", "value_str"]

_UNIT = IrQuantifier(1, 1)


# ── field-naming lookup tables ────────────────────────────────────────
#
# Keys are canonical char-class patterns — the codegen grammar the binding
# view reads is post-canonicalize, so members are deduped, ranges coalesced
# and sorted by codepoint. The pre-canonical hex spellings (``[0-9a-fA-F]`` /
# ``[a-fA-F0-9]``) and the mixed-case ``letter``/``alnum`` forms folded to one
# normal-form key each when derive's non-canonical gate was removed (Task 6).

CHARCLASS_NAMES: dict[str, str] = {
    "[0-9]": "digit",
    "[0-9A-Fa-f]": "hex",
    "[a-f]": "hex_lower",
    "[A-F]": "hex_upper",
    "[a-z]": "lower",
    "[A-Z]": "upper",
    "[A-Za-z]": "letter",
    "[0-9A-Z_a-z]": "alnum",
}

LITERAL_NAMES: dict[str, str] = {
    "-": "sign",
    "+": "sign",
    ".": "dot",
    ",": "comma",
    ":": "colon",
    ";": "semicolon",
    "=": "eq",
}


# ── ruleref detection ─────────────────────────────────────────────────

_HAS_RULEREF: IrVisitor = IrVisitor(
    actions=IrTypeMap(IrAction(IrRuleRef, IrReturn())),
)


@cache
def has_ruleref(node: IrNode) -> bool:
    """True if any :class:`IrRuleRef` exists in the node subtree.

    Short-circuits on first hit: the singleton :class:`IrVisitor` carries an
    :class:`IrReturn` body for :class:`IrRuleRef`, which raises a control-flow
    exception caught by :meth:`IrDispatch.apply`. Cached on node identity.

    :param node: Root of the subtree to scan.
    :returns: ``True`` if an :class:`IrRuleRef` was found, else ``False``.
    """
    return _HAS_RULEREF.apply(node) is not IrNone


@dataclass(frozen=True)
class RuleBinding:
    """One rule's codegen identity: class, kind, parents, bound fields.

    ``fields`` maps each generated field name to its :class:`IrBind`, in item
    order; only ``sequence``-kind rules carry fields (``value_str`` emits the
    implicit ``value`` field, ``alternation`` is a field-less pass-through).

    ``parent_class_names`` holds every alternation the rule is a unit-ref arm of
    (deterministically ordered — see :func:`_parent_rules`); an empty tuple
    means the class subclasses :class:`~lexic.base.GrammarModel` directly.
    """

    rule_name: str
    class_name: str
    parent_class_names: tuple[str, ...]
    kind: RuleKind
    fields: dict[str, IrBind]


# ── class naming (absorbed to_pascal) ─────────────────────────────────

_NAME_SPLIT = re.compile(r"[-_]")


_RESERVED_FIELD_NAMES: frozenset[str] = frozenset(keyword.kwlist) | frozenset(
    {
        # ``GrammarModel``'s whole public surface — the record spine it lives
        # on (settled 10): a rule named after one of these would generate a
        # field shadowing the IrSelf/tuple protocol or a GrammarModel method.
        # The eight spine-protocol names (``bind``/``bound``/``bound_type``/
        # ``children``/``count``/``eval``/``index``/``rebuild``) shadow the
        # inherited IrSelf/tuple protocol; ``dump`` is a GrammarModel
        # method. Only these curated names are reserved — an arbitrary
        # ``model_*`` name unmangles.
        "bind",
        "bound",
        "bound_fields",
        "bound_type",
        "children",
        "count",
        "dump",
        "eval",
        "fast_construct",
        "index",
        "rebuild",
        "semantic_dump",
        "to_grammar",
        "to_text",
    }
)
"""Field names that would break or shadow the generated model: Python keywords
(a ``class: ...`` annotation is a SyntaxError) and ``GrammarModel``'s whole
public surface (its methods plus the inherited IrSelf/tuple protocol). Curated
as a literal — importing ``lexic.base`` here would couple this module to the
runtime — and drift-pinned by a test against the real class."""

_RESERVED_CLASS_NAMES: frozenset[str] = frozenset(
    {
        "GrammarModel",
        "StringConstraints",
        "Annotated",
        "ClassVar",
        "List",
        "Literal",
        "Optional",
        "Union",
        "IrAlternation",
        "IrAst",
        "IrBind",
        "IrCharClass",
        "IrChr",
        "IrItem",
        "IrLiteral",
        "IrNone",
        "IrNot",
        "IrQuantifier",
        "IrRange",
        "IrRule",
        "IrRuleRef",
        "IrSeq",
        "IrSequence",
    }
)
"""Module-scope names a rendered ``.py`` view binds — the exporter's header
imports (:data:`lexic.compile.export._HEADER`) plus the IR node names that
appear as bare constructors inside the exported reprs. A generated class of
the same name would shadow them in that source. Drift-pinned against the
exporter header by ``test_reserved_class_names_cover_the_export_header``."""


def class_name_for(rule_name: str) -> str:
    """PascalCase class name for a rule; reserved names get a ``_`` suffix.

    Reserved: Python keywords and the emitted module's own header bindings.

    :param rule_name: The (canonical) rule name.
    :returns: A valid Python class name (``jp-char`` → ``JpChar``,
        ``true`` → ``True_``, ``annotated`` → ``Annotated_``).
    """
    pascal = "".join(
        part[:1].upper() + part[1:] for part in _NAME_SPLIT.split(rule_name)
    )
    reserved = keyword.iskeyword(pascal) or pascal in _RESERVED_CLASS_NAMES
    return pascal + "_" if reserved else pascal


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

_TOKEN_RE = re.compile(r"[^0-9A-Za-z]")
_BRACKET_RE = re.compile(r"[][^]")
_NON_SLUG_RE = re.compile(r"[^a-z0-9_]")
_UNDERSCORE_RUN_RE = re.compile(r"_+")


def _literal_token(text: str) -> str:
    """Name a literal: library hit, ASCII token of its value, or ``lit``."""
    named = LITERAL_NAMES.get(text)
    if named:
        return named
    token = _TOKEN_RE.sub("_", text).strip("_").lower()[:12]
    return token or "lit"


def _charclass_key(cc: IrCharClass) -> str:
    """The bracketed lookup key for a char class (``[0-9]``)."""
    return f"[{cc.pattern()}]"


def _pattern_slug(key: str) -> str:
    """Identifier-safe slug of a bracketed pattern; empty when nothing survives."""
    slug = _BRACKET_RE.sub("", key).replace("-", "_").lower()
    slug = _UNDERSCORE_RUN_RE.sub("_", _NON_SLUG_RE.sub("", slug).strip("_"))
    if not slug:
        return ""
    if slug[0].isdigit():
        slug = "cc_" + slug
    return slug[:12].strip("_")


def _ref_field(_d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> IrStr:
    """Tier-1 body: a rule ref names its field after the rule."""
    return IrStr(str(n).replace("-", "_"))


def _literal_field(_d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> IrStr:
    """Tier-2 body: a (quantified) literal always names itself — never tier-3."""
    return IrStr(_literal_token(str(n)))


def _charclass_hint(_d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> IrStr:
    """Hint body: char class names from the library, its slug, or ``cc``."""
    assert isinstance(n, IrCharClass)
    key = _charclass_key(n)
    return IrStr(CHARCLASS_NAMES.get(key) or _pattern_slug(key) or "cc")


def _charclass_field(_d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> IrSelf:
    """Tier-2 body: char class names only on a library hit, else tier-3."""
    assert isinstance(n, IrCharClass)
    named = CHARCLASS_NAMES.get(_charclass_key(n))
    return IrStr(named) if named else IrNone


def _group_hint(d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> IrStr:
    """Hint body: ref-bearing group → ``kind``; else named from its first atom."""
    assert isinstance(n, IrAlternation)
    if has_ruleref(n):
        return IrStr("kind")
    if not (len(n) and len(n[0])):
        return IrStr("inline")
    return IrStr(str(_HINT.eval(d, n[0][0].atom, ())))


def _group_field(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> IrSelf:
    """Tier-2 body: group named by its hint unless the hint is a bare fallback."""
    hint = str(_group_hint(d, n, nc))
    return IrNone if hint in {"inline", "lit", "cc"} else IrStr(hint)


# _HINT always yields a name (used to label literal-only group content);
# _TIER2 may yield IrNone, routing the field to the tier-3 positional names.
# Both inherit IrDispatch's raising default: an unregistered atom type fails
# loudly instead of silently dropping a field.
_HINT: IrDispatch = IrDispatch(
    actions=IrTypeMap(
        IrAction(IrLiteral, IrLambda(_literal_field)),
        IrAction(IrRuleRef, IrLambda(_ref_field)),
        IrAction(IrCharClass, IrLambda(_charclass_hint)),
        IrAction(IrAlternation, IrLambda(_group_hint)),
    ),
)

_TIER2: IrDispatch = IrDispatch(
    actions=IrTypeMap(
        IrAction(IrLiteral, IrLambda(_literal_field)),
        IrAction(IrRuleRef, IrLambda(_ref_field)),
        IrAction(IrCharClass, IrLambda(_charclass_field)),
        IrAction(IrAlternation, IrLambda(_group_field)),
    ),
)


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
        IrAction(IrRuleRef, IrLambda(_ref_mode)),
        IrAction(IrAlternation, IrLambda(_group_mode)),
    ),
)


def mode_for(item: IrItem) -> str:
    """The fold mode of a field-bearing item, from its atom and quantifier.

    :param item: The bound item.
    :returns: One of :data:`~lexic.ir.bind.BIND_MODES`.
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


def bind_fields(
    items: Sequence[IrItem], non_semantic: frozenset[str]
) -> dict[str, IrBind]:
    """Bind a sequence arm's items to named fields via the three-tier cascade.

    Structural literals produce no field. A reserved name (Python keyword or
    a ``GrammarModel`` public-surface name) gets a ``_`` suffix; name
    collisions get a numeric suffix in occurrence order (``ws``, ``ws2``, …).

    :param items: The rule's single sequence arm.
    :param non_semantic: Names of the grammar's structural-noise rules.
    :returns: Field name → :class:`IrBind`, in item order.
    """
    fields: dict[str, IrBind] = {}
    counts: defaultdict[str, int] = defaultdict(int)
    pattern_pos = 0
    for index, item in enumerate(items):
        if _is_structural_literal(item):
            continue
        base = _TIER2.apply(item.atom)
        if isinstance(base, IrNoneType):
            pattern_pos += 1
            name = "head" if pattern_pos == 1 else f"part_{pattern_pos}"
        else:
            name = str(base)
        if name in _RESERVED_FIELD_NAMES:
            name += "_"
        counts[name] += 1
        if counts[name] > 1:
            name = f"{name}{counts[name]}"
        fields[name] = IrBind(
            index, mode_for(item), _is_semantic_field(item, non_semantic)
        )
    return fields


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


# ── open binding: the supplied-class sugar contract ───────────────────
#
# Rule→class binding is open (settled 7): the compile seam builds each rule's
# fold body from EITHER a full authored ``ModelBody`` (the primitive — total
# control, what the notation uses) OR a *supplied class* (the sugar — a body
# derived from this binding view, the class serving as the fold constructor).
# The fold calls the constructor with the binding's field-name kwargs
# (``ctor(**kwargs)`` / ``ctor(value=...)``), so a supplied class must accept
# them; ``check_supplied_class`` enforces that contract loudly.


def field_kwargs(binding: RuleBinding) -> frozenset[str]:
    """The kwarg names the fold hands a rule's constructor.

    A ``value_str`` rule folds through ``ctor(value=<text>)``; a ``sequence``
    rule through ``ctor(**{field: value})`` over its bound fields; an
    ``alternation`` passes its matched arm's sub-model through and calls no
    constructor.

    :param binding: The rule's binding view.
    :returns: The constructor kwarg names for the rule's kind.
    """
    if binding.kind == "value_str":
        return frozenset({"value"})
    if binding.kind == "alternation":
        return frozenset()
    return frozenset(binding.fields)


def check_supplied_class(cls: type, kwargs: frozenset[str]) -> None:
    """Assert a supplied class accepts the fold's field-name kwargs.

    The fold constructs instances via ``cls(**kwargs)``; a class whose
    signature rejects one of the kwargs would fail deep inside the parse. This
    surfaces the mismatch at bind time. A class with a ``**kwargs`` catch-all,
    or one whose constructor cannot be introspected (a C-level builtin), is
    trusted.

    :param cls: The supplied constructor class.
    :param kwargs: The field-name kwargs the fold will pass.
    :raises UnsupportedConstructError: When ``cls`` accepts none-such kwarg.
    """
    try:
        params = inspect.signature(cls).parameters
    except TypeError, ValueError:
        return  # un-introspectable (builtin) — trust the caller
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return
    accepted = {
        name
        for name, p in params.items()
        if p.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    missing = set(kwargs) - accepted
    if missing:
        raise UnsupportedConstructError(
            f"supplied class {cls.__name__!r} does not accept fold kwargs "
            f"{sorted(missing)} (accepts {sorted(accepted)})"
        )
