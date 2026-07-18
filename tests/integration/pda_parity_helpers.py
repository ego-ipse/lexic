"""Shared PDA-vs-engine differential helpers (``test_pda_parity.py`` cluster).

Also consumed by ``tests.integration.test_delegation_parity`` (the A/B
delegate-compile toggle drives the same per-grammar generation seam) and
``tests.unit.lexic.parsing.pda.runtime.test_runtime``/``golden_fixtures``
(the arithmetic bench corpus).
"""

from __future__ import annotations

from typing import cast

from lexic.compile import (
    CompiledGrammar,
    canonical_grammar,
    compile_from_path,
    compile_text,
)
from lexic.grammars import flavour_for_extension
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.model import GrammarModel
from lexic.parsing import parse_first
from lexic.parsing.pda.compiler.specs import IslandRef
from lexic.parsing.pda.runtime.reduce_runtime import parse_pda
from lexic.parsing.pda.runtime.runtime import PdaFail
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.parsing_helpers import _prod

# Mirrors tools/benchmark/pipeline_bench.py's arithmetic instance workload
# (same snippets, same ~4800-char target) — not imported (that module builds
# its own corpus for timing, not as an importable package) but pinned here as
# the same data so the runtime parity test exercises the actual bench corpus
# shape. Public (not module-private) so tests/integration/golden_fixtures.py can import
# the same literals rather than duplicating them (pylint R0801).
ARITHMETIC_BENCH_SNIPPETS: tuple[str, ...] = (
    "x=1\n",
    "y=z\n",
    "a+b=100\n",
    "foo=(bar)\n",
    "abc123-xyz=42\n",
)


def _arithmetic_bench_corpus(target_len: int = 4800) -> str:
    """The pinned arithmetic bench corpus, cycled to at least ``target_len`` chars."""
    pieces: list[str] = []
    size = 0
    n = 0
    while size < target_len:
        piece = ARITHMETIC_BENCH_SNIPPETS[n % len(ARITHMETIC_BENCH_SNIPPETS)]
        pieces.append(piece)
        size += len(piece)
        n += 1
    return "".join(pieces)


# A couple of representative bench-shaped corpora. json's mirrors
# tools/benchmark/pipeline_bench.py's ``_JSON_ITEMS``/``_json_corpus`` (same
# items, same target length) — pinned locally since nothing else in the test
# tree defines it yet.
_JSON_BENCH_ITEMS: tuple[str, ...] = (
    '{"name": "alpha", "id": 1, "ok": true}',
    '{"nested": {"a": [1, 2.5e3, -4], "b": null}}',
    '"quote \\" backslash \\\\ unicode \\u0041 tab \\t"',
    "-12.75e-2",
    '[true, false, null, 0, "s"]',
    '{"deep": [{"x": [[1], [2.0]]}], "y": false}',
)


def _json_bench_corpus(target_len: int = 4200) -> str:
    """One JSON document (single top-level array) of at least ``target_len`` chars."""
    items: list[str] = []
    total = 0
    i = 0
    while total < target_len:
        piece = _JSON_BENCH_ITEMS[i % len(_JSON_BENCH_ITEMS)]
        items.append(piece)
        total += len(piece) + 4
        i += 1
    return "[\n  " + ",\n  ".join(items) + "\n]\n"


_START_OVERRIDES: dict[str, str] = {
    # c's natural start ``root ::= (declaration)*`` is ``lo=0`` and rolls
    # empty 70% of the time (``generate``'s ``_pick_count``) — thin coverage
    # over 40 seeds. ``tests/property/conftest.py``'s ``c_statement_grammar``
    # fixture solves the identical problem the same way: drive generation
    # from "statement" instead (if/while/for/return/assignment/call/comments
    # — and c's own islands, e.g. ``relationoperator``/``statement-arm7``).
    "c.gbnf": "statement",
}


def _grammar_for(stem: str) -> tuple[CompiledGrammar, dict, str]:
    """Compile ``stem``, resolving its generation start rule.

    :returns: ``(compiled grammar, {rule_name: IrRule}, start rule name)`` —
        the start defaults to the grammar's own resolved start rule (so
        json/json.abnf generate from ``JSON-text``, not a hardcoded
        ``"root"``), overridden per :data:`_START_OVERRIDES` where the
        natural start gives thin coverage.
    """
    path = GROUND_TRUTH / stem
    override = _START_OVERRIDES.get(stem)
    if override is None:
        flavour = flavour_for_extension(path)
        canonical = canonical_grammar(path.read_text(encoding="utf-8"), flavour)
        specs = {r.name: r for r in canonical.rules}
        cg = compile_from_path(path)
        return cg, specs, str(canonical.start)
    text = path.read_text(encoding="utf-8") + f"\n# @start {override}\n"
    canonical = canonical_grammar(text, GBNF_FLAVOUR)
    specs = {r.name: r for r in canonical.rules}
    cg = compile_text(text, cache_key=f"pda-parity-{stem}-{override}-start")
    return cg, specs, override


def _forced_engine(cg: CompiledGrammar, text: str) -> GrammarModel:
    """Parse ``text`` via the forced-engine seam (bypassing the PDA entirely)."""
    tree = parse_first(_prod(cg).instance_grammar, text, _prod(cg).tables)
    return cast(GrammarModel, cg.fold.apply(tree))


def _deep_semantic(value: object) -> object:
    """The ruling-1 comparator: drop ``semantic=False`` binds at EVERY level.

    ``semantic_dump()``'s exclusion is top-level-only (R2-5); the prior
    declared-schema dump's erasure (F-DUMP-1) happened to hide nested noise
    splits too, so ``semantic_dump()`` equality *looked* like the ruling-1
    bar. The runtime-complete native dump exposes those nested
    ``semantic=False`` fields, so the noise split the PDA is licensed to
    make differently (see the module docstring) must be dropped explicitly,
    at every model level, before comparing.
    """
    if isinstance(value, GrammarModel):
        return {
            name: _deep_semantic(getattr(value, name)) for name in value.semantic_dump()
        }
    if isinstance(value, tuple):
        return [_deep_semantic(sub) for sub in value]
    return value


def _check_one(cg: CompiledGrammar, text: str, tally: dict) -> None:
    """Run both seams on ``text``, tally the outcome, assert what parity demands.

    :raises UnsupportedConstructError: Propagated from the engine path on a
        generator-overshoot input the grammar itself rejects — the caller
        skips the sample rather than counting it.
    """
    engine_model = _forced_engine(cg, text)
    assert engine_model.to_text() == text
    if isinstance(_prod(cg).pda.start_key, IslandRef):
        tally["checked"] += 1
        tally["engine_only"] += 1
        return
    try:
        pda_model = cast(GrammarModel, parse_pda(_prod(cg).pda, text, cg.fold))
    except PdaFail:
        tally["fallback"] += 1
        tally["checked"] += 1
        return
    tally["pda_ok"] += 1
    tally["checked"] += 1
    assert _deep_semantic(pda_model) == _deep_semantic(engine_model)
    assert pda_model.to_text() == text
    if pda_model.dump() == engine_model.dump():
        tally["dump_exact"] += 1


def _report(stem: str, cg: CompiledGrammar, tally: dict) -> None:
    """Print the per-grammar summary line (reported, not asserted)."""
    n = tally["checked"] or 1
    if isinstance(_prod(cg).pda.start_key, IslandRef):
        print(
            f"{stem:16s} checked={tally['checked']:3d} ENGINE-ONLY (whole-grammar PDA opt-out)"
        )
        return
    islands = sorted(_prod(cg).pda.islands)
    exact = (
        f"{tally['dump_exact'] / tally['pda_ok']:5.1%}" if tally["pda_ok"] else "n/a"
    )
    print(
        f"{stem:16s} checked={tally['checked']:3d} "
        f"pda_ok={tally['pda_ok']:3d} "
        f"fallback_rate={tally['fallback'] / n:5.1%} "
        f"dump_exact_rate={exact} "
        f"islands({len(islands)})={islands}"
    )
