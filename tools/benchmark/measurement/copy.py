"""Materialise a revision's MEASUREMENT COPY — its own benchmark, corrected.

The A/B runs each revision's own worker against its own `src`. But a baseline
revision's benchmark predates the protocol corrections — its cohort preparation
overlapped real parses, it disabled the collector while timing, it recorded one
clock, and it carried no row contract. Comparing a corrected arm against an
uncorrected one measures the harness, not Lexic.

So both arms get the corrected protocol, and each keeps ONLY its native API
reference. This tool is that instrumentation patch, made reproducible: it copies
the protocol modules into a checkout and rewrites what that checkout spells
differently: the build object's name, and a resolver where the revision takes
it bare rather than inside a parse configuration. Neither copy gains a branch
for the other, and neither `src` tree is touched — the baseline stays
byte-identical to its revision.

    uv run python -m tools.benchmark.measurement.copy ../base --rename fold

Print the digest of what it produced with ``--digest``; that digest belongs in
the measurement report beside the numbers it made possible.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import shutil
from collections.abc import Sequence
from pathlib import Path

PROTOCOL_MODULES = (
    "bench.py",
    "compare.py",
    "regression.py",
    "cases/corpora.py",
    "cases/directives.py",
    "cases/engine_reach.py",
    "cases/grammars.py",
    "diagnostics/split_ab.py",
    "engines/seats.py",
    "execution/isolation.py",
    "execution/roster.py",
    "execution/worker.py",
    "judging/__init__.py",
    "judging/arithmetic.py",
    "measurement/__init__.py",
    "measurement/contract.py",
    "measurement/copy.py",
    "measurement/health.py",
    "measurement/language.py",
    "measurement/occupancy.py",
    "measurement/sampling.py",
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
        "lexic.generate.generate",
        "lexic.grammars.ABNF_FLAVOUR",
        "lexic.grammars.GBNF_FLAVOUR",
        "lexic.ir.IrAst",
        "lexic.ir.inline_refs",
        "lexic.model.GrammarModel",
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

ARM_SPELLED = frozenset({"lexic.parsing.ParseConfig"})
"""``lexic`` names a protocol module may import though the base may LACK them,
because :func:`materialise` spells them away in an arm whose ``src`` does not
export them (:func:`_unwrap_config`). Declared, like the shared vocabulary, so
the gate reads it rather than trusting that the rewrite still covers a name."""

BUILD_OBJECT = "product"
"""What current Lexic calls the compiled grammar's model-build object."""

PARSE_CONFIG = "ParseConfig"
"""What current Lexic calls the record a parse's resolver rides inside."""

type _Edit = tuple[int, int, bytes]
"""One replacement in a module's UTF-8 text: start, end, the new bytes."""


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


def exports_config(root: Path) -> bool:
    """Whether the checkout at ``root`` exports the parse configuration.

    Its package root is parsed, never imported: the copy must not run the other
    revision's code to learn how to spell a call to it. A name counts when the
    root lists it in ``__all__`` or imports it; a mention in a docstring does
    not.
    """
    init = root / "src" / "lexic" / "parsing" / "__init__.py"
    return PARSE_CONFIG in _exported_names(ast.parse(init.read_text(encoding="utf-8")))


def _exported_names(tree: ast.Module) -> set[str]:
    """Every name a module's top level imports or lists in ``__all__``."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Assign) and _assigns_all(node):
            names.update(_strings(node.value))
    return names


def _assigns_all(node: ast.Assign) -> bool:
    """Whether ``node`` assigns ``__all__``."""
    return any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)


def _strings(value: ast.expr) -> list[str]:
    """The string literals of a list or tuple display."""
    if not isinstance(value, (ast.List, ast.Tuple)):
        return []
    return [
        e.value
        for e in value.elts
        if isinstance(e, ast.Constant) and isinstance(e.value, str)
    ]


def _unwrap_config(root: Path) -> None:
    """Spell a resolver the way a revision without the parse configuration takes
    it: every ``ParseConfig(...)`` call becomes the bare resolver it wrapped,
    and ``ParseConfig`` leaves every import.

    Refuses, naming the module, any use that has no bare spelling: a decider,
    or a use that is not a call. That is a local error at materialise, never a
    base arm dying at import on the runner.

    Removable once main carries ``ParseConfig``: every base an A/B compares
    against is then a revision that exports it, and nothing reaches this.
    """
    for module in PROTOCOL_MODULES:
        path = root / "tools" / "benchmark" / module
        source = path.read_bytes()
        unwrapped = _applied(source, _config_edits(source, module))
        _require_no_config(unwrapped, module)
        if unwrapped != source:
            path.write_bytes(unwrapped)


def _config_edits(source: bytes, module: str) -> list[_Edit]:
    """The edits that take ``ParseConfig`` out of one module's text."""
    tree = ast.parse(source)
    starts = _line_starts(source)
    edits: list[_Edit] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and _imports_config(node):
            edits.append(_import_edit(node, starts))
        elif isinstance(node, ast.Call) and _names_config(node.func):
            edits.append(_call_edit(node, source, starts, module))
    return edits


def _imports_config(node: ast.ImportFrom) -> bool:
    """Whether an import statement names ``ParseConfig``."""
    return any(alias.name == PARSE_CONFIG for alias in node.names)


def _names_config(node: ast.AST) -> bool:
    """Whether ``node`` names ``ParseConfig``, bare or dotted."""
    if isinstance(node, ast.Attribute):
        return node.attr == PARSE_CONFIG
    return isinstance(node, ast.Name) and node.id == PARSE_CONFIG


def _line_starts(source: bytes) -> list[int]:
    """The byte offset each line starts at, 1-based as ``ast`` counts lines."""
    starts = [0, 0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def _span(node: ast.expr | ast.stmt, starts: list[int]) -> tuple[int, int]:
    """A node's byte span; ``ast`` columns are UTF-8 byte offsets."""
    end_line = node.end_lineno or node.lineno
    end_col = node.end_col_offset or 0
    return starts[node.lineno] + node.col_offset, starts[end_line] + end_col


def _import_edit(node: ast.ImportFrom, starts: list[int]) -> _Edit:
    """Drop ``ParseConfig`` from one import; the whole line if it was alone."""
    kept = [alias for alias in node.names if alias.name != PARSE_CONFIG]
    start, end = _span(node, starts)
    if not kept:
        return starts[node.lineno], starts[(node.end_lineno or node.lineno) + 1], b""
    rest = ast.ImportFrom(module=node.module, names=kept, level=node.level)
    return start, end, ast.unparse(rest).encode("utf-8")


def _call_edit(node: ast.Call, source: bytes, starts: list[int], module: str) -> _Edit:
    """``ParseConfig(resolve=X)`` or ``ParseConfig(X)`` as the bare ``X``."""
    wrapped = _resolver_argument(node, module)
    inner_start, inner_end = _span(wrapped, starts)
    start, end = _span(node, starts)
    return start, end, source[inner_start:inner_end]


def _resolver_argument(node: ast.Call, module: str) -> ast.expr:
    """The one argument a bare resolver can stand for, or a refusal."""
    keywords = {keyword.arg: keyword.value for keyword in node.keywords}
    if not node.args and set(keywords) == {"resolve"}:
        return keywords["resolve"]
    if len(node.args) == 1 and not keywords:
        return node.args[0]
    raise ValueError(
        f"{module}: {PARSE_CONFIG} call at line {node.lineno} carries more than a "
        "resolver, which a base without it cannot take"
    )


def _applied(source: bytes, edits: list[_Edit]) -> bytes:
    """``source`` with non-overlapping ``edits`` applied, last first."""
    out = source
    limit = len(source)
    for start, end, text in sorted(edits, reverse=True):
        if end > limit:
            raise ValueError("overlapping ParseConfig edits: a call nested in a call")
        out = out[:start] + text + out[end:]
        limit = start
    return out


def _require_no_config(source: bytes, module: str) -> None:
    """Refuse a module that still names ``ParseConfig`` after the unwrap."""
    left = [node for node in ast.walk(ast.parse(source)) if _names_config(node)]
    if left:
        lines = sorted({node.lineno for node in left if isinstance(node, ast.expr)})
        raise ValueError(
            f"{module}: {PARSE_CONFIG} at line(s) {lines} is used in a form a "
            "base without it cannot spell"
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
    if not exports_config(root):
        _unwrap_config(root)


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
