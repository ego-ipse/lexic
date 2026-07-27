"""P3 structured / P5 probe — folding-aware loop gates (Task 6.6).

The structured (folding-aware) tail over :mod:`lexic.parsing.pda.core.scanner`:
:func:`structured_loop_gate` classifies a comment-bearing / LWS-folding loop
decision into an ``SG_MATCH`` (exact-match over a non-semantic ref — pure
folding, noise↔noise), ``SG_SCAN`` (skip the loop body's leading noise, take
on a disjoint post-noise content lead) or ``SG_PROBE`` (the P5 escalation when
those leads overlap on a next-construct header ``ref(R) noise* lit(L)``, the
"rulename … defined-as" shape) :class:`~lexic.parsing.pda.core.scanner.ScanGate`,
or ``None`` when the decision does not separate (the loop stays an island).

A leaf w.r.t. :mod:`lexic.parsing.pda.analysis.analysis` (the kwindow/noise precedent):
the analysis is taken as an ``Any``-typed oracle argument (``rules`` /
``atom_first`` / ``item_nullable`` / ``first`` / ``cont_at``), so ``analysis``
imports this, never the reverse. The P6 precision clause reads the semantic
FOLLOW table from :mod:`lexic.parsing.pda.analysis.noise`
(:func:`~lexic.parsing.pda.analysis.noise.sem_follow_table`).
"""

from __future__ import annotations

from typing import Any, Sequence

from lexic.ir import IrAlternation, IrItem, IrLiteral, IrNoneType, IrRuleRef, IrSelf
from lexic.parsing.pda.analysis.noise import sem_follow_table
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import (
    SG_MATCH,
    SG_PROBE,
    SG_SCAN,
    ArmGate,
    Recognizer,
    ScanGate,
    build_recognizer,
)

__all__ = [
    "noise_roots",
    "structured_loop_gate",
    "structured_arm_gate",
]


def _items(seq: Sequence[IrSelf]) -> list[IrItem]:
    """The :class:`IrItem` members of a sequence arm, in order (others skipped)."""
    return [i for i in seq if isinstance(i, IrItem)]


def noise_roots(analysis: Any) -> frozenset[str]:
    """The run-forming noise-rule names — the structured scanner's roots.

    A non-semantic rule referenced *anywhere* with a nullable quantifier
    (``lo == 0``, i.e. ``*``/``?``) forms skippable runs (ABNF ``c-wsp``/
    ``filler``/``c-nl``; GBNF ``n``); the recognizer pulls their transitive
    closure. Non-nullable-only refs (required token markers) are excluded.
    """
    roots: set[str] = set()
    for rule in analysis.rules.values():
        for arm in rule.body:
            for item in _items(arm):
                atom = item.atom
                if not isinstance(atom, IrRuleRef) or int(item.quantifier.lo) != 0:
                    continue
                target = analysis.rules.get(str(atom))
                if target is not None and not target.semantic:
                    roots.add(str(atom))
    return frozenset(roots)


def _leading_roots(
    analysis: Any, all_roots: frozenset[str], atom: Any, seen: frozenset[str]
) -> frozenset[str]:
    """The noise roots that lead the loop body — the only noise the gate skips.

    Skipping the *global* noise set is unsound: at ABNF ``concatenation`` it
    would eat the ``c-nl`` rule terminator into the next rule. The gate skips
    only what actually prefixes one loop iteration (``catrest`` leads with
    ``c-wsp``, never ``c-nl``), so a non-leading noise rule stays a real exit
    boundary.
    """
    if isinstance(atom, IrRuleRef):
        name = str(atom)
        if name in seen or name not in analysis.rules:
            return frozenset()
        out: set[str] = set()
        for arm in analysis.rules[name].body:
            out |= _seq_leading_roots(analysis, all_roots, _items(arm), seen | {name})
        return frozenset(out)
    if isinstance(atom, IrAlternation):
        out = set()
        for arm in atom:
            out |= _seq_leading_roots(analysis, all_roots, _items(arm), seen)
        return frozenset(out)
    return frozenset()


def _seq_leading_roots(
    analysis: Any,
    all_roots: frozenset[str],
    items: Sequence[IrItem],
    seen: frozenset[str],
) -> frozenset[str]:
    """The leading noise roots of one sequence — up to the first content atom."""
    out: set[str] = set()
    for item in items:
        atom = item.atom
        if isinstance(atom, IrRuleRef) and str(atom) in all_roots:
            out.add(str(atom))
            continue
        out |= _leading_roots(analysis, all_roots, atom, seen)
        if not analysis.item_nullable(item):
            break
    return frozenset(out)


def _content_first(
    analysis: Any, roots: frozenset[str], atom: Any, seen: frozenset[str]
) -> CharSet:
    """The first *content* (non-noise) chars reachable at ``atom``'s start."""
    if isinstance(atom, IrRuleRef):
        name = str(atom)
        if name in seen or name not in analysis.rules:
            return CharSet.EMPTY
        out = CharSet.EMPTY
        for arm in analysis.rules[name].body:
            out = out.union(_seq_content(analysis, roots, _items(arm), seen | {name}))
        return out
    if isinstance(atom, IrAlternation):
        out = CharSet.EMPTY
        for arm in atom:
            out = out.union(_seq_content(analysis, roots, _items(arm), seen))
        return out
    return analysis.atom_first(atom)


def _seq_content(
    analysis: Any,
    roots: frozenset[str],
    items: Sequence[IrItem],
    seen: frozenset[str],
) -> CharSet:
    """Content FIRST of a sequence — leading noise-root refs skipped."""
    out = CharSet.EMPTY
    for item in items:
        atom = item.atom
        if isinstance(atom, IrRuleRef) and str(atom) in roots:
            continue  # a noise run the scanner skips
        out = out.union(_content_first(analysis, roots, atom, seen))
        if not analysis.item_nullable(item):
            return out
    return out


def _noise_or_nullable(analysis: Any, roots: frozenset[str], item: IrItem) -> bool:
    """Whether ``item`` is nullable or a noise-root reference (scanner-skipped)."""
    atom = item.atom
    if isinstance(atom, IrRuleRef) and str(atom) in roots:
        return True
    return analysis.item_nullable(item)


def _post_noise_follow(
    analysis: Any, roots: frozenset[str], skip: int | None = None
) -> dict[str, CharSet]:
    """Rule → the *content* (non-noise) chars reachable after it once the noise
    run is skipped — the sound exit set for a P3 loop peek.

    Raw FOLLOW conflates a noise-lead (the inter-construct separator) with real
    content; skipping the noise at the exit exposes whatever content lies behind
    it (e.g. after a GBNF ``sequence`` the separator ``n`` then the *next rule's*
    rulename), so a peek that ignores it would mistake the next construct for a
    loop continuation. This fixpoint threads content through noise the way the
    runtime scanner will, keeping the peek honest.

    :param skip: ``id()`` of one :class:`~lexic.ir.grammar.nodes.IrItem` occurrence to
        exclude from the feed — the P5 probe licence removes the candidate
        *header* occurrence itself when asking what else can follow the name
        rule (:func:`_probe_candidate`).
    """
    follow: dict[str, CharSet] = {name: CharSet.EMPTY for name in analysis.rules}
    while _grow_post_noise(analysis, roots, follow, skip):
        pass
    return follow


def _grow_post_noise(
    analysis: Any,
    roots: frozenset[str],
    follow: dict[str, CharSet],
    skip: int | None,
) -> bool:
    """One sweep of the post-noise-FOLLOW fixpoint; ``True`` iff an entry grew."""
    changed = False
    for name, rule in analysis.rules.items():
        for arm in rule.body:
            its = _items(arm)
            for i, item in enumerate(its):
                atom = item.atom
                if not isinstance(atom, IrRuleRef) or str(atom) not in follow:
                    continue
                if skip is not None and id(item) == skip:
                    continue
                cont = _follow_content(analysis, roots, its[i + 1 :], follow[name])
                hi = item.quantifier.hi
                if isinstance(hi, IrNoneType) or int(hi) > 1:
                    cont = cont.union(
                        _content_first(analysis, roots, atom, frozenset())
                    )
                grown = follow[str(atom)].union(cont)
                if grown != follow[str(atom)]:
                    follow[str(atom)] = grown
                    changed = True
    return changed


def _follow_content(
    analysis: Any,
    roots: frozenset[str],
    rest: Sequence[IrItem],
    tail: CharSet,
) -> CharSet:
    """Content FIRST of ``rest``, plus ``tail`` when ``rest`` is all noise/nullable."""
    out = _seq_content(analysis, roots, rest, frozenset())
    if all(_noise_or_nullable(analysis, roots, i) for i in rest):
        out = out.union(tail)
    return out


def _exit_is_noise(analysis: Any, items: Sequence[IrItem], k: int) -> bool:
    """Whether everything after ``k`` up to (and including) the first required
    item is non-semantic references.

    The ``SG_MATCH`` licence: a noise-root loop whose exit is itself noise —
    a required one (ABNF ``rule[5]``: ``c-wsp*`` before the noise ``c-nl``) or
    a run of optional ones to the arm's end (GBNF ``grammar``'s trailing
    ``n? tail-comment?``) — is pure folding, noise↔noise, so a maximal-munch
    recogniser match is the sound take decision. A nullable *semantic* follower
    denies it: an over-take could eat chars that were semantic content. An
    empty rest also denies — the exit is then the rule's FOLLOW, whose
    noise-ness this arm-local walk cannot see.
    """
    if not items[k + 1 :]:
        return False
    for item in items[k + 1 :]:
        atom = item.atom
        target = analysis.rules.get(str(atom)) if isinstance(atom, IrRuleRef) else None
        if target is None or target.semantic:
            return False
        if int(item.quantifier.lo) >= 1:
            return True
    return True


def _root_idxs(rec: Recognizer, names: frozenset[str]) -> tuple[int, ...]:
    """The recognizer indices of ``names``, sorted for determinism."""
    return tuple(sorted(rec.index[n] for n in names))


def structured_loop_gate(
    analysis: Any, items: Sequence[IrItem], k: int, scope: Any
) -> "ScanGate | None":
    """A folding-aware loop gate for a comment-bearing / folding decision, or
    ``None`` when it does not separate (the loop stays an island).

    ``SG_MATCH`` — the loop item is itself a noise root and its exit is noise
    (pure folding); ``SG_SCAN`` — skip the loop body's leading noise, take iff
    the post-noise char is a loop-body content lead disjoint from the exit's;
    ``SG_PROBE`` — the P5 escalation when those leads overlap on a
    next-construct header (see :func:`_probe_gate`).
    """
    roots = noise_roots(analysis)
    if not roots:
        return None
    gate = _match_gate(analysis, roots, items, k, scope)
    if gate is not None:
        return gate
    return _scan_or_probe_gate(analysis, roots, items, k, scope)


def _match_gate(
    analysis: Any, roots: frozenset[str], items: Sequence[IrItem], k: int, scope: Any
) -> "ScanGate | None":
    """The pure-folding ``SG_MATCH`` gate, or ``None``.

    Take another iteration iff a *complete* instance of the loop atom's rule
    matches at the cursor — exact recognition, no greed. Licensed for a loop
    over a non-semantic rule whose over-take is provably noise↔noise, via
    either arm-local structure (:func:`_exit_is_noise` — ABNF ``rule[5]``) or
    the P6 precision clause (:func:`_sem_follow_clear` — every over-takeable
    char cannot follow the rule as semantic content; GBNF ``n``'s
    ``nunit+`` loop, whose ``#``-overlap with the trailing ``tail-comment``
    the exact match resolves: an incomplete ``comment-line`` simply does not
    match, so the tail comment keeps its chars).
    """
    atom = items[k].atom
    if not isinstance(atom, IrRuleRef):
        return None
    target = analysis.rules.get(str(atom))
    if target is None or target.semantic:
        return None
    if not (
        _exit_is_noise(analysis, items, k)
        or _sem_follow_clear(analysis, items, k, scope)
    ):
        return None
    rec = build_recognizer(analysis.rules, roots | {str(atom)})
    if rec is None:
        return None
    return ScanGate(SG_MATCH, rec, (rec.index[str(atom)],))


def _sem_follow_clear(
    analysis: Any, items: Sequence[IrItem], k: int, scope: Any
) -> bool:
    """The P6 precision clause for an exact-match gate.

    ``True`` iff the loop sits in a rule body, everything after it in the arm
    is non-semantic references (or nothing), and no over-takeable char — the
    loop atom's FIRST intersected with its effective continuation — can follow
    the rule as *semantic* content (:func:`~lexic.parsing.pda.analysis.noise
    .sem_follow_table`). Then any over-take only re-splits adjacent noise: same
    bytes, unchanged reduction.
    """
    if not scope.body:
        return False
    for item in items[k + 1 :]:
        atom = item.atom
        target = analysis.rules.get(str(atom)) if isinstance(atom, IrRuleRef) else None
        if target is None or target.semantic:
            return False
    first = analysis.atom_first(items[k].atom)
    cont = analysis.cont_at(items, k, scope.tail)
    eatable = first.subtract(first.subtract(cont))
    return not sem_follow_table(analysis)[scope.rule].overlaps(eatable)


def _scan_or_probe_gate(
    analysis: Any, roots: frozenset[str], items: Sequence[IrItem], k: int, scope: Any
) -> "ScanGate | None":
    """The skip-then-peek ``SG_SCAN`` gate, escalating to ``SG_PROBE`` when the
    post-noise take and exit content leads overlap."""
    lead = _leading_roots(analysis, roots, items[k].atom, frozenset())
    if not lead:
        return None
    take = _content_first(analysis, lead, items[k].atom, frozenset())
    if take.is_empty() or take.negated:
        return None
    exit_cs = _follow_content(
        analysis, lead, items[k + 1 :], _post_noise_follow(analysis, lead)[scope.rule]
    )
    return _scan_from(analysis, lead, take, exit_cs)


def _scan_from(
    analysis: Any, lead: frozenset[str], take: CharSet, exit_cs: CharSet
) -> "ScanGate | None":
    """Build the ``SG_SCAN`` gate for a skip-then-peek decision, escalating to
    ``SG_PROBE`` when the post-noise take and exit content leads overlap.

    Shared by the loop (:func:`_scan_or_probe_gate`) and arm
    (:func:`structured_arm_gate`) skip-then-peek paths: both reduce to a
    ``lead`` noise set, a ``take`` content lead and an ``exit_cs`` exit lead.
    """
    if take.overlaps(exit_cs):
        return _probe_gate(analysis, lead, take, exit_cs)
    rec = build_recognizer(analysis.rules, lead)
    if rec is None:
        return None
    return ScanGate(SG_SCAN, rec, _root_idxs(rec, lead), (take.chars, take.negated))


def _arm_nullable(analysis: Any, arm: Sequence[IrSelf]) -> bool:
    """Whether every item of an alternation arm can consume nothing (empty arm)."""
    return all(analysis.item_nullable(item) for item in _items(arm))


def structured_arm_gate(
    analysis: Any, arms: Sequence[Sequence[IrSelf]], label: str
) -> "ArmGate | None":
    """A folding-aware gate for an empty-arm alternation, or ``None``.

    Licensed for an alternation with a *single* empty/all-nullable escape arm
    whose gated (content) arms lead with skippable noise: skip that leading
    noise non-consuming and admit the gated arms on a disjoint post-noise
    content lead (``SG_SCAN``), escalating to ``SG_PROBE`` when the take/exit
    content overlap is explained by the next construct's header (GBNF ``rule``'s
    ``rulename n* "::="``, see :func:`_probe_gate`). The runtime selects the
    escape arm when the gate refuses; the gated arms then separate among
    themselves by their own FIRST sets.

    Denial (``None``) leaves the caller's greedy behavior — a gate must never
    silently pick a wrong arm. Inline-group arms never reach here: ``label`` is
    a rule name (the taxonomy store key), never a bracketed group tag.

    :param arms: The alternation's arms (item sequences), in body order.
    :param label: The enclosing rule name — the FOLLOW anchor and store key.
    :returns: The :class:`~lexic.parsing.pda.core.scanner.ArmGate` (scan gate + escape
        arm index), or ``None`` on a licence miss.
    """
    roots = noise_roots(analysis)
    if not roots or label not in analysis.rules:
        return None
    nullable = [i for i, arm in enumerate(arms) if _arm_nullable(analysis, arm)]
    if len(nullable) != 1:
        return None
    escape = nullable[0]
    gated = [_items(arm) for i, arm in enumerate(arms) if i != escape]
    if not gated:
        return None
    lead: frozenset[str] = frozenset()
    for arm in gated:
        lead |= _seq_leading_roots(analysis, roots, arm, frozenset())
    if not lead:
        return None
    take = CharSet.EMPTY
    for arm in gated:
        take = take.union(_seq_content(analysis, lead, arm, frozenset()))
    if take.is_empty() or take.negated:
        return None
    exit_cs = _post_noise_follow(analysis, lead)[label]
    scan = _scan_from(analysis, lead, take, exit_cs)
    return None if scan is None else ArmGate(scan, escape)


def _probe_gate(
    analysis: Any, lead: frozenset[str], take: CharSet, exit_cs: CharSet
) -> "ScanGate | None":
    """The P5 skip-then-probe gate (GBNF ``sequence[1]``), or ``None``.

    Licensed when the take/exit content overlap is exactly a next-construct
    *header*: some rule's arm reads ``ref(R) noise* lit(L) …`` (the "rulename …
    defined-as" shape) with the whole overlap inside ``FIRST(R)``, and ``L``'s
    lead char unable to follow an ``R`` occurrence anywhere else (the header
    occurrence itself excluded) — so a successful ``R noise* L`` match at the
    post-noise position *refutes the take reading* and the gate exits, while a
    failed match on an overlap char leaves the take side as the only
    header-free reading. Chars in neither content set exit (and fail soft
    downstream if they were junk). The candidate header must be unique
    grammar-wide, or the decision stays an island.
    """
    overlap = take.subtract(take.subtract(exit_cs))
    spec = _probe_candidate(analysis, lead, overlap)
    if spec is None:
        return None
    r_name, mid_root, lit = spec
    rec = build_recognizer(analysis.rules, lead | {r_name, mid_root})
    if rec is None:
        return None
    take_only = take.subtract(analysis.first[r_name])
    return ScanGate(
        SG_PROBE,
        rec,
        _root_idxs(rec, lead),
        (take_only.chars, take_only.negated),
        (rec.index[r_name], rec.index[mid_root], lit, False),
    )


def _probe_candidate(
    analysis: Any, lead: frozenset[str], overlap: CharSet
) -> tuple[str, str, str] | None:
    """The unique ``(R, noise root, L)`` header spec explaining ``overlap``.

    Scans every semantic rule's arms for the header shape
    (:func:`_header_shape`), keeps candidates whose name rule covers the whole
    overlap and whose probe literal passes the refutation licence
    (:func:`_post_noise_follow` with the header occurrence skipped), and
    demands exactly one distinct spec grammar-wide.
    """
    cands: set[tuple[str, str, str]] = set()
    for rule in analysis.rules.values():
        if not rule.semantic:
            continue
        for arm in rule.body:
            shape = _header_shape(analysis, _items(arm))
            if shape is None:
                continue
            head, r_name, mid_root, lit = shape
            if not overlap.subtract(analysis.first[r_name]).is_empty():
                continue
            pnf = _post_noise_follow(analysis, lead, skip=id(head))[r_name]
            if pnf.has(lit[0]):
                continue
            cands.add((r_name, mid_root, lit))
    if len(cands) != 1:
        return None
    return next(iter(cands))


def _header_shape(
    analysis: Any, arm_items: Sequence[IrItem]
) -> "tuple[IrItem, str, str, str] | None":
    """Match ``[ref R (1,1)] [same noise ref]+ [lit L] …`` at an arm's head.

    :returns: ``(head item, R, noise root, L)``, or ``None`` on any other
        shape. The middle items must all reference one non-semantic rule (the
        probe skips a maximal run of it between the name and the literal;
        at least one such item — a zero-noise header would make the probe's
        noise run over-permissive for nothing).
    """
    if not arm_items:
        return None
    head = arm_items[0]
    hi = head.quantifier.hi
    if (
        not isinstance(head.atom, IrRuleRef)
        or str(head.atom) not in analysis.rules
        or int(head.quantifier.lo) != 1
        or isinstance(hi, IrNoneType)
        or int(hi) != 1
    ):
        return None
    mid: str | None = None
    for item in arm_items[1:]:
        atom = item.atom
        if isinstance(atom, IrLiteral):
            if mid is None or not str(atom) or int(item.quantifier.lo) < 1:
                return None
            return (head, str(head.atom), mid, str(atom))
        name = str(atom) if isinstance(atom, IrRuleRef) else None
        target = analysis.rules.get(name) if name is not None else None
        if target is None or target.semantic or mid not in (None, name):
            return None
        mid = name
    return None
