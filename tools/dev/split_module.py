"""Split a module by moving named top-level definitions into a new one.

Written after doing this by hand four times. Each hand-rolled attempt made the
same three mistakes, so this makes them structurally impossible:

* imports are placed by AST node position, never by ``rfind("\\nfrom ")`` — which
  twice landed a block *inside* a parenthesised import and produced a syntax
  error out of a "safe" edit;
* the free names of the moved code are computed in ONE pass and resolved against
  every sibling's definitions, rather than discovered one ``NameError`` per test
  run;
* a rewrite is a single pass over one alternation, so no rule can match another
  rule's output;
* a definition's span starts at its first DECORATOR, not at its ``def`` — moving
  a decorated function otherwise leaves ``@cache`` behind to attach itself to
  the next definition, which is a bug no test names and no import catches.

Not a general refactoring tool: it knows this repo's layout and is meant to be
read before it is trusted.
"""

from __future__ import annotations

import ast
import builtins
import pathlib
import sys


def _spans(tree: ast.Module) -> dict[str, tuple[int, int]]:
    """Each top-level name's line range, INCLUDING its trailing docstring.

    A module-level docstring is its own ``Expr`` node, so a range taken from the
    definition alone leaves the string behind — which either orphans it as a
    stray statement or, if the range is stretched by counting quotes, cuts a
    multi-line docstring in half and produces a syntax error out of a move.
    """
    body = tree.body
    out: dict[str, tuple[int, int]] = {}
    for i, node in enumerate(body):
        bound: list[str] = []
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            bound = [node.name]
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            bound = [
                leaf.id
                for t in targets
                for leaf in ast.walk(t)
                if isinstance(leaf, ast.Name)
            ]
        if not bound:
            continue
        # DECORATORS ARE PART OF THE DEFINITION. `lineno` points at the `def`,
        # not at `@cache` above it, so a span taken from the node alone moves
        # the function and leaves its decorators behind — silently applying
        # them to whatever follows. That is how a `@cache` landed on the next
        # class and turned its construction into a dict hash.
        start = min(
            [node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))]
        )
        end = node.end_lineno or node.lineno
        nxt = body[i + 1] if i + 1 < len(body) else None
        if (
            isinstance(nxt, ast.Expr)
            and isinstance(nxt.value, ast.Constant)
            and isinstance(nxt.value.value, str)
        ):
            end = nxt.end_lineno or nxt.lineno
        for name in bound:
            out[name] = (start, end)
    return out


def _bound_names(tree: ast.Module) -> set[str]:
    """Every name a module binds at any level."""
    out = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out |= {a.asname or a.name.split(".")[0] for a in node.names}
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            out.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            out.add(node.id)
        elif isinstance(node, ast.arg):
            out.add(node.arg)
    return out


def free_names(source: str) -> set[str]:
    """Names a module reads but never binds."""
    tree = ast.parse(source)
    used = {
        n.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }
    return used - _bound_names(tree)


def homes(package: pathlib.Path) -> dict[str, str]:
    """Every top-level name each module in ``package`` defines."""
    found: dict[str, str] = {}
    for path in sorted(package.glob("*.py")):
        if path.name == "__init__.py":
            continue
        for name in _spans(ast.parse(path.read_text(encoding="utf-8"))):
            found.setdefault(name, path.stem)
    return found


def import_anchor(source: str) -> int:
    """The line AFTER the last top-level import — where a new block belongs.

    By AST, because a textual search for the last ``from`` finds one INSIDE a
    parenthesised import and splices a block into its name list.
    """
    tree = ast.parse(source)
    ends = [
        n.end_lineno or n.lineno
        for n in tree.body
        if isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    return max(ends) if ends else 0


def split(module: pathlib.Path, out: pathlib.Path, names: list[str], doc: str) -> None:
    """Move ``names`` from ``module`` into ``out``, carrying what they need."""
    source = module.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    spans = _spans(tree)
    missing = [n for n in names if n not in spans]
    if missing:
        raise SystemExit(f"not top-level definitions of {module.name}: {missing}")
    body = "\n".join(
        "".join(lines[spans[n][0] - 1 : spans[n][1]]).rstrip() for n in names
    )
    head = "".join(lines[: import_anchor(source)])
    prelude = head.split('"""', 2)[-1].lstrip("\n")
    out.write_text(doc + "\n\n" + prelude + "\n" + body + "\n", encoding="utf-8")
    # DEDUPLICATED: `END, MORE, UNK = ...` is one statement under three names,
    # and deleting its span once per name removes two innocent neighbours —
    # which is how `MAX_K` vanished from a file nothing had asked to change.
    for start, end in sorted({spans[n] for n in names}, reverse=True):
        del lines[start - 1 : end]
    module.write_text("".join(lines), encoding="utf-8")
    _wire(module, out)


def dotted(package: pathlib.Path) -> str:
    """``package``'s importable dotted name, by walking its ``__init__.py`` chain.

    NOT ``parts[1:]`` — that spells "drop ``src/``", which under ``tests/`` names
    the package ``unit.…`` and imports a module that does not exist.
    """
    parts: list[str] = []
    here = package
    while (here / "__init__.py").exists():
        parts.append(here.name)
        here = here.parent
    return ".".join(reversed(parts))


def _prune(path: pathlib.Path) -> None:
    """Drop sibling imports of names the module now defines itself.

    Wiring only ever ADDS, so a name that moved leaves its old import behind —
    which reads as a circular import rather than as the stale line it is.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    local = set(_spans(tree))
    lines = source.splitlines(keepends=True)
    package = dotted(path.parent)
    for node in sorted(tree.body, key=lambda n: -getattr(n, "lineno", 0)):
        if not (isinstance(node, ast.ImportFrom) and node.module):
            continue
        if not node.module.startswith(package):
            continue
        keep = [a for a in node.names if a.name not in local]
        if len(keep) == len(node.names):
            continue
        spec = ", ".join(
            a.name if not a.asname else f"{a.name} as {a.asname}" for a in keep
        )
        block = [f"from {node.module} import {spec}\n"] if keep else []
        lines[node.lineno - 1 : (node.end_lineno or node.lineno)] = block
    path.write_text("".join(lines), encoding="utf-8")


def _wire(*modules: pathlib.Path) -> None:
    """Give each module an import for every free name a sibling defines."""
    package = modules[0].parent
    where = homes(package)
    for path in modules:
        _prune(path)
    for path in modules:
        source = path.read_text(encoding="utf-8")
        wanted: dict[str, list[str]] = {}
        for name in sorted(free_names(source)):
            home = where.get(name)
            if home and home != path.stem:
                wanted.setdefault(home, []).append(name)
        if not wanted:
            continue
        block = "".join(
            f"from {dotted(package)}.{home} import {', '.join(sorted(got))}\n"
            for home, got in sorted(wanted.items())
        )
        lines = source.splitlines(keepends=True)
        lines.insert(import_anchor(source), block)
        path.write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    _src, _dst, _doc, *_moving = sys.argv[1:]
    split(pathlib.Path(_src), pathlib.Path(_dst), _moving, _doc)
