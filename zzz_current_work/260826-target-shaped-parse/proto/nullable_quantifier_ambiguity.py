"""Scope same-span quantified-nullable families and the Leo readout hazard.

The public parser currently exempts every generated quantifier-helper family
from value ambiguity. That is sound only when the selected family changes an
extent without changing the requested product.  This witness asks the real
model fold which quantified-nullable shapes violate that premise, forces the
PDA and Earley routes separately, and inventories every shipped grammar
flavour.

It also pins the independent readout defect: ``ambiguity_points`` is incomplete
until deferred Leo provenance is expanded.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from lexic.compile import canonical_grammar, compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import flavour_for_extension
from lexic.ir import IrItem
from lexic.model import GrammarModel
from lexic.parsing import earley_model, pda_tables
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    ambiguity_points,
    same_value,
)
from lexic.parsing.earley.kernel.forest.support.readout import accept_handle
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.loop.leo import expand_leo
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.splits import is_arm_choice
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.fold import collapsed_fold_tables, lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.kernel.kernel import pda_model


class Case(NamedTuple):
    """One quantified nullable spelling and its empty-span document."""

    name: str
    body: str
    gap: str = 'gap ::= item?\nitem ::= "a"\n'

    @property
    def grammar(self) -> str:
        """The complete grammar for this case."""
        return f'root ::= pad list\nlist ::= {self.body}\n{self.gap}pad ::= "x"\n'


CASES = (
    Case("star-ref", "gap*"),
    Case("plus-ref", "gap+"),
    Case("optional-ref", "gap?"),
    Case("bounded-zero-two", "gap{0,2}"),
    Case("bounded-one-two", "gap{1,2}"),
    Case("exact-two", "gap{2}"),
    Case("star-group", "(gap)*"),
    Case("star-empty-rule", "gap*", 'gap ::= ""\n'),
)


class FamilyScope(NamedTuple):
    """What one finished Earley chart exposes after complete readout."""

    points: int
    differing_points: int
    differing_non_arm_points: int


def complete_ambiguity_points(kernel: Kernel, root: int) -> list[int]:
    """Read ambiguity only after expanding all deferred Leo provenance."""
    for key in tuple(kernel.st.leo_links):
        expand_leo(kernel.st, kernel.tables, key)
    return ambiguity_points(kernel, root)


def _answer(work: Callable[[], GrammarModel]) -> str:
    """Run one forced route and preserve its public outcome in one line."""
    try:
        return repr(work())
    except PdaFail as error:
        return f"PdaFail: {error}"
    except UnsupportedConstructError as error:
        return f"UnsupportedConstructError: {error}"


def _family_scope(compiled_text: str, *, lift: bool) -> FamilyScope:
    """Count family points whose one-step alternate changes the real model."""
    compiled = compile_text(compiled_text)
    source = (
        lift_optional_nullables(compiled.codegen_grammar)
        if lift
        else compiled.codegen_grammar
    )
    grammar = normalize(source)
    tables = collapsed_fold_tables(grammar, compiled.fold, tier_for(1))
    kernel = Kernel(tables, "x", True).run()
    root = accept_handle(kernel)
    baseline_tree = FastTree(kernel, {}).build(root)
    if not isinstance(baseline_tree, ParseTree):
        raise UnsupportedConstructError("nullable quantifier: no baseline tree")
    baseline = compiled.fold.apply(baseline_tree)
    points = complete_ambiguity_points(kernel, root)
    differing = 0
    non_arm = 0
    bits = kernel.tables.packing.bits
    for key in points:
        bucket = kernel.st.links[key]
        changed = False
        for family in range(1, len(bucket)):
            alternate_tree = FastTree(kernel, {key: family}).build(root)
            if not isinstance(alternate_tree, ParseTree):
                continue
            alternate = compiled.fold.apply(alternate_tree)
            if not same_value(baseline, alternate):
                changed = True
        if not changed:
            continue
        differing += 1
        if not is_arm_choice(bucket, bits, kernel.tables.code_choice):
            non_arm += 1
    return FamilyScope(len(points), differing, non_arm)


def prove_quantifier_scope() -> None:
    """Compare public, forced-PDA, and forced-Earley outcomes per shape."""
    for case in CASES:
        compiled = compile_text(case.grammar)
        grammar = normalize(lift_optional_nullables(compiled.codegen_grammar))
        tables = collapsed_fold_tables(grammar, compiled.fold, tier_for(1))
        raw_scope = _family_scope(case.grammar, lift=False)
        effective_scope = _family_scope(case.grammar, lift=True)
        public = _answer(lambda: compiled.parse("x", cores=1))
        predictive = _answer(
            lambda: pda_model(
                pda_tables(compiled.codegen_grammar, compiled.fold),
                "x",
                compiled.fold,
            )
        )
        earley = _answer(lambda: earley_model(grammar, "x", compiled.fold, tables))
        raw_grammar = normalize(compiled.codegen_grammar)
        raw_tables = collapsed_fold_tables(raw_grammar, compiled.fold, tier_for(1))
        raw_earley = _answer(
            lambda: earley_model(raw_grammar, "x", compiled.fold, raw_tables)
        )
        print(
            "quantifier",
            case.name,
            f"raw_points={raw_scope.points}",
            f"raw_differing_non_arm={raw_scope.differing_non_arm_points}",
            f"effective_points={effective_scope.points}",
            f"effective_differing_non_arm={effective_scope.differing_non_arm_points}",
            f"public={public}",
            f"pda={predictive}",
            f"earley={earley}",
            f"raw_earley={raw_earley}",
            sep="\t",
        )


LEO_GRAMMAR = (
    "doc ::= entry+\n"
    'entry ::= key "=" value ";"\n'
    "value ::= num1 | num2\n"
    "num1 ::= [0-9]\n"
    "num2 ::= [0-9]\n"
    "key ::= [a-z] [a-z0-9]*\n"
)


def prove_leo_readout() -> None:
    """The standalone ambiguity readout changes after lazy Leo expansion."""
    compiled = compile_text(LEO_GRAMMAR)
    grammar = normalize(lift_optional_nullables(compiled.codegen_grammar))
    tables = collapsed_fold_tables(grammar, compiled.fold, tier_for(4_096))
    text = "version=3;size=7;"
    kernel = Kernel(tables, text, True).run()
    root = accept_handle(kernel)
    before = len(ambiguity_points(kernel, root))
    after = len(complete_ambiguity_points(kernel, root))
    assert before == 0 and after == 2, (before, after)
    print(
        "leo-readout",
        f"deferred={len(kernel.st.leo_links)}",
        f"before={before}",
        f"after={after}",
        sep="\t",
    )


class CorpusSite(NamedTuple):
    """One authored quantified atom whose body can consume no characters."""

    path: str
    rule: str
    low: int
    high: str


class CorpusScope(NamedTuple):
    """The audited grammar population and every exposed site."""

    grammars: int
    flavours: tuple[str, ...]
    sites: tuple[CorpusSite, ...]


def corpus_scope() -> CorpusScope:
    """Inventory quantified-nullable atoms in every shipped grammar corpus."""
    root = Path(__file__).resolve().parents[3]
    found: list[CorpusSite] = []
    grammars = 0
    flavours: set[str] = set()
    paths = sorted((root / "resources" / "ground_truth").glob("*.*"))
    for path in paths:
        if path.suffix not in (".gbnf", ".abnf", ".ebnf"):
            continue
        grammars += 1
        flavours.add(path.suffix.removeprefix("."))
        grammar = canonical_grammar(
            path.read_text(encoding="utf-8"), flavour_for_extension(path)
        )
        analysis = GrammarAnalysis(grammar)
        for rule in grammar.rules:
            for arm in rule.body:
                for part in arm:
                    if not isinstance(part, IrItem):
                        continue
                    quantifier = part.quantifier
                    low = int(quantifier.lo)
                    high = str(quantifier.hi)
                    if low == 1 and high == "1":
                        continue
                    if analysis.atom_nullable(part.atom):
                        found.append(CorpusSite(path.name, str(rule.name), low, high))
    return CorpusScope(grammars, tuple(sorted(flavours)), tuple(found))


def prove_corpus_scope() -> None:
    """Report real cross-flavour exposure before implementing refusal."""
    scope = corpus_scope()
    print(
        "corpus",
        f"grammars={scope.grammars}",
        f"flavours={scope.flavours}",
        f"quantified_nullable_sites={len(scope.sites)}",
        f"sites={scope.sites}",
        sep="\t",
    )


def main() -> None:
    """Run both shipped-bug scopes without modifying production code."""
    prove_quantifier_scope()
    prove_leo_readout()
    prove_corpus_scope()


if __name__ == "__main__":
    main()
