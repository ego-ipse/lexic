"""Materialise a revision's MEASUREMENT COPY — its own benchmark, corrected.

The A/B runs each revision's own worker against its own `src`. But a baseline
revision's benchmark predates the protocol corrections — its cohort preparation
overlapped real parses, it disabled the collector while timing, it recorded one
clock, and it carried no row contract. Comparing a corrected arm against an
uncorrected one measures the harness, not Lexic.

So both arms get the corrected protocol, and each keeps ONLY its native API
reference. This tool is that instrumentation patch, made reproducible: it copies
the protocol modules into a checkout and rewrites the one name the public rename
moved. Neither copy gains a branch for the other, and neither `src` tree is
touched — the baseline stays byte-identical to its revision.

    uv run python -m tools.benchmark.measurement.copy ../base --rename fold

Print the digest of what it produced with ``--digest``; that digest belongs in
the measurement report beside the numbers it made possible.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from collections.abc import Sequence
from pathlib import Path

PROTOCOL_MODULES = (
    "bench.py",
    "compare.py",
    "regression.py",
    "cases/directives.py",
    "cases/grammars.py",
    "diagnostics/split_ab.py",
    "execution/isolation.py",
    "execution/roster.py",
    "execution/worker.py",
    "measurement/__init__.py",
    "measurement/contract.py",
    "measurement/copy.py",
    "measurement/health.py",
    "measurement/occupancy.py",
    "presentation/cli.py",
    "presentation/reporting.py",
)
"""The harness files the corrected protocol owns, copied into every arm."""

RETIRED_MODULES = (
    "cases/variants.py",
    "contract.py",
    "health.py",
    "measure_copy.py",
)
"""Files the correction deletes.

`cases/variants.py` derived a row's directives from the engine's own eligibility
and speed, which let one label denote two workloads. The rest are earlier
locations of files this layout moved.
"""

SHARED_VOCABULARY = frozenset(
    {
        "lexic.compile.CompiledGrammar",
        "lexic.compile.Directives",
        "lexic.compile.compile_from_path",
        "lexic.compile.compile_text",
        "lexic.exceptions.LexicError",
        "lexic.exceptions.UnsupportedConstructError",
        "lexic.grammars.ABNF_FLAVOUR",
        "lexic.grammars.GBNF_FLAVOUR",
        "lexic.ir.IrAst",
        "lexic.ir.inline_refs",
        "lexic.model.GrammarModel",
        "lexic.parsing.earley.kernel.forest.support.ambiguity.Resolver",
        "lexic.parsing.parallel.AUTO",
        "lexic.parsing.parallel.available_workers",
        "lexic.parsing.parallel.orchestrate.Request",
        "lexic.parsing.parallel.split_model",
        "lexic.parsing.parallel.worker_count",
        "lexic.parsing.pda.core.errors.PdaFail",
        "lexic.parsing.pda.runtime.kernel.kernel.pda_model",
        "lexic.parsing.products._model_product",
        "lexic.parsing.products.earley_model",
        "lexic.parsing.products.parse_model",
    }
)
"""Every ``lexic`` name a protocol module may import, as an exact dotted path.

A protocol module is imported inside a FOREIGN revision's checkout, so a name
that postdates the comparison base kills that whole arm at import — one
traceback, no rows, and a performance run that measured nothing. This list is
not a convenience: it is the point at which adding an import means checking the
other arm has it, and a gate reads it so the check cannot be skipped.
"""

BUILD_OBJECT = "product"
"""What current Lexic calls the compiled grammar's model-build object."""


def _rewrite(root: Path, name: str) -> None:
    """Point one copy's benchmark at the build-object name ITS Lexic uses.

    Every protocol module is rewritten, not a listed subset: a module that
    starts naming the build object would otherwise reach the other arm still
    naming this one's, and the list that was supposed to say so is exactly the
    thing nobody updates.
    """
    for module in PROTOCOL_MODULES:
        path = root / "tools" / "benchmark" / module
        source = path.read_text(encoding="utf-8")
        path.write_text(
            source.replace(f"compiled.{BUILD_OBJECT}", f"compiled.{name}"),
            encoding="utf-8",
        )


def materialise(root: Path, name: str, here: Path) -> None:
    """Install the corrected protocol into ``root`` for ITS API name.

    :param root: The checkout to correct. Its ``src`` is never touched.
    :param name: What that revision's `CompiledGrammar` calls its build object.
    :param here: This checkout, the protocol modules are copied from.
    """
    target = root / "tools" / "benchmark"
    if not target.is_dir():
        raise ValueError(f"{root} has no tools/benchmark to correct")
    for module in PROTOCOL_MODULES:
        destination = target / module
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(here / "tools" / "benchmark" / module, destination)
    for module in RETIRED_MODULES:
        (target / module).unlink(missing_ok=True)
    if name != BUILD_OBJECT:
        _rewrite(root, name)


def digest(root: Path) -> str:
    """A digest of the measurement copy's benchmark, for the report."""
    listing = hashlib.sha256()
    for module in sorted(PROTOCOL_MODULES):
        listing.update(module.encode("utf-8"))
        listing.update((root / "tools" / "benchmark" / module).read_bytes())
    return listing.hexdigest()[:16]


def main(argv: Sequence[str] | None = None) -> int:
    """Correct one checkout's benchmark and print its digest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument(
        "--rename",
        default=BUILD_OBJECT,
        help="what THAT revision's CompiledGrammar calls its build object",
    )
    parser.add_argument("--here", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    materialise(args.root, args.rename, args.here)
    print(f"measurement copy {args.root}: benchmark digest {digest(args.root)}")
    print(f"head             {args.here}: benchmark digest {digest(args.here)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
