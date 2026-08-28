"""Expose why child-local ambiguity meaning is not root-value equivalent."""

from __future__ import annotations

import time
from typing import NamedTuple

from lexic.compile import canonical_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrAlternation, IrAst, IrLiteral, IrRule, IrRuleRef, IrSelf, IrSeq
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    ambiguity_points,
    another_meaning,
    same_value,
)
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
    accept_items,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.splits import is_arm_choice
from lexic.parsing.earley.normalize import normalize

type Meaning = str | tuple["Meaning", ...]
"""A compositional stand-in for a target meaning — nested rule/kid tuples."""

PAD = 300
"""Filler characters on each side of the distant ambiguity point. The
quantifier desugars to a helper chain one level deep per character, and the
root-rooted comparison hands the resulting PAD-deep meanings to the engine's
recursive ``same_value`` — larger documents overflow the interpreter stack
through that comparator before cost even becomes the question."""


class Witness(NamedTuple):
    """One ambiguous grammar/input with expected verdicts for both folds.

    :ivar name: The shape's label.
    :ivar grammar: GBNF source with one arm-choice ambiguity point.
    :ivar text: The input.
    :ivar handlers: Rule-name meaning policies (``drop`` / ``atom``).
    :ivar root_differs: What root-rooted refolds conclude today.
    :ivar local_differs: What ambiguity-node-rooted folds conclude.
    """

    name: str
    grammar: str
    text: str
    handlers: dict[str, str]
    root_differs: bool
    local_differs: bool


AMBIGUOUS = 'root ::= t "z"\nt ::= u | v\nu ::= "x"\nv ::= "x"\n'
"""Two arms of ``t`` deriving the same span — one arm-choice point."""

DISTANT = (
    "root ::= filler t filler\n"
    "filler ::= item*\n"
    "item ::= [ab]\n"
    "t ::= u | v\n"
    'u ::= "q"\nv ::= "q"\n'
)
"""The same choice buried in a long document — the locality cost witness."""

WITNESSES = (
    Witness("kept-difference", AMBIGUOUS, "xz", {}, True, True),
    Witness("dropping-parent", AMBIGUOUS, "xz", {"root": "drop"}, False, True),
    Witness(
        "same-meaning",
        AMBIGUOUS,
        "xz",
        {"u": "atom", "v": "atom"},
        False,
        False,
    ),
    Witness(
        "distant-point",
        DISTANT,
        "a" * PAD + "q" + "b" * PAD,
        {},
        True,
        True,
    ),
)
"""``dropping-parent`` is the counterexample: child-local comparison refuses
even though both complete derivations produce the same root value."""


class MeaningFold(NamedTuple):
    """Compositional meaning evaluator counting its fold-body executions.

    :ivar handlers: Rule-name policies; unnamed rules nest.
    :ivar counter: One mutable cell holding the fold-body execution count.
    """

    handlers: dict[str, str]
    counter: list[int]

    @property
    def folds(self) -> int:
        """Fold-body executions so far."""
        return self.counter[0]

    def apply(self, node: ParseTree) -> Meaning:
        """One subtree's meaning, folded bottom-up on an explicit stack."""
        memo: dict[int, Meaning] = {}
        stack: list[tuple[ParseTree, bool]] = [(node, False)]
        while stack:
            current, expanded = stack.pop()
            if expanded:
                memo[id(current)] = self._assemble(current, memo)
                continue
            stack.append((current, True))
            for kid in current.kids:
                if isinstance(kid, ParseTree):
                    stack.append((kid, False))
        return memo[id(node)]

    def _assemble(self, node: ParseTree, memo: dict[int, Meaning]) -> Meaning:
        """One fold-body execution over already-folded kid meanings."""
        self.counter[0] += 1
        name = str(node.symbol)
        policy = self.handlers.get(name, "")
        if policy == "atom":
            return ("atom", _node_text(node))
        if policy == "drop":
            return (name,)
        return (name,) + tuple(
            memo[id(kid)] for kid in node.kids if isinstance(kid, ParseTree)
        )


def _node_text(node: ParseTree) -> str:
    """The text a subtree consumed, from its leaves."""
    parts: list[str] = []
    stack: list[IrSelf] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, ParseTree):
            stack.extend(reversed(current.kids))
        else:
            parts.append(str(current))
    return "".join(parts)


def _kernel(grammar: str, text: str) -> Kernel:
    """Run one recorded kernel over the witness input."""
    ast = normalize(canonical_grammar(grammar, GBNF_FLAVOUR))
    kernel = Kernel(compile_tables(ast, tier_for(len(text))), text, True).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError("local meaning prototype: no parse")
    return kernel


def _kernel_ast(grammar: IrAst, text: str) -> Kernel:
    """Run one recorded kernel over an already-native witness grammar."""
    kernel = Kernel(compile_tables(normalize(grammar)), text, True).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError("local meaning prototype: no native parse")
    return kernel


def _first_tree(kernel: Kernel) -> ParseTree:
    """The default-family derivation the engine holds before the check."""
    built = FastTree(kernel, {}).build(accept_handle(kernel))
    if not isinstance(built, ParseTree):
        raise UnsupportedConstructError(
            "local meaning prototype: the pinned build missed"
        )
    return built


def _key_differs(kernel: Kernel, key: int, fold: MeaningFold) -> bool:
    """Whether the families at ``key`` mean different things locally.

    Each family's differing CHILD subtree is built and folded fresh — the
    packed key itself names the parent chain position, whose build would drag
    the parent's context (and its dropping policies) back in.
    """
    meanings: list[Meaning] = []
    for _pitem, _pend, child in kernel.st.links[key]:
        if not isinstance(child, int) or isinstance(child, bool):
            continue
        built = FastTree(kernel, {}).build(child)
        if not isinstance(built, ParseTree):
            continue
        meanings.append(fold.apply(built))
    for index in range(1, len(meanings)):
        if not same_value(meanings[0], meanings[index]):
            return True
    return False


def _local_differs(kernel: Kernel, handle: int, fold: MeaningFold) -> bool:
    """The ambiguity verdict from root siblings then node-rooted folds."""
    roots = [
        (item << kernel.tables.packing.bits) | len(kernel.text)
        for item in accept_items(kernel)
    ]
    if len(roots) > 1:
        meanings: list[Meaning] = []
        for root in roots:
            built = FastTree(kernel, {}).build(root)
            if isinstance(built, ParseTree):
                meanings.append(fold.apply(built))
        for index in range(1, len(meanings)):
            if not same_value(meanings[0], meanings[index]):
                return True
    bits = kernel.tables.packing.bits
    for key in ambiguity_points(kernel, handle):
        bucket = kernel.st.links[key]
        if not is_arm_choice(bucket, bits, kernel.tables.code_choice):
            continue
        if _key_differs(kernel, key, fold):
            return True
    return False


def _root_sibling_witness() -> None:
    """Pin the separate accepting-item case the internal-point walk cannot see."""
    grammar = IrAst(
        IrSeq(
            IrRule("v", IrAlternation(IrRuleRef("a"), IrRuleRef("b"))),
            IrRule("a", IrLiteral("x")),
            IrRule("b", IrLiteral("x")),
        ),
        "v",
    )
    kernel = _kernel_ast(grammar, "x")
    if len(accept_items(kernel)) != 2:
        raise AssertionError("root sibling witness lost its two accepting items")
    different = MeaningFold({}, [0])
    if not _local_differs(kernel, accept_handle(kernel), different):
        raise AssertionError("local mechanism missed differing root siblings")
    same = MeaningFold({"a": "atom", "b": "atom"}, [0])
    if _local_differs(kernel, accept_handle(kernel), same):
        raise AssertionError("local mechanism split equal root sibling meanings")
    print(
        "root-siblings",
        "accepting_items=2",
        f"different_folds={different.folds}",
        f"same_folds={same.folds}",
        sep="\t",
    )


class Outcome(NamedTuple):
    """Both approaches' verdicts, fold counts, and wall seconds."""

    root_differs: bool
    root_folds: int
    root_wall: float
    local_differs: bool
    local_folds: int
    local_wall: float


def _exercise(witness: Witness) -> Outcome:
    """Run the root-rooted and node-rooted checks over one witness."""
    kernel = _kernel(witness.grammar, witness.text)
    handle = accept_handle(kernel)
    first = _first_tree(kernel)
    root_fold = MeaningFold(witness.handlers, [0])
    started = time.perf_counter()
    root_witness = another_meaning(kernel, handle, root_fold.apply, first)
    root_wall = time.perf_counter() - started
    local_fold = MeaningFold(witness.handlers, [0])
    started = time.perf_counter()
    local = _local_differs(kernel, handle, local_fold)
    local_wall = time.perf_counter() - started
    return Outcome(
        root_witness is not None,
        root_fold.folds,
        root_wall,
        local,
        local_fold.folds,
        local_wall,
    )


def _check(witness: Witness, outcome: Outcome) -> None:
    """Pin the expected verdict pair for one witness."""
    if outcome.root_differs != witness.root_differs:
        raise AssertionError(
            f"{witness.name}: root verdict {outcome.root_differs},"
            f" expected {witness.root_differs}"
        )
    if outcome.local_differs != witness.local_differs:
        raise AssertionError(
            f"{witness.name}: local verdict {outcome.local_differs},"
            f" expected {witness.local_differs}"
        )


def main() -> None:
    """Run every witness and pin the cheap but unsound local divergence."""
    _root_sibling_witness()
    distant: Outcome | None = None
    for witness in WITNESSES:
        outcome = _exercise(witness)
        _check(witness, outcome)
        print(
            witness.name,
            f"root_differs={outcome.root_differs}",
            f"root_folds={outcome.root_folds}",
            f"root_wall={outcome.root_wall:.6f}",
            f"local_differs={outcome.local_differs}",
            f"local_folds={outcome.local_folds}",
            f"local_wall={outcome.local_wall:.6f}",
            sep="\t",
        )
        if witness.name == "distant-point":
            distant = outcome
    if distant is None:
        raise AssertionError("the distant-point witness did not run")
    if distant.local_folds * 100 > distant.root_folds:
        raise AssertionError(
            "locality no longer saves two orders of magnitude of folds"
        )
    print(
        "conclusion",
        "child-local folds are cheap but not root-value equivalent;"
        " dropping-parent forbids this scope",
        sep="\t",
    )


if __name__ == "__main__":
    main()
