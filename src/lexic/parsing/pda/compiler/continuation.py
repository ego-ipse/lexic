"""What may follow an island REFERENCE, and whether that bounds the island.

Two questions the clone compiler asks once per island and carries on the
:class:`~lexic.parsing.pda.compiler.specs.IslandRef` it emits. Both are about
the island's *occurrence* — what the enclosing grammar puts after it — and
neither is answerable from the island rule's own FOLLOW, which is what made
them worth a module of their own rather than two more methods on a compiler
that already has enough.

The seam reads the first to decide whether a shorter completion could compose
with the caller (:mod:`lexic.parsing.pda.runtime.islands`), and the second to
decide whether one sub-parse at an exact width settles the island instead of a
doubling climb.
"""

from __future__ import annotations

from lexic.ir import IrRuleRef
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.predicates import rule_alphabets
from lexic.parsing.pda.compiler.specs import arm_items
from lexic.parsing.pda.core.charsets import CharSet


class IslandContinuations:
    """One grammar's island continuations, derived once and memoised.

    :ivar analysis: The grammar analysis the sets are derived from.
    :ivar islands: The island rule names — the rules whose own arms are never
        reference sites, because an island is never cloned.
    """

    __slots__ = ("analysis", "islands", "_follows", "_alphabets")

    analysis: GrammarAnalysis
    islands: frozenset[str]
    _follows: dict[str, CharSet]
    _alphabets: dict[str, CharSet] | None

    def __init__(self, analysis: GrammarAnalysis, islands: frozenset[str]) -> None:
        """Bind the analysis and island set; derive nothing until asked."""
        self.analysis = analysis
        self.islands = islands
        self._follows = {}
        self._alphabets = None

    def follow(self, name: str) -> CharSet:
        """What may follow island ``name`` where it is REFERENCED, unioned.

        The seam's two-ends evidence. It is deliberately not the island rule's
        own FOLLOW, and deliberately not one site's continuation either.

        *Not the rule's FOLLOW*, because the fixpoint walks the island's own
        arms too: ``expr ::= expr op term`` puts ``op``'s FIRST into
        FOLLOW(``expr``) purely because the rule places ``expr`` before ``op``.
        A shorter end followed by ``+`` is then the island CONTINUING ITSELF,
        which longest-match absorbs under the same arm — not the caller
        accepting it. Reading the rule's FOLLOW made every left-recursive
        island with an infix operator refuse by construction, on its first
        completion, every time.

        *Not one site's continuation*, because the caller may reach the island
        through more than one arm and the PDA commits to an arm BEFORE
        entering. With ``root ::= expr "+" term nl | expr nl`` the two sites
        see ``{'+'}`` and ``{'\\n'}``; ``a+b\\n`` derives both ways and means
        two different things. Asking only the entered site's set answers it
        silently. The union asks whether the shorter end could compose with
        ANY way back into the caller, which is the question.

        The island's own arms contribute nothing because an island rule is
        never cloned — its internal recursion is resolved inside the Earley
        sub-parse and never reaches a reference site here.

        :param name: The island rule name.
        :returns: The union over external reference sites; empty when the
            island is referenced from nowhere (the start rule itself), which
            carries no evidence and accepts plain longest-match.
        """
        cached = self._follows.get(name)
        if cached is not None:
            return cached
        analysis = self.analysis
        found = CharSet.EMPTY
        for rule, body in analysis.rules.items():
            if rule in self.islands:
                continue  # an island's own arms are never entry sites
            for arm in body.body:
                items = arm_items(arm)
                for at, item in enumerate(items):
                    atom = item.atom
                    if isinstance(atom, IrRuleRef) and str(atom) == name:
                        found = found.union(
                            analysis.cont_at(items, at, analysis.follow[rule])
                        )
        self._follows[name] = found
        return found

    def bounds(self, name: str, cont: CharSet) -> bool:
        """Can island ``name``'s extent be read off one linear scan for ``cont``?

        When the island can derive no character of its own continuation, no
        completion of it reaches past the first continuation character after
        the cursor: the island would have to consume that character to get
        there, and it cannot. So the extent is bounded by that position, the
        window is exactly that wide, and ONE sub-parse at that width settles
        the island — no 256-character floor, no doubling, no re-parse of the
        same characters at five widths.

        This does not weaken the two-ends refusal. A completion end BEFORE the
        bound is exactly the case that refusal already handles, and it is
        handled inside this window as it was inside a climbing one; the bound
        only removes ends that could not exist.

        An island whose alphabet MEETS its continuation keeps the climb — a
        string literal that can hold its own terminator is the shape, and
        there the first continuation character says nothing about the extent.

        :param name: The island rule name.
        :param cont: The occurrence continuation from :meth:`follow`.
        :returns: ``True`` when the scan is a sound bound.
        """
        if cont.is_empty() or cont.negated:
            return False  # nothing to scan for, or a set no scan enumerates
        if self._alphabets is None:
            self._alphabets = rule_alphabets(self.analysis.rules)
        held = self._alphabets.get(name)
        return held is not None and not held.overlaps(cont)
