"""Does one proved consult decide the same extent the per-character program does?

The consult replaces a clone's whole program — arm selection, every descent
under it, every per-character loop inside those — with one possessive match.
The claim that buys is an EXTENT: the recognizer stops exactly where the
interpreted program would have stopped. Nothing else about the consult matters
if that is ever false, and a model comparison alone cannot see it, because a
wrong extent usually fails the parse and `parse()` then quietly completes on
Earley and returns the right model.

So this drives `pda_model` DIRECTLY — a `PdaFail` surfaces instead of being
absorbed — and compares three answers per document: the predictive engine with
consults live, the same engine with consults suppressed (the program that
shipped before), and the Earley oracle. Every consult call is recorded, and
each rule's recorded spans are compared as a MULTISET against that rule's own
values in the consult-free model, so the row is per occurrence rather than per
document.

A grammar whose consult clones are never reached is reported UNEXERCISED
rather than counted as agreement.

Run: `uv run python zzz_current_work/260826-target-shaped-parse/proto/s4_extent_differential.py`

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

import random
from collections import Counter
from pathlib import Path
from typing import NamedTuple

import lexic.parsing.pda.compiler.program.lower as lowering
import lexic.parsing.pda.compiler.program.specialize as specialize
import lexic.parsing.pda.runtime.matchers as matchers
from lexic.compile import compile_from_path
from lexic.compile.artifact import CompiledGrammar
from lexic.exceptions import LexicError
from lexic.generate import generate
from lexic.model import GrammarModel
from lexic.parsing.caches import reset_caches
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.pda.compiler.program.flatten import FlatArm, FlatClone
from lexic.parsing.pda.compiler.program.opcodes import OP_CONSULT
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.products import _model_product, earley_model, reset_product_cache

ROOT = Path(__file__).resolve().parents[3]
GROUND_TRUTH = ROOT / "resources" / "ground_truth"
SEEDS = tuple(range(40))
"""Fixed seeds, so a disagreement is replayable rather than anecdotal."""

AUTHORED = {
    "c.gbnf": (
        "int f(){if(a<=b){//hi\n}}",
        "int f(){if(a<b){}}int g(){if(x>=y){}}",
        "int f(){while(n!=m){//loop\n}}",
        "int f(){if(p==q){}else{//else\n}}",
        "float g(int a){char b = c;if(b>a){//tail\n}}",
    ),
}
"""Documents written to reach a consult clone the generator reaches rarely.
Only ever ADDED to the generated set: a witness that measured hand-picked text
alone would be measuring the author's expectations."""

_BAKE_CONSULTS = specialize.bake_consults
_CONSULT_MAP = lowering._consults
_CONSULT_EXTENT = matchers.consult_extent


class Occurrence(NamedTuple):
    """One consult call, as it happened.

    :ivar rule: The clone's rule name.
    :ivar pos: Where it was asked.
    :ivar span: The text between there and what it answered.
    """

    rule: str
    pos: int
    span: str


class Row(NamedTuple):
    """One grammar's differential result.

    :ivar name: The grammar file.
    :ivar clones: How many clones carry a consult arm.
    :ivar rules: The rule names those clones stand for.
    :ivar documents: Documents compared.
    :ivar occurrences: Consult calls made across them.
    :ivar declined: Documents both predictive passes declined.
    :ivar speculative: Consults whose span was abandoned before any model.
    """

    name: str
    clones: int
    rules: tuple[str, ...]
    documents: int
    occurrences: int
    declined: int
    speculative: int


INSTALLED: list[str] = []
"""Rule names of the clones the last compile gave a consult arm."""

SEEN: list[Occurrence] = []
"""Every consult call of the run in progress."""


class Defect(AssertionError):
    """A claim this witness makes that the corpus does not support."""


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise Defect(f"s4 extent: {claim}")


def _recording_bake(clones: list[FlatClone], consults: object) -> None:
    """The shipped consult bake, plus a note of which clones took one."""
    _BAKE_CONSULTS(clones, consults)
    INSTALLED.extend(
        clone.name
        for clone in clones
        if clone.runarm is not None and clone.runarm.kinds[0] == OP_CONSULT
    )


def _recording_extent[Carry](
    text: str, clone: FlatClone[Carry], runarm: FlatArm, pos: int
) -> int:
    """The shipped consult, plus the span it decided."""
    end = _CONSULT_EXTENT(text, clone, runarm, pos)
    SEEN.append(Occurrence(clone.name, pos, text[pos:end]))
    return end


def _cold() -> None:
    """Drop every memo, so the next parse recompiles under the live patches."""
    reset_product_cache()
    reset_caches()


def _documents(compiled: CompiledGrammar, name: str) -> list[str]:
    """Real documents for one grammar: the generator's, then the authored ones."""
    ast = compiled.grammar
    rules = {str(rule.name): rule for rule in ast.rules}
    texts = [generate(str(ast.start), rules, rng=random.Random(seed)) for seed in SEEDS]
    return [text for text in texts if text] + list(AUTHORED.get(name, ()))


def _pda_models(
    compiled: CompiledGrammar, documents: list[str]
) -> list[GrammarModel | None]:
    """Every document through the PREDICTIVE engine alone — no Earley fallback.

    ``None`` is a decline, kept rather than absorbed: the predictive engine
    does not claim every document, and a document it declines in BOTH passes
    says nothing about the consult. One it declines only when consults are
    live is the defect this shape exists to catch.
    """
    out: list[GrammarModel | None] = []
    for text in documents:
        product = _model_product(
            compiled.codegen_grammar, compiled.product, tier_for(len(text))
        )
        try:
            out.append(pda_model(product.pda, text, compiled.executor))
        except PdaFail:
            out.append(None)
    return out


def _earley_models(
    compiled: CompiledGrammar, documents: list[str]
) -> list[GrammarModel]:
    """The same documents through the gated engine — the independent oracle."""
    out: list[GrammarModel] = []
    for text in documents:
        product = _model_product(
            compiled.codegen_grammar, compiled.product, tier_for(len(text))
        )
        out.append(
            earley_model(
                product.instance_grammar, text, compiled.product, product.tables
            )
        )
    return out


def _consult_free(
    compiled: CompiledGrammar, documents: list[str]
) -> list[GrammarModel | None]:
    """The same documents through the program that shipped before the consult."""
    lowering._consults = lambda _clones, _low: {}
    try:
        _cold()
        return _pda_models(compiled, documents)
    finally:
        lowering._consults = _CONSULT_MAP
        _cold()


def _models_of(compiled: CompiledGrammar, rule: str, root: GrammarModel) -> list[str]:
    """Every value one rule contributed to ``root``, as text.

    The rule's own declared constructor is the identity used, not a name
    guessed from the rule's spelling — a value-string rule's model IS its
    matched extent, so this is the per-occurrence oracle the recorded spans
    are compared against.
    """
    routine = compiled.product.routines.get(rule)
    _check(f"{rule}: no routine to read a class off", routine is not None)
    assert routine is not None
    construction = routine.construction
    _check(f"{rule}: no construction to read a class off", construction is not None)
    assert construction is not None
    found: list[GrammarModel] = []
    _collect(root, construction.call, found)
    return [model.to_text() for model in found]


def _collect(node: object, call: object, out: list[GrammarModel]) -> None:
    """Every descendant built by ``call``, in walk order."""
    if isinstance(node, GrammarModel) and type(node) is call:
        out.append(node)
    if isinstance(node, tuple):
        for child in node:
            _collect(child, call, out)


def _per_occurrence(
    compiled: CompiledGrammar,
    parses: list[tuple[GrammarModel, list[Occurrence]]],
    rules: tuple[str, ...],
) -> int:
    """Every recorded span against that rule's own values in the plain model.

    Two claims, and the second is why this is not plain equality. A consult can
    be ASKED inside a speculative descent the kernel then abandons, so a
    decided span need not reach a model — but every span that does reach one
    must have been decided, and one position must never be decided two ways.

    :returns: The consults whose span did not reach a model — speculative
        re-asks, reported rather than hidden.
    """
    surplus = 0
    for rule in rules:
        decided: Counter[str] = Counter()
        meant: Counter[str] = Counter()
        for model, seen in parses:
            decided.update(
                occurrence.span for occurrence in seen if occurrence.rule == rule
            )
            meant.update(_models_of(compiled, rule, model))
            _positions_agree(rule, seen)
        _check(
            f"{rule}: the model holds values no consult decided ({meant - decided})",
            not (meant - decided),
        )
        surplus += sum((decided - meant).values())
    return surplus


def _positions_agree(rule: str, seen: list[Occurrence]) -> None:
    """One position, one extent — within a single document's parse."""
    answers: dict[int, str] = {}
    for occurrence in seen:
        if occurrence.rule != rule:
            continue
        was = answers.setdefault(occurrence.pos, occurrence.span)
        _check(
            f"{rule}: position {occurrence.pos} was decided both {was!r} and "
            f"{occurrence.span!r} in one document",
            was == occurrence.span,
        )


def _consulting_pass(
    compiled: CompiledGrammar, documents: list[str]
) -> tuple[list[GrammarModel | None], list[list[Occurrence]]]:
    """The consulting pass, document by document, keeping each one's calls.

    Per document rather than in bulk so a declined document's consults can be
    dropped: they decided extents in a parse that never produced a model, and
    counting them against a model would compare two different populations.
    """
    models: list[GrammarModel | None] = []
    slices: list[list[Occurrence]] = []
    matchers.consult_extent = _recording_extent
    try:
        for text in documents:
            mark = len(SEEN)
            models.extend(_pda_models(compiled, [text]))
            slices.append(SEEN[mark:])
    finally:
        matchers.consult_extent = _CONSULT_EXTENT
    return models, slices


def _one_grammar(path: Path) -> Row:
    """One grammar: three engines, every document, every consult occurrence."""
    compiled = compile_from_path(path)
    INSTALLED.clear()
    _cold()
    documents = _documents(compiled, path.name)
    _check(f"{path.name}: the generator produced no document", bool(documents))
    # One warm compile, snapshotted: a document of another size recompiles at
    # its own packing tier, and counting those would report one clone per tier.
    INSTALLED.clear()
    _model_product(
        compiled.codegen_grammar, compiled.product, tier_for(len(documents[0]))
    )
    installed = list(INSTALLED)
    rules = tuple(sorted(set(installed)))
    SEEN.clear()
    with_consult, slices = _consulting_pass(compiled, documents)
    if not rules:
        return Row(path.name, 0, (), 0, 0, 0, 0)
    plain = _consult_free(compiled, documents)
    oracle = _earley_models(compiled, documents)
    compared = _compare(path.name, documents, with_consult, plain, oracle)
    parses = [(_model(plain[at]), slices[at]) for at in compared]
    surplus = _per_occurrence(compiled, parses, rules)
    return Row(
        path.name,
        len(installed),
        rules,
        len(compared),
        sum(len(seen) for _model, seen in parses),
        len(documents) - len(compared),
        surplus,
    )


def _model(found: GrammarModel | None) -> GrammarModel:
    """A model the comparison already proved present."""
    _check("a compared document had no model after all", found is not None)
    assert found is not None
    return found


def _compare(
    name: str,
    documents: list[str],
    with_consult: list[GrammarModel | None],
    plain: list[GrammarModel | None],
    oracle: list[GrammarModel],
) -> list[int]:
    """The documents both predictive passes claimed, checked three ways.

    :returns: The indices compared — the rest were declined by BOTH passes,
        which is the predictive engine's own reach and not the consult's.
    """
    compared: list[int] = []
    for at, text in enumerate(documents):
        got, was = with_consult[at], plain[at]
        _check(
            f"{name}/doc {at}: the consult changed what the engine can parse "
            f"(consult={got is not None}, plain={was is not None})",
            (got is None) == (was is None),
        )
        if got is None:
            continue
        _check(
            f"{name}/doc {at}: consult built {got!r}, consult-free {was!r}", got == was
        )
        _check(
            f"{name}/doc {at}: consult built {got!r}, Earley {oracle[at]!r}",
            got == oracle[at],
        )
        _check(
            f"{name}/doc {at}: the model does not round-trip to its document",
            got.to_text() == text,
        )
        compared.append(at)
    return compared


def _grammars() -> list[Path]:
    """The ground-truth corpus, in a fixed order."""
    paths = sorted(GROUND_TRUTH.glob("*.gbnf"))
    return (
        paths
        + sorted(GROUND_TRUTH.glob("*.abnf"))
        + sorted(GROUND_TRUTH.glob("*.ebnf"))
    )


def main() -> None:
    """Run the differential over every grammar that installs a consult."""
    specialize.bake_consults = _recording_bake
    rows: list[Row] = []
    skipped: list[str] = []
    try:
        for path in _grammars():
            try:
                rows.append(_one_grammar(path))
            except LexicError as refusal:
                skipped.append(f"{path.name} ({refusal.args[0][:40]}…)")
    finally:
        specialize.bake_consults = _BAKE_CONSULTS
        _cold()
    carrying = [row for row in rows if row.clones]
    print(
        f"{'grammar':<20}{'clones':>7}{'docs':>6}{'declined':>9}{'consults':>9}"
        f"{'specul.':>8}  rules"
    )
    for row in carrying:
        print(
            f"{row.name:<20}{row.clones:>7}{row.documents:>6}{row.declined:>9}"
            f"{row.occurrences:>9}{row.speculative:>8}  {', '.join(row.rules)}"
        )
    unexercised = [row.name for row in carrying if not row.occurrences]
    _check(f"consult clones were never reached in {unexercised}", not unexercised)
    _check(
        "no grammar installed a consult — the differential is vacuous", bool(carrying)
    )
    print(
        f"\ntotal\t{len(carrying)} grammars carry consults, "
        f"{sum(row.clones for row in carrying)} clones, "
        f"{sum(row.occurrences for row in carrying)} occurrences, "
        f"{sum(row.documents for row in carrying)} documents compared three ways"
    )
    print(
        f"clean\t{len(rows) - len(carrying)} grammars install none; skipped {skipped}"
    )
    print(
        "s4 extent differential\tPASS\tone consult decides the extent the program does"
    )


if __name__ == "__main__":
    main()
