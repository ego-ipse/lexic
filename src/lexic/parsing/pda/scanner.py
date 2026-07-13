"""Structured-noise recognizer — the folding-aware P3/P5 scanner substrate.

The 6.4 char-set P3 skips a maximal run of chars in a flat alphabet ``W``
(json whitespace). That cannot skip *comment-bearing* noise: GBNF ``#…\\n`` and
ABNF ``;…\\n`` have co-finite comment interiors no char set captures, and ABNF
LWS folding (``c-nl`` continues a run only when a ``wsp`` follows it) is a
2-char decision. Both spines therefore stayed islands under the char-set
scanner (``noise_alphabet`` is even *empty* for the self-grammars — their noise
rules are non-nullable).

This module compiles the flavour's own noise rules — read from the lifted
``IrAst`` it is handed, so the engine never imports :mod:`lexic.grammars` — into
a small **backtracking recognizer**: one flat rule per closure member, arms
tried in order with a full position reset on arm failure. That reset is what
makes folding fall out for free: ``c-wsp = wsp / (c-nl wsp)`` matched arm-in-order
rejects a bare ``c-nl`` not followed by ``wsp`` (its arm fails, and the ``wsp``
arm already failed), so ``(c-wsp)*`` stops exactly at the terminator — the exact
ABNF fold semantics, derived, never hardcoded.

Two runtime shapes ride the same recognizer:

- :func:`scan_run` — skip a maximal ``(root)*`` run *without consuming* (the P3
  peek's first half; the winning branch re-parses the noise, so the skip is
  recognition-only and fail-soft);
- :func:`scan_match` — whether one ``root`` instance matches at the cursor (the
  pure-folding loop gate, ABNF ``rule[5]``: take another ``c-wsp`` iff one is
  actually here).

A leaf w.r.t. the rest of :mod:`lexic.parsing.pda` — it imports only
:mod:`lexic.ir` and :mod:`~lexic.parsing.pda.charsets`, so ``noise`` (analysis
build) and ``flatten`` (runtime dispatch) both import it, never the reverse.
"""

from __future__ import annotations

from typing import Any, Mapping, NamedTuple

from lexic.ir.base import IrLeaf, IrNoneType, IrSelf
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
)
from lexic.ir.operators import IrNot
from lexic.parsing.pda.charsets import CharSet

__all__ = [
    "Recognizer",
    "ScanGate",
    "ArmGate",
    "SG_MATCH",
    "SG_SCAN",
    "SG_PROBE",
    "build_recognizer",
    "scan_run",
    "scan_run_any",
    "scan_match",
    "scan_gate_take",
]

SG_MATCH, SG_SCAN, SG_PROBE = 0, 1, 2
"""ScanGate kinds: recogniser-match loop (pure folding, ABNF ``rule[5]``);
skip-then-peek loop (P3 structured noise-skip); skip-then-probe loop (P5 —
the post-noise char is rulename-led in both branches, GBNF ``sequence[1]``)."""

_NA_CS, _NA_LIT, _NA_REF = 0, 1, 2
"""Flat noise-atom kinds: char-set membership, literal string, rule reference."""

_HI_UNBOUNDED = -1
"""The ``hi`` sentinel for an unbounded (``None``) quantifier upper bound."""


class Recognizer(IrLeaf[IrSelf, IrSelf]):
    """A flat backtracking recognizer over a closure of simple grammar rules.

    Immutable after :func:`build_recognizer`; shared across every parse.

    :ivar rules: Per-rule-index arms. Each rule is a tuple of arms; each arm a
        tuple of ``(kind, payload, lo, hi)`` item tuples — ``kind`` one of
        :data:`_NA_CS` / :data:`_NA_LIT` / :data:`_NA_REF`, ``payload`` a
        ``(chars, negated)`` pair (CS), a ``str`` (LIT), or a rule index (REF);
        ``hi`` is :data:`_HI_UNBOUNDED` for an unbounded loop.
    :ivar index: Rule name → its index in :attr:`rules`.
    """

    __slots__ = ("rules", "index")

    rules: tuple[tuple[tuple[tuple[int, Any, int, int], ...], ...], ...]
    index: dict[str, int]

    def __init__(
        self,
        rules: tuple[tuple[tuple[tuple[int, Any, int, int], ...], ...], ...],
        index: dict[str, int],
    ) -> None:
        """Bind the flat rule table and the name→index map."""
        self.rules = rules
        self.index = index


def _hi(item: IrItem) -> int:
    """The item's upper bound as an int, :data:`_HI_UNBOUNDED` for unbounded."""
    hi = item.quantifier.hi
    return _HI_UNBOUNDED if isinstance(hi, IrNoneType) else int(hi)


def _compile_item(
    item: IrItem, index: Mapping[str, int]
) -> "tuple[int, Any, int, int] | None":
    """Lower one item to its flat ``(kind, payload, lo, hi)`` tuple, or ``None``.

    ``None`` when the atom is not a simple recognizer construct (an inline group,
    an ``IrNot`` over a non-class, or a ref outside the compiled closure) — the
    caller then opts the whole recognizer out.
    """
    atom = item.atom
    lo = int(item.quantifier.lo)
    hi = _hi(item)
    if isinstance(atom, IrLiteral):
        return (_NA_LIT, str(atom), lo, hi)
    if isinstance(atom, IrCharClass):
        cs = CharSet.from_charclass(atom)
        return (_NA_CS, (cs.chars, cs.negated), lo, hi)
    if isinstance(atom, IrNot):
        inner = atom[0]
        if not isinstance(inner, IrCharClass):
            return None
        cs = CharSet.from_not(inner)
        return (_NA_CS, (cs.chars, cs.negated), lo, hi)
    if isinstance(atom, IrRuleRef):
        idx = index.get(str(atom))
        return None if idx is None else (_NA_REF, idx, lo, hi)
    return None


def _closure(rules: Mapping[str, IrRule], roots: frozenset[str]) -> "list[str] | None":
    """The acyclic rule closure reachable from ``roots``, or ``None``.

    ``None`` when a reference leaves ``rules`` (undefined), an inline group is
    reached (not a simple recognizer), or the closure is cyclic (a recursive
    recognizer could loop without consuming — opt out). Grey/black DFS: a name
    seen on the current stack is a back edge.
    """
    grey: set[str] = set()
    done: set[str] = set()
    order: list[str] = []

    def visit(name: str) -> bool:
        if name in done:
            return True
        if name in grey or name not in rules:
            return False
        grey.add(name)
        for arm in rules[name].body:
            for item in arm:
                if not isinstance(item, IrItem):
                    continue
                atom = item.atom
                if isinstance(atom, IrAlternation):
                    return False
                if isinstance(atom, IrRuleRef) and not visit(str(atom)):
                    return False
        grey.discard(name)
        done.add(name)
        order.append(name)
        return True

    return order if all(visit(r) for r in roots) else None


def build_recognizer(
    rules: Mapping[str, IrRule], roots: frozenset[str]
) -> "Recognizer | None":
    """Compile the acyclic closure of ``roots`` into a flat :class:`Recognizer`.

    :param rules: The lifted grammar's rule table (name → :class:`IrRule`).
    :param roots: The recognizer's entry rule names (noise roots, or a probe's
        discriminator rules).
    :returns: The recognizer, or ``None`` when any closure member is not a simple
        greedy-recognizable rule (the decision then stays an island).
    """
    order = _closure(rules, roots)
    if order is None:
        return None
    index = {name: i for i, name in enumerate(order)}
    flat: list[tuple[tuple[tuple[int, Any, int, int], ...], ...]] = []
    for name in order:
        arms: list[tuple[tuple[int, Any, int, int], ...]] = []
        for arm in rules[name].body:
            items: list[tuple[int, Any, int, int]] = []
            for item in arm:
                if not isinstance(item, IrItem):
                    continue
                compiled = _compile_item(item, index)
                if compiled is None:
                    return None
                items.append(compiled)
            arms.append(tuple(items))
        flat.append(tuple(arms))
    return Recognizer(tuple(flat), index)


def _match_atom(text: str, pos: int, rec: Recognizer, kind: int, payload: Any) -> int:
    """Match one atom at ``pos``; return the new position or ``-1`` on a miss."""
    if kind == _NA_CS:
        ch = text[pos : pos + 1]
        chars, negated = payload
        member = (ch != "" and ch not in chars) if negated else (ch in chars)
        return pos + 1 if member else -1
    if kind == _NA_LIT:
        return pos + len(payload) if text.startswith(payload, pos) else -1
    return _match_rule(text, pos, rec, payload)


def _match_seq(text: str, pos: int, rec: Recognizer, arm: Any) -> int:
    """Match an arm's items in order (greedy per item); ``-1`` on failure."""
    for kind, payload, lo, hi in arm:
        count = 0
        while count < lo:
            nxt = _match_atom(text, pos, rec, kind, payload)
            if nxt < 0:
                return -1
            pos = nxt
            count += 1
        while hi == _HI_UNBOUNDED or count < hi:
            nxt = _match_atom(text, pos, rec, kind, payload)
            if nxt < 0 or nxt == pos:
                break
            pos = nxt
            count += 1
    return pos


def _match_rule(text: str, pos: int, rec: Recognizer, ridx: int) -> int:
    """Match one instance of rule ``ridx`` (arms in order); ``-1`` on failure."""
    for arm in rec.rules[ridx]:
        end = _match_seq(text, pos, rec, arm)
        if end >= 0:
            return end
    return -1


def scan_run(text: str, pos: int, rec: Recognizer, ridx: int) -> int:
    """Skip a maximal ``(rule ridx)*`` run at ``pos`` (non-consuming peek).

    Repeatedly matches the root rule, advancing past each instance, until it
    fails or makes no progress (a nullable root). The caller inspects the char
    at the returned position without moving the real cursor.
    """
    while True:
        end = _match_rule(text, pos, rec, ridx)
        if end < 0 or end == pos:
            return pos
        pos = end


def scan_run_any(text: str, pos: int, rec: Recognizer, roots: tuple[int, ...]) -> int:
    """Skip a maximal run at ``pos`` where each step matches *any* root in ``roots``.

    A loop body's leading noise can be a short sequence of distinct noise roots
    (the factored ABNF ``rl-cont = c-nl filler* rule`` leads with ``c-nl`` then
    ``filler*``); skipping the union of the noise roots lands exactly on the
    first content char on valid input. Longest match wins at each step, so the
    fold-aware roots keep their arm-in-order semantics.
    """
    while True:
        best = pos
        for ridx in roots:
            best = max(best, _match_rule(text, pos, rec, ridx))
        if best == pos:
            return pos
        pos = best


def scan_match(text: str, pos: int, rec: Recognizer, ridx: int) -> bool:
    """Whether one instance of rule ``ridx`` matches (and consumes) at ``pos``.

    The pure-folding loop gate (ABNF ``rule[5]``): take another ``c-wsp`` iff a
    ``c-wsp`` actually begins here — the recognizer's arm-in-order fold decides.
    """
    end = _match_rule(text, pos, rec, ridx)
    return end > pos


class ScanGate(NamedTuple):
    """A folding-aware structured-noise loop gate (P3 structured / P5 probe).

    The analysis-sourced spec the clone compiler stores and the runtime consults
    via :func:`scan_gate_take`; the loop iteration then re-parses the noise
    normally, so the gate is recognition-only and fail-soft.

    :ivar kind: :data:`SG_MATCH` / :data:`SG_SCAN` / :data:`SG_PROBE`.
    :ivar rec: The recogniser (noise closure, plus a probe's discriminator rules).
    :ivar roots: The noise-root indices skipped before the decision (``SG_MATCH``
        carries the single loop-body noise root).
    :ivar take: ``(chars, negated)`` post-noise take-set (``SG_SCAN``/``SG_PROBE``),
        or ``None``.
    :ivar probe: ``(name_idx, noise_idx, defined_literal, take_on_match)`` for
        ``SG_PROBE`` — after the take-set peek misses on an overlap char, match
        ``rulename`` then a noise run then ``defined_literal``; ``take_on_match``
        is the loop polarity (GBNF ``sequence`` exits on a matched rule header).
    """

    kind: int
    rec: Recognizer
    roots: tuple[int, ...]
    take: tuple[frozenset[str], bool] | None = None
    probe: tuple[int, int, str, bool] | None = None


class ArmGate(NamedTuple):
    """A structured arm-selection gate — a scan gate plus the escape arm index.

    The analysis-sourced spec for an alternation with a single empty/all-nullable
    escape arm whose gated (content) arms lead with skippable noise. The runtime
    consults :attr:`gate` via :func:`scan_gate_take`: a ``True`` admits the gated
    arms (whose FIRST sets then separate them), a ``False`` selects the escape
    arm at :attr:`escape`.

    :ivar gate: The folding-aware :class:`ScanGate` (``SG_SCAN`` / ``SG_PROBE``).
    :ivar escape: The nullable escape arm's index in the rule body.
    """

    gate: ScanGate
    escape: int


def _peek_member(text: str, pos: int, take: tuple[frozenset[str], bool]) -> bool:
    """Whether the char at ``pos`` is in the ``(chars, negated)`` take-set."""
    ch = text[pos : pos + 1]
    chars, negated = take
    return (ch != "" and ch not in chars) if negated else ch in chars


def scan_gate_take(text: str, pos: int, gate: ScanGate) -> bool:
    """Whether the structured-noise loop gate admits another iteration at ``pos``.

    ``SG_MATCH`` takes iff a noise-root instance begins here (folding);
    ``SG_SCAN`` skips the maximal noise run then tests the post-noise char
    against ``take``; ``SG_PROBE`` does the same, and on an overlap char runs the
    ``rulename … defined`` probe to break the tie.
    """
    if gate.kind == SG_MATCH:
        return scan_match(text, pos, gate.rec, gate.roots[0])
    p = scan_run_any(text, pos, gate.rec, gate.roots)
    if gate.take is not None and _peek_member(text, p, gate.take):
        return True
    if gate.kind == SG_SCAN or gate.probe is None:
        return False
    name_idx, noise_idx, defined, take_on_match = gate.probe
    ch = text[p : p + 1]
    name_lead = _match_rule(text, p, gate.rec, name_idx)
    if name_lead < 0 or ch == "":
        return False  # not a rulename-led overlap char — plain exit
    after = scan_run(text, name_lead, gate.rec, noise_idx)
    matched = text.startswith(defined, after)
    return take_on_match if matched else not take_on_match
