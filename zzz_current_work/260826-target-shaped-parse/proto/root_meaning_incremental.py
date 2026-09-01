"""Compare root meanings by replaying only one ambiguity's ancestor cone."""

from __future__ import annotations

from typing import NamedTuple

from lexic.compile import canonical_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    ambiguity_points,
    same_value,
)
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.loop.leo import expand_leo
from lexic.parsing.earley.kernel.tables.atoms import predecessor_chain, tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.splits import ChainSpec, is_arm_choice
from lexic.parsing.earley.normalize import normalize

type Meaning = str | tuple["Meaning", ...]

PAD = 300


class Witness(NamedTuple):
    """One ambiguity with the expected final-root verdict."""

    name: str
    grammar: str
    text: str
    policies: dict[str, str]
    differs: bool


class Choice(NamedTuple):
    """One packed family selected for one ambiguity key."""

    key: int
    family: int


class Graph(NamedTuple):
    """Default-derivation dependencies and predecessor-key ownership."""

    parents: dict[int, set[int]]
    owners: dict[int, set[int]]


class Outcome(NamedTuple):
    """Root-equivalent verdict and its incremental fold-body cost."""

    differs: bool
    baseline_folds: int
    alternate_folds: int


class MeaningMemo:
    """A read-only baseline plus one alternate's sparse changed meanings."""

    __slots__ = ("base", "changed")

    def __init__(self, base: dict[int, Meaning]) -> None:
        self.base = base
        self.changed: dict[int, Meaning] = {}

    def contains(self, handle: int) -> bool:
        """Whether either layer contains ``handle``."""
        return handle in self.changed or handle in self.base

    def read(self, handle: int) -> Meaning:
        """Read the sparse alternate before its immutable baseline."""
        if handle in self.changed:
            return self.changed[handle]
        return self.base[handle]

    def write(self, handle: int, meaning: Meaning) -> None:
        """Write only this evaluation's changed layer."""
        self.changed[handle] = meaning


AMBIGUOUS = 'root ::= t "z"\nt ::= u | v\nu ::= "x"\nv ::= "x"\n'
DISTANT = (
    "root ::= filler t filler\n"
    "filler ::= item*\n"
    "item ::= [ab]\n"
    "t ::= u | v\n"
    'u ::= "q"\nv ::= "q"\n'
)

WITNESSES = (
    Witness("kept-difference", AMBIGUOUS, "xz", {}, True),
    Witness("dropping-parent", AMBIGUOUS, "xz", {"root": "drop"}, False),
    Witness(
        "same-meaning",
        AMBIGUOUS,
        "xz",
        {"u": "atom", "v": "atom"},
        False,
    ),
    Witness(
        "distant-point",
        DISTANT,
        "a" * PAD + "q" + "b" * PAD,
        {},
        True,
    ),
)


def _kernel(grammar: str, text: str) -> Kernel:
    """Run the real Earley kernel for one witness."""
    ast = normalize(canonical_grammar(grammar, GBNF_FLAVOUR))
    kernel = Kernel(compile_tables(ast, tier_for(len(text))), text, True).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError("root meaning prototype: no parse")
    return kernel


def _code(kernel: Kernel, handle: int) -> int:
    """The completed code carried by one packed handle."""
    return handle >> (2 * kernel.tables.packing.bits)


def _name(kernel: Kernel, handle: int) -> str:
    """The decoded rule name for one completed handle."""
    codes = kernel.tables.codes
    rule = codes.arm_rule[codes.code_arm[_code(kernel, handle)]]
    return str(kernel.tables.decode.rule_refs[rule])


def _program(kernel: Kernel, policies: dict[str, str]) -> tuple[str, ...]:
    """Lower rule policies onto completed codes, the future clone key."""
    codes = kernel.tables.codes
    lowered: list[str] = []
    for code in range(len(codes.code_arm)):
        rule = codes.arm_rule[codes.code_arm[code]]
        name = str(kernel.tables.decode.rule_refs[rule])
        lowered.append(policies.get(name, ""))
    return tuple(lowered)


def _resolved(
    kernel: Kernel,
    handle: int,
    choice: Choice | None,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return subtree handles and every predecessor key this completion owns."""
    bits = kernel.tables.packing.bits
    codes = kernel.tables.codes
    code = _code(kernel, handle)
    base = codes.arm_base[codes.code_arm[code]]
    if handle in kernel.st.leo_links:
        expand_leo(kernel.st, kernel.tables, handle)
    selected = {} if choice is None else {choice.key: choice.family}
    chain = predecessor_chain(
        kernel.st.links,
        handle,
        ChainSpec(base, bits, kernel.tables.code_choice),
        selected,
    )
    if chain is None:
        start = (handle >> bits) & kernel.tables.packing.mask
        end = handle & kernel.tables.packing.mask
        if start == end:
            return (), (handle,)
        raise UnsupportedConstructError(
            f"root meaning prototype: {_name(kernel, handle)}"
            f" [{start}:{end}] did not resolve"
        )
    children = tuple(
        child
        for _predecessor, _end, child in chain
        if isinstance(child, int) and not isinstance(child, bool)
    )
    keys = (handle,) + tuple(
        (predecessor << bits) | end for predecessor, end, _child in chain
    )
    return children, keys


def _graph(kernel: Kernel, root: int) -> Graph:
    """Index the default derivation without building a second tree."""
    parents: dict[int, set[int]] = {}
    owners: dict[int, set[int]] = {}
    pending = [root]
    seen: set[int] = set()
    while pending:
        handle = pending.pop()
        if handle in seen:
            continue
        seen.add(handle)
        children, keys = _resolved(kernel, handle, None)
        for key in keys:
            owners.setdefault(key, set()).add(handle)
        for child in children:
            parents.setdefault(child, set()).add(handle)
            pending.append(child)
    return Graph(parents, owners)


def _dirty(graph: Graph, key: int) -> set[int]:
    """The completed handles whose meanings depend on one packed key."""
    dirty = set(graph.owners.get(key, ()))
    pending = list(dirty)
    while pending:
        child = pending.pop()
        for parent in graph.parents.get(child, ()):
            if parent in dirty:
                continue
            dirty.add(parent)
            pending.append(parent)
    return dirty


class Folder:
    """A completed-code meaning program with an execution counter."""

    __slots__ = ("kernel", "program", "folds")

    def __init__(self, kernel: Kernel, policies: dict[str, str]) -> None:
        self.kernel = kernel
        self.program = _program(kernel, policies)
        self.folds = 0

    def apply(
        self,
        root: int,
        memo: MeaningMemo,
        dirty: set[int],
        choice: Choice | None,
    ) -> Meaning:
        """Fold ``root``, reusing every memoized handle outside ``dirty``."""
        stack: list[tuple[int, bool]] = [(root, False)]
        while stack:
            handle, expanded = stack.pop()
            if memo.contains(handle) and handle not in dirty:
                continue
            children, _keys = _resolved(self.kernel, handle, choice)
            if not expanded:
                stack.append((handle, True))
                for child in reversed(children):
                    if not memo.contains(child) or child in dirty:
                        stack.append((child, False))
                continue
            memo.write(handle, self._assemble(handle, children, memo))
        return memo.read(root)

    def _assemble(
        self,
        handle: int,
        children: tuple[int, ...],
        memo: MeaningMemo,
    ) -> Meaning:
        """Execute one code-selected meaning operation."""
        self.folds += 1
        name = _name(self.kernel, handle)
        policy = self.program[_code(self.kernel, handle)]
        if policy == "atom":
            bits = self.kernel.tables.packing.bits
            mask = self.kernel.tables.packing.mask
            start = (handle >> bits) & mask
            end = handle & mask
            return ("atom", self.kernel.text[start:end])
        if policy == "drop":
            return (name,)
        return (name,) + tuple(memo.read(child) for child in children)


def _exercise(witness: Witness) -> Outcome:
    """Compare every authored arm through the root continuation."""
    kernel = _kernel(witness.grammar, witness.text)
    root = accept_handle(kernel)
    graph = _graph(kernel, root)
    folder = Folder(kernel, witness.policies)
    initial = MeaningMemo({})
    first = folder.apply(root, initial, set(), None)
    baseline = initial.changed
    baseline_folds = folder.folds
    folder.folds = 0
    differs = False
    bits = kernel.tables.packing.bits
    for key in ambiguity_points(kernel, root):
        bucket = kernel.st.links[key]
        if not is_arm_choice(bucket, bits, kernel.tables.code_choice):
            continue
        affected = _dirty(graph, key)
        for family in range(1, len(bucket)):
            alternate = folder.apply(
                root,
                MeaningMemo(baseline),
                affected,
                Choice(key, family),
            )
            if not same_value(first, alternate):
                differs = True
                break
        if differs:
            break
    return Outcome(differs, baseline_folds, folder.folds)


def main() -> None:
    """Pin root-equivalent verdicts and the distant-point locality gain."""
    distant: Outcome | None = None
    for witness in WITNESSES:
        outcome = _exercise(witness)
        if outcome.differs != witness.differs:
            raise AssertionError(
                f"{witness.name}: verdict {outcome.differs}, expected {witness.differs}"
            )
        print(
            witness.name,
            f"differs={outcome.differs}",
            f"baseline_folds={outcome.baseline_folds}",
            f"alternate_folds={outcome.alternate_folds}",
            sep="\t",
        )
        if witness.name == "distant-point":
            distant = outcome
    if distant is None:
        raise AssertionError("root meaning prototype: distant witness did not run")
    if distant.alternate_folds * 100 > distant.baseline_folds:
        raise AssertionError("root meaning prototype: ancestor replay lost locality")
    print(
        "conclusion",
        "root verdict preserved; fold-body cost follows the ancestor cone",
        sep="\t",
    )


if __name__ == "__main__":
    main()
