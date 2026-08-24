"""The split plan — one grammar's cut shape, reused across documents.

What a split parse settles ONCE per grammar and then reuses per document. It
lives beside the shape analyses that produce it rather than in the orchestrator
that consumes it: the envelope reader, the routed-region derivation and this
record answer the same question at different depths, and the orchestrator's job
is to run whichever one a grammar admits.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrAst, IrCharClass, IrItem, IrLiteral, IrRule, IrRuleRef, IrSelf
from lexic.parsing.parallel.discovery.scan import Scanner
from lexic.parsing.parallel.plan.envelope import EnvelopePlan
from lexic.parsing.parallel.roles import Separator
from lexic.parsing.parallel.stitch.safety import Boundary
from lexic.parsing.pda.core.charsets import CharSet


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
    :ivar mark: The spellings cuts key on. One for most grammars; two
        characters where the boundary is a blank line or a doubled anchor; a
        whole SET where the unit's arms close differently and every one of
        their closing characters bounds a unit.
    :ivar owner: The repeated unit that must exclude the mark; empty for a
        terminated plan whose mark belongs to the unit itself.
    :ivar wrappers: Single-reference rules between the grammar start and the
        repeated container; empty when the container is the start rule.
    :ivar sep: The separator record, or ``None`` for a terminated plan.
    :ivar lead_grammar: The grammar rooted at the lead rule; ``None`` for a
        terminated plan or a bare-literal lead.
    :ivar lead_literal: The bare-literal lead text (else ``""``).
    :ivar skip: Characters the cut extends over after the mark.
    :ivar envelope: The certified envelope plan, when the container wraps its
        repetition in optional head and tail items and the separator is a noise
        run rather than one character; ``None`` for every other shape.
    :ivar opening: Whether the mark OPENS a unit rather than closing one. A
        cut then lands ON the occurrence instead of after it, and the
        occurrence is a PROPOSAL the piece parse verifies rather than a
        boundary a proof established.
    :ivar trailing: Whether an overlapping run of the mark's characters holds
        its boundary at the LAST occurrence rather than the first. Only a
        spelling that is its own border can overlap; every one-character mark
        leaves this ``False`` and every run a singleton.
    :ivar bound: The certified announcing prefix, when a TERMINATED plan is
        licensed by the boundary proof rather than by terminates-once. The unit
        then emits its own mark (continuation lines), so not every mark is a
        boundary: candidates are filtered by the same admission the envelope
        path runs. ``None`` when the unit's mark is its own final edge, where
        every mark IS a boundary and no filter is needed.
    """

    grammar: IrAst
    scanner: Scanner
    mark: frozenset[str]
    owner: str
    wrappers: tuple[str, ...]
    sep: Separator | None
    lead_grammar: IrAst | None
    lead_literal: str
    skip: frozenset[str]
    envelope: EnvelopePlan | None = None
    opening: bool = False
    trailing: bool = False
    bound: Boundary | None = None

    @property
    def terminated(self) -> bool:
        """Whether cuts land after a unit's own final character.

        A terminated unit OWNS its mark, so its chunk keeps it and there is no
        separator to re-parse. Both other shapes hand the mark back: a
        separated cut hands one character, an envelope cut a whole noise run.
        """
        return self.sep is None and self.envelope is None


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


def lead_skip(
    items: tuple[IrItem, ...] | None, rule_map: dict[str, IrRule], mark: str
) -> frozenset[str]:
    """The chars a lead rule may consume AFTER its separator mark.

    Only what the lead itself derives (``comma ::= "," ws`` → the ws charset)
    — the cut extends over exactly this noise, so the chunk starts where the
    unit starts. Over- or under-collection is safe: a lead or chunk that then
    fails to parse makes the whole attempt fall back.

    :param items: The lead rule's only arm, or ``None`` when it has more.
    :param rule_map: The grammar's rules by name.
    :param mark: The separator spelling, which the skip never re-consumes.
    """
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
    return frozenset(out) - set(mark)


def matched(text: str, at: int, marks: frozenset[str]) -> str:
    """The mark standing at ``at``, longest first, or ``""`` when none does.

    Longest first for the same reason a region's skip table orders its
    openings that way: a two-character spelling whose first character is also
    a mark must read as the wider one, or the cut lands mid-spelling.
    """
    for mark in sorted(marks, key=len, reverse=True):
        if text.startswith(mark, at):
            return mark
    return ""
