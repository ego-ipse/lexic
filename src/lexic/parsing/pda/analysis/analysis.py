"""Grammar analysis + decision taxonomy — the PDA compiler's oracle.

:class:`GrammarAnalysis`, over a *lifted codegen grammar*, runs the predictive
fixpoints (nullability, FIRST/hard-FIRST, FOLLOW/hard-FOLLOW, LL(2) prefixes) and
classifies each decision ``island`` / ``stopset`` / ``("pairs", set)`` into
:attr:`conflicts` / :attr:`demoted` / :attr:`fail_islands`, via an open dispatch
raising :exc:`~lexic.exceptions.UnsupportedConstructError` on an unknown atom.
"""

from __future__ import annotations

__all__ = ["AttemptSpec", "GrammarAnalysis", "Taxonomy", "nullable_names"]


from typing import Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAst,
    IrAtom,
    IrItem,
    IrLeaf,
    IrNoneType,
    IrRule,
    IrRuleRef,
    IrSelf,
)
from lexic.parsing.pda.analysis.conflicts import (
    attempt_group,
    attempt_spec,
    soft_gap_conflict,
    sub_conflict,
)
from lexic.parsing.pda.analysis.cursors import (
    Cont,
    FeedCtx,
    FollowPass,
    Notes,
    Scope,
    Site,
)
from lexic.parsing.pda.analysis.gates import kwindow
from lexic.parsing.pda.analysis.gates.leftrec import left_recursive_names
from lexic.parsing.pda.analysis.gates.noise import (
    noise_alphabet,
    noise_greedy_licensed,
    peek_arm_gate,
    peek_loop_gate,
    stopset_escapes_soft_follow,
)
from lexic.parsing.pda.analysis.gates.structured import (
    structured_arm_gate,
    structured_loop_gate,
)
from lexic.parsing.pda.analysis.gates.windows import END, MORE, UNK, KWindowFirst
from lexic.parsing.pda.analysis.predicates import (
    FIRST,
    FOLLOW_FEED,
    HARD,
    NULLABLE,
    STOPSET_ATOM,
    item_nullable,
    nullable_names,
    seq_nullable,
)
from lexic.parsing.pda.analysis.taxonomy import AttemptSpec, Taxonomy
from lexic.parsing.pda.core.charsets import CharSet

_EOF: CharSet = CharSet.from_chars("")
"""The FOLLOW-set seed for the start rule: the empty-string end-of-input
sentinel in a positive :class:`CharSet`."""


def _items(seq: Sequence[IrSelf]) -> list[IrItem]:
    """The :class:`IrItem` members of a sequence arm, in order (others skipped)."""
    return [i for i in seq if isinstance(i, IrItem)]


def _hi(item: IrItem) -> int | None:
    """The item's quantifier upper bound as an ``int``, or ``None`` (unbounded)."""
    hi = item.quantifier.hi
    return None if isinstance(hi, IrNoneType) else int(hi)


# ── the analysis ──────────────────────────────────────────────────────────


# Taxonomy (and its _GateStore) moved to lexic.parsing.pda.analysis.taxonomy by pure
# motion (C0302 headroom, Task 6.6); re-exported above for the public surface.


class GrammarAnalysis(IrLeaf[IrSelf, IrSelf]):
    """FIRST/hard-FIRST/FOLLOW/nullability + per-rule conflict classification.

    Constructed over a lifted codegen grammar; all fixpoints run in
    ``__init__`` and the results live on the instance. The analysis IS the
    dispatcher slot ``d`` handed to every atom-type table body — its
    :attr:`first` / :attr:`hard` / :attr:`follow` / :attr:`nullable` state and
    ``seq_*`` helpers are read straight off ``d``.
    """

    __slots__ = (
        "rules",
        "start",
        "nullable",
        "first",
        "hard",
        "_follows",
        "taxonomy",
    )

    rules: dict[str, IrRule]
    start: str
    nullable: frozenset[str]
    first: dict[str, CharSet]
    hard: dict[str, CharSet]
    _follows: tuple[dict[str, CharSet], dict[str, CharSet], dict[str, CharSet]]
    taxonomy: Taxonomy

    def __init__(self, grammar: IrAst) -> None:
        """Run every fixpoint and classify every rule of the lifted grammar."""
        self.rules = {str(r.name): r for r in grammar.rules}
        self.start = str(grammar.start)
        self.nullable = nullable_names(list(grammar.rules))
        self.first = self._first_sets()
        self.hard = self._hard_sets()
        self._follows = (
            self._follow_fixpoint(hard=False, loopback=True, nullable_first=True),
            self._follow_fixpoint(hard=True, loopback=False, nullable_first=False),
            self._follow_fixpoint(hard=False, loopback=False, nullable_first=True),
        )
        self.taxonomy = Taxonomy()
        self._classify()

    @property
    def follow(self) -> dict[str, CharSet]:
        """Rule name → its (soft) FOLLOW :class:`CharSet`."""
        return self._follows[0]

    @property
    def hard_follow(self) -> dict[str, CharSet]:
        """Rule name → its hard FOLLOW :class:`CharSet` (nullable followers skipped)."""
        return self._follows[1]

    @property
    def _structural_follow(self) -> dict[str, CharSet]:
        """Rule name → soft FOLLOW with generated repeat loopback omitted."""
        return self._follows[2]

    @property
    def conflicts(self) -> dict[str, list[str]]:
        """Rule name → island-worthy conflict notes (presence marks an island)."""
        return self.taxonomy.conflicts

    @property
    def demoted(self) -> dict[str, list[str]]:
        """Rule name → stop-set / LL(2) demotion notes."""
        return self.taxonomy.demoted

    @property
    def islands(self) -> frozenset[str]:
        """The island rule set — the names keying :attr:`conflicts`."""
        return frozenset(self.taxonomy.conflicts)

    @property
    def fail_islands(self) -> frozenset[str]:
        """Semantic F1 stop-set-escape rules — a reference must raise ``PdaFail``
        (engine fallback), not parse via longest-match. A subset of
        :attr:`islands`."""
        return frozenset(self.taxonomy.fail)

    # ── nullability queries ────────────────────────────────────────────

    def atom_nullable(self, atom: IrAtom) -> bool:
        """Whether ``atom`` can consume nothing under the final nullable set.

        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        return cast(bool, NULLABLE.resolve(atom).eval(self, atom, ()))

    def item_nullable(self, item: IrItem) -> bool:
        """Whether ``item`` can consume nothing (``lo == 0`` or nullable atom)."""
        return item_nullable(self, item)

    # ── FIRST ──────────────────────────────────────────────────────────

    def atom_first(self, atom: IrAtom) -> CharSet:
        """FIRST set of a single atom.

        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        return cast(CharSet, FIRST.resolve(atom).eval(self, atom, ()))

    def seq_first(self, items: Sequence[IrItem]) -> CharSet:
        """FIRST set of an item sequence — union until the first non-nullable."""
        out = CharSet.EMPTY
        for item in items:
            out = out.union(self.atom_first(item.atom))
            if not self.item_nullable(item):
                break
        return out

    def _first_sets(self) -> dict[str, CharSet]:
        """The per-rule FIRST fixpoint (chaotic iteration to stability)."""
        self.first = {name: CharSet.EMPTY for name in self.rules}
        changed = True
        while changed:
            changed = False
            for name, rule in self.rules.items():
                acc = CharSet.EMPTY
                for arm in rule.body:
                    acc = acc.union(self.seq_first(_items(arm)))
                if acc != self.first[name]:
                    self.first[name] = acc
                    changed = True
        return self.first

    # ── hard-FIRST ─────────────────────────────────────────────────────

    def atom_hard(self, atom: IrAtom) -> CharSet:
        """hard-FIRST set of a single atom (nullable prefixes contribute nothing).

        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        return cast(CharSet, HARD.resolve(atom).eval(self, atom, ()))

    def seq_hard(self, items: Sequence[IrItem]) -> CharSet:
        """hard-FIRST of a sequence — the first non-nullable item's hard-FIRST."""
        for item in items:
            if self.item_nullable(item):
                continue
            return self.atom_hard(item.atom)
        return CharSet.EMPTY

    def hard_cont_at(
        self, items: Sequence[IrItem], k: int, hard_tail: CharSet
    ) -> CharSet:
        """hard continuation after item ``k``: the next required chars, else tail.

        :param hard_tail: The rule's hard continuation (for an all-nullable rest).
        """
        for item in items[k + 1 :]:
            if self.item_nullable(item):
                continue
            return self.atom_hard(item.atom)
        return hard_tail

    def structural_cont_at(
        self, items: Sequence[IrItem], k: int, tail: CharSet
    ) -> CharSet:
        """Structural continuation after item ``k``.

        A nullable, once-only follower is authored optional structure, so its
        FIRST remains visible. FIRST for a repeated nullable follower is the
        generated take-another-copy edge and is omitted; the tail beyond it
        remains visible.
        """
        cont = CharSet.EMPTY
        for item in items[k + 1 :]:
            first = self.atom_first(item.atom)
            if not self.item_nullable(item):
                return cont.union(first)
            hi = _hi(item)
            if hi is not None and hi <= 1:
                cont = cont.union(first)
            else:
                continue
        return cont.union(tail)

    def _hard_sets(self) -> dict[str, CharSet]:
        """The per-rule hard-FIRST fixpoint."""
        self.hard = {name: CharSet.EMPTY for name in self.rules}
        changed = True
        while changed:
            changed = False
            for name, rule in self.rules.items():
                acc = CharSet.EMPTY
                for arm in rule.body:
                    acc = acc.union(self.seq_hard(_items(arm)))
                if acc != self.hard[name]:
                    self.hard[name] = acc
                    changed = True
        return self.hard

    # ── loop policy (the pivot-6 taxonomy) ─────────────────────────────

    def loop_policy(
        self, item: IrItem, rest: Sequence[IrItem]
    ) -> tuple[str, frozenset[str]] | str:
        """Classify a looping item whose FIRST overlaps its hard continuation.

        :returns: ``("pairs", set)`` for an LL(2) gate, ``"stopset"`` for a
            non-greedy single-char loop, or ``"island"`` otherwise.
        """
        atom = item.atom
        lo = int(item.quantifier.lo)
        hi = _hi(item)
        if lo == 0 and hi == 1:
            taken = kwindow.atom_two_prefix(self, atom)
            skip = kwindow.two_prefix_seq(self, list(rest))
            if taken is not None and skip is not None and not taken & skip:
                return ("pairs", taken)
        if hi is None and self._stopset_eligible(atom):
            return "stopset"
        return "island"

    def _stopset_eligible(self, atom: IrAtom) -> bool:
        """Whether ``atom`` is a single-char loop atom (char class / negation)."""
        return cast(bool, STOPSET_ATOM.resolve(atom).eval(self, atom, ()))

    def _store_loop_gate(
        self, item: IrItem, spec: tuple[tuple[CharSet, ...], ...]
    ) -> None:
        """File a demoted loop's ``taken`` windows under the item node's identity.

        :raises UnsupportedConstructError: If the same node already carries a
            *different* spec — a shared node at two decision sites with distinct
            FOLLOWs, which the identity key cannot express (a confident-wrong
            gate would be silent, so the whole grammar opts out instead).
        """
        key = id(item)
        prior = self.taxonomy.loop_gates.get(key)
        if prior is not None and prior != spec:
            raise UnsupportedConstructError(
                "pda analysis: conflicting k-window loop gates for one item node"
            )
        self.taxonomy.loop_gates[key] = spec

    def _demote_arms(
        self,
        arms: list[Sequence[IrItem]],
        site: Site,
        notes: Notes,
    ) -> bool:
        """The arm-overlap demotion cascade — P2 k-window, then the P3
        noise-skip peek — storing the winning gate spec in its taxonomy
        channel plus the soft note. ``False`` ⇒ the overlap stays hard.

        Serves a rule body and an inline group alike: the cascade reads only
        the arms and the continuation, so ``site`` is the only thing that
        differs between them.
        """
        gate = kwindow.arm_gate(self.rules, arms, site.follow)
        if gate is not None:
            self.taxonomy.store_arm_windows(
                site.at, tuple(kwindow.windows_of(s) for s in gate[1])
            )
            notes.soft.append(f"{site.label}: arms k-window separable (demoted)")
            return True
        w = noise_alphabet(self)
        peek = peek_arm_gate(self, arms, w)
        if peek is not None:
            self.taxonomy.store_arm_peek(site.at, (w, peek))
            notes.soft.append(f"{site.label}: arms noise-skip separable (demoted)")
            return True
        return False

    def _demote_follow_windows(
        self, arms: Sequence[Sequence[IrItem]], label: str, notes: Notes
    ) -> bool:
        """Empty-arm FOLLOW\\ :sub:`k` demotion via :func:`kwindow.follow_arm_gate`:
        store the separating per-arm windows (body-arm order) in
        :attr:`Taxonomy.arm_gates` + the soft note; ``False`` ⇒ no licence."""
        gate = kwindow.follow_arm_gate(self.rules, self.start, arms, label)
        if gate is None:
            return False
        self.taxonomy.arm_gates[label] = gate
        notes.soft.append(f"{label}: arms FOLLOW-window separable (demoted)")
        return True

    def _demote_struct_arm(
        self, arms: Sequence[Sequence[IrItem]], label: str, notes: Notes
    ) -> bool:
        """The empty-arm structured-noise demotion: store the scan gate + escape
        arm index in its taxonomy channel plus the soft note. ``False`` ⇒ no
        licence (the caller keeps today's greedy behavior)."""
        gate = structured_arm_gate(self, list(arms), label)
        if gate is None:
            return False
        self.taxonomy.store_struct_arm(label, gate)
        notes.soft.append(f"{label}: empty-arm structured-noise (demoted)")
        return True

    def _demote_loop(
        self, items: Sequence[IrItem], k: int, scope: Scope, notes: Notes
    ) -> bool:
        """The loop take/skip demotion cascade — P2 k-window, then the P3
        noise-skip peek — storing the spec under the item node's identity plus
        the soft note. ``False`` ⇒ the decision stays an island note."""
        gate = kwindow.loop_gate(self.rules, items, k, scope.tail)
        if gate is not None:
            self._store_loop_gate(items[k], kwindow.windows_of(gate[1]))
            notes.soft.append(f"{scope.rule}[{k}]: loop k-window (demoted)")
            return True
        w = noise_alphabet(self)
        take = peek_loop_gate(self, items, k, self.cont_at(items, k, scope.tail), w)
        if take is not None:
            key = id(items[k])
            prior = self.taxonomy.pn_loop_gates.get(key)
            if prior is not None and prior != (w, take):
                raise UnsupportedConstructError(
                    "pda analysis: conflicting noise-skip loop gates for one item node"
                )
            self.taxonomy.pn_loop_gates[key] = (w, take)
            notes.soft.append(f"{scope.rule}[{k}]: loop noise-skip (demoted)")
            return True
        struct = structured_loop_gate(self, items, k, scope)
        if struct is not None:
            self.taxonomy.store_struct_loop(id(items[k]), struct)
            notes.soft.append(f"{scope.rule}[{k}]: loop structured-noise (demoted)")
            return True
        return False

    # ── FOLLOW ─────────────────────────────────────────────────────────

    def _follow_fixpoint(
        self, hard: bool, loopback: bool, nullable_first: bool
    ) -> dict[str, CharSet]:
        """A per-rule FOLLOW fixpoint (EOF-seeded at the start rule).

        :param hard: When ``True``, compute *hard* FOLLOW — nullable followers
            skipped (the union of the HARD continuations every reference site
            cuts its PDA clone against); when ``False``, the classical soft FOLLOW.
        :param loopback: Whether repeated-item FIRST contributes. Disabling it
            on a soft pass preserves authored/nullable continuation while
            excluding split-only repeat edges.
        :param nullable_first: Whether nullable-follower FIRST contributes. The
            structural pass retains once-only optional followers and omits
            repeated nullable followers.
        """
        tgt = {name: CharSet.EMPTY for name in self.rules}
        tgt[self.start] = _EOF
        pass_ = FollowPass(tgt, hard, loopback, nullable_first)
        changed = True
        while changed:
            changed = False
            for name, rule in self.rules.items():
                for arm in rule.body:
                    if self.feed_seq(_items(arm), tgt[name], name, pass_):
                        changed = True
        return tgt

    def feed_seq(
        self,
        items: Sequence[IrItem],
        tail: CharSet,
        rule: str,
        pass_: FollowPass,
    ) -> bool:
        """Feed FOLLOW contributions of a sequence whose continuation is ``tail``.

        Walks the arm right to left carrying the running continuation. Soft mode
        unions each nullable item's FIRST into it; hard mode uses hard-FIRST and
        *skips* nullable items (mirroring the PDA clone tails). Each atom's
        sub-rule FOLLOW update is delegated to :data:`FOLLOW_FEED`.

        :param tail: The continuation at the arm's end (the rule's FOLLOW).
        :param pass_: The FOLLOW pass constant (target table + hard flag).
        :returns: ``True`` iff any FOLLOW set grew.
        """
        hard = pass_.hard
        changed = False
        cont = tail
        for item in reversed(items):
            atom = item.atom
            hi = _hi(item)
            eff = cont
            if (hi is None or hi > 1) and pass_.loopback:
                # Loopback is a MAY-follow. Treating it as hard makes a repeated
                # child stop before its next possible occurrence, reversing the
                # documented leftmost split policy. Mandatory successors still
                # enter hard FOLLOW through the ordinary right-to-left carry.
                eff = eff.union(self.atom_first(atom))
            ctx = FeedCtx(eff, rule, pass_)
            if cast(bool, FOLLOW_FEED.resolve(atom).eval(self, atom, (ctx,))):
                changed = True
            if hard:
                if not self.item_nullable(item):
                    cont = self.atom_hard(atom)
            else:
                first = self.atom_first(atom)
                if not self.item_nullable(item):
                    cont = first
                elif pass_.nullable_first and (pass_.loopback or hi == 1):
                    cont = cont.union(first)
        return changed

    # ── conflict classification ────────────────────────────────────────

    def _classify(self) -> None:
        """Fill :attr:`conflicts` and :attr:`demoted` from every rule.

        A left-recursive rule islands unconditionally, before any other
        classification: no gate family can license it (a gate only picks an
        arm — the winning recursive arm still re-enters at the same
        position), so its decision points are never analysed for gates.
        """
        left = left_recursive_names(self)
        for name, rule in self.rules.items():
            if name in left:
                self.taxonomy.conflicts[name] = [
                    f"{name}: left-recursive — predictive descent cannot run it"
                ]
                continue
            notes = Notes()
            scope = Scope(
                name,
                Cont(
                    self.follow[name],
                    self.hard_follow[name],
                    self._structural_follow[name],
                ),
                body=True,
            )
            arms = [_items(arm) for arm in rule.body]
            self.arm_conflicts(arms, Site(name, name, self.follow[name]), notes)
            body_hard = len(notes.hard)
            for arm in arms:
                self.seq_conflicts(arm, scope, notes)
            fail = notes.f1 and self.rules[name].semantic
            if notes.hard:
                self.taxonomy.conflicts[name] = notes.hard
                if body_hard + notes.covered == len(notes.hard) and not fail:
                    self.taxonomy.attempts[name] = attempt_spec(self, arms)
            if notes.soft:
                self.taxonomy.demoted[name] = notes.soft
            if fail:
                self.taxonomy.fail.add(name)

    def arm_conflicts(
        self,
        arms: Sequence[Sequence[IrItem]],
        site: Site,
        notes: Notes,
    ) -> None:
        """Flag pairwise FIRST overlaps and empty-arm-vs-FOLLOW ambiguities.

        An overlap is settled in three tiers, and a rule body and an inline
        group take the same cascade — they differ only in ``site``'s key
        space. A k-window (or noise-skip peek) SELECTS an arm and stores its
        specs; failing that, a group earns an ordered-ATTEMPT licence
        (:func:`~lexic.parsing.pda.analysis.conflicts.attempt_group`, which
        also counts the notes as covered). Withholding either from groups is
        what made ``@lexical`` inlining island a rule whose alternation had
        been decided all along. A rule body's attempt licence is
        :meth:`_classify`'s — it sees the whole note ledger.

        The empty-arm-vs-FOLLOW branch below stays rule-body-only: its gates
        are computed from the rule's own FOLLOW\\ :sub:`k`, which a group has
        no equivalent of. Its note is soft, so it never islands.

        :param site: The alternation — its label, store key and continuation.
        """
        infos = [(self.seq_first(arm), seq_nullable(self, arm)) for arm in arms]
        overlaps: list[tuple[int, int]] = []
        for i, (first_i, _) in enumerate(infos):
            for j, (first_j, _) in enumerate(infos[i + 1 :], i + 1):
                if first_i.overlaps(first_j):
                    overlaps.append((i, j))
        if overlaps:
            demoted = self._demote_arms(list(arms), site, notes)
            if not demoted:
                for i, j in overlaps:
                    notes.hard.append(f"{site.label}: arms {i}/{j} FIRST overlap")
                attempt_group(self, arms, site, notes, len(overlaps))
        if any(nullable for _, nullable in infos):
            greedy = [
                i
                for i, (first_i, nullable) in enumerate(infos)
                if not nullable and first_i.overlaps(site.follow)
            ]
            gated = (
                bool(greedy)
                and site.label in self.rules
                and (
                    self._demote_follow_windows(list(arms), site.label, notes)
                    or self._demote_struct_arm(arms, site.label, notes)
                )
            )
            if not gated:
                for i in greedy:
                    notes.soft.append(
                        f"{site.label}: arm {i} FIRST hits FOLLOW (greedy)"
                    )

    def seq_conflicts(
        self, items: Sequence[IrItem], scope: Scope, notes: Notes
    ) -> None:
        """Classify every decision point in one sequence arm."""
        for k, item in enumerate(items):
            self._loop_conflict(items, k, scope, notes)
            sub_conflict(self, items, k, scope, notes)
            if self._same_ref_extent_split(items, k):
                name = str(item.atom)
                notes.hard.append(
                    f"{scope.rule}[{k}]: adjacent {name!r} references need "
                    "a leftmost extent split"
                )

    def _same_ref_extent_split(self, items: Sequence[IrItem], k: int) -> bool:
        """Whether adjacent required refs need extent-aware splitting.

        A variable-width child followed by another required occurrence of the
        same rule cannot be cut by a one-character stop set: that assigns all
        shared FIRST text to the right child. The Earley island owns this cold
        structural case until the PDA has an extent-aware boundary primitive.
        """
        if k + 1 >= len(items):
            return False
        left, right = items[k], items[k + 1]
        if not isinstance(left.atom, IrRuleRef) or not isinstance(
            right.atom, IrRuleRef
        ):
            return False
        if str(left.atom) != str(right.atom):
            return False
        if int(left.quantifier.lo) < 1 or int(right.quantifier.lo) < 1:
            return False
        prefixes = KWindowFirst(self.rules, 5).rule_prefixes(str(left.atom), 5)
        complete = [len(prefix) for prefix, state in prefixes if state == END]
        if not complete:
            return any(state == UNK for _prefix, state in prefixes)
        shortest = min(complete)
        return any(
            len(prefix) > shortest and state in (END, MORE)
            for prefix, state in prefixes
        )

    def _loop_conflict(
        self, items: Sequence[IrItem], k: int, scope: Scope, notes: Notes
    ) -> None:
        """Classify item ``k``'s continue/exit decision (the pivot-6 taxonomy)."""
        item = items[k]
        atom = item.atom
        lo = int(item.quantifier.lo)
        hi = _hi(item)
        if hi is not None and hi <= lo:
            return
        if self.atom_nullable(atom) and (hi is None or hi - lo > 1):
            notes.hard.append(f"{scope.rule}[{k}]: unbounded loop over nullable atom")
            return
        first = self.atom_first(atom)
        if first.overlaps(self.hard_cont_at(items, k, scope.tail)):
            policy = self.loop_policy(item, items[k + 1 :])
            if policy == "island":
                if not self._demote_loop(items, k, scope, notes):
                    notes.hard.append(f"{scope.rule}[{k}]: loop overlap, not gatable")
                    self.taxonomy.attempt_loops[id(item)] = self.beyond_at(
                        items, k, scope
                    )
                    notes.covered += 1
            elif policy == "stopset":
                if not stopset_escapes_soft_follow(self, items, k, scope):
                    notes.soft.append(f"{scope.rule}[{k}]: loop stop-set applied")
                elif noise_greedy_licensed(self, items, k, scope):
                    notes.soft.append(
                        f"{scope.rule}[{k}]: loop stop-set applied (noise-greedy)"
                    )
                else:
                    notes.hard.append(
                        f"{scope.rule}[{k}]: loop stop-set escapes soft FOLLOW"
                    )
                    notes.f1 = True
            else:
                notes.soft.append(f"{scope.rule}[{k}]: LL(2) pair gate")
            return
        soft_gap_conflict(self, items, k, scope, notes)

    def beyond_at(self, items: Sequence[IrItem], k: int, scope: Scope) -> CharSet:
        """The continuation visible only BEYOND the arm after item ``k``.

        The attempt licence's audit set: a boundary char viable via the
        same-arm rest is a SPLIT (one production carved two ways — the first
        slot owns the text, greedy take, never refused); only viability via
        the ENCLOSING tail — reachable when the rest is all-nullable — makes
        the boundary an arm choice in loop clothing, worth the composition
        probe. (Subtracting the hard tail here was tried and is UNSOUND —
        the escape alternative's first char can be hard at another site of
        the same rule; the union follow keeps the audit alive at the cost of
        spurious probes, and per-SITE precision is the honest narrowing.)
        """
        rest = items[k + 1 :]
        if all(self.item_nullable(i) for i in rest):
            return scope.structural_tail
        return CharSet.EMPTY

    def cont_at(self, items: Sequence[IrItem], k: int, tail: CharSet) -> CharSet:
        """The continuation char set after item ``k`` (rest of arm, then tail)."""
        rest = items[k + 1 :]
        cont = self.seq_first(rest)
        if all(self.item_nullable(i) for i in rest):
            cont = cont.union(tail)
        return cont
