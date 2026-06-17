"""Earley driver — the Scott/Earley loop over an :class:`~lexic.ir.nodes.IrAst`.

:class:`EarleyParser` IS-AN :class:`~lexic.ir.walk.IrDispatch`: its ``actions``
table is :data:`~lexic.parsing_2.ops.EARLEY_OPS`, so resolving the next operation
is the inherited type-dispatch. The driver itself stays stateless (an
``IrDispatch`` is an immutable tuple value); all per-parse state lives in the
:class:`~lexic.parsing_2.chart.Chart` and flows to the operation bodies through a
:class:`~lexic.parsing_2.ops.ParseCtx` on the argument channel.

The loop matches the reference (``lark/parsers/earley.py``): per column, run
predict/complete to a fixpoint, then scan one character into the next column.
:meth:`EarleyParser.recognize` answers acceptance; :meth:`EarleyParser.parse`
reconstructs the derivation (a :class:`~lexic.parsing_2.forest.ParseTree`) from
the chart's provenance links, ready for :class:`~lexic.parsing_2.reduce.Reducer`.
"""

from __future__ import annotations

from typing import ClassVar

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrAtom, IrNamedTuple, IrTuple
from lexic.ir.mapping import IrMap, IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRange,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.walk import IrDispatch
from lexic.parsing_2.chart import Chart
from lexic.parsing_2.forest import ParseTree, build_tree
from lexic.parsing_2.item import EarleyItem
from lexic.parsing_2.ops import EARLEY_OPS, ParseCtx


class _ParseInputs(IrNamedTuple):
    """Parse-invariant trio bundled for the column-close loop.

    Scalar payload only (``_child_attrs = ()``): this is engine state,
    not a grammar node to walk.

    :ivar rules: Rule index — :class:`~lexic.ir.nodes.IrRuleRef` → its body.
    :ivar text: The full input string.
    :ivar nullable: Names of rules that can derive the empty string.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    rules: IrMap[IrRuleRef, IrAlternation]
    text: str
    nullable: frozenset[str]


def _index(grammar: IrAst) -> IrMap[IrRuleRef, IrAlternation]:
    """Build the rule index: :class:`IrRuleRef` → its alternation body.

    Keys are ``IrRuleRef`` (not the rule's bare ``name`` string) so lookups by a
    dotted item's ``IrRuleRef`` resolve under type-aware equality.

    :param grammar: The grammar to index.
    :returns: An :class:`~lexic.ir.mapping.IrMap` from rule ref to body.
    """
    return IrMap(*(IrTuple(IrRuleRef(rule.name), rule.body) for rule in grammar.rules))


def _nullable_rules(grammar: IrAst) -> frozenset[str]:
    """Names of rules that can derive the empty string, by least-fixpoint.

    A rule is nullable if any arm is nullable; an arm is nullable if every item
    is — an empty arm vacuously, a ruleref item iff its target is nullable.
    Assumes the grammar is Earley-normalised (all quantifiers ``(1, 1)``), so
    nullability flows purely through empty arms and nullable rulerefs.

    :param grammar: The grammar to analyse.
    :returns: The set of nullable rule names.
    """
    nullable: set[str] = set()
    changed = True
    while changed:
        changed = False
        for rule in grammar.rules:
            if rule.name not in nullable and _alt_nullable(rule.body, nullable):
                nullable.add(rule.name)
                changed = True
    return frozenset(nullable)


def _alt_nullable(alt: IrAlternation, nullable: set[str]) -> bool:
    """Whether any arm of ``alt`` is nullable under the current ``nullable`` set."""
    return any(_seq_nullable(arm, nullable) for arm in alt)


def _seq_nullable(seq: IrSequence, nullable: set[str]) -> bool:
    """Whether every item of ``seq`` is nullable (vacuously true if empty)."""
    return all(_item_nullable(item, nullable) for item in seq)


def _item_nullable(item: IrItem, nullable: set[str]) -> bool:
    """Whether ``item`` is a ruleref to a currently-nullable rule."""
    atom = item.atom
    return isinstance(atom, IrRuleRef) and str(atom) in nullable


def _matches(atom: IrAtom, char: str) -> bool:
    """Whether a terminal ``atom`` accepts a single ``char``.

    Assumes literals were split to one char each (see
    :mod:`lexic.parsing_2.normalize`).

    :param atom: A terminal atom — a literal or a char class.
    :param char: The single input character to test.
    :returns: Whether the atom accepts the character.
    """
    if isinstance(atom, IrLiteral):
        return char == str(atom)
    if isinstance(atom, IrCharClass):
        for element in atom:
            if isinstance(element, IrRange):
                if str(element.lo) <= char <= str(element.hi):
                    return True
            elif char in str(element):
                return True
    return False


class EarleyParser(IrDispatch):
    """Recognises and parses text against an IR grammar by the Earley algorithm.

    The dispatch table is the engine; the methods here are the loop that feeds it.
    """

    actions: IrTypeMap = EARLEY_OPS

    def recognize(self, grammar: IrAst, text: str) -> bool:
        """Return whether ``text`` derives from ``grammar``'s start rule.

        :param grammar: The grammar, Earley-normalised (see
            :mod:`lexic.parsing_2.normalize`).
        :param text: The input string.
        :returns: ``True`` if the start rule spans the whole input.
        """
        chart = self._build_chart(grammar, text)
        return self._accepting_item(chart, grammar.start, len(text)) is not None

    def parse(self, grammar: IrAst, text: str) -> ParseTree:
        """Parse ``text`` into its derivation tree.

        The returned :class:`~lexic.parsing_2.forest.ParseTree` is reduced to an
        :class:`IrAst` (or a value) by a flavour's
        :class:`~lexic.parsing_2.reduce.Reducer` — that reduction table is the
        "meta notation" a flavour supplies (e.g. ``abnf_2.ABNF_REDUCTIONS``).

        :param grammar: The grammar, Earley-normalised.
        :param text: The input string.
        :returns: The derivation of ``text`` under the start rule.
        :raises UnsupportedConstructError: If ``text`` does not parse.
        """
        chart = self._build_chart(grammar, text)
        item = self._accepting_item(chart, grammar.start, len(text))
        if item is None:
            raise UnsupportedConstructError(
                f"parsing_2: input does not derive from {grammar.start!r}"
            )
        return build_tree(chart, item, len(text))

    def _build_chart(self, grammar: IrAst, text: str) -> Chart:
        """Run the full Earley loop and return the completed chart.

        :param grammar: The grammar to parse against.
        :param text: The input string.
        :returns: The chart, with provenance links populated.
        """
        inputs = _ParseInputs(
            rules=_index(grammar),
            text=text,
            nullable=_nullable_rules(grammar),
        )
        chart = Chart()
        chart.ensure(0)
        start = IrRuleRef(grammar.start)
        for arm in inputs.rules.resolve(start):
            chart[0].add(EarleyItem(start, arm, 0, 0))

        for i in range(len(text) + 1):
            chart.ensure(i)
            self._close_column(chart, inputs, i)
            self._scan(chart, text, i)

        return chart

    def _close_column(self, chart: Chart, inputs: _ParseInputs, i: int) -> None:
        """Run predict/complete to a fixpoint over column ``i``.

        A cursor walks the column; predict/complete append in place, so newly
        added items are visited without a separate worklist.

        :param chart: The chart being grown.
        :param inputs: The parse-invariant trio (rules, text, nullable).
        :param i: The column to close.
        """
        column = chart[i]
        cursor = 0
        while cursor < len(column):
            item = column[cursor]
            cursor += 1
            ctx = ParseCtx(chart, inputs.rules, inputs.text, i, item, inputs.nullable)
            self.eval(self, item.next_symbol(), IrTuple(ctx))

    def _scan(self, chart: Chart, text: str, i: int) -> None:
        """Match one character for each buffered terminal item into column ``i+1``.

        Records the consumed character as the advanced item's provenance child.

        :param chart: The chart being grown.
        :param text: The full input.
        :param i: The column whose scan buffer to drain.
        """
        if i >= len(text):
            return
        for item in chart[i].to_scan:
            atom = item.next_symbol()
            if isinstance(atom, IrAtom) and _matches(atom, text[i]):
                chart.ensure(i + 1)
                advanced = item.advance()
                if chart[i + 1].add(advanced):
                    chart.links[(advanced, i + 1)] = (item, i, IrLiteral(text[i]))

    @staticmethod
    def _accepting_item(chart: Chart, start: str, end: int) -> EarleyItem | None:
        """The start-rule item that completed spanning the whole input, if any.

        :param chart: The completed chart.
        :param start: The start-rule name.
        :param end: The final column index (``len(text)``).
        :returns: The accepting item, or ``None`` on a parse failure.
        """
        if end >= len(chart):
            return None
        for item in chart[end]:
            if item.is_complete and str(item.rule_name) == start and item.origin == 0:
                return item
        return None


def recognize(grammar: IrAst, text: str) -> bool:
    """Module-level entry: recognise ``text`` against ``grammar``.

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :returns: Whether the input derives from the start rule.
    """
    return EarleyParser().recognize(grammar, text)


def parse(grammar: IrAst, text: str) -> ParseTree:
    """Module-level entry: parse ``text`` into its derivation tree.

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :returns: The derivation of ``text`` under the start rule.
    :raises UnsupportedConstructError: If ``text`` does not parse.
    """
    return EarleyParser().parse(grammar, text)
