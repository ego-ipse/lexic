"""Earley items — a dotted arm ``(rule_name, arm, dot, origin)`` as a plain tuple."""

from __future__ import annotations

from lexic.ir.nodes import IrRuleRef, IrSequence

EarleyItem = tuple[IrRuleRef, IrSequence, int, int]
