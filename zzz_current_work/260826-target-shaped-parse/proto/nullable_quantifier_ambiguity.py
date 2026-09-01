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

import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from lexic.compile import (
    canonical_grammar,
    compile_ast,
    compile_from_path,
    compile_text,
)
from lexic.compile.artifact import CompiledGrammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import flavour_for_extension
from lexic.ir import IrAst, IrItem, IrNode, IrSelf
from lexic.model import GrammarModel
from lexic.parsing import earley_model, parse_model, pda_tables
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
    control_gap: str = 'gap ::= item\nitem ::= "a"\n'
    control_text: str = "xa"

    @property
    def grammar(self) -> str:
        """The complete grammar for this case."""
        return f'root ::= pad list\nlist ::= {self.body}\n{self.gap}pad ::= "x"\n'

    @property
    def control(self) -> str:
        """The matched grammar whose quantified atom is NOT nullable."""
        return (
            f'root ::= pad list\nlist ::= {self.body}\n{self.control_gap}pad ::= "x"\n'
        )


CASES = (
    Case("star-ref", "gap*"),
    Case("plus-ref", "gap+"),
    Case("optional-ref", "gap?"),
    Case("bounded-zero-two", "gap{0,2}"),
    Case("bounded-one-two", "gap{1,2}"),
    Case("exact-two", "gap{2}", control_text="xaa"),
    Case("star-group", "(gap)*"),
    Case("star-empty-rule", "gap*", 'gap ::= ""\n', 'gap ::= "a"\n'),
)

BASELINE: dict[str, tuple[str, str, str, str]] = {
    "star-ref": (
        "Root(Pad('x'), List(()))",
        "Root(Pad('x'), List(()))",
        "Root(Pad('x'), List(()))",
        "Root(Pad('x'), List(()))",
    ),
    "plus-ref": (
        "Root(Pad('x'), List((Gap(),)))",
        "Root(Pad('x'), List((Gap(),)))",
        "Root(Pad('x'), List((Gap(),)))",
        "Root(Pad('x'), List((Gap(),)))",
    ),
    "optional-ref": (
        "Root(Pad('x'), List(Gap()))",
        "Root(Pad('x'), List(Gap()))",
        "Root(Pad('x'), List(Gap()))",
        "Root(Pad('x'), List())",
    ),
    "bounded-zero-two": (
        "Root(Pad('x'), List(()))",
        "Root(Pad('x'), List(()))",
        "Root(Pad('x'), List(()))",
        "Root(Pad('x'), List(()))",
    ),
    "bounded-one-two": (
        "Root(Pad('x'), List((Gap(),)))",
        "Root(Pad('x'), List((Gap(),)))",
        "Root(Pad('x'), List((Gap(),)))",
        "Root(Pad('x'), List((Gap(),)))",
    ),
    "exact-two": (
        "Root(Pad('x'), List((Gap(), Gap())))",
        "Root(Pad('x'), List((Gap(), Gap())))",
        "Root(Pad('x'), List((Gap(), Gap())))",
        "Root(Pad('x'), List((Gap(), Gap())))",
    ),
    "star-group": (
        "Root(Pad('x'), List(()))",
        "Root(Pad('x'), List(()))",
        "Root(Pad('x'), List(()))",
        "Root(Pad('x'), List(()))",
    ),
    "star-empty-rule": (
        "Root(Pad('x'), List(()))",
        "Root(Pad('x'), List(()))",
        "Root(Pad('x'), List(()))",
        "Root(Pad('x'), List(()))",
    ),
}
"""The UNCONTAMINATED pre-fix answer of each route, pinned so the source phase
cannot silently redefine what it is comparing against.

Order is ``(public, pda, earley, raw_earley)``. Every entry is the wrong
answer for a case whose quantifier admits more than one occurrence count over
a nullable atom, and the right answer for ``exact-two``, which admits one."""


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
        earley = _answer(lambda: earley_model(grammar, "x", compiled.product, tables))
        raw_grammar = normalize(compiled.codegen_grammar)
        raw_tables = collapsed_fold_tables(raw_grammar, compiled.fold, tier_for(1))
        raw_earley = _answer(
            lambda: earley_model(raw_grammar, "x", compiled.product, raw_tables)
        )
        pinned = BASELINE[case.name]
        assert (public, predictive, earley, raw_earley) == pinned, (case.name, pinned)
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
    # Nothing may materialise the forest between the run and this read: the
    # defect IS that a standalone predicate is wrong before expansion, and a
    # tree build here would satisfy the hidden precondition by accident.
    deferred = len(kernel.st.leo_links)
    before = len(ambiguity_points(kernel, root))
    assert deferred > 0, deferred
    after = len(complete_ambiguity_points(kernel, root))
    assert before == 0 and after == 2, (before, after)
    forced = FastTree(kernel, {}).build(root)
    assert isinstance(forced, ParseTree)
    settled = len(ambiguity_points(kernel, root))
    assert settled == after, (settled, after)
    print(
        "leo-readout",
        f"deferred_before_any_tree={deferred}",
        f"points_before_expansion={before}",
        f"points_after_expansion={after}",
        f"points_after_a_tree_build={settled}",
        "no tree was built between the run and the first read",
        sep="\t",
    )


class CorpusSite(NamedTuple):
    """One quantified atom whose body can consume no characters."""

    path: str
    rule: str
    low: int
    high: str
    atom: str


class CorpusScope(NamedTuple):
    """The audited grammar population and every exposed site."""

    grammars: int
    flavours: tuple[str, ...]
    sites: tuple[CorpusSite, ...]


def _items(node: IrSelf) -> tuple[IrItem, ...]:
    """Every item anywhere below one grammar node, nesting included.

    A top-level walk misses a quantified item inside a group — the
    ``star-group`` shape this module itself tests — so the census recurses.
    """
    found: list[IrItem] = []
    stack: list[IrSelf] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, IrItem):
            found.append(current)
        if isinstance(current, IrNode):
            stack.extend(current.children())
    return tuple(found)


def scan_grammar(name: str, grammar: IrAst) -> tuple[CorpusSite, ...]:
    """Every quantified-nullable site in one grammar, at one pipeline stage."""
    analysis = GrammarAnalysis(grammar)
    found: list[CorpusSite] = []
    for rule in grammar.rules:
        for item in _items(rule.body):
            quantifier = item.quantifier
            low, high = int(quantifier.lo), str(quantifier.hi)
            if low == 1 and high == "1":
                continue
            if analysis.atom_nullable(item.atom):
                found.append(
                    CorpusSite(name, str(rule.name), low, high, str(item.atom))
                )
    return tuple(found)


def corpus_scope(stage: str) -> CorpusScope:
    """Inventory quantified-nullable atoms in the shipped grammar corpus.

    ``stage`` selects WHICH grammar is measured, and the two answers differ:

    - ``canonical`` is the authored grammar. It has none of these sites.
    - ``codegen`` is what the parser actually runs. The ``@non-semantic`` pass
      relaxes a required reference to a NULLABLE noise rule to ``min=0``, which
      MAKES a quantified-nullable site out of a rule that had none.

    Measuring the canonical stage and reporting it as corpus exposure is the
    error this function now exists to prevent.
    """
    root = Path(__file__).resolve().parents[3]
    found: list[CorpusSite] = []
    grammars = 0
    flavours: set[str] = set()
    for path in sorted((root / "resources" / "ground_truth").glob("*.*")):
        if path.suffix not in (".gbnf", ".abnf", ".ebnf"):
            continue
        grammars += 1
        flavours.add(path.suffix.removeprefix("."))
        canonical = canonical_grammar(
            path.read_text(encoding="utf-8"), flavour_for_extension(path)
        )
        grammar = (
            canonical
            if stage == "canonical"
            else compile_ast(canonical).codegen_grammar
        )
        found.extend(scan_grammar(path.name, grammar))
    return CorpusScope(grammars, tuple(sorted(flavours)), tuple(found))


def prove_corpus_scope() -> None:
    """Report real cross-flavour exposure at BOTH pipeline stages."""
    for stage in ("canonical", "codegen"):
        scope = corpus_scope(stage)
        per_grammar: dict[str, int] = {}
        atoms: set[str] = set()
        for site in scope.sites:
            per_grammar[site.path] = per_grammar.get(site.path, 0) + 1
            atoms.add(site.atom)
        print(
            "corpus",
            f"stage={stage}",
            f"grammars={scope.grammars}",
            f"flavours={scope.flavours}",
            f"quantified_nullable_sites={len(scope.sites)}",
            f"per_grammar={dict(sorted(per_grammar.items()))}",
            f"atoms={sorted(atoms)}",
            sep="\t",
        )


EXPOSED = (
    ("json.gbnf", '{"a": 1, "b": [2, 3]}'),
    ("json.abnf", '{"a": 1, "b": [2, 3]}'),
    ("json.ebnf", '{"a": 1, "b": [2, 3]}'),
    ("json_ws.gbnf", '{"a": 1, "b": [2, 3]}'),
    ("json_arr.gbnf", "[\n1,\n2]"),
    ("arithmetic.gbnf", "a=1\n"),
)
"""One real document per shipped grammar whose CODEGEN stage is exposed."""


def _exposure(path: Path, text: str, *, lift: bool) -> tuple[int, int, int, int]:
    """Points, arm-choice points, differing POINTS and differing FAMILIES.

    The two differing counts are reported separately on purpose: a point can
    pack more than two families, so one differing point can contribute several
    differing families, and a ratio that mixes the two denominators is not a
    fact about either.
    """
    compiled = compile_from_path(path)
    source = (
        lift_optional_nullables(compiled.codegen_grammar)
        if lift
        else compiled.codegen_grammar
    )
    grammar = normalize(source)
    tables = collapsed_fold_tables(grammar, compiled.fold, tier_for(len(text)))
    kernel = Kernel(tables, text, True).run()
    root = accept_handle(kernel)
    baseline_tree = FastTree(kernel, {}).build(root)
    if not isinstance(baseline_tree, ParseTree):
        raise UnsupportedConstructError(f"corpus exposure: {path.name} did not parse")
    baseline = compiled.fold.apply(baseline_tree)
    points = complete_ambiguity_points(kernel, root)
    bits = kernel.tables.packing.bits
    arms = sum(
        1
        for key in points
        if is_arm_choice(kernel.st.links[key], bits, kernel.tables.code_choice)
    )
    differing_points = 0
    differing_families = 0
    for key in points:
        changed = 0
        for family in range(1, len(kernel.st.links[key])):
            alternate = FastTree(kernel, {key: family}).build(root)
            if not isinstance(alternate, ParseTree):
                continue
            if not same_value(baseline, compiled.fold.apply(alternate)):
                changed += 1
        differing_points += 1 if changed else 0
        differing_families += changed
    return len(points), arms, differing_points, differing_families


def prove_corpus_exposure() -> None:
    """What the proposed fix would DO to the shipped corpus, measured.

    The decisive row of this module. Every exposed site is a
    ``@non-semantic``-relaxed reference to the nullable ``ws`` rule, and ``ws``
    IS a bound model field — a JSON document folds to ``JsonText(…, Ws(''),
    Ws(''))``. So an absent versus present empty ``ws`` is a difference the
    public model shows, and with ``lift_optional_nullables`` removed the
    shipped JSON grammars stop being a control and become the exposure.
    """
    root = Path(__file__).resolve().parents[3] / "resources" / "ground_truth"
    for name, text in EXPOSED:
        path = root / name
        lifted = _exposure(path, text, lift=True)
        raw = _exposure(path, text, lift=False)
        print(
            "corpus-exposure",
            name,
            f"chars={len(text)}",
            f"lift_on_points={lifted[0]} lift_on_differing_points={lifted[2]}",
            f"lift_off_points={raw[0]} lift_off_arm_choice={raw[1]}",
            f"lift_off_differing_points={raw[2]} lift_off_differing_families={raw[3]}",
            sep="\t",
        )


def prove_non_semantic_parse_shape() -> None:
    """Keep directive ergonomics out of the grammar the parser recognizes.

    `GrammarMoments.armed` is the exact pre-relaxation grammar. Parsing that
    shape while retaining the already-built classes and fold from the relaxed
    binding moment removes only the compiler-created optional occurrence: the
    nullable noise rule remains required in the parse and still constructs the
    same empty noise model. Authored optionality is untouched because it is
    already present in `armed`.
    """
    root = Path(__file__).resolve().parents[3] / "resources" / "ground_truth"
    for name, text in EXPOSED:
        compiled = compile_from_path(root / name)
        parse_shape = compiled.moments.grammar.armed
        lifted = lift_optional_nullables(compiled.codegen_grammar)
        grammar = normalize(parse_shape)
        tables = collapsed_fold_tables(grammar, compiled.fold, tier_for(len(text)))
        current = compiled.parse(text, cores=1)
        general = earley_model(grammar, text, compiled.product, tables)
        predictive_status = "matched current"
        try:
            predictive = pda_model(
                pda_tables(parse_shape, compiled.fold), text, compiled.fold
            )
            assert same_value(current, predictive), name
        except PdaFail:
            predictive_status = "declined to gated completion"
        gated = parse_model(parse_shape, text, compiled.fold)
        scope = _exposure(root / name, text, lift=False)
        assert same_value(current, general), name
        assert same_value(current, gated), name
        assert lifted == parse_shape, name
        assert scope[2] > 0, (name, scope)
        assert not scan_grammar(name, parse_shape), name
        print(
            "non-semantic-parse-shape",
            name,
            f"chars={len(text)}",
            f"relaxed_differing_points={scope[2]}",
            "armed_quantified_nullable_sites=0",
            f"current_lifted_grammar_equals_armed={lifted == parse_shape}",
            f"earley_matches_current={same_value(current, general)}",
            f"predictive_route={predictive_status}",
            f"gated_product_matches_current={same_value(current, gated)}",
            "the parser can retain required nullable noise while binding keeps"
            " its separate constructor ergonomics",
            sep="\t",
        )


def prove_exposure_scaling() -> None:
    """How the un-exempted point population grows with the document.

    Structural counts only — no timing. `another_meaning` builds a whole-handle
    tree and folds it per family at every point it does not skip, so a point
    population linear in the document makes the per-parse ambiguity check
    quadratic in it.
    """
    path = (
        Path(__file__).resolve().parents[3] / "resources" / "ground_truth" / "json.gbnf"
    )
    for repeats in (1, 8, 64):
        text = "[" + ", ".join('{"a": 1}' for _ in range(repeats)) + "]"
        lifted = _exposure(path, text, lift=True)
        raw = _exposure(path, text, lift=False)
        print(
            "exposure-scaling",
            "json.gbnf",
            f"chars={len(text)}",
            f"lift_on_points={lifted[0]}",
            f"lift_off_points={raw[0]}",
            f"lift_off_differing_points={raw[2]}",
            f"lift_off_differing_families={raw[3]}",
            sep="\t",
        )


def prove_island_placement() -> None:
    """Which witnesses the PDA answers WITHOUT an Earley chart.

    `code_choices` is a table the predictive runtime never consults. A witness
    the PDA islands escapes to Earley and would meet the corrected table; a
    witness it answers predictively would not. The post-fix differential asks
    all three routes to refuse, so the two populations must be separated before
    a placement can be called complete.
    """
    for case in CASES:
        compiled = compile_text(case.grammar)
        tables = pda_tables(compiled.codegen_grammar, compiled.fold)
        islands = sorted(str(name) for name in getattr(tables, "islands", ()))
        print(
            "island-placement",
            case.name,
            f"pda_islands={islands}",
            f"reaches_earley_tables={bool(islands)}",
            "code_choices can only decide a witness that escapes to Earley",
            sep="\t",
        )


def prove_leo_expansion_cost() -> None:
    """How many deferred Leo keys a complete readout would expand per parse.

    Structural counts only. `another_meaning` calls `ambiguity_points` on every
    parse, so making that call own complete Leo readout adds one eager
    expansion of every deferred key to the unambiguous path too.
    """
    path = (
        Path(__file__).resolve().parents[3] / "resources" / "ground_truth" / "json.gbnf"
    )
    compiled = compile_from_path(path)
    grammar = normalize(lift_optional_nullables(compiled.codegen_grammar))
    for repeats in (1, 16, 128, 512):
        text = "[" + ", ".join('{"a": 1}' for _ in range(repeats)) + "]"
        tables = collapsed_fold_tables(grammar, compiled.fold, tier_for(len(text)))
        kernel = Kernel(tables, text, True).run()
        print(
            "leo-expansion-cost",
            "json.gbnf",
            f"chars={len(text)}",
            f"deferred_leo_keys={len(kernel.st.leo_links)}",
            "a complete readout expands all of them on every parse",
            sep="\t",
        )


REPEATS = 2_000
"""Parses per timed lane — the witnesses are three characters long."""

ROUNDS = 5
"""Alternating rounds; the reported figure is the minimum of the rounds."""


def _lane(compiled: CompiledGrammar, text: str) -> float:
    """One lane's process CPU for :data:`REPEATS` unchanged public parses."""
    started = time.process_time()
    for _ in range(REPEATS):
        compiled.parse(text, cores=1)
    return time.process_time() - started


def prove_baseline_timing() -> None:
    """Time UNCHANGED public parsing on each witness and a matched control.

    In-process and alternating because nothing is being swapped yet: this is
    the pre-fix reference the source phase re-runs. The control is the SAME
    grammar shape with a non-nullable quantified atom, so it exercises the
    same quantifier helper, the same fold and the same public entry.

    The two lanes do NOT parse the same document — a non-nullable ``gap+``
    cannot accept ``"x"`` — so the ratio between them is not a matched
    comparison and is reported as two absolute numbers, never as a factor. The
    island flag is printed beside them because it, not the ambiguity check, is
    what separates the fast rows from the slow ones.

    Run this row on its own: no other benchmark, pool or agent may be alive.
    """
    for case in CASES:
        affected = compile_text(case.grammar)
        control = compile_text(case.control)
        affected.parse("x", cores=1)
        control.parse(case.control_text, cores=1)
        affected_cpu = []
        control_cpu = []
        for round_index in range(ROUNDS):
            if round_index % 2 == 0:
                affected_cpu.append(_lane(affected, "x"))
                control_cpu.append(_lane(control, case.control_text))
                continue
            control_cpu.append(_lane(control, case.control_text))
            affected_cpu.append(_lane(affected, "x"))
        best_affected = min(affected_cpu) / REPEATS
        best_control = min(control_cpu) / REPEATS
        islands = sorted(
            str(name)
            for name in getattr(
                pda_tables(affected.codegen_grammar, affected.fold), "islands", ()
            )
        )
        print(
            "baseline-timing",
            case.name,
            f"parses_per_lane={REPEATS}",
            f"rounds={ROUNDS}",
            f"affected_document='x' affected_cpu_per_parse={best_affected:.9f}",
            f"control_document={case.control_text!r}"
            f" control_cpu_per_parse={best_control:.9f}",
            f"affected_pda_islands={islands}",
            "documents differ, so these are two absolute numbers and not a"
            " ratio; the island escape is what separates them",
            sep="\t",
        )


POST_FIX_DIFFERENTIALS = (
    "every CASES row except exact-two must REFUSE under compiled.parse(text)"
    " with no resolver, on the public route, forced pda_model and forced"
    " earley_model alike; the refusal must name the rule and the occurrence"
    " counts, not a generic ambiguity. optional-ref, bounded-one-two and"
    " exact-two do NOT island, so the predictive route answers them without an"
    " Earley chart and code_choices cannot reach them: a PDA-side placement in"
    " pda/analysis/gates/ is required, and its cost is not measured here",
    "exact-two must still return Root(Pad('x'), List((Gap(), Gap()))) — one"
    " admitted count is not a family",
    "with a deterministic resolver supplied, all three routes must return the"
    " resolver's choice and must be handed the SAME pair under whichever"
    " scope the user rules in the resolver-scope decision",
    "optional-ref must agree between the authored parser grammar and every"
    " engine route; today the relaxed grammar and its lifted parser shape"
    " return List() and List(Gap()) respectively, so"
    " lift_optional_nullables and the optional parser shape both leave",
    "the SIX exposed ground-truth grammars — arithmetic.gbnf, json.gbnf,"
    " json.abnf, json.ebnf, json_arr.gbnf, json_ws.gbnf — must still parse"
    " ordinary documents through the pre-relaxation armed grammar while the"
    " generated constructors keep their relaxed shape. All six match today's"
    " public model in the executed proof; the other NINE must reparse to"
    " byte-identical models and round-trip text",
    "ambiguity_points on the LEO_GRAMMAR witness must return 2 on a finished"
    " kernel with no intervening tree build, and the same 2 afterwards",
    "cyclic_meaning's witnesses must keep their current verdicts: the"
    " quantified-nullable family is a SEPARATE universe and must not change"
    " any component classification",
)

REGRESSION_COMPARISON = (
    "the family classification is present on every parse, so it is a"
    " STRUCTURAL change: compare two trees CROSS-PROCESS, alternating, with a"
    " byte-identical control tree through the same harness to read the floor",
    "rows: the 15 ground-truth grammars parsed by their own flavours, the"
    " generic catalog witness, and the Qwen tokenizer document; sequential"
    " first, then cores=AUTO, never two multithreaded rows at once",
    "report process CPU and wall separately, per row, with the control floor"
    " beside them; a row inside the floor is not a result",
    "no parse regression is accepted by this report; the user gives the final"
    " go-ahead after isolated attribution, even for a bugfix",
    "BUG 2's complete Leo readout is NOT free: ambiguity_points runs on every"
    " parse and the deferred key population is linear in the document (2 / 17"
    " / 129 / 513 keys at 10 / 160 / 1280 / 5120 characters on json.gbnf), so"
    " eager expansion on the unambiguous path reverses part of what Leo buys"
    " and must be measured with the same cross-process discipline",
)

IMPLEMENTATION_PLACEMENT = (
    "the parser recognizes the armed grammar, before @non-semantic relaxation;"
    " the relaxed grammar remains the binding and synthesis shape that gives"
    " generated constructors their optional noise fields. For token-bound"
    " grammars the parse-ready moment is concretize(armed, registry), not the"
    " existing resolved-relaxed moment",
    "the current lifted relaxed grammar equals the armed grammar on all six"
    " exposed fixtures, and parsing armed with the existing relaxed fold"
    " returns the current public model through Earley and the gated product."
    " The forced PDA matches on four and lawfully declines on json_ws.gbnf"
    " and json_arr.gbnf, after which the gated product still matches",
    "the 71 relaxed quantified-nullable sites are compiler-manufactured and"
    " never enter the parser grammar, so they create neither semantic families"
    " nor the measured linear point population. Authored optional nullable"
    " sites remain in armed and still enter the complete meaning relation",
    "delete lift_optional_nullables rather than preserve a canceling"
    " relax-then-lift parser path. Keep the relaxation only where its separate"
    " constructor contract consumes it, and name the two moments so no caller"
    " mistakes a binding shape for a recognition shape",
    "the classification belongs in code_choices"
    " (parsing/earley/kernel/tables/records.py), which already derives"
    " code -> authored choice identity at TABLE-COMPILATION time: a quantifier"
    " helper keeps its shared negative identity only when its atom is"
    " non-nullable or its quantifier admits exactly one count, and takes"
    " distinct arm ids otherwise",
    "the nullability it reads is a grammar property the analysis already"
    " computes (GrammarAnalysis.atom_nullable); nothing per-character, nothing"
    " dynamic, and no instrumentation in the paid loop",
    "the paid loop never reads code_choice at all — only the forest readers"
    " do — so the authored-family classification does not touch the kernel's"
    " inner loop. Complete family discovery remains cold ambiguity work",
)


def prove_post_fix_specification() -> None:
    """State the exact differentials the source phase must satisfy."""
    canonical = len(corpus_scope("canonical").sites)
    codegen = len(corpus_scope("codegen").sites)
    assert (canonical, codegen) == (0, 71), (canonical, codegen)
    for line in POST_FIX_DIFFERENTIALS:
        print("post-fix-differential", line, sep="\t")
    for line in REGRESSION_COMPARISON:
        print("regression-comparison", line, sep="\t")
    for line in IMPLEMENTATION_PLACEMENT:
        print("implementation-placement", line, sep="\t")


def main() -> None:
    """Run both shipped-bug scopes without modifying production code."""
    prove_quantifier_scope()
    prove_leo_readout()
    prove_corpus_scope()
    prove_corpus_exposure()
    prove_non_semantic_parse_shape()
    prove_exposure_scaling()
    prove_island_placement()
    prove_leo_expansion_cost()
    prove_baseline_timing()
    prove_post_fix_specification()


if __name__ == "__main__":
    main()
