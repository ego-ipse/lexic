"""Witness product completion once per DAG node and effects per occurrence.

The executor memo stores an explicit completed result for a value-bearing
node. Replaying a tree reuses that value, including through a transparent
node, while each parent capture occurrence still observes it. A second real
Earley witness pins ambiguity replay: the baseline and alternate values are
each constructed once and the already-built chosen value is retained.

Uncommitted implementation evidence, not a test. Luna owns the committed
suite.
"""

from __future__ import annotations

from typing import ClassVar

from lexic.compile import canonical_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrRuleRef, IrSeq
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree, PayloadLeaf
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    MeaningBuilder,
    different_meaning,
)
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.executable import ModelExecutable
from lexic.parsing.product import (
    CaptureMode,
    CaptureSpec,
    LoweringOwned,
    PassOp,
    RecordConstructor,
    RecordOp,
    ResultMemo,
    RuleProduct,
)


class Value:
    """The witness product's closed carry base."""


class Leaf(Value):
    """A value whose constructor count reveals duplicate DAG execution."""

    calls: ClassVar[int] = 0

    def __init__(self) -> None:
        type(self).calls += 1


class Root(Value):
    """A parent recording every captured occurrence of its shared child."""

    calls: ClassVar[int] = 0

    def __init__(self, children: list[Value]) -> None:
        type(self).calls += 1
        self.children = children


def shared_dag() -> None:
    """One shared value is built once and captured once per occurrence."""
    Leaf.calls = 0
    Root.calls = 0
    rules: dict[str, RuleProduct[Value]] = {
        "leaf": RuleProduct((), RecordOp(0), 0),
        "root": RuleProduct((CaptureSpec(int(CaptureMode.MANY), 0),), RecordOp(1), 1),
    }
    owned = LoweringOwned(
        constructors=(
            RecordConstructor(Leaf),
            RecordConstructor(Root, ("children",)),
        )
    )
    executor = ModelExecutable[Value](rules, owned).executor

    leaf = ParseTree(IrRuleRef("leaf"), IrSeq())
    transparent = ParseTree(IrRuleRef("__grp_1"), IrSeq(leaf, leaf))
    root = ParseTree(IrRuleRef("root"), IrSeq(transparent))
    memo: ResultMemo[Value] = {}
    first = executor.replay(root, memo)

    if Leaf.calls != 1 or Root.calls != 1:
        raise AssertionError(
            f"shared DAG first build: leaf={Leaf.calls}, root={Root.calls}"
        )
    if not isinstance(first, Root):
        raise AssertionError("shared DAG: root constructor did not run")
    if len(first.children) != 2 or first.children[0] is not first.children[1]:
        raise AssertionError("shared DAG: two occurrences did not retain one value")

    chosen = executor.replay(root, memo)
    if chosen is not first or Leaf.calls != 1 or Root.calls != 1:
        raise AssertionError("shared DAG: replay constructed the chosen value again")

    alternate_root = ParseTree(IrRuleRef("root"), IrSeq(transparent))
    alternate = executor.replay(alternate_root, memo)
    if Leaf.calls != 1 or Root.calls != 2:
        raise AssertionError(
            f"dirty parent replay: leaf={Leaf.calls}, root={Root.calls}"
        )
    if not isinstance(alternate, Root) or len(alternate.children) != 2:
        raise AssertionError("dirty parent replay lost per-occurrence effects")
    print(
        "shared-dag",
        "leaf_constructions=1",
        "root_constructions=2 (two distinct roots)",
        "capture_occurrences=2 per root",
        "chosen_reconstructions=0",
        sep="\t",
    )


class MaybeRoot(Value):
    """A parent proving a present delegated Python ``None`` is not absence."""

    def __init__(self, child: Value | None) -> None:
        self.child = child


def present_none() -> None:
    """A delegated real ``None`` fills a required capture as a present value."""
    rules: dict[str, RuleProduct[Value | None]] = {
        "root": RuleProduct((CaptureSpec(int(CaptureMode.ONE), 0),), RecordOp(0), 1)
    }
    owned = LoweringOwned(constructors=(RecordConstructor(MaybeRoot, ("child",)),))
    root = ParseTree(IrRuleRef("root"), IrSeq(PayloadLeaf[Value | None](None, "null")))
    built = ModelExecutable[Value | None](rules, owned).executor.build(root)
    if not isinstance(built, MaybeRoot) or built.child is not None:
        raise AssertionError("present None was treated as a missing completion")
    print("presence\tpayload=None\trequired_capture=present")


class Left(Value):
    """The first ambiguous arm's value."""

    calls: ClassVar[int] = 0

    def __init__(self, text: str) -> None:
        type(self).calls += 1
        self.text = text

    @classmethod
    def fast_construct(cls) -> tuple[object, dict[str, object], tuple[str, ...]]:
        """The field order lowering cross-checks ``matched_field`` against."""
        return cls, {}, ("text",)


class Right(Value):
    """The other ambiguous arm's distinguishable value."""

    calls: ClassVar[int] = 0

    def __init__(self, text: str) -> None:
        type(self).calls += 1
        self.text = text

    @classmethod
    def fast_construct(cls) -> tuple[object, dict[str, object], tuple[str, ...]]:
        """The field order lowering cross-checks ``matched_field`` against."""
        return cls, {}, ("text",)


def ambiguity_replay() -> None:
    """Meaning replay constructs the default and differing witness once each."""
    Left.calls = 0
    Right.calls = 0
    grammar = normalize(
        canonical_grammar(
            'root ::= left | right\nleft ::= "x"\nright ::= "x"\n',
            GBNF_FLAVOUR,
        )
    )
    kernel = Kernel(compile_tables(grammar, tier_for(1)), "x", True).run()
    if accept_item(kernel) < 0:
        raise AssertionError("ambiguity replay: no parse")
    handle = accept_handle(kernel)
    first = FastTree(kernel, {}).build(handle)
    if not isinstance(first, ParseTree):
        raise AssertionError("ambiguity replay: default tree did not build")

    rules: dict[str, RuleProduct[Value]] = {
        "root": RuleProduct((CaptureSpec(int(CaptureMode.ONE), 0),), PassOp(0), 1),
        "left": RuleProduct((), RecordOp(0), 1),
        "right": RuleProduct((), RecordOp(1), 1),
    }
    owned = LoweringOwned(
        constructors=(
            RecordConstructor(Left, matched_field="text"),
            RecordConstructor(Right, matched_field="text"),
        )
    )
    executor = ModelExecutable[Value](rules, owned).executor
    pair = different_meaning(
        kernel,
        handle,
        MeaningBuilder(executor.build, executor.replay),
        first,
    )
    if pair.witness is None:
        raise AssertionError("ambiguity replay: the different value was not found")
    if Left.calls + Right.calls != 2 or Left.calls != 1 or Right.calls != 1:
        raise AssertionError(
            f"ambiguity replay constructions: left={Left.calls}, right={Right.calls}"
        )

    chosen = pair.first.value
    before = Left.calls + Right.calls
    if chosen is not pair.first.value or Left.calls + Right.calls != before:
        raise AssertionError("ambiguity replay: choosing baseline rebuilt it")
    print(
        "ambiguity-replay",
        "baseline_constructions=1",
        "witness_constructions=1",
        "chosen_reconstructions=0",
        sep="\t",
    )


def main() -> None:
    """Run both product-executor construction-count witnesses."""
    shared_dag()
    present_none()
    ambiguity_replay()
    print("s3 shared forest\tPASS")


if __name__ == "__main__":
    main()
