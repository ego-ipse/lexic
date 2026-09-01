"""Execute a tiny sequence/map product over REAL Earley recognition.

The PDA cannot reach a product completion yet — `FlatClone` carries a
`RuleFold`, not a `RuleProduct`, and giving it one is §4's migration. Earley
is different: its completion seam is a post-order fold over a real
`ParseTree`, so a product can execute there today with no clone-carried data
and no `src` change at all.

So this drives genuine Earley recognition over real text, then runs the
VERIFIED flat tables at the tree's completion sites. The executor is
proto-side; the program, its lowering, its verification and its parse-local
state are the real ones.

What it exercises, all against tree shapes a hand-driven interpreter never
produces: MANY captures over a real repetition, TEXT over real spans, a
transparent synthetic node looked through, value-once over a shared subtree,
`ParseState` transactions including a rolled-back speculative insert, the
mapping duplicate policy, and the built value asserted against the expected
one.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from lexic.compile import compile_text
from lexic.compile.product import LoweringOwned, lower_product
from lexic.exceptions import SemanticVerdict, UnsupportedConstructError
from lexic.parsing.earley.engine import AmbiguityPolicy, EarleyParser, first_meaning
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.product import (
    BeginMappingOp,
    CaptureMode,
    CaptureSpec,
    DecodeCode,
    DecodeOp,
    FinishMappingOp,
    FinishSequenceOp,
    InsertMappingOp,
    MeaningOp,
    OperandTables,
    ParseState,
    ProductProgram,
    RootOp,
    RuleProduct,
    verify_program,
)
from lexic.parsing.products import _model_product

GRAMMAR = (
    'root ::= "{" pair more "}"\n'
    "more ::= sep pair more | \n"
    'sep ::= ","\n'
    'pair ::= key ":" val\n'
    "key ::= [a-z]+\n"
    "val ::= [0-9]+\n"
)
"""A tiny map whose keys are a real repetition — `key`'s `__rep` node is what
a MANY capture collects, and the `more` chain is the entry stream."""

TEXT = "{a:1,bb:22}"
EXPECTED = (("a", "1"), ("bb", "22"))

type Carry = str | tuple[tuple[str, str], ...]

# Contextual rule codes, one per rule the product completes at.
ROOT, PAIR, KEY, VAL = 0, 1, 2, 3
RULE_CODES = {"root": ROOT, "pair": PAIR, "key": KEY, "val": VAL}

SKIP = CaptureSpec(CaptureMode.SKIP, 0)

RULES: tuple[RuleProduct[Carry], ...] = (
    # root: "{" pair more "}" — the mapping is finished here.
    RuleProduct((SKIP, SKIP, SKIP, SKIP), FinishMappingOp(0, 0)),
    # pair: key ":" val — one entry inserted from a TEXT key and a ONE value.
    RuleProduct(
        (
            CaptureSpec(CaptureMode.ONE, 0),
            SKIP,
            CaptureSpec(CaptureMode.ONE, 1),
        ),
        InsertMappingOp(0, 0, 1),
    ),
    # key: its one kid is the transparent repetition — MANY over its chars.
    RuleProduct((CaptureSpec(CaptureMode.MANY, 0),), FinishSequenceOp(0, 0)),
    # val: the same shape, decoded as text rather than accumulated.
    RuleProduct((CaptureSpec(CaptureMode.TEXT, 0),), DecodeOp(0, DecodeCode.TEXT)),
)

BEGINS = {ROOT: BeginMappingOp(0, 0)}
"""Container rules open their accumulator on DESCENT, which is what a frame
push does in the PDA. A pure post-order walk would try to insert into a
mapping that does not exist yet."""


def _join(values: tuple[Carry, ...]) -> Carry:
    """The sequence finisher — one of the three admitted callables."""
    return "".join(str(value) for value in values)


def _as_map(entries: tuple[tuple[str, Carry], ...]) -> Carry:
    """The mapping finisher."""
    return tuple((key, str(value)) for key, value in entries)


OPERANDS: OperandTables[Carry, Carry] = OperandTables(
    constants=(),
    constructors=(),
    sequences=(_join,),
    mappings=(_as_map,),
    meanings=(),
    roots=(lambda carry, verdicts: carry,),
    routes=(),
    continuations=(),
)


class Counts(NamedTuple):
    """What one execution actually did, for the assertions to read."""

    completed: dict[str, int]
    folds: dict[int, int]


def _text_of(node: object) -> str:
    """All characters consumed under one node, in source order."""
    parts: list[str] = []
    stack: list[object] = [node]
    while stack:
        item = stack.pop()
        if isinstance(item, ParseTree):
            stack.extend(reversed(item.kids))
        else:
            parts.append(str(item))
    return "".join(parts)


class Executor:
    """Runs a verified product's flat tables at Earley completion sites.

    Enter on descent, complete on ascent — the same shape a frame push and
    pop have, which is why a container's `begin` can run before the entries
    that insert into it.
    """

    def __init__(
        self,
        program: ProductProgram[Carry, Carry],
        codes: dict[str, int] = RULE_CODES,
        begins: dict[int, BeginMappingOp] = BEGINS,
    ) -> None:
        self.program = program
        self.codes = codes
        self.begins = begins
        self.state: ParseState[Carry] = ParseState()
        self.values: dict[int, Carry] = {}
        self.counts = Counts({}, {})
        self.mapping: Any = None
        self.sequences: dict[int, Any] = {}

    def run(self, root: ParseTree) -> Carry:
        """Walk the real derivation, completing every rule that has a product."""
        stack: list[tuple[ParseTree, bool]] = [(root, False)]
        folded: set[int] = set()
        while stack:
            node, ascending = stack.pop()
            code = self.codes.get(str(node.symbol))
            if not ascending:
                if id(node) in folded:
                    continue  # a shared subtree: its value is already computed
                self._enter(node, code)
                stack.append((node, True))
                stack.extend(
                    (kid, False)
                    for kid in reversed(node.kids)
                    if isinstance(kid, ParseTree)
                )
                continue
            if id(node) in folded:
                continue
            folded.add(id(node))
            if code is not None:
                self._complete(node, code)
        return self.values[id(root)]

    def _enter(self, node: ParseTree, code: int | None) -> None:
        """Open a container's accumulator on the way down."""
        if code is None or code not in self.begins:
            return
        begin = self.begins[code]
        self.mapping = self.state.begin_mapping(begin.duplicates)
        del node

    def _complete(self, node: ParseTree, code: int) -> None:
        """Read the rule's ONE completion range and execute it."""
        rule = self.program.rules[code]
        completion = self.program.completions[rule.completion]
        opcode = self.program.fused_opcodes[completion.start]
        row = self.program.fused_operand_rows[opcode][
            self.program.fused_operands[completion.start]
        ]
        frame = self._captures(node, rule.capture_modes)
        self.counts.completed[str(node.symbol)] = (
            self.counts.completed.get(str(node.symbol), 0) + 1
        )
        self.counts.folds[id(node)] = self.counts.folds.get(id(node), 0) + 1
        value = self._execute(node, opcode, row, frame)
        if value is not None:
            self.values[id(node)] = value

    def _captures(
        self, node: ParseTree, modes: tuple[int, ...]
    ) -> dict[str, list[Any]]:
        """Fill the typed capture lanes from this node's real kids."""
        lanes: dict[str, list[Any]] = {"texts": [], "ones": [], "many": []}
        for at, mode in enumerate(modes):
            if mode == CaptureMode.SKIP or at >= len(node.kids):
                continue
            kid = node.kids[at]
            if mode == CaptureMode.TEXT:
                lanes["texts"].append(_text_of(kid))
            elif mode == CaptureMode.ONE:
                lanes["ones"].append(self.values[id(kid)])
            elif mode == CaptureMode.MANY:
                # The transparent repetition node is LOOKED THROUGH — its
                # children are the repetition's real elements.
                inner = kid.kids if isinstance(kid, ParseTree) else ()
                lanes["many"].append([_text_of(one) for one in inner])
        return lanes

    def _execute(
        self, node: ParseTree, opcode: int, row: tuple[int, ...], lanes: dict[str, list]
    ) -> Carry | None:
        """One plain-int opcode over its own operand row."""
        if opcode == 9:  # FINISH_MAPPING
            entries = self.state.finish_mapping(self.mapping)
            return self.program.operands.mappings[row[1]](entries)
        if opcode == 8:  # INSERT_MAPPING
            key = str(lanes["ones"][row[1]])
            self.state.insert_mapping(
                self.mapping,
                key,
                lanes["ones"][row[2]],
                SemanticVerdict("duplicate-key", f"repeated {key!r}", 0, 0),
            )
            return None
        if opcode == 6:  # FINISH_SEQUENCE
            handle = self.state.begin_sequence()
            for one in lanes["many"][0]:
                self.state.append_sequence(handle, one)
            return self.program.operands.sequences[row[1]](
                self.state.finish_sequence(handle)
            )
        if opcode == 2:  # DECODE
            return lanes["texts"][row[0]]
        raise UnsupportedConstructError(f"{node.symbol}: unhandled opcode {opcode}")


def _tree(text: str, grammar: str = GRAMMAR) -> ParseTree:
    """A REAL Earley derivation of ``text`` — genuine chart, genuine FastTree."""
    compiled = compile_text(grammar)
    product = _model_product(compiled.codegen_grammar, compiled.fold, tier_for(len(text)))
    tree = first_meaning(
        EarleyParser(),
        product.instance_grammar,
        text,
        product.tables,
        AmbiguityPolicy(compiled.fold.apply, None),
    )
    if not isinstance(tree, ParseTree):
        raise AssertionError("the Earley path did not produce a derivation")
    return tree


def _program() -> ProductProgram[Carry, Carry]:
    """Lower and VERIFY the tiny target through the real chain."""
    program = lower_product(
        RULES, OPERANDS, owned=LoweringOwned(), root=RootOp(0), meaning=MeaningOp(0)
    )
    verify_program(program)
    return program


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s3 earley target: {claim}")


def the_product_executes_over_real_recognition() -> None:
    """The headline: real Earley recognition drives the product completions."""
    program = _program()
    _check("a collection-building product was not derived stateful", program.stateful)
    tree = _tree(TEXT)
    run = Executor(program)
    built = run.run(tree)

    _check(f"the built value is {built!r}, not {EXPECTED!r}", built == EXPECTED)
    _check(
        "the repetition did not complete once per key",
        run.counts.completed.get("key") == 2,
    )
    _check(
        "the entries did not complete once per pair",
        run.counts.completed.get("pair") == 2,
    )
    _check(
        "a node completed more than once",
        all(count == 1 for count in run.counts.folds.values()),
    )
    print(
        "execute",
        f"text={TEXT}",
        f"built={built}",
        f"completions={sum(run.counts.completed.values())}",
        sep="\t",
    )


def many_captures_read_the_real_repetition() -> None:
    """A MANY capture collects the repetition's real elements, not its text."""
    program = _program()
    tree = _tree("{abc:7}")
    run = Executor(program)
    built = run.run(tree)
    _check(f"the multi-character key did not join: {built!r}", built == (("abc", "7"),))
    print("many\tkey 'abc' collected char-by-char through the transparent node")


def the_duplicate_policy_refuses() -> None:
    """A repeated decoded key records a verdict under the declared policy."""
    program = _program()
    tree = _tree("{a:1,a:2}")
    run = Executor(program)
    built = run.run(tree)
    _check(f"the duplicate was not refused: {built!r}", built == (("a", "1"),))
    _check(
        "no verdict was recorded for the repeated key",
        [v.sort for v in run.state.verdicts] == ["duplicate-key"],
    )
    print(f"duplicates\trefused, verdict recorded\t{run.state.verdicts[0].words}")


def a_rolled_back_speculation_leaves_nothing() -> None:
    """A speculative insert mid-parse is undone exactly, mid-execution."""
    program = _program()
    tree = _tree(TEXT)
    run = Executor(program)

    # Drive the real walk, then speculate on the live state the parse built.
    built = run.run(tree)
    mark = run.state.mark()
    run.state.insert_mapping(
        run.mapping, "speculative", "9", SemanticVerdict("duplicate-key", "spec", 0, 0)
    )
    _check(
        "the speculative insert did not land",
        len(run.state.finish_mapping(run.mapping)) == 3,
    )
    run.state.rollback(mark)
    _check(
        "rollback left the speculative entry behind",
        run.state.finish_mapping(run.mapping) == (("a", "1"), ("bb", "22")),
    )
    _check("the committed value changed", built == EXPECTED)
    print("rollback\tspeculative insert undone exactly; the parse's own entries kept")


SHARED_GRAMMAR = (
    'root ::= pad "{" pair "}" pad\n'
    'pad ::= " "?\n'
    'pair ::= key ":" val\n'
    "key ::= [a-z]+\n"
    "val ::= [0-9]+\n"
)
"""`pad` is nullable and referenced twice, so both zero-width occurrences are
ONE interned forest node reached from two kid slots — the sharing the
value-once guard exists for."""

SHARED_CODES = {"root": ROOT, "pair": PAIR, "key": KEY, "val": VAL, "pad": 4}

SHARED_RULES: tuple[RuleProduct[Carry], ...] = RULES + (
    RuleProduct((CaptureSpec(CaptureMode.TEXT, 0),), DecodeOp(0, DecodeCode.TEXT)),
)
"""The same four rules plus `pad`, whose completion is a plain decode — enough
that the executor visits it and the guard has something to guard."""


def a_shared_subtree_completes_once() -> None:
    """One interned node reached from two slots completes exactly once.

    `pad` is nullable and appears twice, so the forest interns ONE node for
    both zero-width occurrences. Without the value-once guard the walk would
    complete it per slot; the count is what proves the guard is load-bearing
    rather than decorative.
    """
    program = lower_product(
        SHARED_RULES,
        OPERANDS,
        owned=LoweringOwned(),
        root=RootOp(0),
        meaning=MeaningOp(0),
    )
    verify_program(program)
    tree = _tree("{a:1}", SHARED_GRAMMAR)

    slots: dict[int, int] = {}
    seen: set[int] = set()
    stack = [tree]
    names: dict[int, str] = {}
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        names[id(node)] = str(node.symbol)
        for kid in node.kids:
            if isinstance(kid, ParseTree):
                slots[id(kid)] = slots.get(id(kid), 0) + 1
                stack.append(kid)
    shared = {node for node, count in slots.items() if count > 1}
    _check("nothing is shared — the guard would be untested", bool(shared))

    run = Executor(program, SHARED_CODES, BEGINS)
    built = run.run(tree)
    _check(f"the shared-grammar value is wrong: {built!r}", built == (("a", "1"),))
    for node in shared:
        _check(
            f"the shared {names[node]!r} completed "
            f"{run.counts.folds.get(node, 0)} times, not once",
            run.counts.folds.get(node, 0) == 1,
        )
    print(
        "shared",
        f"{names[next(iter(shared))]} reached from {slots[next(iter(shared))]} slots",
        "completed once",
        sep="\t",
    )


def main() -> None:
    """Run every claim; any failure raises."""
    the_product_executes_over_real_recognition()
    many_captures_read_the_real_repetition()
    the_duplicate_policy_refuses()
    a_rolled_back_speculation_leaves_nothing()
    a_shared_subtree_completes_once()
    print(
        "s3 earley target",
        "PASS",
        "verified product executed over real Earley recognition",
        sep="\t",
    )


if __name__ == "__main__":
    main()
