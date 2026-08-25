"""Refusal parity anchors for the fold's four raise sites plus the poisoned
sub-parse escape — the sequential baseline a partitioned/threaded fold (the
design's step 4) must reproduce EXACTLY: same exception type, same message.

``ReduceFold`` raises :class:`~lexic.exceptions.UnsupportedConstructError`
from five places: :meth:`~lexic.compile.reduce.fold.ReduceFold.rule`,
:meth:`~lexic.compile.reduce.fold.ReduceFold.chain`,
:meth:`~lexic.compile.reduce.fold.ReduceFold._terminal_channel`,
:meth:`~lexic.compile.reduce.fold.ReduceFold._raw_channel`, and — one level
removed — a poisoned marked run's sub-parse
(:meth:`~lexic.compile.reduce.fold.ReduceFold._splice_run`, which re-enters
the parser and can itself refuse). No ground-truth corpus document refuses
mid-fold, so this file is what makes §6's post-order refusal rule
(the future partitioned fold must raise the exception the SEQUENTIAL
post-order would have hit first, not whichever worker fails first) a
checkable claim rather than an assumption.

**One site is reachable by a genuinely authored document + reducer**
(:func:`test_a_poisoned_marked_run_refuses_from_its_sub_parse` — this is
THE anchor a step-4 threaded fold gets measured against for refusal
parity). The other three raise sites were searched for hours across every
ground-truth grammar, every reducer family, and dozens of hand-built
grammars targeting each site's exact precondition, and none reaches them —
see each test's docstring for the argument. Those three are pinned DIRECTLY
against the private method instead (never through a document), which is
weaker evidence of real-world relevance but still locks the exception
type/message so a refactor cannot silently change either without a test
going red.
"""

from __future__ import annotations

from typing import Any

import pytest

from lexic.compile import compile_text
from lexic.compile.artifact import _reduce_entry
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    KEEP_RAW,
    YIELD,
    IrArg,
    IrArgs,
    IrItem,
    IrJoin,
    IrLiteral,
    IrMap,
    IrNone,
    IrQuantifier,
    IrRaise,
    IrRuleRef,
    IrSelf,
    IrTuple,
    Reducer,
)
from tests.integration.lexic.parity.fold_recorder_helpers import (
    CarriesFoldState,
    count_pool_entries,
)

# ── the one reachable site: a poisoned marked run's sub-parse refuses ──────

_POISON_GRAMMAR = (
    "root ::= item\n"
    'item ::= char* "c"\n'
    "char ::= plain | bang\n"
    "plain ::= [^!c]\n"
    'bang ::= "!"\n'
)
"""``char*`` hoists to a marked, poison-conditional run (poison ``!``):
``bang`` is the only non-text-equivalent arm, so its lead character is the
run's poison and the run's raw-text shortcut applies to everything else."""


def _poison_reducer() -> Reducer:
    """A reducer whose 'bang' arm refuses — deliberately, so a poisoned run's
    sub-parse has something to fail on.

    Every rule from ``root`` down to ``char`` is mapped explicitly (never
    left at the ``YIELD`` default): a ``YIELD`` rule proves "text-equivalent"
    from reachability alone (nothing reachable is DROPPED), independent of
    what a deeper rule's OWN mapped body does — so a ``YIELD`` ancestor
    collapses the whole subtree to a raw span and the run mechanism, along
    with 'bang''s raise, is never reached at all. Mapping every rule with a
    real (non-``YIELD``) body is what keeps the run's poison check — and the
    sub-parse it guards — live.
    """
    return Reducer(
        actions=IrMap(
            IrTuple(IrRuleRef("root"), IrArg(0)),
            IrTuple(IrRuleRef("item"), IrJoin(IrArgs())),
            IrTuple(IrRuleRef("char"), IrArg(0)),
            IrTuple(
                IrRuleRef("bang"),
                IrRaise(UnsupportedConstructError, "poisoned bang encountered"),
            ),
        ),
        default=YIELD,
    )


def test_an_unpoisoned_run_never_sub_parses() -> None:
    """The control: no poison character present, so the run's raw-text
    shortcut applies and 'bang''s refusing body is never reached."""
    grammar = compile_text(_POISON_GRAMMAR, cache_key="fold-refusal-poison-control")
    assert grammar.reduce("abdc", _poison_reducer()) == "abdc"


def test_a_poisoned_marked_run_refuses_from_its_sub_parse() -> None:
    """A poison character in the run's text forces ``_splice_run`` to
    sub-parse and fold the interior — T2 (the design notes' term for a fold
    that transitively re-enters the parser). The sub-parse's own fold then
    reaches ``bang``'s mapped body, which refuses.

    **This is the parity anchor.** A future partitioned/threaded fold must
    raise this SAME exception type and message for this document, regardless
    of which worker's partition happens to contain the poisoned run.
    """
    grammar = compile_text(_POISON_GRAMMAR, cache_key="fold-refusal-poison-hit")
    with pytest.raises(UnsupportedConstructError, match="poisoned bang encountered"):
        grammar.reduce("ab!c", _poison_reducer())


_POISON_RUN_GRAMMAR = (
    "root ::= item+\n"
    'item ::= char* "c" nl\n'
    "char ::= plain | bang\n"
    "plain ::= [^!c\\n]\n"
    'bang ::= "!"\n'
    'nl ::= "\\n"\n'
)
"""``_POISON_GRAMMAR`` widened to REPEATED items — one poison-free ``item``
per line, thirty-odd of them — so the outer fold has enough independent
units to actually cross the ``2 * workers`` partition floor. The anchor
above proves the sub-parse refuses correctly at all; this proves it still
refuses correctly when the refusing item's OWN fold is one of MANY units
running through the parallel path, not the document's only unit."""


def _poison_run_reducer() -> Reducer:
    """Every rule mapped, same reason as ``_poison_reducer``: a ``YIELD``
    ancestor would collapse everything to a span before the run mechanism —
    or the parallel partitioner, which reads the same tables — ever
    engages."""
    return Reducer(
        actions=IrMap(
            IrTuple(IrRuleRef("root"), IrJoin(IrArgs())),
            IrTuple(IrRuleRef("item"), IrJoin(IrArgs())),
            IrTuple(IrRuleRef("char"), IrArg(0)),
            IrTuple(
                IrRuleRef("bang"),
                IrRaise(UnsupportedConstructError, "poisoned bang encountered"),
            ),
        ),
        default=YIELD,
    )


def test_the_poisoned_run_anchor_refuses_correctly_from_inside_a_parallel_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item 5: verify the committed anchor actually reaches the PARALLEL
    branch under threads, not just the sequential/AUTO-on-a-tiny-document
    path the anchor above exercises.

    Thirty poison-free ``item``s plus one poisoned one is enough to clear
    the partition floor at ``cores=4`` — a ``PoolLease`` entry-counting spy
    (the same observable ``tests/unit/lexic/compile/reduce/test_fold.py``'s
    engagement pins use) confirms the pool was entered before the raise
    ever surfaces, so the refusing unit's fold genuinely runs as one of
    several parallel units, and the exception that reaches the caller is
    still exactly T2's: ``UnsupportedConstructError('poisoned bang
    encountered')``, raised via ``_splice_run``'s sub-parse from inside
    that one worker.
    """
    entered = count_pool_entries(monkeypatch)
    grammar = compile_text(_POISON_RUN_GRAMMAR, cache_key="fold-refusal-poison-run")
    text = "abdc\n" * 15 + "ab!c\n" + "abdc\n" * 15
    with pytest.raises(UnsupportedConstructError, match="poisoned bang encountered"):
        grammar.reduce(text, _poison_run_reducer(), cores=4)
    assert entered[0] >= 1, "the pool was never entered — did not partition"


# ── the three sites no authored document reaches ────────────────────────────


class _Probe(CarriesFoldState):
    """A real fold, wrapped so ``_terminal_channel``/``_raw_channel`` are
    reachable through PUBLIC methods rather than external protected access —
    both are engineered-precondition pins (see each test's docstring for why
    no document reaches them), and calling a private method from within its
    own class hierarchy is the ordinary way to expose that for a test.
    """

    def probe_terminal_channel(self, model: Any, rule: str) -> list[IrSelf]:
        """``_terminal_channel``, reachable from outside without protected access."""
        return self._terminal_channel(model, rule)

    def probe_raw_channel(
        self,
        rule: str,
        by_item: dict[int, Any],
        slots: dict[int, tuple[str, bool]],
        parts: list[IrSelf],
    ) -> None:
        """``_raw_channel``, reachable from outside without protected access."""
        self._raw_channel(rule, by_item, slots, parts)


def _small_fold() -> tuple[_Probe, str]:
    """A real, minimal fold — the vehicle for the direct pins below."""
    cg = compile_text('root ::= "a" "b"\n', cache_key="fold-refusal-direct-vehicle")
    reducer = Reducer(actions=IrMap(), default=YIELD, literal=KEEP_RAW)
    entry = _reduce_entry(cg, reducer)
    top = entry.fold.rule(entry.variant.parse("ab", cores=1))
    return _Probe.carrying(entry.fold), top


def test_rule_refuses_a_model_type_it_never_synthesized() -> None:
    """``rule()`` raises when a value's exact type has no entry in
    ``tables.rule_of``. Every class a channel walk can ever DISCOVER as a
    field value was synthesized by the SAME compile that built ``rule_of``,
    and a dropped subtree's model is never constructed at all (a sibling
    invariant already pinned in
    ``tests/unit/lexic/parsing/test_products.py::
    test_conditional_run_subparse_never_constructs_a_dropped_descendant``),
    so no authored document can hand ``rule()`` a foreign type. Pinned
    directly against an object the fold never produced.
    """
    fold, _top = _small_fold()
    with pytest.raises(UnsupportedConstructError, match="no rule for model 'object'"):
        fold.rule(object())


def test_chain_refuses_an_unreachable_pass_through_target() -> None:
    """``chain()`` raises when a pass-through walk from the field's declared
    rule resolves 0 (or 2+) paths to the value's actual rule.

    **0 paths:** every ``slot``/``body_rule`` pair ``chain()`` is ever called
    with comes from the SAME compile's own binding — the declared field type
    and the value's actual synthesized type are never independently sourced,
    so a real mismatch does not arise from any document.

    **2+ paths:** an ambiguous pass-through diamond (two alternation arms
    reaching the same target rule) is a genuine VALUE ambiguity — two
    differently-typed derivations of the same text — and the PARSE stage's
    own ambiguity guard refuses it before the fold ever runs (confirmed:
    the direct construction of such a diamond raises "ambiguous input" at
    the parse/variant-parse step, never reaching ``chain()``).

    Pinned directly with a target ``chain()`` cannot reach through the real
    fold's own tables.
    """
    fold, top = _small_fold()
    with pytest.raises(UnsupportedConstructError, match="resolved 0 ways"):
        fold.chain(top, "not-a-reachable-rule")


def test_terminal_channel_refuses_a_span_collapsed_rule_with_kept_refs() -> None:
    """``_terminal_channel`` raises when a rule is classified ``value_str``
    (span-collapsed — codegen's definition is "no ``IrRuleRef`` anywhere in
    the body") yet the fold's own ``span_opaque`` table says its channel
    still keeps ref contributions — a contradiction in terms, since
    ``span_opaque`` is derived from ``_opaque_span``, which collects refs
    from the EXACT SAME rule body ``value_str`` classification reads. A
    rule in ``text_rules`` therefore always has zero refs, so
    ``span_opaque`` is empty for every witness checked: the full
    ground-truth corpus under its own flavour's reducer, and JSON's own
    poisoned-run sub-grammar (the one other place a ``ReduceFold`` gets
    built with a hand-assembled ``FoldPlan``). Pinned by engineering the
    precondition directly onto a real fold's tables — no document reaches it.
    """
    fold, top = _small_fold()
    fold.tables = fold.tables._replace(span_opaque=frozenset({top}))
    with pytest.raises(UnsupportedConstructError, match="collapsed to a span"):
        fold.probe_terminal_channel(None, top)


def test_raw_channel_refuses_an_unbound_non_exactly_once_literal() -> None:
    """``_raw_channel`` (the ``literal=KEEP_RAW`` channel) raises when an
    arm's inline literal item is quantified other than exactly-once AND has
    no bound field to record how many times it occurred.

    Per the field-naming binding cascade, an unquantified literal gets no
    field (its occurrence count is fixed by the grammar, nothing to
    record) — and a QUANTIFIED literal always does get one, precisely so its
    count survives. Every combination tried (bare quantified literals,
    literals in optional/starred groups, hoisted anonymous groups, nested
    groups, nested repetitions) got a field. Pinned by engineering an
    ``arm_items`` entry a real fold's binding would never actually produce.
    """
    fold, top = _small_fold()
    unbound = IrItem(IrLiteral("x"), IrQuantifier(0, IrNone))
    fold.tables = fold.tables._replace(arm_items={top: (unbound,)})
    with pytest.raises(UnsupportedConstructError, match="unbound inline literal"):
        fold.probe_raw_channel(top, {}, {}, [])
