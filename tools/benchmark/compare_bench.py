"""Unified path comparison — the same input, every way at once.

The other two benches each measure one slice: ``parse_bench`` races Lark
against the engine's **Earley** grammar-text path, and ``pipeline_bench`` times
the instance product. Neither puts **Lark**, **Earley**, and the **full PDA**
on the same input side by side, so their numbers cannot be read against each
other. This harness does: for each input text it times every applicable path
and prints them in one row, so "on this string, the PDA is X, Earley is Y,
Lark is Z" is a direct read.

## The six columns

- **lark-lalr** / **lark-earley** — the external reference, given every sample a
  native Lark grammar (``lark_refs``) and run under **both** of Lark's parsers,
  each its own column, timed at Lark's native output: ``parser.parse(text)`` → a
  Lark ``Tree`` (LALR uses the contextual lexer). Lark is *not* burdened with a
  second-pass transform to ``IrAst`` — that is work its native pipeline does not
  do. Where LALR is not viable for a grammar (it builds with conflicts then
  fails to parse the corpus — the two meta-grammars), the ``lark-lalr`` cell is
  empty and the row carries the failure note; LALR is never silently swapped for
  Earley.
- **earley** — the engine's Earley completion (``earley_reduce`` for
  grammar-text, ``earley_model`` for instances) → the typed ``IrAst`` / model.
- **parse-first** (instance rows only) — ``parse_first`` over the same
  normalised grammar and collapsed tables the ``earley`` column uses, but
  WITHOUT the fold: recognition + one derivation → a ``ParseTree``. The
  decomposition read: ``earley − parse-first`` is the fold's own cost, and
  ``parse-first`` vs ``pda`` is tree-then-fold Earley against the PDA's fused
  model build. Like Lark it is verified by recognition only — a ``ParseTree``
  is not the engine's typed result.
- **pda** — the engine's full predictive PDA (``pda_reduce``/``pda_model`` over the compiled
  tables — the exact path the product runs first, islands sub-parsed inline) →
  the typed ``IrAst`` / model.
- **product** — the public product entry itself (``parse_reduced`` for
  grammar-text, ``CompiledGrammar.parse`` for instances): PDA-first with the
  Earley completion inside, memoised per identity. Expected to read ≡ ``pda``;
  the delta IS the product-entry + memo-lookup overhead. Equality-gated
  against the reference like the other engine paths.

Because Lark yields a generic ``Tree`` while the engine builds a typed result,
the two ``lark`` columns omit construction the ``earley`` / ``pda`` columns
include — a fair reading of the numbers keeps that in mind.

## The two input families

- **grammar-text** (text → ``IrAst``): the ABNF/GBNF self-emit sources, each
  concatenated x1/x2/x4.
- **instance** (text → model): the ground-truth arithmetic/c/chess/json
  corpora parsed against their compiled grammars.

## Correctness gate

Before timing a case, every path is run once. The two **engine** paths are
cross-checked for output equality (``IrAst`` for grammar-text, round-trip
``to_text`` for models) — racing diverging implementations is meaningless, so a
divergence is reported loudly. **Lark** is verified by *recognition* — that it
parses the input without error — since its native ``Tree`` is a different shape
from the engine's typed result and cannot be equality-compared. An engine path
that raises ``PdaFail`` (an island start) is dropped from the timing.

Timing discipline (shared with ``parse_bench``): interleaved samples (one of
every path per round, so machine drift hits all alike), gc disabled per sample,
median ± stdev in ms, µs/char throughput, and a ``×pda`` ratio column.

Usage:
  uv run python tools/benchmark/compare_bench.py
  uv run --with lark python tools/benchmark/compare_bench.py   # force lark on
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from types import ModuleType
from typing import Callable

from lexic.compile import compile_from_path
from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir import IrFlavour
from lexic.model import GrammarModel
from lexic.parsing import parse_first, parse_reduced
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce.reducer import Reducer
from lexic.parsing.pda.runtime.reduce_runtime import pda_model, pda_reduce
from lexic.parsing.pda.runtime.runtime import PdaFail
from lexic.parsing.products import (
    _model_product,
    _reduce_product,
    earley_model,
    earley_reduce,
)
from tools.benchmark.lark_refs import lark_mirror_variants, lark_variants
from tools.benchmark.parse_bench import SIZES, interleaved, load_lark, make_input
from tools.benchmark.pipeline_bench import _INSTANCE_WORKLOADS, GROUND_TRUTH

Path = Callable[[str], object]
# column order; absent paths render "—". Both Lark parsers race every sample.
_ORDER = (
    "lark-lalr",
    "lark-earley",
    "lark-lalr-same",
    "lark-earley-same",
    "earley",
    "parse-first",
    "pda",
    "product",
)
# engine paths whose outputs are equality-gated against the reference;
# parse-first yields a ParseTree (not the typed result) — recognition only.
_ENGINE_COMPARED = ("earley", "pda", "product")


@dataclass(slots=True)
class Case:
    """One input text and the paths that parse it, all producing one output type.

    :ivar label: The row label in the report.
    :ivar text: The input parsed by every path.
    :ivar paths: Path name → its timed one-shot callable (closes over the
        pre-built grammar / tables; construction is outside every timed loop).
    :ivar same: ``(a, b) -> bool`` — do the two *engine* paths' outputs agree?
        (``IrAst`` equality for grammar-text; round-trip ``to_text`` for
        models.) Lark is excluded — its native output is a generic Lark ``Tree``,
        not the engine's typed result, so it is verified by recognition (it
        parses the input) rather than output equality.
    :ivar rounds: Timing samples per path.
    :ivar lark_note: A note about a missing ``lark-lalr`` (LALR not viable for
        this grammar), or ``""``.
    """

    label: str
    text: str
    paths: dict[str, Path]
    same: Callable[[object, object], bool]
    rounds: int
    lark_note: str = ""
    agree: bool = True


def _reduce_paths(flavour: IrFlavour, lark: dict[str, Path]) -> dict[str, Path]:
    """The grammar-text paths for one flavour — Lark ×2, earley, pda, product.

    All construction (normalisation, reduce-PDA compilation) happens here, once,
    outside every timed loop; the ``product`` column's memoised per-identity
    compile is warmed by the same ``_reduce_product`` call.

    :param flavour: The flavour whose self-grammar parses the input.
    :param lark: The viable native Lark parse callables (``lark-lalr`` /
        ``lark-earley``).
    :returns: Path name → timed callable, in column order.
    """
    norm = normalize(flavour.grammar)
    grammar = flavour.grammar
    reducer = flavour.reducer
    assert isinstance(reducer, Reducer)  # narrow the ClassVar[IrDispatch] declaration
    reduce_tables = _reduce_product(grammar, reducer).pda
    paths: dict[str, Path] = dict(lark)
    paths["earley"] = lambda t: earley_reduce(norm, t, reducer)
    paths["pda"] = lambda t: pda_reduce(reduce_tables, t)
    paths["product"] = lambda t: parse_reduced(grammar, t, reducer)
    return paths


def _model_paths(stem: str, lark: dict[str, Path]) -> dict[str, Path]:
    """The instance paths for one GT grammar — Lark ×2, earley, parse-first, pda, product.

    Compiles the grammar and builds the product once, outside timing. The
    ``parse-first`` path shares the ``earley`` column's normalised grammar and
    collapsed tables, minus the fold; ``product`` is the artefact's own
    :meth:`~lexic.compile.artifact.CompiledGrammar.parse`.

    :param stem: The ground-truth grammar file stem (e.g. ``json.gbnf``).
    :param lark: The viable native Lark parse callables (``lark-lalr`` /
        ``lark-earley``).
    :returns: Path name → timed callable, in column order.
    """
    compiled = compile_from_path(GROUND_TRUTH / stem)
    fold = compiled.fold
    product = _model_product(compiled.codegen_grammar, fold)
    paths: dict[str, Path] = dict(lark)
    paths["earley"] = lambda t: earley_model(
        product.instance_grammar, t, fold, product.tables
    )
    paths["parse-first"] = lambda t: parse_first(
        product.instance_grammar, t, product.tables
    )
    paths["pda"] = lambda t: pda_model(product.pda, t, fold)
    paths["product"] = compiled.parse
    return paths


def _ir_same(a: object, b: object) -> bool:
    """Grammar-text agreement: structural ``IrAst`` equality."""
    return a == b


def _semantic_same(a: object, b: object) -> bool:
    """Recursive SEMANTIC equality — the engines' designed contract.

    The PDA's greed over noise is licensed by the analysis (the P6
    noise-greedy licence: an over-eatable gap must be provably noise↔noise),
    so on a noise-ambiguous grammar the two engines may attach whitespace to
    different ``ws?`` slots while agreeing on every SEMANTIC field. This
    check enforces exactly that promise: same concrete types, semantic-bound
    fields recursively equal; non-semantic (noise) fields free to differ.

    :param a: One engine's model (or sub-value).
    :param b: The other engine's model (or sub-value).
    :returns: ``True`` when the semantic content is identical.
    """
    if isinstance(a, GrammarModel) and isinstance(b, GrammarModel):
        if type(a) is not type(b):
            return False
        binds = type(a).bound_fields()
        if not binds:  # value_str / alternation leaf — full equality
            return a == b
        return all(
            _semantic_same(getattr(a, name), getattr(b, name))
            for _slot, (name, bind) in binds.items()
            if bind.semantic
        )
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(_semantic_same(x, y) for x, y in zip(a, b))
    return a == b


def _model_same(a: object, b: object) -> bool:
    """Instance agreement: same reconstructed text AND same semantic content.

    Text equality alone under-checks (two semantically different parses could
    in principle re-emit the same text); structural equality over-checks (the
    licensed noise-attachment freedom would false-alarm). The conjunction is
    the engines' actual contract.
    """
    if isinstance(a, GrammarModel) and isinstance(b, GrammarModel):
        return a.to_text() == b.to_text() and _semantic_same(a, b)
    return a == b


def _lark(
    lark_mod: ModuleType | None, key: str, probe: str
) -> tuple[dict[str, Path], str]:
    """Both viable native Lark parse callables for a sample, plus any LALR note.

    :param lark_mod: The imported ``lark`` module, or ``None``.
    :param key: The registry key (``abnf`` / ``gbnf`` / a ``.gbnf`` stem).
    :param probe: The corpus LALR must parse to be counted viable.
    :returns: ``(name -> parse callable, lalr note)``.
    """
    if lark_mod is None:
        return {}, ""
    native, note = lark_variants(lark_mod, key, probe)
    # The `-same` columns ask Lark the grammar LEXIC was handed. Native and
    # same-grammar answer different questions and are labelled apart on purpose:
    # reading one as the other is what produced "json costs 3x Lark-LALR" for a
    # gap that does not exist.
    mirror, mirror_note = lark_mirror_variants(lark_mod, key, probe)
    notes = [n for n in (note, mirror_note) if n]
    return {**native, **mirror}, "; ".join(notes)


def build_cases(lark_mod: ModuleType | None) -> list[Case]:
    """Assemble every timed case — grammar-text (x1/x2/x4) and instance.

    :param lark_mod: The imported ``lark`` module, or ``None`` to omit Lark.
    :returns: The ordered list of cases.
    """
    cases: list[Case] = []
    grammar_text = (
        ("abnf self-emit", "abnf", ABNF_FLAVOUR),
        ("gbnf self-emit", "gbnf", GBNF_FLAVOUR),
    )
    for label, key, flavour in grammar_text:
        base = str(flavour.apply(flavour.grammar))
        lark, note = _lark(lark_mod, key, base)
        paths = _reduce_paths(flavour, lark)
        for repeat in SIZES:
            text = make_input(base, repeat)
            cases.append(
                Case(
                    f"{label} x{repeat}",
                    text,
                    paths,
                    _ir_same,
                    max(7, 40 // repeat),
                    note,
                )
            )
    for stem, make_corpus in _INSTANCE_WORKLOADS:
        corpus = make_corpus()
        lark, note = _lark(lark_mod, stem, corpus)
        paths = _model_paths(stem, lark)
        cases.append(Case(f"instance {stem}", corpus, paths, _model_same, 15, note))
    return cases


def check(case: Case) -> None:
    """Run every path once; verify Lark recognises and the engine paths agree.

    An engine path that raises :class:`PdaFail` (an island start) is dropped.
    The typed engine paths (``earley`` / ``pda`` / ``product``) are
    cross-checked for output equality (referenced against the PDA, so a message
    names the outlier). Lark and ``parse-first`` are *not* compared on output —
    a Lark ``Tree`` / engine ``ParseTree`` is not the engine's typed result —
    only that they ran (recognition). Mutates ``case`` in place so the timed
    loop races only the surviving paths.

    :param case: The case to verify (mutated in place).
    """
    outputs: dict[str, object] = {}
    for name, fn in list(case.paths.items()):
        try:
            outputs[name] = fn(case.text)
        except PdaFail:
            del case.paths[name]
            print(f"  ! {case.label}: {name} raised PdaFail (island start) — dropped")
    ref_name = next((n for n in ("pda", "earley", "product") if n in outputs), None)
    if ref_name is None:
        return
    reference = outputs[ref_name]
    for name in _ENGINE_COMPARED:  # lark Tree / parse-first ParseTree: other shapes
        if (
            name in outputs
            and name != ref_name
            and not case.same(outputs[name], reference)
        ):
            case.agree = False
            print(f"  ! {case.label}: {name} DIVERGES from {ref_name}")


def _cell(samples: list[float]) -> str:
    """Format one ``median±stdev`` millisecond cell."""
    sd = statistics.stdev(samples) if len(samples) > 1 else 0.0
    return f"{statistics.median(samples):>7.1f}±{sd:<4.1f}ms"


def report(case: Case, samples: dict[str, list[float]]) -> dict[str, float]:
    """Print one case's side-by-side table; return its per-path µs/char.

    :param case: The timed case.
    :param samples: Path name → per-sample durations (ms).
    :returns: Path name → µs/char (for the closing summary matrix).
    """
    chars = len(case.text)
    pda = statistics.median(samples["pda"]) if "pda" in samples else None
    flag = "" if case.agree else "   [DIVERGENCE — see above]"
    note = f" · {case.lark_note}" if case.lark_note else ""
    print(f"{case.label}  ({chars} chars · {case.rounds} rounds{note}){flag}")
    print(f"  {'path':<12}{'median±sd':>15}{'µs/char':>10}{'×pda':>8}")
    per_char: dict[str, float] = {}
    for name in _ORDER:
        if name not in samples:
            continue
        med = statistics.median(samples[name])
        per_char[name] = med / chars * 1e3
        ratio = f"{med / pda:>6.2f}x" if pda else f"{'—':>7}"
        tail = "  ← reference" if name == "pda" else ""
        print(
            f"  {name:<12}{_cell(samples[name]):>15}{per_char[name]:>9.1f}{ratio}{tail}"
        )
    print()
    return per_char


def summary(matrix: list[tuple[str, dict[str, float]]]) -> None:
    """Print the closing µs/char matrix — every input × every path.

    :param matrix: ``(case label, path → µs/char)`` for every case, in order.
    """
    print("== summary — µs/char (lower is faster) ==")
    heads = ("lk-lalr", "lk-earley", "earley", "p-first", "pda", "product")
    print(f"  {'input':<26}" + "".join(f"{h:>11}" for h in heads))
    for label, per_char in matrix:
        cells = "".join(
            f"{per_char[p]:>11.1f}" if p in per_char else f"{'—':>11}" for p in _ORDER
        )
        print(f"  {label:<26}{cells}")
    print()
    print("  lark-lalr / lark-earley = native parse → Lark Tree; an empty lk-lalr")
    print("  cell means LALR is not viable for that grammar (see the row's note).")
    print("  earley / pda / product = parse → typed IrAst / model, so those columns")
    print("  include construction the lark columns omit. p-first (instances only)")
    print("  = the earley column minus its fold (recognition + one ParseTree);")
    print("  earley − p-first reads the fold's cost, p-first vs pda the PDA's")
    print("  fused-build advantage. product = the public entry; ≈ pda by design.")
    print()


def main() -> None:
    """Build the cases, cross-check, time each path interleaved, and report."""
    lark_mod = load_lark()
    side = "lark + earley + pda" if lark_mod else "earley + pda (lark not installed)"
    print(f"== unified path comparison: {side} ==\n")

    cases = build_cases(lark_mod)
    matrix: list[tuple[str, dict[str, float]]] = []
    for case in cases:
        check(case)
        samples = interleaved(case.paths, case.text, case.rounds)
        matrix.append((case.label, report(case, samples)))
    summary(matrix)


if __name__ == "__main__":
    main()
