"""The split plan — one grammar's cut shape, reused across documents.

What a split parse settles ONCE per grammar and then reuses per document. It
lives beside the shape analyses that produce it rather than in the orchestrator
that consumes it: the envelope reader, the routed-region derivation and this
record answer the same question at different depths, and the orchestrator's job
is to run whichever one a grammar admits.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrAst
from lexic.parsing.parallel.discovery.scan import Scanner
from lexic.parsing.parallel.plan.envelope import EnvelopePlan
from lexic.parsing.parallel.roles import Separator


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
    """

    grammar: IrAst
    scanner: Scanner
    mark: str
    owner: str
    wrappers: tuple[str, ...]
    sep: Separator | None
    lead_grammar: IrAst | None
    lead_literal: str
    skip: frozenset[str]
    envelope: EnvelopePlan | None = None

    @property
    def terminated(self) -> bool:
        """Whether cuts land after a unit's own final character.

        A terminated unit OWNS its mark, so its chunk keeps it and there is no
        separator to re-parse. Both other shapes hand the mark back: a
        separated cut hands one character, an envelope cut a whole noise run.
        """
        return self.sep is None and self.envelope is None
