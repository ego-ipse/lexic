"""One bracket rule's model-bearing region plan, derived once per product.

The DERIVATION half of the structural stitch: which repeated-items child a
bracket rule has, which generated classes and field slots that recurrence
binds to, and which finite characters the arms around it own. Its own module
because the answer is derived once per grammar and product and then reused,
while :mod:`~lexic.parsing.parallel.stitch.model` spends it on every document.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import (
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNone,
    IrNoneType,
    IrRuleRef,
)
from lexic.model import GrammarModel
from lexic.parsing.caches import adopt, memo
from lexic.parsing.executable import ModelExecutable
from lexic.parsing.parallel.discovery.regions import Region
from lexic.parsing.parallel.discovery.shapes import (
    RuleTable,
    derives_empty,
    literal_char,
    rule_table,
)
from lexic.parsing.parallel.roles.derive import (
    Separator,
    TerminatedRun,
    roles,
    run_terminators,
)
from lexic.parsing.parallel.roles.runs import holds_run
from lexic.parsing.pda.analysis.predicates import (
    atom_alphabet,
    rule_alphabets,
    seq_alphabet,
)
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.product import RuleRoutine

__all__ = [
    "RegionPlan",
    "RegionWork",
    "bracket_rule",
    "derive_plan",
    "field_slot",
    "model_type",
]


class RegionPlan(NamedTuple):
    """The model-bearing shape of one bracketed region rule."""

    root: IrAst
    head_rule: str
    separators: frozenset[str]
    outer_type: type[GrammarModel]
    items_type: type[GrammarModel]
    tail_type: type[GrammarModel]
    outer_begin: int | None
    outer_skip: frozenset[str]
    outer_items: int
    outer_end: int | None
    outer_trail: frozenset[str]
    around: CharSet
    items_head: int
    items_rest: int
    tail_head: int
    edges: tuple[tuple[int, bool], ...]
    """Every slot inside the brackets whose truth is a piece's, with whether it
    stands before the run: the wrapper edges (``outer_begin``, ``outer_end``)
    and each inline capture between the delimiters (:func:`_edges`)."""
    ends: bool = False
    """A TERMINATED run (``"[" entry+ "]"``): ``separators`` are its units'
    terminators, a piece keeps the one it is cut after, and the region's node is
    its first piece's with the run slot (``items_rest``) the pieces' runs joined."""


class RegionWork(NamedTuple):
    """One divided region, the separators between its pieces, and stitch plan."""

    region: Region
    cuts: tuple[int, ...]
    plan: RegionPlan
    witness: str = ""
    """The head text standing in for the region where it is held — assigned,
    with its uniqueness checked, before any piece is parsed."""
    needle: GrammarModel | None = None
    """The items node the witness parses to in the region's brackets — what
    finds the stand-in in its holder's model."""


def model_type(routine: RuleRoutine | None) -> type[GrammarModel] | None:
    """The generated class this rule constructs, or ``None`` — refused, not assumed."""
    construction = None if routine is None else routine.construction
    call = None if construction is None else construction.call
    if isinstance(call, type) and issubclass(call, GrammarModel):
        return call
    return None


def field_slot(routine: RuleRoutine, item: int) -> int | None:
    """The model-child slot from grammar item ``item`` — its rank among the captures."""
    ordered = sorted(capture.slot for capture in routine.captures)
    return next((rank for rank, slot in enumerate(ordered) if slot == item), None)


_BRACKET_RULES: dict[tuple[int, str, str], tuple[IrAst, str]] = memo({}, 0)
"""Per-grammar bracket-arm rules, with a strong identity pin."""


def bracket_rule(grammar: IrAst, rule_name: str, opener: str) -> str:
    """The rule whose sole arm spells the bracket a region opens with.

    Regions are found over the analysis view, where one rule may bracket more
    than one way (``value ::= "[" … "]" | "{" … "}" | num``); the codegen
    grammar hoists each such arm into a single-arm rule of its own, and THAT is
    the rule a plan binds to. A single-arm rule is its own answer; otherwise the
    one arm that is a unit reference to a single-arm rule opening with
    ``opener`` names it. Anything else answers ``rule_name`` unchanged, and its
    plan declines as before. Memoised: a region asks once per document.

    :param grammar: The codegen grammar.
    :param rule_name: The rule the region was discovered under.
    :param opener: The region's opening character.
    :returns: The rule to derive the region's plan for.
    """
    key = (id(grammar), rule_name, opener)
    entry = _BRACKET_RULES.get(key)
    if entry is None:
        entry = (grammar, _bracket_rule(grammar, rule_name, opener))
        _BRACKET_RULES[key] = entry
    return entry[1]


def _bracket_rule(grammar: IrAst, rule_name: str, opener: str) -> str:
    """Resolve :func:`bracket_rule` once."""
    rules = rule_table(grammar)
    outer = rules.get(rule_name)
    if outer is None or len(outer.body) == 1:
        return rule_name
    found = [
        target
        for arm in outer.body
        if len(arm) == 1
        and not isinstance(target := arm[0].unit_ref(), IrNoneType)
        and (held := rules.get(target)) is not None
        and not isinstance(inner := held.sole_arm(), IrNoneType)
        and inner
        and literal_char(inner[0], rules) == opener
    ]
    return found[0] if len(found) == 1 else rule_name


def _ref_at(items: tuple[IrItem, ...], at: int) -> str | None:
    """The rule reference at one arm position, ignoring its quantifier."""
    atom = items[at].atom
    return str(atom) if isinstance(atom, IrRuleRef) else None


def _leads(
    rules: RuleTable,
    records: tuple[Separator, ...],
    tail_arm: tuple[IrItem, ...],
    container: str,
) -> frozenset[str]:
    """What a tail's lead separates by: the one literal it spells, else the
    one-character records :func:`~lexic.parsing.parallel.roles.derive.roles` keeps for
    the run's container — a SET (``addop ::= "+" | "-"``). Empty when neither."""
    char = literal_char(tail_arm[0], rules)
    if char is not None:
        return frozenset({char})
    own = {r.mark for r in records if r.container == container and len(r.mark) == 1}
    return frozenset(own) if len(own) > 1 else frozenset()


def _candidate(
    rules: RuleTable,
    records: tuple[Separator, ...],
    outer_arm: tuple[IrItem, ...],
    at: int,
) -> tuple[str, str, str, frozenset[str]] | None:
    """The items/tail recurrence rooted at one outer-arm position."""
    items_name = _ref_at(outer_arm, at)
    items_rule = rules.get(items_name or "")
    items_arm = items_rule.sole_arm() if items_rule is not None else IrNone
    if items_name is None or isinstance(items_arm, IrNoneType) or len(items_arm) != 2:
        return None
    head, tail_name = _ref_at(items_arm, 0), _ref_at(items_arm, 1)
    tail_rule = rules.get(tail_name or "")
    tail_arm = tail_rule.sole_arm() if tail_rule is not None else IrNone
    leads = (
        _leads(rules, records, tuple(tail_arm), items_name)
        if not isinstance(tail_arm, IrNoneType) and len(tail_arm) == 2
        else frozenset()
    )
    valid_tail = (
        not isinstance(tail_arm, IrNoneType)
        and len(tail_arm) == 2
        and _ref_at(tail_arm, 1) == head
    )
    if head is None or tail_name is None or not items_arm[1].quantifier.unbounded():
        return None
    return (items_name, tail_name, head, leads) if valid_tail and leads else None


def _direct_candidate(
    rules: RuleTable,
    records: tuple[Separator, ...],
    outer_arm: tuple[IrItem, ...],
    at: int,
    container: str,
) -> tuple[str, str, frozenset[str]] | None:
    """A direct ``head tail*`` recurrence at two outer-arm positions."""
    if at + 1 >= len(outer_arm):
        return None
    head, tail_name = _ref_at(outer_arm, at), _ref_at(outer_arm, at + 1)
    tail_rule = rules.get(tail_name or "")
    tail_arm = tail_rule.sole_arm() if tail_rule is not None else IrNone
    leads = (
        _leads(rules, records, tuple(tail_arm), container)
        if not isinstance(tail_arm, IrNoneType) and len(tail_arm) == 2
        else frozenset()
    )
    repeats = outer_arm[at + 1].quantifier.unbounded()
    returns_head = (
        not isinstance(tail_arm, IrNoneType)
        and len(tail_arm) == 2
        and _ref_at(tail_arm, 1) == head
    )
    if head and tail_name and leads and repeats and returns_head:
        return tail_name, head, leads
    return None


class _PlanInput(NamedTuple):
    """Inputs already derived before model-product binding begins."""

    root: IrAst
    binding: ModelExecutable
    rule_name: str
    outer_arm: tuple[IrItem, ...]
    candidate: tuple[int, str, str, str, frozenset[str]]


def _boundary_slots(
    arm: tuple[IrItem, ...], before: int, after: int, routine: RuleRoutine
) -> tuple[int | None, int | None]:
    """Model slots for the wrapper refs immediately around a recurrence."""
    begin = (
        field_slot(routine, before)
        if before >= 0 and _ref_at(arm, before) is not None
        else None
    )
    end = (
        field_slot(routine, after)
        if after < len(arm) and _ref_at(arm, after) is not None
        else None
    )
    return begin, end


def _edges(
    rules: RuleTable,
    arm: tuple[IrItem, ...],
    run: range,
    kept: tuple[int | None, int | None],
    routine: RuleRoutine,
) -> tuple[tuple[int, bool], ...] | None:
    """The plan's :attr:`RegionPlan.edges`, or ``None`` where a capture inside
    the brackets cannot be laid back.

    The merged node is a stand-in's with the region's items overlaid, so every
    other slot between the delimiters — the nearest one-character items either
    side of the run (:func:`literal_char`) — must take its value from a piece:
    ``"(" [ ]* list [ ]* ")"`` would come back without its spaces. A capture
    before the run is read from the FIRST piece and one after it from the LAST,
    whose text between the bracket and the run is the document's own. That
    holds when the capture can be empty, so a middle piece, cut on both sides,
    parses without it; and when its alphabet misses the run's, so a piece's
    shorter text carves capture and run where the whole document does.
    """
    spells = [literal_char(item, rules) is not None for item in arm]
    opens = max((at for at in range(run.start) if spells[at]), default=-1)
    closes = next((at for at in range(run.stop, len(arm)) if spells[at]), len(arm))
    alphabets = rule_alphabets(rules)
    runs = seq_alphabet(arm[run.start : run.stop], alphabets)
    edges = [(kept[0], True)] if kept[0] is not None else []
    for at in range(opens + 1, closes):
        slot = field_slot(routine, at) if at not in run else None
        if slot is None or slot in kept:
            continue
        item = arm[at]
        if not derives_empty(item, rules):
            return None
        if atom_alphabet(item.atom, (alphabets,)).overlaps(runs):
            return None
        edges.append((slot, at < run.start))
    return (*edges, (kept[1], False)) if kept[1] is not None else tuple(edges)


def _finite_chars(
    item: IrItem, rules: RuleTable, seen: frozenset[str] = frozenset()
) -> frozenset[str]:
    """Finite characters emitted by a boundary item; co-finite means unknown."""
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return frozenset(str(atom))
    if isinstance(atom, IrCharClass):
        chars = CharSet.from_charclass(atom)
        return frozenset() if chars.negated else chars.chars
    if not isinstance(atom, IrRuleRef) or str(atom) in seen:
        return frozenset()
    name = str(atom)
    rule = rules.get(name)
    if rule is None:
        return frozenset()
    return frozenset().union(
        *(
            _finite_chars(inner, rules, seen | {name})
            for arm in rule.body
            for inner in arm
        )
    )


def _around(root: IrAst, arm: tuple[IrItem, ...], run: range) -> CharSet:
    """Everything the bracket arm's items other than the run can emit — their
    ALPHABET, a least fixpoint, so a recursive wrapper (``ws ::= " " ws | ""``)
    reads as what it spells — so a lead it holds is known not to be a wrapper's."""
    alphabets = (rule_alphabets(rule_table(root)),)
    found = CharSet.EMPTY
    for at, item in enumerate(arm):
        if at not in run:
            found = found.union(atom_alphabet(item.atom, alphabets))
    return found


def _boundary_charsets(
    root: IrAst, arm: tuple[IrItem, ...], before: int, after: int
) -> tuple[frozenset[str], frozenset[str]]:
    """Finite source characters owned by the arms around one recurrence."""
    rules = rule_table(root)
    opening = _finite_chars(arm[before], rules) if before >= 0 else frozenset()
    closing = _finite_chars(arm[after], rules) if after < len(arm) else frozenset()
    return opening, closing


class _ConfiguredBinding(NamedTuple):
    """Validated model classes and slots for one configured recurrence."""

    outer_type: type[GrammarModel]
    items_type: type[GrammarModel]
    tail_type: type[GrammarModel]
    items_slot: int
    head_slot: int
    rest_slot: int
    tail_head: int


def _configured_binding(
    outer_pr: RuleRoutine, items_pr: RuleRoutine, tail_pr: RuleRoutine, items_at: int
) -> _ConfiguredBinding | None:
    """Bind a configured recurrence's classes and slots, all-or-nothing."""
    outer_type = model_type(outer_pr)
    items_type = model_type(items_pr)
    tail_type = model_type(tail_pr)
    at = field_slot(outer_pr, items_at)
    head = field_slot(items_pr, 0)
    rest = field_slot(items_pr, 1)
    tail = field_slot(tail_pr, 1)
    if outer_type is None or items_type is None or tail_type is None:
        return None
    if at is None or head is None or rest is None or tail is None:
        return None
    return _ConfiguredBinding(outer_type, items_type, tail_type, at, head, rest, tail)


def _configured_plan(source: _PlanInput) -> RegionPlan | None:
    """Bind a derived recurrence to exact generated model slots/classes."""
    items_at, items_name, tail_name, head_name, leads = source.candidate
    routines = source.binding.routines
    outer_pr = routines.get(source.rule_name)
    items_pr = routines.get(items_name)
    tail_pr = routines.get(tail_name)
    if outer_pr is None or items_pr is None or tail_pr is None:
        return None
    bound = _configured_binding(outer_pr, items_pr, tail_pr, items_at)
    if bound is None:
        return None
    begin, end = _boundary_slots(source.outer_arm, items_at - 1, items_at + 1, outer_pr)
    edges = _edges(
        rule_table(source.root),
        source.outer_arm,
        range(items_at, items_at + 1),
        (begin, end),
        outer_pr,
    )
    if edges is None:
        return None
    boundary = _boundary_charsets(
        source.root, source.outer_arm, items_at - 1, items_at + 1
    )
    return RegionPlan(
        root=source.root,
        head_rule=head_name,
        separators=leads,
        outer_type=bound.outer_type,
        items_type=bound.items_type,
        tail_type=bound.tail_type,
        outer_begin=begin,
        outer_skip=boundary[0],
        outer_items=bound.items_slot,
        outer_end=end,
        outer_trail=boundary[1],
        around=_around(source.root, source.outer_arm, range(items_at, items_at + 1)),
        items_head=bound.head_slot,
        items_rest=bound.rest_slot,
        tail_head=bound.tail_head,
        edges=edges,
    )


class _DirectInput(NamedTuple):
    """Inputs for binding a recurrence held directly by its bracket rule."""

    root: IrAst
    binding: ModelExecutable
    rule_name: str
    outer_arm: tuple[IrItem, ...]
    candidate: tuple[int, str, str, frozenset[str]]


class _DirectBinding(NamedTuple):
    """Validated model classes and slots for one direct recurrence."""

    outer_type: type[GrammarModel]
    tail_type: type[GrammarModel]
    head_slot: int
    rest_slot: int
    tail_head: int


def _direct_binding(
    outer_pr: RuleRoutine, tail_pr: RuleRoutine, head_at: int
) -> _DirectBinding | None:
    """Bind direct model classes and slots, all-or-nothing."""
    outer_type = model_type(outer_pr)
    tail_type = model_type(tail_pr)
    head = field_slot(outer_pr, head_at)
    rest = field_slot(outer_pr, head_at + 1)
    tail = field_slot(tail_pr, 1)
    if outer_type is None or tail_type is None:
        return None
    if head is None or rest is None or tail is None:
        return None
    return _DirectBinding(outer_type, tail_type, head, rest, tail)


def _direct_plan(source: _DirectInput) -> RegionPlan | None:
    """Bind a bracket rule that carries ``head tail*`` on itself."""
    head_at, tail_name, head_name, leads = source.candidate
    outer_pr = source.binding.routines.get(source.rule_name)
    tail_pr = source.binding.routines.get(tail_name)
    if outer_pr is None or tail_pr is None:
        return None
    bound = _direct_binding(outer_pr, tail_pr, head_at)
    if bound is None:
        return None
    begin, end = _boundary_slots(source.outer_arm, head_at - 1, head_at + 2, outer_pr)
    edges = _edges(
        rule_table(source.root),
        source.outer_arm,
        range(head_at, head_at + 2),
        (begin, end),
        outer_pr,
    )
    if edges is None:
        return None
    boundary = _boundary_charsets(
        source.root, source.outer_arm, head_at - 1, head_at + 2
    )
    return RegionPlan(
        root=source.root,
        head_rule=head_name,
        separators=leads,
        outer_type=bound.outer_type,
        items_type=bound.outer_type,
        tail_type=bound.tail_type,
        outer_begin=begin,
        outer_skip=boundary[0],
        outer_items=-1,
        outer_end=end,
        outer_trail=boundary[1],
        around=_around(source.root, source.outer_arm, range(head_at, head_at + 2)),
        items_head=bound.head_slot,
        items_rest=bound.rest_slot,
        tail_head=bound.tail_head,
        edges=edges,
    )


def _terminated_plan(
    root: IrAst,
    binding: ModelExecutable,
    rule_name: str,
    arm: tuple[IrItem, ...],
    ended: TerminatedRun,
) -> RegionPlan | None:
    """A bracket arm holding ``unit+`` directly, its units closed by the
    terminators :func:`~lexic.parsing.parallel.roles.derive.run_terminators`
    reads for that container."""
    outer_pr = binding.routines.get(rule_name)
    outer_type = model_type(outer_pr)
    at, unit = ended.at, ended.unit
    slot = field_slot(outer_pr, at) if outer_pr is not None else None
    if outer_pr is None or outer_type is None or slot is None:
        return None
    begin, end = _boundary_slots(arm, at - 1, at + 1, outer_pr)
    edges = _edges(rule_table(root), arm, range(at, at + 1), (begin, end), outer_pr)
    if edges is None:
        return None
    boundary = _boundary_charsets(root, arm, at - 1, at + 1)
    return RegionPlan(
        root=root,
        head_rule=unit,
        separators=ended.marks,
        outer_type=outer_type,
        items_type=outer_type,
        tail_type=outer_type,
        outer_begin=begin,
        outer_skip=boundary[0],
        outer_items=-1,
        outer_end=end,
        outer_trail=boundary[1],
        around=_around(root, arm, range(at, at + 1)),
        items_head=slot,
        items_rest=slot,
        tail_head=0,
        edges=edges,
        ends=True,
    )


_REGION_PLANS: dict[
    tuple[int, int, str], tuple[IrAst, ModelExecutable, RegionPlan | None]
] = memo({}, 0, 1)
"""Per-product region plans. Strong grammar/binding references pin identity.

The rooted grammar owns compiled parser tables and worker replicas. Rebuilding
it per document made every split a cold compile and discarded every supposedly
warm replica, dwarfing the parse at benchmark scale.
"""


def derive_plan(
    grammar: IrAst, binding: ModelExecutable, rule_name: str
) -> RegionPlan | None:
    """Derive the unique repeated-items child of one bracket rule.

    Brackets and whitespace may be referenced wrapper rules or inline grammar
    items. Only the items/tail recurrence is essential. Exact three-reference
    wrappers additionally expose their boundary fields for source restoration.
    """
    key = (id(grammar), id(binding), rule_name)
    entry = _REGION_PLANS.get(key)
    if entry is None:
        rules = rule_table(grammar)
        records = roles(grammar).records
        outer_arm = rules[rule_name].sole_arm() if rule_name in rules else IrNone
        # A run held by a reference between the delimiters is the bracket's own
        # only where the arm holds no run itself (`holds_run`): `"[" e ("," e)*
        # "]"` is the list's run, never the sum each `e` holds.
        candidates = (
            [
                (at, *candidate)
                for at in range(len(outer_arm))
                if (candidate := _candidate(rules, records, outer_arm, at)) is not None
            ]
            if not isinstance(outer_arm, IrNoneType)
            and not holds_run(tuple(outer_arm), rules)
            else []
        )
        direct = (
            [
                (at, *candidate)
                for at in range(len(outer_arm))
                if (
                    candidate := _direct_candidate(
                        rules, records, outer_arm, at, rule_name
                    )
                )
                is not None
            ]
            if not isinstance(outer_arm, IrNoneType)
            else []
        )
        root = IrAst(grammar.rules, rule_name)
        ended = (
            None
            if isinstance(outer_arm, IrNoneType)
            else run_terminators(
                rule_name, tuple(outer_arm), rules, roles(grammar).terminators
            )
        )
        if ended is not None and not isinstance(outer_arm, IrNoneType):
            plan = _terminated_plan(root, binding, rule_name, tuple(outer_arm), ended)
        elif not isinstance(outer_arm, IrNoneType) and len(candidates) == 1:
            plan = _configured_plan(
                _PlanInput(
                    root,
                    binding,
                    rule_name,
                    outer_arm,
                    candidates[0],
                )
            )
        elif not isinstance(outer_arm, IrNoneType) and len(direct) == 1:
            plan = _direct_plan(
                _DirectInput(root, binding, rule_name, outer_arm, direct[0])
            )
        else:
            plan = None
        entry = (grammar, binding, plan)
        _REGION_PLANS[key] = entry
        adopt(id(grammar), root)  # the witness memo keys on the rooted grammar
    return entry[2]
