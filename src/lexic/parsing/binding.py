"""The bound model product — what a parse entry is handed.

A grammar's rules and the fold its completion sites read travel as ONE object,
so the per-identity memo has a single key and no caller can pair one grammar's
rules with another grammar's constructors. Its own module because both halves
of the engine reach it: the product entry hands it down, and the clone
compiler bakes from it, and a record either of them owned would make the other
import it back.

"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

from lexic.parsing.fold import ModelFold
from lexic.parsing.product import RecordConstructor, RuleProduct

__all__ = ["ModelBinding"]


class ModelBinding[M](NamedTuple):
    """One grammar's model product — what a parse entry is handed.

    The product IS the binding: the rules each contextual name completes
    through, and the constructor table a record completion indexes. It is one
    object rather than two parameters so a caller cannot pair a grammar's
    rules with another grammar's constructors, and so the per-identity memo
    has a single key to hold.

    ``fold`` is transitional. The completion sites still build models through
    it, and they move in their own step; when they do, the field goes and this
    record is the product alone. It is a FIELD rather than a parallel
    parameter for the same reason as above — one object, one identity, one
    memo key.

    :ivar fold: The positional ParseTree → model fold the completions read.
    :ivar rules: Rule name → its authored product. An authored compile-time
        surface fills this from its own table; a generated model from the
        binding view.
    :ivar constructors: The constructor operand table a record completion
        indexes. Empty for a surface that constructs no declared record.
    """

    fold: ModelFold[M]
    rules: Mapping[str, RuleProduct] = {}
    constructors: tuple[RecordConstructor, ...] = ()
