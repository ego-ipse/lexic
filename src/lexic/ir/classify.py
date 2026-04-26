"""Generic rule classification — delegates to RuleClassifier protocol."""

from __future__ import annotations

from typing import Literal, TypeVar

from lexic.ir.protocols import RuleClassifier

Node = TypeVar("Node")


def classify_rule(
    rule: Node,
    classifier: RuleClassifier[Node],
) -> Literal["sequence", "alternation", "value_str"]:
    """Return the IR kind of a rule by asking the classifier.

    The historical `Classifier` class wrapped this in OO; the algorithm is
    a single delegation, so it stays a function.
    """
    return classifier.kind(rule)
