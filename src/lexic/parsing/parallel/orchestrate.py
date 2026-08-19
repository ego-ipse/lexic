"""The split orchestration — one document, chunk-parsed, stitched exactly.

The recipe: scan for the derived separator, cut at separator occurrences
(each cut consumes the separator and the noise run its lead owns), parse
every chunk under the container rule with the SAME grammar and fold (so
models are class-identical), re-parse each cut's 1–3 char lead text under
the lead rule (bounded, O(cuts)), rebuild the cut item nodes from a
template via ``GrammarModel.rebuild``, and rebuild the container.

Scope: the grammar's START rule must itself be the separated-repetition
container — a single arm ``unit item*`` whose item is ``lead unit``. Every
other formulation, any failing or ambiguous chunk, and any policy verdict
of one worker falls back to the sequential product: fallback is an answer,
and a chunk's refusal surfaces as the SEQUENTIAL parse's own refusal, so
splitting never changes what an input means.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple

from lexic.exceptions import LexicError
from lexic.ir import (
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNamedTuple,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrTuple,
)
from lexic.parsing.earley.kernel.forest.ambiguity import Resolver
from lexic.parsing.fold import ModelFold
from lexic.parsing.parallel.policy import AUTO, worker_count
from lexic.parsing.parallel.pool import ParsePool
from lexic.parsing.parallel.replicas import worker_replicas
from lexic.parsing.parallel.roles import Separator, roles
from lexic.parsing.parallel.scan import Scanner, Window
from lexic.parsing.parallel.shapes import UNIT, unbounded
from lexic.parsing.pda.core.charsets import CharSet


class Request[M: IrNamedTuple](NamedTuple):
    """One split parse's per-call inputs — what changes between documents.

    Bundled because the plan, the product and the request are three
    different lifetimes: the product is fixed, the plan is per grammar, and
    only this varies per call.

    :ivar text: The document.
    :ivar fold: The instance fold producing ``M``.
    :ivar resolve: The caller's ambiguity resolver, or ``None``.
    """

    text: str
    fold: ModelFold[M]
    resolve: Resolver | None = None


ModelProduct = Callable[..., Any]
"""The model product, injected: this module splits products, never imports
them — that direction is what lets a product's own entry call into it."""


class SplitPlan(NamedTuple):
    """Everything a split parse of one grammar reuses across documents.

    Two shapes reach here. **Terminated** (``root ::= line+``, the unit
    ending with an anchor): a cut after the terminator leaves whole units on
    both sides, so every chunk is a document and the stitch is a
    concatenation. **Separated** (``root ::= unit (sep unit)*``): the cut
    consumes the separator, whose text is re-parsed under the lead rule and
    rebuilt into the item node the cut fell inside.

    :ivar grammar: The codegen grammar chunks parse under.
    :ivar scanner: The role-driven structural scan.
    :ivar mark: The character cuts key on.
    :ivar sep: The separator record, or ``None`` for a terminated plan.
    :ivar lead_grammar: The grammar rooted at the lead rule; ``None`` for a
        terminated plan or a bare-literal lead.
    :ivar lead_literal: The bare-literal lead text (else ``""``).
    :ivar skip: Characters the cut extends over after the mark.
    """

    grammar: IrAst
    scanner: Scanner
    mark: str
    sep: Separator | None
    lead_grammar: IrAst | None
    lead_literal: str
    skip: frozenset[str]


def _unit_ref(item: IrItem) -> str | None:
    """The unit rule an item references, when it is a plain unit reference."""
    atom = item.atom
    if isinstance(atom, IrRuleRef) and item.quantifier == UNIT:
        return str(atom)
    return None


def _single_arm(rule: IrRule) -> tuple[IrItem, ...] | None:
    """The rule's only arm, when it has exactly one."""
    arms = tuple(rule.body)
    return tuple(arms[0]) if len(arms) == 1 else None


def _item_shape(rule: IrRule, sep: Separator, unit: str) -> bool:
    """Whether the repeated rule is ``lead unit`` for this separator."""
    items = _single_arm(rule)
    if items is None or len(items) != 2 or _unit_ref(items[1]) != unit:
        return False
    lead_atom = items[0].atom
    if sep.lead:
        return _unit_ref(items[0]) == sep.lead
    return isinstance(lead_atom, IrLiteral) and str(lead_atom) == sep.char


def _plan_for(
    grammar: IrAst, sep: Separator, rule_map: dict[str, IrRule]
) -> SplitPlan | None:
    """The plan one separator record admits, or ``None`` on a shape miss."""
    container = rule_map.get(sep.container)
    item_rule = rule_map.get(sep.item)
    if container is None or item_rule is None:
        return None
    items = _single_arm(container)
    if items is None or len(items) != 2:
        return None
    unit = _unit_ref(items[0])
    repeated = items[1].atom
    repeats = isinstance(repeated, IrRuleRef) and str(repeated) == sep.item
    if unit is None or not repeats or not _item_shape(item_rule, sep, unit):
        return None
    if sep.lead:
        lead_grammar, literal = IrAst(grammar.rules, sep.lead), ""
        skip = _lead_skip(sep, rule_map)
    else:
        lead_grammar, literal = None, sep.char
        skip = frozenset()
    return SplitPlan(
        grammar, Scanner(roles(grammar)), sep.char, sep, lead_grammar, literal, skip
    )


def _terminated_plan(grammar: IrAst, rule_map: dict[str, IrRule]) -> SplitPlan | None:
    """The plan a ``start ::= unit+`` terminated repetition admits.

    The start rule's only arm must be one unbounded reference to a unit that
    ends with a single anchor character. Cuts land after the terminator, so
    each chunk holds whole units and parses under the start rule unchanged.
    """
    start = rule_map.get(str(grammar.start))
    if start is None:
        return None
    items = _single_arm(start)
    if items is None or len(items) != 1 or not unbounded(items[0]):
        return None
    target = items[0].atom
    if not isinstance(target, IrRuleRef):
        return None
    derived = roles(grammar)
    unit = str(target)
    for record in derived.terminators:
        if record.unit == unit and record.container == str(grammar.start):
            return SplitPlan(
                grammar, Scanner(derived), record.char, None, None, "", frozenset()
            )
    return None


def _atom_chars(atom: IrSelf) -> frozenset[str]:
    """The chars a literal or char-class atom can emit (co-finite: none).

    A starred literal (``" "*``) emits its chars just as a class does — the
    first skip derivation only looked at classes and missed json-style
    ``ws ::= " "*``, silently degrading every lead-rule split to fallback.
    """
    if isinstance(atom, IrLiteral):
        return frozenset(str(atom))
    if not isinstance(atom, IrCharClass):
        return frozenset()
    emits = CharSet.from_charclass(atom)
    return frozenset() if emits.negated else emits.chars


def _lead_skip(sep: Separator, rule_map: dict[str, IrRule]) -> frozenset[str]:
    """The chars the lead rule may consume AFTER its separator char.

    Only what the lead itself derives (``comma ::= "," ws`` → the ws
    charset) — the cut extends over exactly this noise, so the chunk starts
    where the unit starts. Over- or under-collection is safe: a lead or
    chunk that then fails to parse makes the whole attempt fall back.
    """
    items = _single_arm(rule_map[sep.lead])
    if items is None:
        return frozenset()
    out: set[str] = set()
    for item in items[1:]:
        atom = item.atom
        out |= _atom_chars(atom)
        if isinstance(atom, IrRuleRef) and str(atom) in rule_map:
            for arm in rule_map[str(atom)].body:
                for inner in arm:
                    out |= _atom_chars(inner.atom)
    return frozenset(out) - {sep.char}


_PLANS: dict[int, tuple[IrAst, SplitPlan | None]] = {}
"""Plan memo — id(grammar) → (grammar, plan). The strong reference pins the
id, so a recycled id can never alias a live entry."""


def split_plan(grammar: IrAst) -> SplitPlan | None:
    """The grammar's split plan, memoised per identity; ``None`` = sequential.

    :param grammar: The codegen grammar (repetitions hoisted to rules).
    :returns: A plan when the START rule is a separated repetition whose
        shape the stitch supports; ``None`` otherwise.
    """
    entry = _PLANS.get(id(grammar))
    if entry is None:
        rule_map = {str(rule.name): rule for rule in grammar.rules}
        plan = _terminated_plan(grammar, rule_map)
        for sep in roles(grammar).records if plan is None else ():
            if sep.container == str(grammar.start) and sep.item:
                plan = _plan_for(grammar, sep, rule_map)
                if plan is not None:
                    break
        entry = (grammar, plan)
        _PLANS[id(grammar)] = entry
    return entry[1]


def _scan(plan: SplitPlan, text: str, workers: int) -> list[int]:
    """Depth-0 marks of this plan's char, scanned over ``workers`` windows.

    Windows are arithmetic and each is scanned with no left context — a
    mark character is structural at every occurrence, so a window needs
    nothing from its predecessor and the prefix-sum rebase recovers the
    absolute depths. One window IS the sequential scan.
    """
    if workers < 2:
        windows = [plan.scanner.window(text, 0, len(text))]
    else:
        step = len(text) // workers
        bounds = [
            (k * step, (k + 1) * step if k < workers - 1 else len(text))
            for k in range(workers)
        ]
        pool = ParsePool[tuple[int, int], Window](
            lambda span: plan.scanner.window(text, span[0], span[1]), workers
        )
        try:
            windows = pool.map(bounds)
        finally:
            pool.close()
    return [
        offset
        for offset in plan.scanner.offsets(windows, depth=0)
        if text[offset] == plan.mark
    ]


def _cut_offsets(plan: SplitPlan, text: str, cores: int) -> list[int]:
    """The chosen cut offsets — depth-0 marks of this plan's char, thinned.

    The worker CEILING is settled before anything is scanned: it depends
    only on the build, the core count and the input size, so a document
    that could never occupy two workers must not pay a scan to find that
    out — that scan is a full pass over the input, and charging it to every
    small parse is a regression on grammars that merely HAVE a plan.

    A terminated plan's final mark is dropped: cutting after the document's
    last terminator leaves an empty chunk, which is not a document.
    """
    ceiling = worker_count(len(text), len(text), cores)
    if ceiling < 2:
        return []
    marks = _scan(plan, text, ceiling)
    if plan.sep is None and marks and marks[-1] == len(text) - 1:
        marks.pop()
    workers = worker_count(len(text), len(marks), cores)
    if workers < 2:
        return []
    step = max(1, len(marks) // workers)
    return [marks[k * step] for k in range(1, workers) if k * step < len(marks)]


def _stitch_terminated[M: IrNamedTuple](chunks: list[M]) -> M | None:
    """Concatenate whole-unit chunks; ``None`` = shape surprise.

    Each chunk is a document of complete units, so the container's single
    repetition field is the concatenation — no node is rebuilt or rebased.

    The field must be an ``IrTuple``, not merely tuple-shaped: an ``IrMap``
    iterates and has a length without subclassing one, so a structural test
    would read a keyed field as a repetition and concatenate its entries.
    """
    sequences = []
    for chunk in chunks:
        fields = tuple(chunk)
        if len(fields) != 1 or not isinstance(fields[0], IrTuple):
            return None
        sequences.extend(fields[0])
    return chunks[0].rebuild([IrTuple(*sequences)])


def _stitch_separated[M: IrNamedTuple](
    chunks: list[M], lead_models: list[tuple]
) -> M | None:
    """Rebuild the container from chunk models; ``None`` = shape surprise."""
    heads = [tuple(chunk)[0] for chunk in chunks]
    rests = [tuple(chunk)[1] for chunk in chunks]
    template = next((rest[0] for rest in rests if rest), None)
    if template is None or len(tuple(template)) != len(lead_models[0]) + 1:
        return None
    merged = list(rests[0])
    for k in range(1, len(chunks)):
        merged.append(template.rebuild([*lead_models[k - 1], heads[k]]))
        merged.extend(rests[k])
    return chunks[0].rebuild([heads[0], IrTuple(*merged)])


def _spans(plan: SplitPlan, text: str, cuts: list[int]) -> tuple[list, list[str]]:
    """The chunk spans and each cut's carried lead text.

    A terminated unit OWNS its final character, so its chunk keeps it and
    carries no lead; a separated cut hands the separator (and the noise the
    lead owns) to the lead re-parse instead.
    """
    spans: list[tuple[int, int]] = []
    leads: list[str] = []
    prev = 0
    terminated = plan.sep is None
    for cut in cuts:
        after = cut + 1
        while after < len(text) and text[after] in plan.skip:
            after += 1
        spans.append((prev, after if terminated else cut))
        leads.append("" if terminated else text[cut:after])
        prev = after
    spans.append((prev, len(text)))
    return spans, leads


def _split_parse[M: IrNamedTuple](
    parse: ModelProduct, plan: SplitPlan, ask: Request[M], cuts: list[int]
) -> M | None:
    """One split attempt; ``None`` means: parse sequentially instead."""
    text, fold, resolve = ask
    terminated = plan.sep is None
    spans, leads = _spans(plan, text, cuts)
    if not terminated and plan.lead_grammar is None:
        if any(lead != plan.lead_literal for lead in leads):
            return None
    # Each worker parses against its OWN equal grammar and fold copy: the
    # tables are read-only, but sharing one set of them across cores is what
    # flattens scaling at ~1.8x (refcount cache-line traffic, measured).
    views = worker_replicas(plan.grammar, fold, len(spans))
    pool = ParsePool[int, M](
        lambda k: parse(
            views[k][0], text[spans[k][0] : spans[k][1]], views[k][1], resolve
        ),
        len(spans),
    )
    try:
        chunks = pool.map(range(len(spans)))
        lead_models = [
            (parse(plan.lead_grammar, lead, fold, resolve),)
            if plan.lead_grammar is not None
            else ()
            for lead in leads
        ]
    except LexicError:
        return None
    finally:
        pool.close()
    if terminated:
        return _stitch_terminated(chunks)
    return _stitch_separated(chunks, lead_models)


def split_model[M: IrNamedTuple](
    parse: ModelProduct, grammar: IrAst, ask: Request[M], cores: int = AUTO
) -> M | None:
    """Split this input across workers, or say the split does not apply.

    Returns exactly what :func:`~lexic.parsing.products.parse_model` returns
    for this input, with the wall-clock divided across workers, whenever a
    plan exists, the policy grants more than one worker, and every chunk
    parses. ``None`` says the caller should parse sequentially: no plan, too
    few cut points, or a chunk that failed — and a chunk failing is not a
    verdict on the input, only on the split, so the caller's sequential
    parse is what raises (or does not).

    :param parse: The model product, injected by the layer that owns it.
    :param grammar: The codegen grammar.
    :param ask: The document, its fold, and the caller's ambiguity resolver.
    :param cores: 0 = auto, 1 = sequential (so: never split), N = that many.
    :returns: The model, or ``None`` to parse sequentially.
    """
    text = ask.text
    plan = split_plan(grammar)
    if plan is None:
        return None
    cuts = _cut_offsets(plan, text, cores)
    return _split_parse(parse, plan, ask, cuts) if cuts else None
